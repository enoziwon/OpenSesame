"""최종본 응답 형식. 팀 형식(src/common/schema.py)을 넓힌 것이다.

팀 화면은 모르는 칸을 그대로 통과시키므로 기존 칸의 뜻은 바꾸지 않고 칸만 더한다.
팀 AnalyzeResponse로 읽어도(model_validate) 그대로 통과한다.

basis 값 (알레르기마다, 판정을 정한 근거 순서대로)
    INGREDIENT  원재료에 확정 근거가 있다          KR-DECL   한국 알레르기 표시란에 적혀 있다
    R1-1        표시란의 대두가 유지 때문일 수 있다    LIKELY    대개 들어가는 원료가 있다 (추정)
    POSSIBLE    들어가는 경우가 드물지 않은 원료       OPAQUE    속 모를 양념·국물 원료
    COMPOUND    속 모를 섞은 원료 (표시란을 못 읽었을 때만)
    LLM-FIX     OCR이 잘못 읽은 이름을 LLM이 고쳐 사전에서 찾았다 (read_as가 고친 이름). 확정이어도 추정으로 낮춘다
    LLM         사전에 없는 이름을 LLM이 판단했다. 확정이어도 추정으로 낮춘다
LLM-FIX와 LLM은 OPENSESAME_FINAL_FALLBACK=llm일 때만 나온다. LLM 근거는 추정·판정 불가까지만 만들고 확정은 만들지 않는다.

같은 시설 문구는 판정에 쓰지 않는다. 판정이 없는 알레르기만 shared_facility에 고정 문장과 함께 담는다(src/final/facility.py).
화면과 LLM 설명이 이 칸들을 어떻게 쓰는지는 docs/10_may_contain.md.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from src.common.schema import Allergen, AllergenResult, AnalyzeResponse, Ingredient


class FinalIngredient(Ingredient):
    """원재료 나무의 노드. group은 면·스프처럼 구성품을 묶는 머리말이다 (원재료가 아님)."""

    children: List[FinalIngredient] = Field(default_factory=list)
    group: bool = False


class FinalAllergenResult(AllergenResult):
    basis: List[str] = Field(default_factory=list)
    species: List[str] = Field(default_factory=list)      # 종의 영어 이름. 예: ["anchovy"]
    evidence_en: Optional[str] = None                      # 근거 원료의 영어 이름. 사전에 없으면 None
    reason_en: str = ""                                    # 미국 사용자에게 보여 줄 한 문장
    reason_ko: str = ""
    read_as: Optional[str] = None                          # basis가 LLM-FIX일 때 LLM이 고친 이름. 근거 '유우' -> '우유'
    explanation_en: Optional[str] = None                   # LLM 추가 설명(이진영 담당). 최종본은 비워 두고 채우지 않는다


class FacilityResult(BaseModel):
    """같은 시설 문구에만 있는 알레르기. 판정이 아니다 (판정이 있는 알레르기는 여기 오지 않는다)."""

    allergen: Allergen
    words: List[str] = Field(default_factory=list)         # 문구에 적힌 한국어 낱말. 예: ["새우", "게"]
    reason_en: str = ""                                    # 고정 문장: 원재료에는 없지만 미량이 섞일 수 있다
    reason_ko: str = ""


class FinalAnalyzeResponse(AnalyzeResponse):
    ingredients: List[FinalIngredient]
    allergens: List[FinalAllergenResult]
    declaration_text: Optional[str] = None                 # 한국 알레르기 표시란 원문. 못 찾으면 None
    declared: List[str] = Field(default_factory=list)      # 표시란 낱말 (적힌 그대로)
    notes: List[str] = Field(default_factory=list)         # 판정에 쓰지 않은 참고 사항
    shared_facility: List[FacilityResult] = Field(default_factory=list)   # 같은 시설 문구 (판정 없는 알레르기만)


__all__ = ["FacilityResult", "FinalAllergenResult", "FinalAnalyzeResponse", "FinalIngredient"]
