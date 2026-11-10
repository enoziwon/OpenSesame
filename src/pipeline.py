"""파이프라인 연결: 사진 → OCR → 파서 → 분류기 → 검증 → 제품 단위 합치기.

분류기 출력을 그대로 믿지 않는다.
- 근거 검사: 입력에 없는 원재료에 대한 답은 버린다 (지어낸 근거 차단).
- 누락 검사: 분류기가 답하지 않은 원재료는 '판정 불가 원재료'로 돌린다.
- 합치기: 알레르겐마다 가장 강한 판정을 고른다 (confirmed > inferable > undecidable). 규칙이지 LLM이 아니다.
"""
from __future__ import annotations

from src.common.schema import (
    VERDICT_STRENGTH,
    Allergen,
    AllergenResult,
    AnalyzeMeta,
    AnalyzeResponse,
    IngredientClassification,
)
from src.model import Classifier
from src.ocr import OcrEngine
from src.parser import flatten, parse


def validate(
    inputs: list[str], results: list[IngredientClassification]
) -> tuple[list[IngredientClassification], list[str]]:
    warnings: list[str] = []
    allowed = set(inputs)
    by_name: dict[str, IngredientClassification] = {}
    for r in results:
        if r.ingredient not in allowed:
            warnings.append(f"입력에 없는 원재료에 대한 답을 버림: {r.ingredient}")
            continue
        by_name.setdefault(r.ingredient, r)
    missing = [name for name in inputs if name not in by_name]
    for name in missing:
        by_name[name] = IngredientClassification(ingredient=name, source_unknown=True)
    if missing:
        warnings.append(f"분류기가 답하지 않은 원재료 {len(missing)}개를 판정 불가로 처리함")
    return [by_name[name] for name in inputs], warnings


def aggregate(results: list[IngredientClassification]) -> tuple[list[AllergenResult], list[str]]:
    evidence: dict[Allergen, list[tuple[int, str]]] = {}
    unknown: list[str] = []
    for r in results:
        if r.source_unknown:
            unknown.append(r.ingredient)
        for m in r.matches:
            evidence.setdefault(m.allergen, []).append((VERDICT_STRENGTH[m.verdict], r.ingredient))

    allergens = []
    for allergen in Allergen:  # 고정 순서
        items = evidence.get(allergen)
        if not items:
            continue
        best_strength = max(s for s, _ in items)
        verdict = next(v for v, s in VERDICT_STRENGTH.items() if s == best_strength)
        best = [name for s, name in items if s == best_strength]
        others = [name for s, name in items if name not in best]
        allergens.append(
            AllergenResult(
                allergen=allergen,
                verdict=verdict,
                evidence_ingredient=best[0],
                other_evidence=list(dict.fromkeys(best[1:] + others)),
            )
        )
    return allergens, unknown


def analyze(image: bytes, content_type: str, ocr: OcrEngine, classifier: Classifier) -> AnalyzeResponse:
    ocr_result = ocr.read_text(image, content_type)
    tree = parse(ocr_result.text)
    names = flatten(tree)
    warnings: list[str] = []
    if not names:
        warnings.append("원재료를 읽지 못함. 원재료명이 잘 보이게 다시 찍어 주세요.")

    try:
        raw = classifier.classify(names)
    except Exception as e:  # LLM 장애 등: 아무것도 단정하지 않는다
        raw = []
        warnings.append(f"분류 실패: {type(e).__name__}")

    checked, more = validate(names, raw)
    warnings += more
    allergens, unknown = aggregate(checked)

    return AnalyzeResponse(
        ingredients_text=ocr_result.text,
        ingredients=tree,
        allergens=allergens,
        undecidable_ingredients=unknown,
        warnings=warnings,
        meta=AnalyzeMeta(
            ocr_engine=ocr.name, classifier=classifier.name, prompt_version=classifier.prompt_version
        ),
    )
