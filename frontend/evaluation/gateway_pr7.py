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
# 개발 검증용 PR #7 사본: 630ec8d9d52c00b6f902a3870e6a0357eb0e8d38
# 원본 src/model/llm.py는 수정하지 않으며, PR #7 통합 후 이 사본을 제거한다.
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from src.common.schema import Allergen, AllergenMatch, IngredientClassification, Verdict

PROMPT_VERSION = "classify_v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.txt"

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

# tool 호출을 못 쓰는 모델용: 프롬프트 끝에 붙인다
JSON_ONLY_SUFFIX = (
    "\n\n출력 형식: 설명 없이 아래 형태의 JSON 하나만 출력하세요.\n"
    '{"results": [{"ingredient": "원재료", "matches": [{"allergen": "키", "verdict": "판정"}], '
    '"source_unknown": false}]}'
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
    base_url: str, api_key: str, model: str, use_tools: bool, temperature: float, tool_choice: str = "auto"
) -> CallFn:
    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key)

    def call(system: str, user: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system if use_tools else system + JSON_ONLY_SUFFIX},
                {"role": "user", "content": user},
            ],
        }
        if use_tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {"name": TOOL_NAME, "description": TOOL_DESCRIPTION, "parameters": TOOL_SCHEMA},
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


def _anthropic_call(api_key: str, model: str, temperature: float) -> CallFn:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    tool = {"name": TOOL_NAME, "description": TOOL_DESCRIPTION, "input_schema": TOOL_SCHEMA}

    def call(system: str, user: str) -> dict[str, Any]:
        resp = client.messages.create(
            model=model,
            max_tokens=4096,
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

    def __init__(self, call: CallFn, model: str):
        self._call = call
        self.model = model
        self.system = PROMPT_PATH.read_text(encoding="utf-8")

    @classmethod
    def from_env(cls) -> "LLMClassifier":
        provider = os.getenv("LLM_PROVIDER", "openai")
        api_key = os.getenv("LLM_API_KEY")
        model = os.getenv("LLM_MODEL")
        temperature = float(os.getenv("LLM_TEMPERATURE", "0"))
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
            call = _openai_call(base_url, api_key, model, use_tools, temperature, tool_choice)
        elif provider == "anthropic":
            call = _anthropic_call(api_key, model, temperature)
        else:
            raise RuntimeError(f"알 수 없는 LLM_PROVIDER: {provider}")
        return cls(call=call, model=model)

    def classify(self, ingredients: list[str]) -> list[IngredientClassification]:
        if not ingredients:
            return []
        user = "원재료 목록 (JSON):\n" + json.dumps(ingredients, ensure_ascii=False)
        return parse_tool_output(self._call(self.system, user))

