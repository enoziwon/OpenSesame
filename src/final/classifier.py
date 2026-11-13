"""팀 분류기 인터페이스(classify)를 지키는 최종본 사전 분류기.

팀 파이프라인(src/pipeline.py)에 분류기만 바꿔 끼워 LLM 시제품과 같은 조건에서 비교할 때 쓴다.

    from src.pipeline import analyze
    from src.ocr import MockOcr
    from src.final.classifier import FinalClassifier
    analyze(b"", "image/jpeg", MockOcr(), FinalClassifier())

원재료 이름 하나만 보므로 표시란 규칙(R1~R4)과 괄호 속 하위 원료 규칙은 쓰지 못한다.
그 규칙까지 쓰는 판정은 src.final.pipeline이 한다.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from src.common.schema import VERDICT_STRENGTH, Allergen, AllergenMatch, IngredientClassification, Verdict
from src.final.lexicon import lookup
from src.final.verdict import code_info

GRADE_VERDICT = {"C": Verdict.confirmed, "I": Verdict.inferable, "P": Verdict.undecidable}   # R·F는 세지 않는다


class FinalClassifier:
    """C -> confirmed, I -> inferable, P -> undecidable, 모르는 이름·일반 향료 -> source_unknown,
    정제유(R)·종류 모를 유지(F) -> 없음. 속 모를 원료는 가이드 v1 5장대로 생선(고기 바탕이 적힌 것은 빼고)과
    참깨(양념·소스 계열만)를 undecidable로 낸다."""

    name = "final-lexicon"
    prompt_version: Optional[str] = None

    def __init__(self, resolve: Callable = lookup):
        self._resolve = resolve

    def classify(self, ingredients: List[str]) -> List[IngredientClassification]:
        if isinstance(ingredients, str):
            raise TypeError("원재료 이름 목록(list[str])을 넣어 주세요")
        return [self._one(name) for name in ingredients]

    def _one(self, name: str) -> IngredientClassification:
        hit = self._resolve(name)
        general_flavor = bool(hit.flavor) and not hit.sources
        best: Dict[Allergen, Verdict] = {}
        for code, grade in hit.sources:
            us9 = code_info(code)[0]
            verdict = GRADE_VERDICT.get(grade)
            if us9 and verdict is not None:
                _keep_stronger(best, Allergen(us9), verdict)
        if hit.opaque and not general_flavor:
            if not getattr(hit, "opaque_meat", False):
                _keep_stronger(best, Allergen.fish, Verdict.undecidable)
            if getattr(hit, "opaque_sesame", False):
                _keep_stronger(best, Allergen.sesame, Verdict.undecidable)
        matches = [AllergenMatch(allergen=a, verdict=best[a]) for a in Allergen if a in best]
        unknown = hit.via == "unknown" or general_flavor
        return IngredientClassification(ingredient=name, matches=matches, source_unknown=unknown)


def _keep_stronger(best: Dict[Allergen, Verdict], allergen: Allergen, verdict: Verdict) -> None:
    old = best.get(allergen)
    if old is None or VERDICT_STRENGTH[verdict] > VERDICT_STRENGTH[old]:
        best[allergen] = verdict


__all__ = ["FinalClassifier"]
