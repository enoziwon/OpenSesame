"""3·4단계: 원재료명 텍스트 → 원재료 트리.

담당: 김민재. 지금 구현은 끝에서 끝까지 연결하기 위한 최소 버전이다.
- 최상위 쉼표로 나누고, 괄호 (), [], {} 안은 하위 원재료로 재귀 분해한다.
- 함량(3%), '원재료명:' 머리말, 줄바꿈을 정리한다.
- 닫히지 않은 괄호는 문자열 끝까지를 괄호 안으로 본다 (OCR 오류 대비).
아직 하지 않는 것: 원산지 표기('밀:미국산') 분리, '~함유' 문구, 가운뎃점 구분자, 오타 교정.
"""
from __future__ import annotations

import re

from src.common.schema import Ingredient

OPEN = {"(": ")", "[": "]", "{": "}"}
CLOSE = set(OPEN.values())
_PERCENT = re.compile(r"\s*\d+(?:\.\d+)?\s*%")
_HEADER = re.compile(r"^\s*원\s*재\s*료\s*명?\s*[:：]?\s*")


def normalize(text: str) -> str:
    text = _HEADER.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _split_top(text: str) -> list[str]:
    """괄호 깊이 0에서만 쉼표로 나눈다."""
    parts, buf, depth = [], [], 0
    for ch in text:
        if ch in OPEN:
            depth += 1
        elif ch in CLOSE and depth > 0:
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _parse_item(item: str) -> Ingredient:
    idx = next((i for i, ch in enumerate(item) if ch in OPEN), None)
    if idx is None:
        return Ingredient(name=_clean_name(item))
    name = item[:idx]
    depth, end = 0, len(item)
    for i in range(idx, len(item)):
        if item[i] in OPEN:
            depth += 1
        elif item[i] in CLOSE:
            depth -= 1
            if depth == 0:
                end = i
                break
    inner = item[idx + 1 : end]
    rest = item[end + 1 :].strip() if end < len(item) else ""
    full_name = _clean_name(name + (" " + rest if rest else ""))
    return Ingredient(name=full_name, children=parse_items(inner))


def _clean_name(s: str) -> str:
    s = _PERCENT.sub("", s)
    return s.strip(" .·:")


def parse_items(text: str) -> list[Ingredient]:
    return [ing for ing in (_parse_item(p) for p in _split_top(text)) if ing.name or ing.children]


def parse(text: str) -> list[Ingredient]:
    return parse_items(normalize(text))


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
