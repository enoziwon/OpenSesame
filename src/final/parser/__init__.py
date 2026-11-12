"""최종본 3·4단계: 라벨 글자 -> 구역 -> 원재료 나무.

    from src.final.parser import parse_label
    r = parse_label("원재료명: 혼합조미분말(멸치분말, 정제염) 밀, 대두 함유")
    r.to_api()      # {"ingredients_text", "declaration_text", "ingredients": [...]}
    r.mentions()    # [(이름, 깊이, 부모, 잎인가), ...]  분류 단계의 입력

팀 1차 파서(src/parser)와 달리 알레르기 표시란과 같은 시설 문구를 원재료에서 떼어 낸다.
"""
from dataclasses import dataclass
from typing import Optional

from .tree import Node, mentions, parse_tree
from .zones import split_zones, zones_from_fields

MAX_CHARS = 20000     # 라벨 한 장은 길어야 수천 자


@dataclass(frozen=True)
class ParsedLabel:
    ingredients_text: str
    declaration_text: Optional[str]
    declared: tuple
    facility_text: Optional[str]
    tree: tuple
    repairs: int          # 괄호 짝을 고친 횟수. 0보다 크면 OCR이나 라벨이 깨졌을 수 있다

    def mentions(self):
        return mentions(self.tree)

    def to_api(self):
        """팀 응답 형식의 앞부분. allergens와 warnings는 분류·판정 단계가 채운다."""
        return {
            "ingredients_text": self.ingredients_text,
            "declaration_text": self.declaration_text,
            "ingredients": [n.to_dict() for n in self.tree],
        }


def _check(name, value):
    if value is None:
        return
    if not isinstance(value, str):
        raise TypeError(f"{name}에는 글자(str)만 넣을 수 있습니다")
    if len(value) > MAX_CHARS:
        raise ValueError(f"{name}이(가) 너무 깁니다 (최대 {MAX_CHARS}자)")


def parse_label(text=None, *, ingredients=None, declaration=None):
    """사진에서 읽은 글자 전체(text) 또는 API처럼 나뉜 칸(ingredients, declaration)을 받는다."""
    if (text is None) == (ingredients is None):
        raise ValueError("text와 ingredients 중 하나만 넣어 주세요")
    for name, value in (("text", text), ("ingredients", ingredients), ("declaration", declaration)):
        _check(name, value)
    if text is not None:
        z = split_zones(text)
    else:
        z = zones_from_fields(ingredients, declaration)
    tree, repairs = parse_tree(z.ingredients_text)
    return ParsedLabel(z.ingredients_text, z.declaration_text, z.declared, z.facility_text, tree, repairs)


__all__ = ["Node", "ParsedLabel", "parse_label", "parse_tree", "mentions", "split_zones"]
