"""최종본 파서 단위 테스트. 실행: python -m pytest -q"""
import json

import pytest

from src.final.parser import parse_label, parse_tree


def shape(nodes):
    """비교하기 쉽게 이름만 남긴 모양. 자식이 있으면 (이름, [자식...])"""
    return [(n.name, shape(n.children)) if n.children else n.name for n in nodes]


def tree(text):
    return shape(parse_tree(text)[0])


# 실제 라벨 두 장의 원재료 전사 (파일럿 OCR 정답과 같은 글자)
BIBIM = (
    "면/소맥분(밀:미국산,호주산),팜유(말레이시아산),감자전분(덴마크산,독일산),정제소금,감미유S,야채풍미액,"
    "면류첨가알칼리제(탄산칼륨,탄산나트륨,피로인산나트륨),구아검,혼합제제(폴리인산나트륨,메타인산나트륨,메타인산칼륨),"
    "녹차풍미액 스프/설탕,정제수,고추장,양념간장액,덱스트린,정제소금,고춧가루,식초,홍고추엑기스,맛베이스,사과농축과즙,"
    "마늘엑기스,통참깨참기름,효모추출물,겨자분말,산도조절제2종,양파농축액,혼합야채엑기스,파프리카추출색소,향미증진제2종,"
    "사과식초,구아검,참깨,김,만두향미유 ※ 스프 중 사과농축과즙(고형분함량 72 %) 1.8 %, 통참깨참기름 1.3 %, "
    "사과식초 0.3 % 함유 밀, 대두 함유"
)
BULDAK = (
    "면 : 소맥분(미국산), 변성전분1, 팜유(말레이시아산), 활성소맥글루텐, 정제염, 미감에스유, 구아검, "
    "면류첨가알칼리제(탄산칼륨, 탄산나트륨, 제이인산나트륨), 녹차풍미유, 비타민B2, 구연산. / 액상스프 : "
    "삼양간장본(산분해간장(탈지대두 : 인도산), 양조간장(탈지대두 : 인도산)), 정백당, 정제수, 치킨향분말, "
    "하바네로맛시즈닝, 그릴치킨농축액1, 그릴치킨농축액2, 대두유, 양파, 고추씨향미유, 고춧가루, 맛베이스에스, "
    "매운고추베이스분말, 마늘, 변성전분2, 지미강화육수분말, 탈색칠리추출물, 파프리카추출물, 흑후추분말, "
    "치킨카레맛베이스, 유산균발효분말. / 후레이크 : 볶음참깨, 구운김후레이크. 계란, 우유, 대두, 밀, 닭고기, 쇠고기 함유"
)


# ---------- 나무: 쉼표와 괄호 ----------
@pytest.mark.parametrize("text, expected", [
    ("정제수, 설탕, 소금", ["정제수", "설탕", "소금"]),
    ("혼합조미분말(멸치분말, 정제염)", [("혼합조미분말", ["멸치분말", "정제염"])]),
    ("간장(탈지대두(인도산), 소맥(미국산), 정제염)", [("간장", ["탈지대두", "소맥", "정제염"])]),
    ("가(나(다(라(마))))", [("가", [("나", [("다", [("라", ["마"])])])])]),
    ("소스[간장{대두}, 설탕]", [("소스", [("간장", ["대두"]), "설탕"])]),
    ("소스（간장，설탕）", [("소스", ["간장", "설탕"])]),          # 전각 괄호·쉼표
    ("설탕、소금", ["설탕", "소금"]),
    ("정제수,\n설탕", ["정제수", "설탕"]),
    ("원재료명: 정제수, 설탕", ["정제수", "설탕"]),
    ("간장(대두 함유), 설탕", [("간장", ["대두"]), "설탕"]),
])
def test_tree_basic(text, expected):
    assert tree(text) == expected


# ---------- 괄호 짝이 깨진 경우 ----------
@pytest.mark.parametrize("text, expected, repairs", [
    ("소스(간장, 설탕]", [("소스", ["간장", "설탕"])], 1),
    ("소스(간장, 설탕", [("소스", ["간장", "설탕"])], 1),
    ("설탕), 소금", ["설탕", "소금"], 1),
    ("소스(간장, 설탕)", [("소스", ["간장", "설탕"])], 0),
])
def test_tree_repairs(text, expected, repairs):
    nodes, fixed = parse_tree(text)
    assert shape(nodes) == expected
    assert fixed == repairs


# ---------- 함량·원산지·규격 ----------
@pytest.mark.parametrize("text, expected", [
    ("돼지고기 30%", ["돼지고기"]),
    ("소맥분 63.5%(밀)", [("소맥분", ["밀"])]),
    ("돼지고기(국산) 10%", ["돼지고기"]),
    ("쌀(국내산)", ["쌀"]),
    ("대두(미국산, 캐나다산)", ["대두"]),
    ("소맥분(밀:미국산,호주산)", [("소맥분", ["밀"])]),
    ("양조간장(탈지대두 : 인도산)", [("양조간장", ["탈지대두"])]),
    ("구연산, 젖산, 인산", ["구연산", "젖산", "인산"]),          # '산'으로 끝나도 원산지가 아님
    ("미국산대두, 국산콩", ["대두", "콩"]),
    ("대구, 명태(러시아산)", ["대구", "명태"]),                    # 생선 대구는 지역 이름이 아님
    ("멸치(국산(남해))", [("멸치", ["남해"])]),                    # 모르는 지명은 남아도 해가 없다
    ("팜유(싱가포르산), 커피(콜롬비아산, 가나산)", ["팜유", "커피"]),
    ("대두(무농약 국산), 고추(의성군산), 마늘(호주, 세르비아등)", ["대두", "고추", "마늘"]),
    ("사과농축액(사과과즙으로8.5%,국산)", [("사과농축액", ["사과과즙"])]),
    ("두유액[대두고형분 9.5% 이상(대두 100%:국산), 정제수]", [("두유액", [("대두고형분", ["대두"]), "정제수"])]),
    ("홍삼농축액(6년근, 고형분60%이상, 유산균수 1억마리)", ["홍삼농축액"]),
    ("산도조절제, 산도 0.5%", ["산도조절제"]),
    ("사과농축과즙(고형분함량 72 %)", ["사과농축과즙"]),
    ("산도조절제2종, 향미증진제2종", ["산도조절제", "향미증진제"]),
])
def test_amount_and_origin(text, expected):
    assert tree(text) == expected


# ---------- 관리 번호와 기호 ----------
@pytest.mark.parametrize("text, expected", [
    ("물엿1, 맛베이스#6, 비프분말S-101, 감미유S", ["물엿", "맛베이스", "비프분말", "감미유"]),
    ("비타민B2, 비타민C", ["비타민B2", "비타민C"]),
    ("D-소비톨액", ["D-소비톨액"]),
    ("향신료(후추, 마늘 등)", [("향신료", ["후추", "마늘"])]),
    ("6년근홍삼농축액", ["홍삼농축액"]),
    ("구연산.", ["구연산"]),
    ("유기농설탕*", ["유기농설탕"]),
])
def test_codes(text, expected):
    assert tree(text) == expected


# ---------- 구성품 머리말 (면, 스프) ----------
@pytest.mark.parametrize("text, expected", [
    ("면: 소맥분(밀), 팜유 / 스프: 정제염, 고춧가루",
     [("면", [("소맥분", ["밀"]), "팜유"]), ("스프", ["정제염", "고춧가루"])]),
    ("면/소맥분(밀:미국산),팜유 스프/설탕,고추장",
     [("면", [("소맥분", ["밀"]), "팜유"]), ("스프", ["설탕", "고추장"])]),
    ("[면] 소맥분, 팜유 [스프] 정제염",
     [("면", ["소맥분", "팜유"]), ("스프", ["정제염"])]),
    ("면 : 소맥분(미국산), 구연산. / 액상스프 : 간장(탈지대두 : 인도산), 정백당. / 후레이크 : 볶음참깨",
     [("면", ["소맥분", "구연산"]), ("액상스프", [("간장", ["탈지대두"]), "정백당"]), ("후레이크", ["볶음참깨"])]),
    ("면(소맥분, 팜유)", [("면", ["소맥분", "팜유"])]),           # 괄호로 적은 면은 머리말이 아님
    ("녹차풍미유 *스프류 : 정제염, 정백당", ["녹차풍미유", ("스프류", ["정제염", "정백당"])]),
    ("구연산,녹차풍미유 *스프-정백당,정제염", ["구연산", "녹차풍미유", ("스프", ["정백당", "정제염"])]),
    ("혼합제제(레시틴) *순두부찌개양념장:정제수,고춧가루",              # 구체적인 구성품 이름은 이름으로 남긴다
     [("혼합제제", ["레시틴"]), "순두부찌개양념장", "정제수", "고춧가루"]),
    ("간장소스:일본산[간장,설탕],겨자소스:일본산(머스타드시드)",
     [("간장소스", ["간장", "설탕"]), ("겨자소스", ["머스타드시드"])]),
    ("소스:일본산(간장, 설탕)", [("소스", ["간장", "설탕"])]),        # 콜론 뒤가 원산지면 머리말이 아님
])
def test_groups(text, expected):
    assert tree(text) == expected


def test_group_flag_in_dict():
    nodes, _ = parse_tree("면: 소맥분, 팜유 / 스프: 정제염")
    d = [n.to_dict() for n in nodes]
    assert d[0]["group"] is True and d[0]["name"] == "면"
    assert "group" not in d[0]["children"][0]


# ---------- mentions: 분류 단계에 넘기는 목록 ----------
def test_mentions():
    r = parse_label("혼합조미분말(멸치분말)")
    assert r.mentions() == [("혼합조미분말", 0, "", False), ("멸치분말", 1, "혼합조미분말", True)]


def test_mentions_skip_group_header():
    r = parse_label("면: 소맥분(밀)")
    assert r.mentions() == [("소맥분", 0, "", False), ("밀", 1, "소맥분", True)]


# ---------- 구역: 원재료 / 표시란 / 같은 시설 ----------
def test_zone_start_and_stop():
    r = parse_label("제품명 매운라면 원재료명: 정제수, 설탕 내용량 100g")
    assert r.ingredients_text == "정제수, 설탕"


def test_zone_start_with_amount_title():
    assert parse_label("원재료명 및 함량: 정제수, 설탕").ingredients_text == "정제수, 설탕"


def test_declaration_at_end():
    r = parse_label("정제수, 설탕, 밀가루(밀) 밀, 대두 함유")
    assert r.declared == ("밀", "대두")
    assert r.declaration_text == "밀, 대두 함유"
    assert r.ingredients_text == "정제수, 설탕, 밀가루(밀)"


def test_real_label_bibim():
    r = parse_label(BIBIM)
    assert r.declared == ("밀", "대두")
    assert r.ingredients_text.endswith("만두향미유")      # ※ 함량 안내는 원재료가 아님
    assert r.facility_text is None
    groups = [n.name for n in r.tree]
    assert groups == ["면", "스프"]
    names = [m[0] for m in r.mentions()]
    assert "통참깨참기름" in names and "참깨" in names and "맛베이스" in names


def test_real_label_buldak():
    r = parse_label(BULDAK)
    assert r.declared == ("계란", "우유", "대두", "밀", "닭고기", "쇠고기")
    assert "함유" not in r.ingredients_text
    assert [n.name for n in r.tree] == ["면", "액상스프", "후레이크"]
    names = [m[0] for m in r.mentions()]
    for expected in ("활성소맥글루텐", "산분해간장", "탈지대두", "대두유", "볶음참깨", "치킨카레맛베이스", "비타민B2"):
        assert expected in names
    assert r.repairs == 0


def test_facility_sentence():
    text = ("원재료명: 정제수, 설탕. 이 제품은 메밀, 땅콩을 사용한 제품과 같은 제조시설에서 "
            "제조하고 있습니다. 밀 함유")
    r = parse_label(text)
    assert "같은 제조시설" in r.facility_text
    assert r.declared == ("밀",)                       # 시설 문구의 땅콩은 표시란이 아님
    assert r.ingredients_text == "정제수, 설탕"


@pytest.mark.parametrize("text", [
    "정제수, 설탕",
    "칼슘함유분말, 정제수",          # 이름 속 '함유'
    "간장(대두 함유), 설탕",         # 괄호 속 '함유'는 원재료 설명
])
def test_no_declaration(text):
    r = parse_label(text)
    assert r.declaration_text is None and r.declared == ()


@pytest.mark.parametrize("text, declared", [
    ("정제수 밀·대두·우유 함유", ("밀", "대두", "우유")),
    ("정제수, 굴소스 새우, 조개류(굴, 전복, 홍합 포함) 함유", ("새우", "조개류")),
    ("정제수 밀, 대두 등 함유", ("밀", "대두")),
    ("정제수 우유*, 대두* 함유", ("우유", "대두")),
])
def test_declaration_forms(text, declared):
    assert parse_label(text).declared == declared


def test_declaration_header_removed_from_ingredients():
    r = parse_label("원재료명: 정제수, 설탕 [알레르기 유발물질] 밀, 대두 함유")
    assert r.declared == ("밀", "대두")
    assert r.ingredients_text == "정제수, 설탕"


def test_declaration_head_without_suffix():
    r = parse_label("원재료명: 정제수 알레르기 유발물질: 밀, 대두")
    assert r.declared == ("밀", "대두")
    assert r.ingredients_text == "정제수"


# ---------- API처럼 칸이 나뉜 입력 ----------
@pytest.mark.parametrize("declaration, text, declared", [
    ("밀,대두,우유 함유", "밀,대두,우유 함유", ("밀", "대두", "우유")),
    ("밀, 대두", "밀, 대두", ("밀", "대두")),
    ("알수없음", None, ()),
    ("None", None, ()),
    (None, None, ()),
    ("해당없음", "해당없음", ()),          # 표시란은 읽었고 적힌 알레르기가 없음
    ("알러지유발식품없음", "알러지유발식품없음", ()),
    ("대두[d-토코페롤(혼합형)]함유", "대두[d-토코페롤(혼합형)]함유", ("대두",)),
    ("●새우함유", "●새우함유", ("새우",)),
    ("이산화황 함유", "이산화황 함유", ("이산화황",)),
    ("메추리알 함유", "메추리알 함유", ("메추리알",)),
    ("소맥분(밀),탈지대두(대두),난각칼슘(계란)", "소맥분(밀),탈지대두(대두),난각칼슘(계란)", ("밀", "대두", "계란")),
    ("페닐알라닌 함유", None, ()),        # 감미료 주의 문구일 뿐 알레르기 표시가 아님
])
def test_fields(declaration, text, declared):
    r = parse_label(ingredients="정제수, 설탕", declaration=declaration)
    assert r.declaration_text == text
    assert r.declared == declared
    assert shape(r.tree) == ["정제수", "설탕"]


# ---------- 입력 검사 ----------
def test_needs_exactly_one_input():
    with pytest.raises(ValueError):
        parse_label()
    with pytest.raises(ValueError):
        parse_label("정제수", ingredients="설탕")


def test_rejects_non_text():
    with pytest.raises(TypeError):
        parse_label(123)


def test_rejects_too_long():
    with pytest.raises(ValueError):
        parse_label("가," * 20000)


# ---------- 팀 응답 형식 ----------
def test_to_api_matches_team_format():
    r = parse_label("혼합조미분말(멸치분말)")
    api = r.to_api()
    assert api["ingredients"] == [{"name": "혼합조미분말", "children": [{"name": "멸치분말", "children": []}]}]
    assert set(api) == {"ingredients_text", "declaration_text", "ingredients"}
    json.dumps(api, ensure_ascii=False)          # 그대로 JSON으로 보낼 수 있어야 한다
