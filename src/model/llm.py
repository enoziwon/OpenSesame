"""1차 분류기: LLM이 5단계(원재료 이름 → 알레르겐)만 맡는다.

- 입력은 원재료 이름 목록뿐이다. 사진·사용자 프로필은 보내지 않는다.
- 출력은 tool 호출로 형식을 강제하고, 형식이 틀린 항목은 source_unknown으로 낮춘다.
- 근거 검사·누락 검사·제품 단위 합치기는 src/pipeline.py가 한다 (LLM을 믿지 않는다).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from src.common.schema import Allergen, AllergenMatch, IngredientClassification, Verdict

PROMPT_VERSION = "classify_v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.txt"

TOOL = {
    "name": "report_allergens",
    "description": "원재료마다 알레르겐 분류 결과를 보고한다.",
    "input_schema": {
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
    },
}

# (system, user) -> tool 입력(dict). 테스트에서 가짜 함수로 바꿔 끼운다.
CallFn = Callable[[str, str], dict[str, Any]]


def parse_tool_output(raw: dict[str, Any]) -> list[IngredientClassification]:
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


class LLMClassifier:
    name = "llm"
    prompt_version = PROMPT_VERSION

    def __init__(self, call: CallFn, model: str):
        self._call = call
        self.model = model
        self.system = PROMPT_PATH.read_text(encoding="utf-8")

    @classmethod
    def from_env(cls) -> "LLMClassifier":
        import anthropic

        api_key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("LLM_API_KEY가 없다. .env를 확인할 것.")
        model = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
        client = anthropic.Anthropic(api_key=api_key)

        def call(system: str, user: str) -> dict[str, Any]:
            resp = client.messages.create(
                model=model,
                max_tokens=4096,
                temperature=0,
                system=system,
                tools=[TOOL],
                tool_choice={"type": "tool", "name": TOOL["name"]},
                messages=[{"role": "user", "content": user}],
            )
            for block in resp.content:
                if block.type == "tool_use":
                    return dict(block.input)
            return {}

        return cls(call=call, model=model)

    def classify(self, ingredients: list[str]) -> list[IngredientClassification]:
        if not ingredients:
            return []
        user = "원재료 목록 (JSON):\n" + json.dumps(ingredients, ensure_ascii=False)
        return parse_tool_output(self._call(self.system, user))
