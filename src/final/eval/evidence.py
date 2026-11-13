"""근거 일치: 시스템 evidence_ingredient가 정답 근거와 같은 원재료를 가리키는가.

정답 근거는 라벨에 적힌 그대로다. 겉 원료 한 덩어리 '크래미[연육(...), 소맥전분(밀), ...]'를 통째로 적기도 한다.
시스템 근거는 파서가 정리한 이름 하나다. 그래서 정답 덩어리 안의 이름 가운데 하나와 맞으면 일치로 본다.

- 정답 근거를 괄호와 구분자(쉼표, 쌍점, 빗금)로 쪼개 이름들을 얻는다. 깊이는 따지지 않는다.
- 비교 전에 함량(3%)과 공백을 뗀다. 시스템 근거는 첫 여는 괄호부터 뒤를 버린다.
- 두 글자 이상인 이름끼리는 한쪽이 다른 쪽의 앞이나 뒤에 붙은 꼴이어도 일치다.
  '찌개양념베이스3'과 '찌개양념베이스'(뒤에 붙은 번호), '소맥분'과 '면-소맥분'(앞에 남은 머리말)을 같게 보기 위해서다.
- "표시란: X"는 어느 쪽이든 그 꼴이면 글자 그대로 비교한다.
- 빈 근거는 무엇과도 같지 않다.
"""
import re

PERCENT_RE = re.compile(r"\s*\d+(?:\.\d+)?\s*[%％]")
SPACE_RE = re.compile(r"\s+")
OPEN = "([{<（［｛【〈《「『"
CLOSE = ")]}>）］｝】〉》」』"
SEPS = ",、，:：/;"
SPLIT_RE = re.compile("[" + re.escape(OPEN + CLOSE + SEPS) + "]")
BOX = "표시란:"


def clean(text):
    """함량과 공백을 떼고 첫 여는 괄호 앞까지만 남긴다. '간장 (대두, 밀)' -> '간장'"""
    s = SPACE_RE.sub("", PERCENT_RE.sub("", text))
    cut = next((i for i, ch in enumerate(s) if ch in OPEN), len(s))
    return s[:cut]


def accepted_names(gold):
    """정답 근거 안의 이름들. '간장(대두, 밀:미국산)' -> {'간장', '대두', '밀', '미국산'}"""
    s = SPACE_RE.sub("", PERCENT_RE.sub("", gold))
    return {part for part in SPLIT_RE.split(s) if part}


def _same(a, b):
    """같은 이름이거나, 두 글자 이상인 이름끼리 한쪽이 다른 쪽의 앞·뒤에 붙은 꼴."""
    if a == b:
        return True
    if len(a) < 2 or len(b) < 2:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return long_.startswith(short) or long_.endswith(short)


def is_box(text):
    return SPACE_RE.sub("", text).startswith(BOX)


def evidence_matches(gold, pred):
    """정답 근거와 시스템 근거가 같은 원재료를 가리키면 True."""
    if is_box(gold) or is_box(pred):
        return bool(gold) and gold == pred
    name = clean(pred)
    return bool(name) and any(_same(name, t) for t in accepted_names(gold))
