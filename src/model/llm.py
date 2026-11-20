"""1차 분류기: LLM이 5단계(원재료 이름 → 알레르겐)만 맡는다.

- 입력은 원재료 이름 목록뿐이다. 사진·사용자 프로필은 보내지 않는다.
- 출력은 tool(function) 호출로 형식을 강제하고, 형식이 틀린 항목은 source_unknown으로 낮춘다.
- 근거 검사·누락 검사·제품 단위 합치기는 src/pipeline.py가 한다 (LLM을 믿지 않는다).

연결 방식 (.env)
- LLM_PROVIDER=openai    : OpenAI 호환 API (학교 BAZE 게이트웨이 포함). LLM_BASE_URL, LLM_MODEL 필요
- LLM_PROVIDER=anthropic : Claude API 직접
- LLM_USE_TOOLS=0        : 모델이 tool 호출을 지원하지 않을 때. 프롬프트로 JSON만 출력하게 한다
- LLM_TOOL_CHOICE=auto   : 기본. 도구 사용을 프롬프트로 지시 (학교 게이트웨이 Claude는 강제 지정 불가)
  LLM_TOOL_CHOICE=forced : 특정 tool 호출을 강제할 수 있는 모델일 때
"""
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

from src.common.schema import Allergen, AllergenMatch, IngredientClassification, Verdict

PROMPT_VERSION = "classify_v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.txt"
OCR_FIX_PROMPT_VERSION = "ocr_fix_v1"   # 최종본의 오인식 보정 (src/final/resolve.py)
OCR_FIX_PROMPT_PATH = Path(__file__).parent / "prompts" / f"{OCR_FIX_PROMPT_VERSION}.txt"

TOOL_NAME = "report_allergens"
TOOL_DESCRIPTION = "원재료마다 알레르겐 분류 결과를 보고한다."
TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ingredient": {"type": "string"},
                    "matches": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "allergen": {"type": "string", "enum": [a.value for a in Allergen]},
                                "verdict": {"type": "string", "enum": [v.value for v in Verdict]},
                            },
                            "required": ["allergen", "verdict"],
                        },
                    },
                    "source_unknown": {"type": "boolean"},
                },
                "required": ["ingredient", "matches", "source_unknown"],
            },
        }
    },
    "required": ["results"],
}

# 오인식 보정(ocr_fix_v1) 요청 전용: TOOL_SCHEMA에 'corrected' 칸만 더한 것.
# 1차 분류(classify_v1) 요청은 TOOL_SCHEMA를 그대로 보내므로 1차 기준선의 도구 정의는 바뀌지 않는다.
OCR_FIX_TOOL_SCHEMA: dict[str, Any] = copy.deepcopy(TOOL_SCHEMA)
OCR_FIX_TOOL_SCHEMA["properties"]["results"]["items"]["properties"]["corrected"] = {
    "type": "string",
    "description": "OCR이 잘못 읽은 이름의 원래 이름. 고칠 게 없거나 확실하지 않으면 빈 문자열",
}

# tool 호출을 못 쓰는 모델용: 프롬프트 끝에 붙인다
JSON_ONLY_SUFFIX = (
    "\n\n출력 형식: 설명 없이 아래 형태의 JSON 하나만 출력하세요.\n"
    '{"results": [{"ingredient": "원재료", "matches": [{"allergen": "키", "verdict": "판정"}], '
    '"source_unknown": false}]}'
)

OCR_FIX_JSON_ONLY_SUFFIX = (
    "\n\n출력 형식: 설명 없이 아래 형태의 JSON 하나만 출력하세요.\n"
    '{"results": [{"ingredient": "입력 이름", "corrected": "원래 이름 또는 빈 문자열", '
    '"matches": [{"allergen": "키", "verdict": "판정"}], "source_unknown": false}]}'
)

# tool_choice=auto일 때: 도구로 답하라고 프롬프트로 지시한다
TOOL_ONLY_SUFFIX = f"\n\n답은 반드시 {TOOL_NAME} 도구를 한 번 호출해서 하세요. 도구 밖에 글로 답하지 마세요."

# (system, user) -> {"results": [...]}. 테스트에서 가짜 함수로 바꿔 끼운다.
CallFn = Callable[[str, str], dict[str, Any]]


def extract_json(text: str) -> dict[str, Any]:
    """모델이 글로 답한 경우 JSON 부분만 꺼낸다. 실패하면 빈 dict."""
    if not text:
        return {}
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def merge_results(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """여러 tool 호출의 results를 하나로 합친다. 같은 원재료가 두 번 오면 pipeline.validate가 첫 답을 쓴다."""
    results: list[Any] = []
    for p in parts:
        if isinstance(p, dict) and isinstance(p.get("results"), list):
            results.extend(p["results"])
    return {"results": results}


def parse_tool_output(raw: Any) -> list[IngredientClassification]:
    """LLM 출력을 검사한다. 잘못된 match는 버리고 그 원재료를 source_unknown으로 표시한다."""
    out: list[IngredientClassification] = []
    for item in raw.get("results", []) if isinstance(raw, dict) else []:
        if not isinstance(item, dict) or not isinstance(item.get("ingredient"), str):
            continue
        matches, broken = [], False
        for m in item.get("matches") or []:
            try:
                matches.append(AllergenMatch(allergen=m["allergen"], verdict=m["verdict"]))
            except Exception:
                broken = True
        out.append(
            IngredientClassification(
                ingredient=item["ingredient"],
                matches=matches,
                source_unknown=bool(item.get("source_unknown")) or broken,
            )
        )
    return out


def _openai_call(
    base_url: str,
    api_key: str,
    model: str,
    use_tools: bool,
    temperature: float,
    tool_choice: str = "auto",
    max_tokens: int = 8192,
    schema: Optional[dict[str, Any]] = None,
    json_suffix: str = JSON_ONLY_SUFFIX,
) -> CallFn:
    """schema를 주지 않으면 1차 분류용 TOOL_SCHEMA를 보낸다. 오인식 보정은 OCR_FIX_TOOL_SCHEMA를 준다."""
    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key)
    tool_schema = TOOL_SCHEMA if schema is None else schema

    def call(system: str, user: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,  # 기본값이 작으면 원재료가 많을 때 JSON이 잘린다
            "messages": [
                {"role": "system", "content": system if use_tools else system + json_suffix},
                {"role": "user", "content": user},
            ],
        }
        if use_tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {"name": TOOL_NAME, "description": TOOL_DESCRIPTION, "parameters": tool_schema},
                }
            ]
            # 학교 게이트웨이의 Claude Sonnet 5.5는 특정 tool 강제(tool_choice 지정)를 거부한다 (400).
            # 기본은 auto + 프롬프트 지시. 강제가 되는 모델이면 LLM_TOOL_CHOICE=forced.
            if tool_choice == "forced":
                kwargs["tool_choice"] = {"type": "function", "function": {"name": TOOL_NAME}}
            else:
                kwargs["tool_choice"] = "auto"
                kwargs["messages"][0]["content"] = system + TOOL_ONLY_SUFFIX
        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        parts = [extract_json(tc.function.arguments) for tc in (msg.tool_calls or []) if tc.function.name == TOOL_NAME]
        if parts:
            return merge_results(parts)  # 결과를 여러 번의 tool 호출로 나눠 보낸 경우 모두 합친다
        return extract_json(msg.content or "")  # tool을 무시하고 글로 답한 경우

    return call


def _anthropic_call(api_key: str, model: str, temperature: float, max_tokens: int = 8192,
                    schema: Optional[dict[str, Any]] = None) -> CallFn:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    tool = {"name": TOOL_NAME, "description": TOOL_DESCRIPTION, "input_schema": TOOL_SCHEMA if schema is None else schema}

    def call(system: str, user: str) -> dict[str, Any]:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": user}],
        )
        parts = [dict(b.input) for b in resp.content if b.type == "tool_use" and b.name == TOOL_NAME]
        return merge_results(parts)

    return call


class LLMClassifier:
    name = "llm"
    prompt_version = PROMPT_VERSION

    def __init__(self, call: CallFn, model: str, batch_size: int = 40, fix_call: Optional[CallFn] = None):
        self._call = call
        # 오인식 보정 전용 호출 (OCR_FIX_TOOL_SCHEMA). 없으면 call을 쓴다 (테스트의 가짜 함수 등)
        self._fix_call = fix_call or call
        self.model = model
        self.batch_size = max(1, batch_size)
        self.system = PROMPT_PATH.read_text(encoding="utf-8")

    @classmethod
    def from_env(cls) -> "LLMClassifier":
        provider = os.getenv("LLM_PROVIDER", "openai")
        api_key = os.getenv("LLM_API_KEY")
        model = os.getenv("LLM_MODEL")
        temperature = float(os.getenv("LLM_TEMPERATURE", "0"))
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", "8192"))
        batch_size = int(os.getenv("LLM_BATCH", "40"))
        if not api_key:
            raise RuntimeError("LLM_API_KEY가 없다. .env를 확인할 것.")
        if not model:
            raise RuntimeError("LLM_MODEL이 없다. 게이트웨이 '모델' 탭의 이름을 .env에 적을 것.")

        if provider == "openai":
            base_url = os.getenv("LLM_BASE_URL")
            if not base_url:
                raise RuntimeError("LLM_BASE_URL이 없다. .env를 확인할 것.")
            use_tools = os.getenv("LLM_USE_TOOLS", "1") != "0"
            tool_choice = os.getenv("LLM_TOOL_CHOICE", "auto")
            call = _openai_call(base_url, api_key, model, use_tools, temperature, tool_choice, max_tokens)
            fix_call = _openai_call(base_url, api_key, model, use_tools, temperature, tool_choice, max_tokens,
                                    schema=OCR_FIX_TOOL_SCHEMA, json_suffix=OCR_FIX_JSON_ONLY_SUFFIX)
        elif provider == "anthropic":
            call = _anthropic_call(api_key, model, temperature, max_tokens)
            fix_call = _anthropic_call(api_key, model, temperature, max_tokens, schema=OCR_FIX_TOOL_SCHEMA)
        else:
            raise RuntimeError(f"알 수 없는 LLM_PROVIDER: {provider}")
        return cls(call=call, model=model, batch_size=batch_size, fix_call=fix_call)

    def classify(self, ingredients: list[str]) -> list[IngredientClassification]:
        """원재료가 많으면 batch_size개씩 나눠 보낸다. 각 원재료는 이름만 보고 판단하므로 나눠도 결과가 같아야 한다."""
        out: list[IngredientClassification] = []
        for i in range(0, len(ingredients), self.batch_size):
            chunk = ingredients[i : i + self.batch_size]
            user = "원재료 목록 (JSON):\n" + json.dumps(chunk, ensure_ascii=False)
            out.extend(parse_tool_output(self._call(self.system, user)))
        return out

    def correct_and_classify(self, names: list[str]) -> list[tuple[IngredientClassification, str]]:
        """최종본의 오인식 보정: 사전에 없는 이름마다 (알레르겐 분류, OCR 오인식을 바로잡은 이름 또는 "").

        프롬프트는 ocr_fix_v1. 분류는 바로잡은 이름 기준이다. 묻지 않은 이름의 답은 호출한 쪽(resolve)이 버린다.
        """
        system = OCR_FIX_PROMPT_PATH.read_text(encoding="utf-8")
        out: list[tuple[IngredientClassification, str]] = []
        for i in range(0, len(names), self.batch_size):
            chunk = names[i : i + self.batch_size]
            raw = self._fix_call(system, "원재료 이름 목록 (JSON):\n" + json.dumps(chunk, ensure_ascii=False))
            parsed = parse_tool_output(raw)
            fixes = {}
            for item in raw.get("results", []) if isinstance(raw, dict) else []:
                if isinstance(item, dict) and isinstance(item.get("ingredient"), str):
                    c = item.get("corrected")
                    fixes.setdefault(item["ingredient"], c.strip() if isinstance(c, str) else "")
            out.extend((r, fixes.get(r.ingredient, "")) for r in parsed)
        return out
