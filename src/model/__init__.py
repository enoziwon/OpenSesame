"""5단계: 원재료 이름 → 9개 알레르겐 분류.

모든 분류기는 같은 인터페이스(classify)를 지킨다. 그래야 LLM과 자체 모델을 같은 입력으로 비교하고
제품에서 하나만 바꿔 끼울 수 있다.
- 입력: 원재료 이름 목록 (사진·원재료명 전문·사용자 프로필은 주지 않는다)
- 출력: 원재료마다 IngredientClassification 하나
"""
from __future__ import annotations

import os
from typing import Optional, Protocol

from src.common.schema import Allergen, AllergenMatch, IngredientClassification, Verdict


class Classifier(Protocol):
    name: str
    prompt_version: Optional[str]

    def classify(self, ingredients: list[str]) -> list[IngredientClassification]: ...


class MockClassifier:
    """개발·테스트용. 아주 작은 고정 표로 흉내만 낸다.

    사전 매칭 베이스라인이 아니다. 평가에 쓰지 않는다.
    """

    name = "mock"
    prompt_version = None
    _TABLE: dict[str, list[tuple[Allergen, Verdict]]] = {
        "소맥분": [(Allergen.wheat, Verdict.confirmed)],
        "밀": [(Allergen.wheat, Verdict.confirmed)],
        "멸치분말": [(Allergen.fish, Verdict.confirmed)],
        "탈지분유": [(Allergen.milk, Verdict.confirmed)],
        "참기름": [(Allergen.sesame, Verdict.confirmed)],
        "간장": [(Allergen.soy, Verdict.inferable), (Allergen.wheat, Verdict.inferable)],
        "대두레시틴": [(Allergen.soy, Verdict.confirmed)],
    }
    _UNKNOWN = {"향료", "효모추출물"}

    def classify(self, ingredients: list[str]) -> list[IngredientClassification]:
        out = []
        for name in ingredients:
            matches = [AllergenMatch(allergen=a, verdict=v) for a, v in self._TABLE.get(name, [])]
            out.append(
                IngredientClassification(ingredient=name, matches=matches, source_unknown=name in self._UNKNOWN)
            )
        return out


def get_classifier(name: Optional[str] = None) -> Classifier:
    name = name or os.getenv("OPENSESAME_CLASSIFIER", "mock")
    if name == "mock":
        return MockClassifier()
    if name == "llm":
        from src.model.llm import LLMClassifier

        return LLMClassifier.from_env()
    # TODO(2주차): 자체 모델(KLUE-RoBERTa 등)을 여기에 등록
    raise ValueError(f"알 수 없는 분류기: {name}")
