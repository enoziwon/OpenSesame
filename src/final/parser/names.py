"""원재료 이름 정리: 함량·원산지·관리 번호를 걷어내고, 면·스프 같은 구성품 머리말을 알아본다."""
import re

COUNTRIES = (
    "미국", "호주", "캐나다", "중국", "베트남", "태국", "인도네시아", "말레이시아", "필리핀", "브라질",
    "독일", "덴마크", "프랑스", "네덜란드", "뉴질랜드", "러시아", "스페인", "이탈리아", "터키", "튀르키예",
    "칠레", "일본", "대만", "인도", "벨기에", "폴란드", "아르헨티나", "영국", "노르웨이", "페루", "멕시코",
    "미얀마", "이스라엘", "우크라이나", "스리랑카", "불가리아", "헝가리", "오스트리아", "스위스", "핀란드",
    "아일랜드", "에콰도르", "파키스탄", "이집트", "남아공", "스웨덴", "포르투갈", "그리스", "몽골",
    "싱가포르", "싱가폴", "콜롬비아", "세르비아", "가나", "코트디부아르", "케냐", "에티오피아", "탄자니아",
    "우간다", "모로코", "튀니지", "남아프리카공화국", "남아프리카", "나이지리아", "마다가스카르",
    "사우디아라비아", "아랍에미리트", "이란", "요르단", "카자흐스탄", "우즈베키스탄", "방글라데시", "네팔",
    "캄보디아", "라오스", "홍콩", "파푸아뉴기니", "피지", "볼리비아", "파라과이", "우루과이", "베네수엘라",
    "과테말라", "코스타리카", "온두라스", "니카라과", "파나마", "도미니카", "쿠바", "체코", "슬로바키아",
    "슬로베니아", "크로아티아", "루마니아", "몰도바", "벨라루스", "리투아니아", "라트비아", "에스토니아",
    "아이슬란드", "룩셈부르크", "키프로스", "알바니아", "마케도니아", "조지아", "아르메니아", "아제르바이잔",
    "레바논", "오만", "카타르", "쿠웨이트", "아프가니스탄", "브루나이", "한국", "대한민국", "도미니카공화국",
)
REGIONS = (
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "경기", "강원", "충북", "충남", "전북", "전남",
    "경북", "경남", "제주", "경기도", "강원도", "충청북도", "충청남도", "전라북도", "전라남도", "경상북도",
    "경상남도", "제주도",
)
# '국산', '수입산'처럼 뒤에 '산'이 붙어야만 원산지가 되는 말
ORIGIN_WORDS = ("국내", "국", "수입", "외국", "기타외국", "원양", "연근해", "근해")

_COUNTRY = "|".join(COUNTRIES)
_REGION = "|".join(REGIONS)
_ORIGIN = "|".join(ORIGIN_WORDS)
BARE_COUNTRY_RE = re.compile(rf"^(?:{_COUNTRY})$")     # '미국, 호주산'처럼 나라 이름만 쓰기도 함
# 끝에 붙은 원산지: '나라·지역·국내 + 산'(미국산, 제주산, 국산. 구연산·젖산은 아님) 또는 이음표 뒤 나라 이름('밀-미국').
# (앞 글자, 사이, 원산지)로 나눈다: '통참깨 외국산' -> ('통참깨', ' ', '외국산'). 앞 글자는 가장 짧게 잡는다.
ORIGIN_TAIL_RE = re.compile(
    rf"^(.*?)([\s\-]*)((?:{_COUNTRY}|{_REGION}|{_ORIGIN})산|(?:{_COUNTRY}|수입|국내|외국))(?:\s*(?:등|외))?$")
COUNTY_RE = re.compile(r"^[가-힣]{1,5}군산$")           # 의성군산, 청양군산
ORIGIN_PREFIX_RE = re.compile(rf"^(?:(?:{_COUNTRY}|{_REGION}|{_ORIGIN})산-?)+(?=[가-힣])")   # 미국산대두, 프랑스산-계란
# 원산지 앞에 붙어도 원재료 이름이 아닌 말: '무농약 국산', '유기농 국내산', '생강(모두국산)'
NOT_NAME_HEADS = frozenset({"무농약", "유기농", "유기농산물", "무항생제", "친환경", "후레쉬", "모두", "기타", "원산지", "산지"})

AMOUNT_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|ppm|mg|μg|ug|kcal|g(?![A-Za-z])|(?:억|만)?\s*(?:마리|CFU|cfu))")
# 숫자를 뗀 뒤 규격 설명만 남은 이름: 고형분, 고형분함량, 산도. ('대두고형분'은 대두 단서라 남긴다)
SPEC_ONLY_RE = re.compile(r"^(?:가용성|총)?(?:고형분|함량|농도|순도|유산균수|당도|산도|Brix|brix|브릭스)(?:함량|기준)?$")
KEEP_CODE_RE = re.compile(r"(비타민|오메가|코엔자임|엽산)")   # 뒤의 영문·숫자가 이름의 일부
EDGE_RE = re.compile(r"^[^가-힣A-Za-z0-9]+|[^가-힣A-Za-z0-9]+$")   # 앞뒤 기호·마침표

# 구성품 머리말: 면, 유탕면, 스프, 액상스프, 건더기스프, 후레이크 ... ('간장소스'처럼 구체적인 이름은 아님)
GROUP_WORD = (
    r"(?:(?:분말|액상|건더기|유성|후첨|별첨|과립|조미|양념|야채|건조)?(?:스프|수프)류?"
    r"|(?:생|건|유탕|비유탕|쌀|숙)?면류?|(?:분말|액상|별첨)?소스류?|(?:별첨)?양념장?"
    r"|건더기|(?:야채|건더기)?(?:후레이크|플레이크)|토핑|별첨|조미유)"
)
BULLETS = "*·•∙○●◎■□▪▶▷◆◇★☆〮ㅡ\"'\\-"      # 머리말 앞에 붙는 글머리 기호 ('·스프:', '-스프:')
# 머리말 뒤는 ':' '/' 또는 이음표+한글('면-소맥분'). 앞에 번호가 붙기도 한다('1면-밀가루')
GROUP_SEP = r"(?:[:/]|-(?=\s*[가-힣]))"
GROUP_RE = re.compile(rf"^\s*[{BULLETS}]*\s*\d?\s*({GROUP_WORD})\s*{GROUP_SEP}\s*(.*)$", re.S)


def is_origin(name):
    """원산지 표기뿐인가: 국산, 미국산, 무농약국산, 외국산-미국, 의성군산, 미국(나라 이름만)."""
    x = re.sub(r"(?:등|외)$", "", name) if len(name) > 2 else name    # '호주등' -> '호주'
    if BARE_COUNTRY_RE.match(x) or COUNTY_RE.match(x):
        return True
    rest, origin = split_origin(x)
    return bool(origin) and not rest


def split_origin(x):
    """끝에 붙은 원산지를 (이름, 원산지)로 나눈다.

    '통참깨 외국산' -> ('통참깨', '외국산'), '무농약 국산' -> ('', '무농약 국산'), '구연산' -> ('구연산', '')
    """
    if not re.search(r"산\s*(?:등|외)?$", x) and "-" not in x:
        return x, ""
    m = ORIGIN_TAIL_RE.match(x)
    if not m:
        return x, ""
    head, gap, tail = m.groups()
    if not tail.endswith("산") and "-" not in gap:     # 나라 이름만 쓴 것은 이음표 뒤일 때만 ('밀-미국')
        return x, ""
    name = _head_name(head, gap, tail)
    return (name, tail) if name else ("", x)


def _head_name(head, gap, tail):
    """원산지 앞 글자가 원재료 이름이면 그 이름, 아니면 ''."""
    h = re.sub(r"\s+", "", head)
    h = re.sub(r"(?:이상|이하|및|또는|등|외)$", "", h)    # '국간장 이상 국산', '브라질 등 수입산'
    h = re.sub(r"[^가-힣A-Za-z0-9]+$", "", h)
    if not h or h in NOT_NAME_HEADS or SPEC_ONLY_RE.match(h) or is_origin(h):
        return ""
    if h in REGIONS and h != "대구":                   # '제주도 국산' ('대구'는 생선일 수 있다)
        return ""
    glued = not gap and head[-1:].isalnum()            # '쌀.국산'은 떨어져 있다
    if len(h) == 1 and tail == "국산" and glued:       # '마국산', '믹국산': '미국산'을 잘못 쓴 것일 수 있다
        return ""
    return h


def cut_origin(x):
    """이름 뒤에 붙은 원산지만 뗀다. 원산지뿐이면 그대로 둔다 (그런 조각은 is_origin이 버린다)."""
    name, origin = split_origin(x)
    return name if name and origin else x


def is_number(name):
    return bool(re.fullmatch(r"[\d.,]+", name))


def strip_code(name):
    """관리용 번호를 뗀다: 물엿1, 맛베이스#6, 비프분말S-101, 감미유S, 산도조절제2종."""
    if KEEP_CODE_RE.search(name):
        return name
    x = re.sub(r"(?<=[가-힣])\d+종$", "", name)
    x = re.sub(r"(?<=[가-힣])[-_#]?[A-Za-z]{0,3}[-_#]?\d+(?:\.\d+)?$", "", x)
    x = re.sub(r"(?<=[가-힣])[-_]?[A-Za-z]$", "", x)
    return x or name


def clean_name(part):
    """라벨에 적힌 조각 하나를 사전에서 찾기 좋은 이름으로 정리한다."""
    x = re.sub(r"으로\s*(?=\d)", "", part.strip())    # '사과과즙으로 8.5%' -> '사과과즙 8.5%'
    x = AMOUNT_RE.sub(" ", x).strip()          # '63.5%', '10mg', '1억마리' (자리는 띄어 둔다)
    x = re.sub(r"\s+(?:등|외)$", "", x)        # '마늘 등' -> '마늘'
    x = re.sub(r"\s+함유$", "", x)             # '(대두 함유)', '우유16%함유' -> '대두', '우유'
    x = EDGE_RE.sub("", x.replace("*", ""))
    x = cut_origin(x)                          # '통참깨 100% 외국산' -> '통참깨', '밀-미국산' -> '밀'
    x = EDGE_RE.sub("", re.sub(r"\s+", "", x))
    x = re.sub(r"^\d+년근", "", x)             # '6년근홍삼' -> '홍삼'
    x = ORIGIN_PREFIX_RE.sub("", x)            # '미국산대두', '프랑스산-계란' -> '대두', '계란'
    x = re.sub(r"(?<=[가-힣])(?:이상|이하)$", "", x)   # '대두고형분 9.5% 이상' -> '대두고형분'
    return strip_code(x)


def is_name(name):
    """이름으로 남길 조각인가. 원산지·숫자·규격 설명·'등'·한글 없는 한두 글자는 버린다."""
    if not name or name in ("등", "외"):
        return False
    if is_origin(name) or is_number(name) or SPEC_ONLY_RE.match(name):
        return False
    return bool(re.search(r"[가-힣]", name) or len(name) > 2)


def split_pieces(text):
    """노드 글자 하나를 ':' '/' 기준으로 나눠 이름만 남긴다.

    예: '밀:미국산,호주산'의 '밀:미국산' -> ['밀']
    """
    names = (clean_name(part) for part in re.split(r"[:/;]", text))
    return [n for n in names if is_name(n)]
