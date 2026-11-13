"""한글 음절을 자모(초성·중성·종성)로 풀고 자모 단위 편집 거리를 잰다. 표준 라이브러리만 쓴다.

    from src.final.jamo import distance, syllables, to_jamo
    to_jamo("분")                                  # '분' (초성 ㅂ, 중성 ㅜ, 종성 ㄴ)
    distance(to_jamo("탈지분유"), to_jamo("탈지븐유"))   # 1 (ㅜ -> ㅡ)
    syllables("비타민C")                           # 3 (한글 음절만 센다)

자모는 유니코드 첫가끝 글자로 쓴다. 초성 ㄱ(ᄀ)과 종성 ㄱ(ᆨ)은 다른 글자라서
초성이 받침 자리로 옮겨 가는 식의 엉뚱한 맞춤이 싸게 계산되지 않는다.
"""
from __future__ import annotations

from typing import Optional, Tuple

FIRST, LAST = 0xAC00, 0xD7A3       # 가 ~ 힣
CHO, JUNG, JONG = 0x1100, 0x1161, 0x11A7     # 초성 ᄀ, 중성 ᅡ, 종성 자리(번호 0은 받침 없음)
N_CHO, N_JUNG, N_JONG = 19, 21, 28


def is_syllable(ch: str) -> bool:
    """완성형 한글 음절(가~힣) 한 글자인가."""
    return len(ch) == 1 and FIRST <= ord(ch) <= LAST


def split_syllable(ch: str) -> Tuple[int, int, int]:
    """음절 하나 -> (초성 0~18, 중성 0~20, 종성 0~27). 종성 0은 받침 없음."""
    if not is_syllable(ch):
        raise ValueError("한글 음절 한 글자만 풀 수 있습니다")
    i = ord(ch) - FIRST
    return i // (N_JUNG * N_JONG), i % (N_JUNG * N_JONG) // N_JONG, i % N_JONG


def join_syllable(cho: int, jung: int, jong: int = 0) -> str:
    """(초성, 중성, 종성) 번호 -> 음절 한 글자."""
    if not (0 <= cho < N_CHO and 0 <= jung < N_JUNG and 0 <= jong < N_JONG):
        raise ValueError("자모 번호가 범위를 벗어났습니다")
    return chr(FIRST + (cho * N_JUNG + jung) * N_JONG + jong)


def to_jamo(text: str) -> str:
    """한글 음절은 초성·중성·(종성) 글자로 풀고, 한글이 아닌 글자(영문·숫자)는 그대로 둔다."""
    out = []
    for ch in text:
        if is_syllable(ch):
            cho, jung, jong = split_syllable(ch)
            out.append(chr(CHO + cho) + chr(JUNG + jung) + (chr(JONG + jong) if jong else ""))
        else:
            out.append(ch)
    return "".join(out)


def syllables(text: str) -> int:
    """한글 음절 수. 영문·숫자·기호는 세지 않는다."""
    return sum(1 for ch in text if is_syllable(ch))


def distance(a: str, b: str, limit: Optional[int] = None) -> int:
    """편집 거리(바꾸기·빼기·넣기 한 번에 1). 자모 거리는 to_jamo로 푼 두 글자를 넣는다.

    limit을 주면 거리가 limit보다 크다고 밝혀지는 순간 멈추고 limit + 1을 돌려준다(후보가 많을 때 빠르게).
    """
    if a == b:
        return 0
    if limit is not None and abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if limit is not None and min(cur) > limit:
            return limit + 1
        prev = cur
    if limit is not None and prev[-1] > limit:
        return limit + 1
    return prev[-1]


__all__ = ["distance", "is_syllable", "join_syllable", "split_syllable", "syllables", "to_jamo"]
