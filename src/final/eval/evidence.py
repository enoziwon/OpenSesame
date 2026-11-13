"""근거 일치: 시스템 evidence_ingredient가 정답 근거와 같은 원재료를 가리키는가.

- 비교 전에 함량(3%)과 공백을 떼고, 첫 여는 괄호부터 뒤를 버린다. '참기름 3%' -> '참기름'
- 정답 근거가 '부모(자식, …)' 꼴이면 부모나 바로 아래 자식 중 하나와 같으면 일치다. 손자는 보지 않는다.
- "표시란: X"는 어느 쪽이든 그 꼴이면 글자 그대로 비교한다.
- 빈 근거는 무엇과도 같지 않다.
"""
import re

PERCENT_RE = re.compile(r"\s*\d+(?:\.\d+)?\s*[%％]")
SPACE_RE = re.compile(r"\s+")
OPEN = "([{<（［｛【〈《「『"
CLOSE = ")]}>）］｝】〉》」』"
SEPS = ",、，"
BOX = "표시란:"


def clean(text):
    """함량과 공백을 떼고 첫 여는 괄호 앞까지만 남긴다. '간장 (대두, 밀)' -> '간장'"""
    s = SPACE_RE.sub("", PERCENT_RE.sub("", text))
    cut = next((i for i, ch in enumerate(s) if ch in OPEN), len(s))
    return s[:cut]


def _inside(s, start):
    """s[start]의 여는 괄호 안을 맨 위 구분자로 나눈 조각들. 닫는 괄호가 없으면 끝까지 본다."""
    parts, buf, depth = [], [], 0
    for ch in s[start + 1:]:
        if ch in CLOSE and depth == 0:
            break
        if ch in OPEN:
            depth += 1
        elif ch in CLOSE:
            depth -= 1
        if ch in SEPS and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def accepted_names(gold):
    """정답 근거가 받아 주는 이름들: 부모와 바로 아래 자식. '간장(대두, 밀)' -> {'간장', '대두', '밀'}"""
    s = PERCENT_RE.sub("", gold)
    names = {clean(s)}
    start = next((i for i, ch in enumerate(s) if ch in OPEN), None)
    if start is not None:
        names.update(clean(part) for part in _inside(s, start))
    return names - {""}


def is_box(text):
    return SPACE_RE.sub("", text).startswith(BOX)


def evidence_matches(gold, pred):
    """정답 근거와 시스템 근거가 같은 원재료를 가리키면 True."""
    if is_box(gold) or is_box(pred):
        return bool(gold) and gold == pred
    name = clean(pred)
    return bool(name) and name in accepted_names(gold)
