"""최종본 응답 형식. 팀 형식(src/common/schema.py)을 넓힌 것이다.

팀 화면은 모르는 칸을 그대로 통과시키므로 기존 칸의 뜻은 바꾸지 않고 칸만 더한다.
팀 AnalyzeResponse로 읽어도(model_validate) 그대로 통과한다.

basis 값 (알레르기마다, 판정을 정한 근거 순서대로)
    INGREDIENT  원재료에 확정 근거가 있다          KR-DECL   한국 알레르기 표시란에 적혀 있다
    R1-1        표시란의 대두가 유지 때문일 수 있다    LIKELY    대개 들어가는 원료가 있다 (추정)
    POSSIBLE    들어가는 경우가 드물지 않은 원료       OPAQUE    속 모를 양념·국물 원료
    COMPOUND    속 모를 섞은 원료 (표시란을 못 읽었을 때만)
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from src.common.schema import AllergenResult, AnalyzeResponse, Ingredient


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


class FinalAnalyzeResponse(AnalyzeResponse):
    ingredients: List[FinalIngredient]
    allergens: List[FinalAllergenResult]
    declaration_text: Optional[str] = None                 # 한국 알레르기 표시란 원문. 못 찾으면 None
    declared: List[str] = Field(default_factory=list)      # 표시란 낱말 (적힌 그대로)
    notes: List[str] = Field(default_factory=list)         # 판정에 쓰지 않은 참고 사항


__all__ = ["FinalAllergenResult", "FinalAnalyzeResponse", "FinalIngredient"]
