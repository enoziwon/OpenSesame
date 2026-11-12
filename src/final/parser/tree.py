"""원재료 글자를 괄호 구조 그대로 나무로 푼다. 괄호 짝이 깨져도 멈추지 않고 복구한 횟수를 센다."""
import re
import unicodedata
from dataclasses import dataclass, field

from .names import GROUP_RE, GROUP_WORD, clean_name, is_origin, split_pieces

OPEN = {"(": ")", "[": "]", "{": "}", "<": ">", "〈": "〉", "《": "》", "【": "】", "「": "」", "『": "』"}
CLOSE = {v: k for k, v in OPEN.items()}
SEPARATORS = {",", "、"}

_HEADER_RE = re.compile(rf"[\[【〈《<「『]\s*({GROUP_WORD})\s*[\]】〉》>」』]\s*")
_BEFORE_GROUP_RE = re.compile(rf"(?:\s*/\s*|\s+|(?<=[)\]}}]))(?=(?:{GROUP_WORD})\s*[:/])")
# 밀키트 라벨의 '*구성품이름:' 또는 '*스프-' (별표가 구성품을 나눈다)
_STAR_RE = re.compile(r"(?:(?<=[)\]}])|(?<=\s)|^)\*\s*([가-힣A-Za-z][^,:()\[\]{}*\-]{0,20}?)\s*[:\-]\s*")
_LEAD_RE = re.compile(r"^\s*원재료\s*명?\s*(?:및\s*함량)?\s*[:\]]?\s*")


@dataclass(frozen=True)
class Node:
    name: str                 # 정리된 이름 (예: 소맥분)
    raw: str = ""             # 라벨에 적힌 그대로 (예: 소맥분 63.5%)
    children: tuple = ()
    group: bool = False       # 면·스프처럼 구성품을 묶는 머리말

    def to_dict(self):
        """팀 응답 형식 {"name", "children"}. 머리말이면 "group": true를 더한다."""
        d = {"name": self.name, "children": [c.to_dict() for c in self.children]}
        if self.group:
            d["group"] = True
        return d


@dataclass
class _Raw:                   # 나무를 만드는 동안만 쓰는 임시 노드
    text: str = ""
    kids: list = field(default_factory=list)
    group: bool = False


def normalize(text):
    """전각 문자(（，：％)를 반각으로, 줄바꿈과 겹친 띄어쓰기를 한 칸으로."""
    s = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", s).strip()


def mark_groups(s):
    """'[면]', ' / 액상스프 :', ' 스프/', ' *양념장:' 같은 머리말 앞을 쉼표로 끊어 둔다."""
    s = _STAR_RE.sub(r", \1: ", s)
    s = _HEADER_RE.sub(r", \1: ", s)
    return _BEFORE_GROUP_RE.sub(", ", s)


def _parse_brackets(s):
    """쉼표와 괄호를 따라 임시 노드 나무를 만든다. (맨 위 항목들, 복구 횟수)"""
    root = _Raw()
    stack = [(root, None)]    # (괄호를 연 노드, 기다리는 닫는 괄호)
    cur = _Raw()
    buf = []
    repairs = 0

    def take_buf():
        word = "".join(buf).strip()
        buf.clear()
        if word:
            cur.text = f"{cur.text} {word}".strip()

    def finish_item():
        nonlocal cur
        take_buf()
        if cur.text or cur.kids:
            stack[-1][0].kids.append(cur)
        cur = _Raw()

    for ch in s:
        if ch in OPEN:
            take_buf()
            stack.append((cur, OPEN[ch]))
            cur = _Raw()
        elif ch in CLOSE:
            if len(stack) == 1:
                repairs += 1          # 연 적 없는 닫는 괄호는 무시
                continue
            if stack[-1][1] != ch:
                repairs += 1          # 짝이 다르면 가장 가까운 괄호를 닫은 것으로 본다
            finish_item()
            cur, _ = stack.pop()
        elif ch in SEPARATORS:
            finish_item()
        else:
            buf.append(ch)
    while len(stack) > 1:             # 끝까지 안 닫힌 괄호
        repairs += 1
        finish_item()
        cur, _ = stack.pop()
    finish_item()
    return root.kids, repairs


def _group_top(items):
    """맨 위 항목에 '면:' '스프/' 머리말이 있으면 다음 머리말이 나올 때까지 그 아래로 묶는다."""
    out, current = [], None
    for item in items:
        m = GROUP_RE.match(item.text)
        if m and is_origin(clean_name(m.group(2))):
            m = None                  # '소스:일본산(...)'의 콜론 뒤는 원산지라 머리말이 아님
        if m:
            current = _Raw(text=m.group(1), group=True)
            out.append(current)
            rest = _Raw(text=m.group(2), kids=item.kids)
            if rest.text.strip() or rest.kids:
                current.kids.append(rest)
        elif current is not None:
            current.kids.append(item)
        else:
            out.append(item)
    return out


def _build(raws):
    """임시 노드를 정리된 Node로 바꾼다. 이름이 원산지뿐인 노드는 빼고 자식만 올린다."""
    nodes = []
    for r in raws:
        kids = _build(r.kids)
        raw = r.text.strip()
        if r.group:
            nodes.append(Node(name=raw, raw=raw, children=kids, group=True))
            continue
        pieces = split_pieces(r.text)
        if not pieces:
            nodes.extend(kids)
            continue
        for p in pieces[:-1]:
            nodes.append(Node(name=p, raw=raw))
        nodes.append(Node(name=pieces[-1], raw=raw, children=kids))
    return tuple(nodes)


def parse_tree(text):
    """원재료 글자 -> (Node 나무, 괄호 복구 횟수)."""
    s = _LEAD_RE.sub("", normalize(text))
    items, repairs = _parse_brackets(mark_groups(s))
    return _build(_group_top(items)), repairs


def mentions(nodes, depth=0, parent=""):
    """(이름, 깊이, 부모 이름, 잎인가)를 위에서부터 차례로. 구성품 머리말은 건너뛴다."""
    out = []
    for n in nodes:
        if n.group:
            out.extend(mentions(n.children, depth, parent))
            continue
        out.append((n.name, depth, parent, not n.children))
        out.extend(mentions(n.children, depth + 1, n.name))
    return out
