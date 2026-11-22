"""May contain 항목에 LLM 설명(explanation_en)을 덧붙인다 (docs/10_may_contain.md 4절, 11/18 회의).

    from src.final.explain import explain
    res = explain(analyze_text(text))      # OPENSESAME_FINAL_EXPLAIN=llm 일 때만 LLM을 부른다

- 대상: allergens[] 중 verdict가 inferable·undecidable인 항목. confirmed와 shared_facility는 설명하지 않는다.
- 판정은 건드리지 않는다. verdict, basis, reason_en, allergens 목록, shared_facility는 그대로이고 explanation_en만 채운다.
- 제품 하나에 LLM 호출 한 번 (대상 항목을 모아서). 크레딧을 아끼려고 같은 입력은 메모리에 기억해 두고 다시 묻지 않는다.
- 이런 설명은 버리고 null로 둔다: 안심시키는 말(safe, allergen-free 등)과 '들어 있지 않다'는 부정문, 판정 불가인데 '들어 있다'고 단정, LLM-FIX인데 read_as를
  설명에 쓰지 않음(다른 이름으로 다시 추측한 것으로 본다), 너무 길거나 빈 글.
- 꺼져 있거나, 키가 없거나, 호출이 실패하면(크레딧 소진 402 포함) 아무것도 바꾸지 않고 돌려준다. 화면은 reason_en만으로 완성된다.
- warnings가 있는 응답(원재료나 표시란을 못 읽음)은 설명하지 않는다. 다시 찍기가 먼저다.
- LLM에는 라벨 글자와 판정 항목만 보낸다. 사용자 알레르기 프로필은 서버에 없다.

설정 (.env)
    OPENSESAME_FINAL_EXPLAIN=llm      # 켜기. 기본은 끔 (테스트·평가는 늘 LLM 없이)
    LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TEMPERATURE   # 팀 LLM 설정 그대로 (src/model/llm.py와 같음)
    LLM_EXPLAIN_TIMEOUT=20            # 초. 넘으면 설명 없이 돌려준다
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.final.response import FinalAllergenResult, FinalAnalyzeResponse

ENV = "OPENSESAME_FINAL_EXPLAIN"
PROMPT_VERSION = "explain_v1"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "model" / "prompts" / f"{PROMPT_VERSION}.txt"
TARGET_VERDICTS = ("inferable", "undecidable")
MAX_CHARS = 400
CACHE_SIZE = 256
TOOL_NAME = "report_explanations"
TOOL = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "May contain 항목마다 영어 설명 한두 문장을 보고한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"allergen": {"type": "string"}, "explanation": {"type": "string"}},
                        "required": ["allergen", "explanation"],
                    },
                }
            },
            "required": ["results"],
        },
    },
}

# 안심시키는 말. 하나라도 있으면 그 설명은 버린다 (docs/10 4절 지킬 것 3)
REASSURING = re.compile(
    r"\bsafe(ly)?\b|allergen[\s-]*free|\bfree (of|from)\b|\bno risk\b|\bharmless\b|\bguarantee"
    r"|\b(you )?can (safely )?(eat|consume|enjoy)\b|\bok(ay)? to (eat|consume)\b|\bnothing to worry\b",
    re.IGNORECASE,
)
# '들어 있지 않다'는 부정문도 안심시키는 말이다(#17 리뷰 1). may contain 배지 아래에 붙으면 배지와 엇갈린다.
# 'without'과 'not ... in'은 'Without the full list, …'처럼 정당한 설명에도 쓰여서 좁게 잡는다.
_ALLERGEN_WORDS = (r"(?:milk|dairy|eggs?|fish|shellfish|crustaceans?|shrimps?|prawns?|crabs?|lobsters?"
                   r"|tree\s*nuts?|nuts?|almonds?|walnuts?|hazelnuts?|pecans?|cashews?|pistachios?|peanuts?"
                   r"|wheat|gluten|soy(?:beans?)?|sesame)")
DENIAL = re.compile(
    r"\b(?:does|do|did)(?:\s+not|n['’]t)\s+(?:contain|include)\b"     # does not contain, doesn't include
    r"|\bcontains?\s+no\b"                                             # contains no fish
    r"|\bno\s+" + _ALLERGEN_WORDS + r"\b"                              # there is no sesame
    r"|\b(?:made|produced|prepared|manufactured)\s+without\b"          # made without fish
    r"|(?:\bnot|n['’]t)\s+an?\s+ingredient\b",                         # is not an ingredient, isn't an ingredient
    re.IGNORECASE,
)
# 판정 불가인데 들어 있다고 단정하는 말
ASSERTIVE = re.compile(r"\b(definitely|certainly|surely|clearly) contains?\b|\bdoes contain\b", re.IGNORECASE)

CallFn = Callable[[str, str], Any]  # (system, user) -> {"results": [...]} (못 읽으면 {})

_cache: "OrderedDict[str, Dict[str, Optional[str]]]" = OrderedDict()
_default_call: Optional[CallFn] = None


def enabled() -> bool:
    return os.getenv(ENV, "").strip().lower() == "llm"


# ---------------- LLM 호출 ----------------
def _extract_json(text: str) -> Any:
    if not text:
        return {}
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e <= s:
        return {}
    try:
        return json.loads(text[s : e + 1])
    except json.JSONDecodeError:
        return {}


def openai_call(base_url: str, api_key: str, model: str, temperature: float, timeout: float) -> CallFn:
    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key, max_retries=0, timeout=timeout)

    def call(system: str, user: str) -> Any:
        resp = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=1500,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            tools=[TOOL],
            tool_choice="auto",  # 학교 게이트웨이의 Claude는 특정 도구 강제를 거부한다 (EXP-005)
        )
        msg = resp.choices[0].message
        results: List[Any] = []
        found = False
        for tc in msg.tool_calls or []:
            if tc.function.name == TOOL_NAME:
                found = True
                part = _extract_json(tc.function.arguments)
                if isinstance(part, dict):
                    results += part.get("results") or []
        return {"results": results} if found else _extract_json(msg.content or "")

    return call


def _env_call() -> Optional[CallFn]:
    """.env 설정으로 만든 호출 함수. 키가 없으면 None (설명 없이 돌려준다)."""
    global _default_call
    if _default_call is None:
        key, base, model = os.getenv("LLM_API_KEY"), os.getenv("LLM_BASE_URL"), os.getenv("LLM_MODEL")
        if not (key and base and model):
            return None
        _default_call = openai_call(
            base, key, model, float(os.getenv("LLM_TEMPERATURE", "0")), float(os.getenv("LLM_EXPLAIN_TIMEOUT", "20"))
        )
    return _default_call


# ---------------- 입력과 검사 ----------------
def _targets(res: FinalAnalyzeResponse) -> List[FinalAllergenResult]:
    return [a for a in res.allergens if a.verdict.value in TARGET_VERDICTS]


def build_payload(res: FinalAnalyzeResponse, targets: List[FinalAllergenResult]) -> Dict[str, Any]:
    return {
        "label": {"ingredients_text": res.ingredients_text, "declaration_text": res.declaration_text},
        "items": [
            {
                "allergen": a.allergen.value,
                "verdict": a.verdict.value,
                "basis": list(a.basis),
                "evidence_ingredient": a.evidence_ingredient,
                "evidence_en": a.evidence_en,
                "read_as": a.read_as,
                "other_evidence": list(a.other_evidence),
                "reason_en": a.reason_en,
            }
            for a in targets
        ],
    }


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def check(text: Any, item: FinalAllergenResult) -> Optional[str]:
    """쓸 수 있는 설명이면 다듬어서, 아니면 None."""
    if not isinstance(text, str):
        return None
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) > MAX_CHARS:
        return None
    if REASSURING.search(text) or DENIAL.search(text):
        return None
    if item.verdict.value == "undecidable" and ASSERTIVE.search(text):
        return None
    if item.basis and item.basis[0] == "LLM-FIX" and item.read_as and _norm(item.read_as) not in _norm(text):
        return None  # 고친 이름(read_as)을 설명하지 않았다 = 다른 이름으로 다시 추측했을 수 있다
    return text


def parse(raw: Any, targets: List[FinalAllergenResult]) -> Dict[str, Optional[str]]:
    by_allergen = {a.allergen.value: a for a in targets}
    out: Dict[str, Optional[str]] = {}
    items = raw.get("results") if isinstance(raw, dict) else None
    for it in items or []:
        if not isinstance(it, dict):
            continue
        name = it.get("allergen")
        if name in by_allergen and name not in out:  # 목록 밖 알레르기, 두 번째 답은 버린다
            out[name] = check(it.get("explanation"), by_allergen[name])
    return out


# ---------------- 본체 ----------------
def explain(res: FinalAnalyzeResponse, call: Optional[CallFn] = None) -> FinalAnalyzeResponse:
    """explanation_en을 채운 새 응답. 켜져 있지 않거나 실패하면 res를 그대로 돌려준다."""
    if call is None:
        if not enabled():
            return res
        call = _env_call()
        if call is None:
            return res
    if res.warnings:
        return res
    targets = _targets(res)
    if not targets:
        return res

    payload = build_payload(res, targets)
    user = json.dumps(payload, ensure_ascii=False)
    key = hashlib.sha256(user.encode("utf-8")).hexdigest()
    got = _cache.get(key)
    if got is None:
        try:
            got = parse(call(PROMPT_PATH.read_text(encoding="utf-8"), user), targets)
        except Exception:  # 크레딧 소진(402), 시간 초과, 게이트웨이 장애: 설명 없이 간다
            return res
        _cache[key] = got
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    else:
        _cache.move_to_end(key)

    if not any(got.values()):
        return res
    allergens = [
        a.model_copy(update={"explanation_en": got.get(a.allergen.value)}) if a.allergen.value in got else a
        for a in res.allergens
    ]
    return res.model_copy(update={"allergens": allergens})


def clear_cache() -> None:
    _cache.clear()


__all__ = ["ENV", "PROMPT_VERSION", "check", "clear_cache", "enabled", "explain", "openai_call"]
