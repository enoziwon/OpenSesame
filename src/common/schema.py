"""파이프라인 단계 사이를 오가는 데이터 형식.

이 파일이 팀 전체의 계약이다. 바꿀 때는 제안 이슈 → 회의 합의 → docs/decisions 기록 순서를 지킨다.
allergen·verdict 값은 data/schema/label_record.schema.json(gold)과 같아야 한다.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Allergen(str, Enum):
    """미국 의무 표시 알레르겐 9개."""

    milk = "milk"
    egg = "egg"
    fish = "fish"
    crustacean = "crustacean"
    tree_nut = "tree_nut"
    peanut = "peanut"
    wheat = "wheat"
    soy = "soy"
    sesame = "sesame"


class Verdict(str, Enum):
    confirmed = "confirmed"      # 확인됨
    inferable = "inferable"      # 추정
    undecidable = "undecidable"  # 판정 불가


# 제품 단위로 합칠 때 더 강한 판정을 고른다.
VERDICT_STRENGTH = {Verdict.confirmed: 3, Verdict.inferable: 2, Verdict.undecidable: 1}


# ---------- 2단계: OCR ----------
class OcrResult(BaseModel):
    text: str
    engine: str
    confidence: Optional[float] = None


# ---------- 3·4단계: 파서 ----------
class Ingredient(BaseModel):
    name: str
    children: list[Ingredient] = Field(default_factory=list)


# ---------- 5단계: 분류기 (LLM → 자체 모델로 교체되는 부분) ----------
class AllergenMatch(BaseModel):
    allergen: Allergen
    verdict: Verdict


class IngredientClassification(BaseModel):
    """원재료 하나에 대한 분류 결과.

    matches가 비어 있고 source_unknown이 False면 '9개 알레르겐과 관계없음'이다.
    source_unknown=True는 '무엇에서 왔는지 알 수 없음'(예: 향료)이다.
    """

    ingredient: str
    matches: list[AllergenMatch] = Field(default_factory=list)
    source_unknown: bool = False


# ---------- 6단계: 제품 단위 결과 (서버 응답) ----------
class AllergenResult(BaseModel):
    allergen: Allergen
    verdict: Verdict
    evidence_ingredient: str
    other_evidence: list[str] = Field(default_factory=list)


class AnalyzeMeta(BaseModel):
    ocr_engine: str
    classifier: str
    prompt_version: Optional[str] = None


class AnalyzeResponse(BaseModel):
    """POST /analyze 응답.

    allergens에 없는 항목은 '검출 안 됨'이지 '안전'이 아니다.
    개인 프로필과의 대조는 브라우저가 한다. 서버는 프로필을 받지 않는다.
    """

    ingredients_text: str
    ingredients: list[Ingredient]
    allergens: list[AllergenResult]
    undecidable_ingredients: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    meta: AnalyzeMeta
