"""라벨 글자를 원재료 / 알레르기 표시란 / 같은 시설 문구로 나눈다."""
import re
from dataclasses import dataclass

from .tree import normalize

# 한국 표시란에 나오는 이름과 흔한 다른 이름. 표시란인지 알아보는 데만 쓴다.
KR_ALLERGEN_WORDS = frozenset({
    "알류", "난류", "가금류", "계란", "달걀", "우유", "메밀", "땅콩", "대두", "콩", "밀", "고등어", "게",
    "새우", "돼지고기", "복숭아", "토마토", "아황산류", "아황산", "아황산염", "호두", "닭고기", "쇠고기",
    "소고기", "오징어", "조개류", "굴", "전복", "홍합", "잣", "참깨", "들깨", "아몬드", "캐슈너트",
    "메추리알", "오리알",
})
SULFITE_RE = re.compile(r"(아황산|이산화황)")        # 아황산나트륨, 이산화황 등은 한국 표시 대상 '아황산류'
NO_INFO = {"알수없음", "알 수 없음", "-", "", "None", "none", "null"}   # API에 표시란 정보가 없다는 뜻
NONE_DECLARED_RE = re.compile(r"^(?:(?:알레르기|알러지)\s*(?:유발)?\s*(?:식품|물질|성분)?\s*)?(?:해당\s*)?없음$")

LIST_SEPS = ",·ㆍᆞ・、/"
BOUNDARY_RE = re.compile(r"[。※\x00]|\.(?!\d)")       # 문장 끝. '1.8'의 점은 아님
START_RE = re.compile(r"원재료\s*명?\s*(?:및\s*함량)?\s*[\]】:]?\s*")
STOP_RE = re.compile(
    r"(내용량|소비기한|유통기한|보관\s*방법|품목\s*(?:제조\s*)?보고\s*번호|제조원|판매원|제조사|수입원"
    r"|영양\s*정보|영양\s*성분|반품|부정\s*[·ㆍ]?\s*불량|포장\s*재질|주의\s*사항|※|\x00)"
)
FACILITY_RE = re.compile(r"(?:이|본)\s*제품은[^.。]*?(?:같은|동일한?)[^.。]*?(?:시설|공장|라인)[^.。]*(?:[.。]|$)")
DECL_HEAD_RE = re.compile(r"알레르기\s*(?:유발)?\s*(?:물질|성분)?\s*(?:표시|정보)?\s*:")
DECL_PREFIX_RE = re.compile(r"[\[【(<]?\s*알레르기\s*(?:유발)?\s*(?:물질|성분)?\s*(?:표시|정보)?\s*[\]】)>:]?\s*$")


@dataclass(frozen=True)
class Zones:
    ingredients_text: str
    declaration_text: str | None      # 표시란 원문. 못 찾으면 None
    declared: tuple                   # 표시란 항목 ('밀', '대두')
    facility_text: str | None         # 같은 시설 문구. 판정에는 쓰지 않는다


def _split_top(s, seps):
    """괄호 밖의 구분자로만 나눈다. [(조각, 시작 위치)]"""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(s):
        if ch in "([{<〈《【「『":
            depth += 1
        elif ch in ")]}>〉》】」』":
            depth = max(0, depth - 1)
        elif depth == 0 and ch in seps:
            parts.append((s[start:i], start))
            start = i + 1
    parts.append((s[start:], start))
    return parts


def _depth_at(s, pos):
    depth = 0
    for ch in s[:pos]:
        if ch in "([{<〈《【「『":
            depth += 1
        elif ch in ")]}>〉》】」』":
            depth = max(0, depth - 1)
    return depth


def _strip_mark(word):
    return re.sub(r"^[^가-힣A-Za-z]+", "", word.strip())    # '●새우' -> '새우'


def _base(item):
    """표시란 항목의 이름만: '●새우' -> '새우', '조개류(굴, 전복)' -> '조개류', '대두[d-토코페롤]' -> '대두'"""
    base = re.sub(r"[(\[{].*$", "", _strip_mark(item))
    return re.sub(r"[^가-힣A-Za-z]+$", "", base)          # '우유*' -> '우유'


def _is_allergen(item):
    base = _base(item)
    return base in KR_ALLERGEN_WORDS or bool(SULFITE_RE.search(base))


def _allergens_in(item):
    """'소맥분(밀)'처럼 원재료(알레르기) 짝으로 적은 목록에서 알레르기 이름을 꺼낸다."""
    if _is_allergen(item):
        return [_base(item)]
    inner = re.findall(r"[(\[{]([^()\[\]{}]+)[)\]}]", item)
    return [_base(w) for part in inner for w in part.split(",") if _is_allergen(w)]


def _tokens(piece):
    """괄호 밖 띄어쓰기로 나눈 낱말들. [(낱말, 시작 위치)]"""
    return [(t, off) for t, off in _split_top(piece, " ") if t]


def _items_before(s, end):
    """end('함유') 앞에서 알레르기 이름을 오른쪽부터 모은다. (첫 항목 위치, 항목들) 또는 None."""
    seg_start = max((m.end() for m in BOUNDARY_RE.finditer(s, 0, end)), default=0)
    items, first = [], None
    for piece, off in reversed(_split_top(s[seg_start:end], LIST_SEPS)):
        piece = re.sub(r"\s*등\s*$", "", piece)
        toks = _tokens(piece)
        if not toks or not _is_allergen(toks[-1][0]):
            break
        word, woff = toks[-1]
        items.insert(0, _base(word))
        first = seg_start + off + woff + (len(word) - len(_strip_mark(word)))    # 앞 기호(●)는 빼고 시작
        if len(toks) > 1:             # 앞에 다른 낱말이 붙어 있으면 표시란은 여기서 시작
            break
    return (first, items) if items else None


def _find_with_suffix(s):
    """'밀, 대두 함유' 꼴. 괄호 안의 '함유'는 원재료 설명이라 건너뛴다."""
    for m in reversed(list(re.finditer(r"함유", s))):
        if _depth_at(s, m.start()) > 0:
            continue
        found = _items_before(s, m.start())
        if found:
            first, items = found
            head = DECL_PREFIX_RE.search(s[:first])
            cut = head.start() if head else first
            return cut, first, m.end(), items
    return None


def _find_with_head(s):
    """'알레르기 유발물질: 밀, 대두' 꼴('함유'가 없음)."""
    heads = list(DECL_HEAD_RE.finditer(s))
    if not heads:
        return None
    h = heads[-1]
    tail = s[h.end():]
    stops = [m.start() for m in (BOUNDARY_RE.search(tail), STOP_RE.search(tail)) if m]
    tail_end = min(stops) if stops else len(tail)
    items, end = [], h.end()
    for piece, off in _split_top(tail[:tail_end], LIST_SEPS):
        word = re.sub(r"\s*등\s*$", "", piece).strip()
        if not _is_allergen(word):
            break
        items.append(_base(word))
        end = h.end() + off + len(piece.rstrip())
    return (h.start(), h.end(), end, items) if items else None


def find_declaration(s):
    """(잘라낼 시작, 항목 시작, 끝, 항목들) 또는 None."""
    return _find_with_suffix(s) or _find_with_head(s)


def _ingredients_zone(s):
    m = START_RE.search(s)
    body = s[m.end():] if m else s
    stop = STOP_RE.search(body)
    if stop:
        body = body[:stop.start()]
    return body.strip(" ,/.")


def split_zones(text):
    """사진에서 읽은 라벨 글자 전체를 구역으로 나눈다."""
    s = normalize(text)
    facility = [m.group(0).strip() for m in FACILITY_RE.finditer(s)]
    s = FACILITY_RE.sub("\x00", s)
    decl_text, declared = None, ()
    found = find_declaration(s)
    if found:
        cut, first, end, items = found
        decl_text, declared = s[first:end].strip(), tuple(items)
        s = s[:cut] + "\x00" + s[end:]
    return Zones(_ingredients_zone(s), decl_text, declared, " ".join(facility) or None)


def zones_from_fields(ingredients, declaration=None):
    """HACCP API처럼 원재료와 표시란이 따로 온 경우."""
    d = normalize(declaration or "")
    if d in NO_INFO:
        decl_text, declared = None, ()
    elif NONE_DECLARED_RE.match(d.replace(" ", "")):
        decl_text, declared = d, ()    # 표시란은 있는데 적힌 알레르기가 없음
    else:
        found = find_declaration(d)
        if found:
            declared = tuple(found[3])
        else:                          # '밀, 대두'나 '소맥분(밀),탈지대두(대두)'처럼 목록만 온 경우
            declared = tuple(w for item, _ in _split_top(d, LIST_SEPS) for w in _allergens_in(item))
        decl_text = d if declared else None
    return Zones(normalize(ingredients or ""), decl_text, declared, None)
