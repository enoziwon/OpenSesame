"""라벨 글자를 원재료 / 알레르기 표시란 / 같은 시설 문구로 나눈다."""
import re
from dataclasses import dataclass
from typing import Optional

from .names import AMOUNT_RE
from .tree import normalize

# 한국 표시란에 나오는 이름과 흔한 다른 이름. 표시란인지 알아보는 데만 쓴다.
KR_ALLERGEN_WORDS = frozenset({
    "알류", "난류", "가금류", "계란", "달걀", "우유", "메밀", "땅콩", "대두", "콩", "밀", "고등어", "게",
    "새우", "돼지고기", "복숭아", "토마토", "아황산류", "아황산", "아황산염", "호두", "닭고기", "쇠고기",
    "소고기", "오징어", "조개류", "조개", "굴", "전복", "홍합", "잣", "참깨", "들깨", "아몬드", "캐슈너트",
    "메추리알", "오리알",
})
SULFITE_RE = re.compile(r"(아황산|이산화황)")        # 아황산나트륨, 이산화황 등은 한국 표시 대상 '아황산류'
# 표시란에서만 표시란 낱말로 읽는 다른 표기 -> 표준 낱말. 원재료 구역에서는 그대로 원재료다.
# 글자 입력의 '…, 밀가루, 대두 함유'처럼 원재료 끝과 헷갈리는 곳(함유 앞 목록)에서는 읽지 않는다.
DECL_ALIASES = {"밀가루": "밀"}
NO_INFO = {"알수없음", "알 수 없음", "-", "", "None", "none", "null"}   # API에 표시란 정보가 없다는 뜻
# 표시란은 있는데 적힌 알레르기가 없음: '해당없음', '알러지유발식품없음', '알레르기 유발물질: 해당 없음'
_NONE_HEAD = r"[\[【(<]?\s*(?:알레르기|알러지)\s*(?:유발)?\s*(?:식품|물질|성분)?\s*(?:표시|정보)?\s*[\]】)>]?\s*:?\s*"
_NONE_TAIL = r"(?:해당\s*(?:사항\s*)?)?없음"
NONE_DECLARED_RE = re.compile(rf"^(?:{_NONE_HEAD})?{_NONE_TAIL}\.?$")     # 칸 입력 (값 전체)
NONE_BOX_RE = re.compile(rf"{_NONE_HEAD}{_NONE_TAIL}(?![가-힣])")         # 글자 입력 (머리말이 있어야 한다)

LIST_SEPS = ",·ㆍᆞ・、/"
BOUNDARY_RE = re.compile(r"[。※\x00]|\.(?!\d)")       # 문장 끝. '1.8'의 점은 아님
START_RE = re.compile(r"원재료\s*명?\s*(?:및\s*함량)?\s*[\]】:]?\s*")
STOP_RE = re.compile(
    r"(내용량|소비기한|유통기한|보관\s*방법|품목\s*(?:제조\s*)?보고\s*번호|제조원|판매원|제조사|수입원"
    r"|영양\s*정보|영양\s*성분|반품|부정\s*[·ㆍ]?\s*불량|포장\s*재질|주의\s*사항|※|\x00)"
)
# 같은 시설 문구: '이 제품은 … 같은 … 시설' 뒤 문구가 끝나는 말까지. 마침표 없이 이어지는 원재료는 먹지 않는다.
#   1) '…제조하고 있습니다.', '…혼입될 수 있음' (150자 안에서. '조개류(굴, 전복)' 같은 괄호 묶음은 넘는다)
#   2) '…시설에서 우유, 대두를 사용한 제품을 제조'처럼 끝말이 없으면 '사용한 제품…' 낱말까지
#   3) '…시설에서 제조, 간장'처럼 제조·생산 뒤에 쉼표가 오면 거기까지
#   4) 모두 없으면 첫 쉼표·마침표까지
_FAC_SPAN = r"(?:[^.。()\[\]{}]|\([^().。]*\)|\[[^\[\].。]*\])"
FACILITY_RE = re.compile(
    r"(?:이|본)\s*제품은[^.。]*?(?:같은|동일한?)[^.。]*?(?:시설|공장|라인)"
    rf"(?:{_FAC_SPAN}{{0,150}}?(?:니다|있음|었음|였음|됨|(?:제조|생산|가공|사용|포장)함)(?![가-힣])\s*[.。]?"
    rf"|{_FAC_SPAN}{{0,150}}?사용한\s*제품[^.。,]*"
    r"|[^.。,]*?(?:제조|생산|가공|포장)(?=\s*(?:,|$))"
    r"|[^.。,]*[.。]?)"
)
DECL_HEAD_RE = re.compile(r"알레르기\s*(?:유발)?\s*(?:물질|성분)?\s*(?:표시|정보)?\s*:")
DECL_PREFIX_RE = re.compile(r"[\[【(<]?\s*알레르기\s*(?:유발)?\s*(?:물질|성분)?\s*(?:표시|정보)?\s*[\]】)>:]?\s*$")
# 표시란 칸 항목 끝의 군말: '대두 포함', '우유 제품', '땅콩 첨가제품', '밀함유식품', '대두-유래원재료 함유'
FIELD_TAIL_RE = re.compile(r"(?:[\s\-]*(?:유래\s*원재료|함유\s*식품|첨가\s*제품|제품|함유|포함|등))+\s*$")
FIELD_END_RE = re.compile(r"(?:을|를)?\s*(?:함유|포함)(?:하고|되어)?\s*(?:있습니다|있음|합니다|됨|함)\s*$")
# 원재료 끝에 붙은 안내(원재료가 아님): '※특정성분 함량 및 원산지: …', '*특정성분: …', '※스프 중 건조오징어 2.3%', '※한우총함량 11%'
NOTE_RE = re.compile(r"(?:※|[*•·])\s*(?:특정\s*성분|[가-힣]*총\s*함량|[가-힣]*(?:스프|소스)류?\s*중)")
JOSA_RE = re.compile(r"(?:을|를|이|가|은|는|과|와|의|에|도)(?![가-힣])")
OPENS, CLOSES = "([{<〈《【「『", ")]}>〉》】」』"


@dataclass(frozen=True)
class Zones:
    ingredients_text: str
    declaration_text: Optional[str]   # 표시란 원문. 못 찾으면 None
    declared: tuple                   # 표시란 항목 ('밀', '대두')
    facility_text: Optional[str]      # 같은 시설 문구. 판정에는 쓰지 않는다


def _depths(s):
    """글자마다 괄호 깊이. 끝까지 닫히지 않는 여는 괄호(깨진 라벨)는 세지 않는다."""
    stack, closed = [], set()
    for i, ch in enumerate(s):
        if ch in OPENS:
            stack.append(i)
        elif ch in CLOSES and stack:
            closed.add(stack.pop())
    out, depth = [], 0
    for i, ch in enumerate(s):
        if ch in OPENS and i in closed:
            depth += 1
        elif ch in CLOSES:
            depth = max(0, depth - 1)
        out.append(depth)
    return out


def _split_top(s, seps):
    """괄호 밖의 구분자로만 나눈다. [(조각, 시작 위치)]"""
    parts, start = [], 0
    for i, depth in enumerate(_depths(s)):
        if depth == 0 and s[i] in seps:
            parts.append((s[start:i], start))
            start = i + 1
    parts.append((s[start:], start))
    return parts


def _depth_at(s, pos):
    return _depths(s)[pos - 1] if pos > 0 else 0


def _strip_mark(word):
    return re.sub(r"^[^가-힣A-Za-z]+", "", word.strip())    # '●새우' -> '새우'


def _base(item):
    """표시란 항목의 이름만: '●새우' -> '새우', '조개류(굴, 전복)' -> '조개류', '대두[d-토코페롤]' -> '대두'"""
    base = re.sub(r"[(\[{].*$", "", _strip_mark(item))
    return re.sub(r"[^가-힣A-Za-z]+$", "", base)          # '우유*' -> '우유'


def _box_word(item, aliases=False):
    """표시란 낱말이면 그 낱말, 아니면 ''. aliases면 다른 표기도 표준 낱말로 받는다('밀가루' -> '밀').

    함량이 붙은 것('오징어11%(생물기준) 함유')은 함량 문구라 표시란 낱말이 아니다.
    """
    if re.search(r"\d", re.sub(r"[(\[{].*$", "", _strip_mark(item))):
        return ""
    base = _base(item)
    if base in KR_ALLERGEN_WORDS or SULFITE_RE.search(base):
        return base
    return DECL_ALIASES.get(base, "") if aliases else ""


def _is_allergen(item):
    return bool(_box_word(item))


def _allergens_in(item, aliases=False):
    """'소맥분(밀)'처럼 원재료(알레르기) 짝으로 적은 목록에서 알레르기 이름을 꺼낸다."""
    word = _box_word(item, aliases)
    if word:
        return [word]
    inner = re.findall(r"[(\[{]([^()\[\]{}]+)[)\]}]", item)
    words = (_box_word(w, aliases) for part in inner for w in part.split(","))
    return [w for w in words if w]


def _tokens(piece):
    """괄호 밖 띄어쓰기로 나눈 낱말들. [(낱말, 시작 위치)]

    닫는 괄호 바로 뒤에 붙은 낱말도 나눈다('혼합제제(…)대두'). 조사는 떼지 않는다('조개류(굴 포함)를').
    """
    toks, start = [], 0
    for i, depth in enumerate(_depths(piece)):
        if depth > 0:
            continue
        rest = piece[i + 1:]
        if piece[i] == " ":
            toks.append((piece[start:i], start))
            start = i + 1
        elif piece[i] in CLOSES and re.match(r"[가-힣]", rest) and not JOSA_RE.match(rest):
            toks.append((piece[start:i + 1], start))
            start = i + 1
    toks.append((piece[start:], start))
    return [(t, off) for t, off in toks if t]


def _allergen_run(toks, aliases=False):
    """낱말들 끝에서부터 표시란 낱말이 이어진 만큼: '복합조미식품 우유 밀 대두' -> 우유, 밀, 대두.

    가운데의 '및'은 건너뛴다. (표시란 낱말 [(낱말, 위치)], 첫 표시란 낱말의 순번)
    """
    run, k = [], len(toks)
    for i in range(len(toks) - 1, -1, -1):
        word = toks[i][0]
        if _box_word(word, aliases):
            run.insert(0, toks[i])
            k = i
        elif word != "및" or not run:
            break
    return run, k


def _items_before(s, end):
    """end('함유') 앞에서 알레르기 이름을 오른쪽부터 모은다. (첫 항목 위치, 항목들) 또는 None."""
    seg_start = max((m.end() for m in BOUNDARY_RE.finditer(s, 0, end)), default=0)
    items, first = [], None
    for piece, off in reversed(_split_top(s[seg_start:end], LIST_SEPS)):
        if not piece.strip() and not items:
            continue                  # '대두,밀,함유'처럼 '함유' 앞에 쉼표가 있다
        piece = re.sub(r"\s*등\s*$", "", piece)
        run, k = _allergen_run(_tokens(piece))
        if not run:
            break
        items[:0] = [_base(word) for word, _ in run]
        word, woff = run[0]
        first = seg_start + off + woff + (len(word) - len(_strip_mark(word)))    # 앞 기호(●)는 빼고 시작
        if k > 0:                     # 앞에 다른 낱말이 붙어 있으면 표시란은 여기서 시작
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
        word = _box_word(re.sub(r"\s*등\s*$", "", piece).strip(), aliases=True)    # 머리말 뒤라 '밀가루'도 읽는다
        if not word:
            break
        items.append(word)
        end = h.end() + off + len(piece.rstrip())
    return (h.start(), h.end(), end, items) if items else None


def find_declaration(s):
    """(잘라낼 시작, 항목 시작, 끝, 항목들) 또는 None."""
    return _find_with_suffix(s) or _find_with_head(s)


def _cut(s, start, end, filler):
    """s[start:end]를 지운다. 글자 입력(filler='\\x00')은 구역을 끊고, 칸 입력(filler=', ')은 앞뒤를 잇는다."""
    if filler == "\x00":
        return s[:start] + filler + s[end:]
    left, right = s[:start].rstrip(" ,"), s[end:].lstrip(" ,.")
    return left + (filler if left and right else "") + right


def _cut_facility(s, text_mode):
    """같은 시설 문구를 떼어 낸다. (남은 글자, 문구 원문 또는 None)

    칸 입력은 앞뒤 원재료를 잇는다. 사진 글자는 문구 뒤가 쉼표로 이어질 때('…제조, 간장')만 잇고,
    문장으로 끝나면 원재료 구역도 거기서 끝낸다(뒤에 오는 안내문을 원재료로 읽지 않게).
    """
    found = list(FACILITY_RE.finditer(s))
    for m in reversed(found):
        goes_on = s[m.end():].lstrip().startswith(",")
        s = _cut(s, m.start(), m.end(), "\x00" if text_mode and not goes_on else ", ")
    return s, " ".join(m.group(0).strip() for m in found) or None


def _take_box(s, filler):
    """글자에서 표시란을 찾아 떼어 낸다. (남은 글자, 표시란 원문, 항목들) 또는 None.

    '…, 밀, 대두 함유' 꼴과 '알레르기 유발물질: 밀, 대두' 꼴을 먼저 보고,
    없으면 '알레르기 유발물질: 해당없음'처럼 비어 있는 표시란을 본다(항목은 ()).
    """
    found = find_declaration(s)
    if found:
        cut, first, end, items = found
        return _cut(s, cut, end, filler), s[first:end].strip(), tuple(items)
    empty = list(NONE_BOX_RE.finditer(s))
    if empty:
        m = empty[-1]
        return _cut(s, m.start(), m.end(), filler), m.group(0).strip(), ()
    return None


def _cut_note(s):
    """원재료 끝에 붙은 '※특정성분 함량 및 원산지: …' 같은 안내를 끝까지 떼어 낸다(괄호 속이면 두다)."""
    for m in NOTE_RE.finditer(s):
        if _depth_at(s, m.start()) == 0:
            return s[:m.start()].rstrip(" ,/")
    return s


def _ingredients_zone(s):
    m = START_RE.search(s)
    body = s[m.end():] if m else s
    stop = STOP_RE.search(body)
    if stop:
        body = body[:stop.start()]
    return _cut_note(body).strip(" ,/.")


def split_zones(text):
    """사진에서 읽은 라벨 글자 전체를 구역으로 나눈다."""
    s, facility = _cut_facility(normalize(text), True)
    decl_text, declared = None, ()
    taken = _take_box(s, "\x00")
    if taken:
        s, decl_text, declared = taken
    return Zones(_ingredients_zone(s), decl_text, declared, facility)


def _field_words(d):
    """표시란 칸을 항목마다 읽는다: 함량과 끝의 '함유·포함·제품…'을 떼고 끝에서부터 표시란 낱말을 모은다.

    '대두 포함' -> 대두, '밀 40.3% 함유' -> 밀, '대두.우유' -> 대두, 우유, '밀가루' -> 밀. 표시란 낱말이 아니면('생선') 읽지 않는다.
    """
    d = re.sub(r"(?<!\d)\.|\.(?!\d)", ",", AMOUNT_RE.sub(" ", d))
    words = []
    for item, _ in _split_top(d, LIST_SEPS):
        x = FIELD_TAIL_RE.sub("", FIELD_END_RE.sub("", item)).strip()
        run, _ = _allergen_run(_tokens(x), aliases=True)     # 끝 낱말들: '이 제품은 … 유발물질인 대두', '대두 밀'
        words.extend(_allergens_in(x, aliases=True) + [_box_word(w, True) for w, _ in run])   # 앞 낱말·괄호 속도
    return words


def read_field(declaration):
    """표시란 칸 값 -> (표시란 원문 또는 None, 항목들). 못 읽으면 (None, ())."""
    d = normalize(declaration or "")
    if d in NO_INFO:
        return None, ()
    if NONE_DECLARED_RE.match(d):
        return d, ()                   # 표시란은 있는데 적힌 알레르기가 없음
    body, _ = _cut_facility(d, False)  # 같은 시설 문구의 낱말은 표시란이 아니다
    found = find_declaration(body)
    words = []
    for word in _field_words(body) + (found[3] if found else []):
        if word not in words:
            words.append(word)
    return (d if words else None), tuple(words)


def zones_from_fields(ingredients, declaration=None):
    """HACCP API처럼 원재료와 표시란이 따로 온 경우.

    원재료 칸의 같은 시설 문구는 떼어 facility_text에 담는다. 표시란 칸이 비었으면('알수없음')
    원재료 칸에 적힌 표시란('…, 밀, 대두 함유')을 찾아 떼어 표시란으로 쓴다. 끝의 '※특정성분…' 안내는 버린다.
    """
    body, facility = _cut_facility(normalize(ingredients or ""), False)
    decl_text, declared = read_field(declaration)
    if decl_text is None:
        taken = _take_box(body, ", ")
        if taken:
            body, decl_text, declared = taken
    return Zones(_cut_note(body), decl_text, declared, facility)
