"""(내부 구현) OpenSesame 원재료명 괄호 파서.

원재료명 문자열 -> 성분 트리(dict).
    from src.parser.core import parse
    result = parse("소맥분(밀:미국산), 혼합제제(정제수, 프로필렌글리콜), 대두, 밀 함유")

반환 형식 (통합용 계약):
{
  "ingredients": [Node, ...],     # 최상위 성분들
  "kr_declared": ["대두", "밀"],   # '○○ 함유' 표시란 (한국 기준)
  "raw": "...원문..."
}
Node = {
  "name": "혼합제제",              # 성분 이름
  "aliases": ["어육"],             # '연육/어육'처럼 / 로 묶인 다른 이름
  "meta": {"origin": [...], "purpose": [...], "ratio": [...]},
  "children": [Node, ...]          # 괄호 속 하위 원재료
}
"""
import re
import json

OPEN_TO_CLOSE = {"(": ")", "（": "）", "[": "]", "［": "］", "{": "}", "｛": "｝"}
CLOSERS = set(OPEN_TO_CLOSE.values())
SEPARATORS = {",", "，", "、"}

# 한국 의무 표시 항목 이름 (함유 표시란 추출용)
KR_ALLERGENS = {
    "알류", "난류", "계란", "달걀", "우유", "메밀", "땅콩", "대두", "밀", "고등어", "게", "새우",
    "돼지고기", "복숭아", "토마토", "아황산류", "호두", "닭고기", "쇠고기", "오징어", "조개류",
    "굴", "전복", "홍합", "잣",
}

# 괄호 안이 '용도'를 뜻하는 단어 (하위 원재료가 아님)
PURPOSE_WORDS = {
    "산도조절제", "향미증진제", "유화제", "보존료", "감미료", "착색료", "합성향료", "천연향료",
    "증점제", "안정제", "산화방지제", "팽창제", "표백제", "발색제", "소포제", "영양강화제",
    "피막제", "응고제", "젤형성제", "습윤제", "향료", "착향료",
}

# 원산지로 보는 나라·지역 이름. '한글+산'을 모두 원산지로 보면 구연산·젖산 같은 원재료가 사라지므로 목록으로 판단한다.
PLACES = {
    "국내", "제주", "강원", "경기", "충북", "충남", "전북", "전남", "경북", "경남",
    "미국", "캐나다", "멕시코", "브라질", "아르헨티나", "칠레", "페루", "에콰도르", "콜롬비아", "파라과이", "우루과이",
    "호주", "뉴질랜드", "중국", "일본", "대만", "홍콩", "베트남", "태국", "말레이시아", "인도네시아", "필리핀",
    "미얀마", "캄보디아", "라오스", "싱가포르", "인도", "파키스탄", "스리랑카", "방글라데시", "몽골",
    "러시아", "우크라이나", "카자흐스탄", "헝가리", "루마니아", "불가리아", "폴란드", "체코", "슬로바키아",
    "오스트리아", "독일", "프랑스", "덴마크", "네덜란드", "벨기에", "룩셈부르크", "영국", "아일랜드", "스페인",
    "포르투갈", "이탈리아", "그리스", "스위스", "스웨덴", "노르웨이", "핀란드", "아이슬란드", "세르비아", "크로아티아",
    "터키", "튀르키예", "이스라엘", "이란", "이집트", "모로코", "남아공", "남아프리카공화국", "가나", "코트디부아르",
    "나이지리아", "케냐", "에티오피아", "탄자니아", "마다가스카르", "우간다", "유럽",
}
ORIGIN_RE = re.compile(r"^(국산|외국산|수입산|(" + "|".join(sorted(PLACES, key=len, reverse=True)) + r")산)$")
RATIO_RE = re.compile(r"^\d+(\.\d+)?\s*%$")


def _normalize(text: str) -> str:
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"^\s*(원재료명|원료명|원재료)(\s*및\s*함량)?\s*[:：]?\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def split_top(text: str, seps) -> list:
    """괄호 깊이 0인 위치의 구분자로만 자른다."""
    parts, buf, stack = [], [], []
    for ch in text:
        if ch in OPEN_TO_CLOSE:
            stack.append(OPEN_TO_CLOSE[ch])
        elif ch in CLOSERS and stack:  # 괄호 종류가 OCR에서 바뀌어도 깊이만 맞춘다
            stack.pop()
        if ch in seps and not stack:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _bracket_groups(item: str):
    """'이름(A)(B)' -> ('이름', ['A', 'B'], 괄호 뒤 꼬리 텍스트)."""
    name, groups, tail = [], [], []
    i, n = 0, len(item)
    while i < n:
        ch = item[i]
        if ch in OPEN_TO_CLOSE:
            stack, j = [OPEN_TO_CLOSE[ch]], i + 1
            while j < n and stack:
                c = item[j]
                if c in OPEN_TO_CLOSE:
                    stack.append(OPEN_TO_CLOSE[c])
                elif c in CLOSERS:  # 종류 무관, 깊이만
                    stack.pop()
                j += 1
            groups.append(item[i + 1 : j - 1] if not stack else item[i + 1 :])
            i = j
        else:
            (tail if groups else name).append(ch)
            i += 1
    return "".join(name).strip(), groups, "".join(tail).strip()


def _is_origin_text(s: str) -> bool:
    s = s.strip()
    head = split_top(s, {":", "："})[0].strip()
    head_name, _, _ = _bracket_groups(head)
    if ORIGIN_RE.match(head_name):
        return True
    words = [re.sub(r"\s*등$", "", w.strip()) for w in split_top(s, SEPARATORS)]
    return bool(words) and all(not w or ORIGIN_RE.match(w) or w in PLACES for w in words)


def _new_node(name):
    return {"name": name, "aliases": [], "meta": {"origin": [], "purpose": [], "ratio": []}, "children": []}


def _apply_group(node, content: str):
    content = content.strip()
    if not content:
        return
    if RATIO_RE.match(content):
        node["meta"]["ratio"].append(content)
        return
    if content in PURPOSE_WORDS:
        node["meta"]["purpose"].append(content)
        return
    if _is_origin_text(content):
        node["meta"]["origin"].append(content)
        return
    # '게:국산' -> 하위 원재료 '게'(원산지 국산)
    colon = split_top(content, {":", "："})
    if len(colon) == 2 and "," not in colon[0] and _is_origin_text(colon[1]):
        child = _new_node(colon[0].strip())
        child["meta"]["origin"].append(colon[1].strip())
        node["children"].append(child)
        return
    node["children"].extend(parse_list(content))


def parse_item(item: str):
    alts = split_top(item, {"/"})
    main = alts[0]
    name, groups, tail = _bracket_groups(main)
    m = re.search(r"\s*(\d+(?:\.\d+)?\s*%)$", name)
    if m:  # '아몬드분말 5%'
        name = name[: m.start()].strip()
    node = _new_node(name)
    if m:
        node["meta"]["ratio"].append(m.group(1).replace(" ", ""))
    for g in groups:
        _apply_group(node, g)
    if tail:  # '정제소금 (국산) 1%' 같은 꼬리 텍스트
        if RATIO_RE.match(tail):
            node["meta"]["ratio"].append(tail)
        else:
            node["name"] = (node["name"] + " " + tail).strip()
    for a in alts[1:]:
        if _is_origin_text(a):  # '대두유/외국산', '밀/미국산' -> 원산지
            node["meta"]["origin"].append(a.strip())
            continue
        a_name, a_groups, _ = _bracket_groups(a)
        node["aliases"].append(a_name)
        for g in a_groups:
            _apply_group(node, g)
    return node


def parse_list(text: str):
    nodes = []
    for p in split_top(text, SEPARATORS):
        # '밀/미국산, 캐나다산': 원산지 나열이 쉼표로 이어진 것 -> 앞 원재료의 원산지에 붙인다
        if nodes and nodes[-1]["meta"]["origin"] and _is_origin_text(p):
            nodes[-1]["meta"]["origin"].append(p.strip())
            continue
        nodes.append(parse_item(p))
    return nodes


def extract_declared(text: str):
    """끝부분의 '대두, 밀, 게 함유' -> (['대두','밀','게'], 나머지 텍스트)."""
    m = re.search(r"함유\s*$", text)
    if not m:
        return [], text
    before = text[: m.start()].rstrip()
    tokens = re.split(r"(\s*[,，·、]\s*|\s+)", before)
    declared, cut = [], len(before)
    # 오른쪽부터 한국 표시 항목 이름만 떼어 낸다
    pos = len(before)
    for tok in reversed(tokens):
        pos -= len(tok)
        t = tok.strip(" ,，·、")
        if not t:
            continue
        if t in KR_ALLERGENS:
            declared.insert(0, t)
            cut = pos
        else:
            break
    rest = before[:cut].rstrip(" ,，·、")
    return declared, rest


def parse(text: str) -> dict:
    raw = text
    text = _normalize(text)
    declared, body = extract_declared(text)
    return {"ingredients": parse_list(body), "kr_declared": declared, "raw": raw}


def check_brackets(text: str) -> bool:
    """괄호 짝이 맞는지 (OCR 결과 검사용)."""
    stack = []
    for ch in text:
        if ch in OPEN_TO_CLOSE:
            stack.append(OPEN_TO_CLOSE[ch])
        elif ch in CLOSERS:
            if not stack or stack.pop() != ch:
                return False
    return not stack


def flatten(nodes, depth=0):
    """트리를 (깊이, 이름) 목록으로 펼친다. 알레르겐 분류 단계에 넘길 때 사용."""
    out = []
    for nd in nodes:
        out.append((depth, nd["name"]))
        for a in nd["aliases"]:
            out.append((depth, a))
        out.extend(flatten(nd["children"], depth + 1))
    return out


def pretty(nodes, indent=0) -> str:
    lines = []
    for nd in nodes:
        meta = []
        for k, label in (("origin", "원산지"), ("purpose", "용도"), ("ratio", "비율")):
            if nd["meta"][k]:
                meta.append(f"{label}: {'; '.join(nd['meta'][k])}")
        alias = f" (= {', '.join(nd['aliases'])})" if nd["aliases"] else ""
        extra = f"  [{' | '.join(meta)}]" if meta else ""
        lines.append("  " * indent + "- " + nd["name"] + alias + extra)
        if nd["children"]:
            lines.append(pretty(nd["children"], indent + 1))
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    t = sys.stdin.read() if not sys.argv[1:] else " ".join(sys.argv[1:])
    r = parse(t)
    print(pretty(r["ingredients"]))
    print("한국 함유 표시:", r["kr_declared"])
