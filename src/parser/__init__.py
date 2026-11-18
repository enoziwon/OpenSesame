"""3·4단계: 원재료명 텍스트 → 원재료 트리.

담당: 김민재. 실제 처리는 core.py (괄호 파서), 여기서는 팀 계약(schema.Ingredient)으로 바꿔서 내보낸다.
- 최상위 쉼표로 나누고, 괄호 (), [], {} 안은 하위 원재료로 재귀 분해한다.
  OCR이 괄호 종류를 바꿔 읽어도({ -> ( 등) 깊이만 맞으면 된다.
- 원산지('말레이시아산', '밀:미국산'의 '미국산'), 용도('향미증진제'), 함량(3%)은 원재료로 만들지 않는다.
  '밀:미국산' -> 하위 원재료 '밀'
- 'A/B' 표기는 A를 이름으로 쓴다 (B는 core 결과의 aliases).
- 끝의 '밀, 대두, 우유 함유'(한국 표시란)는 원재료 목록에서 떼어 낸다 -> declared_allergens()
- 닫히지 않은 괄호는 문자열 끝까지를 괄호 안으로 본다 (OCR 오류 대비).
"""
from __future__ import annotations

from src.common.schema import Ingredient
from src.parser import core


def _to_schema(nodes) -> list[Ingredient]:
    return [Ingredient(name=n["name"], children=_to_schema(n["children"])) for n in nodes if n["name"] or n["children"]]


def parse(text: str) -> list[Ingredient]:
    return _to_schema(core.parse(text)["ingredients"])


def declared_allergens(text: str) -> list[str]:
    """한국 표시란 '○○ 함유'에 적힌 항목 (예: ['밀', '대두'])."""
    return core.parse(text)["kr_declared"]


def flatten(tree: list[Ingredient]) -> list[str]:
    """분류기 입력용: 트리의 모든 원재료 이름 (부모 포함, 등장 순, 중복 제거)."""
    seen: dict[str, None] = {}

    def walk(nodes: list[Ingredient]) -> None:
        for n in nodes:
            if n.name:
                seen.setdefault(n.name, None)
            walk(n.children)

    walk(tree)
    return list(seen)
