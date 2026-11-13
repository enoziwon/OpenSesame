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
    ("혼합제제(레시틴) *순두부찌개양념장:정제수,고춧가루",              # 별표 구성품 이름도 머리말 (2026-11 조율자 결정)
     [("혼합제제", ["레시틴"]), ("순두부찌개양념장", ["정제수", "고춧가루"])]),
    ("*삼립호빵순백우유:우유카스타드[우유,설탕],밀가루", [("삼립호빵순백우유", [("우유카스타드", ["우유", "설탕"]), "밀가루"])]),
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


# ---------- 이름 뒤에 괄호 없이 붙은 원산지 (2020년 자료의 꼴) ----------
@pytest.mark.parametrize("text, expected", [
    ("통참깨 100% 외국산(인도, 파키스탄)", ["통참깨"]), ("한우100% 국내산", ["한우"]), ("원유100%국산", ["원유"]),
    ("계란 국산, 땅콩5%중국산, 소맥분호주산, 탈지대두인도산, 참깨 수입산", ["계란", "땅콩", "소맥분", "탈지대두", "참깨"]),
    ("국간장 이상 국산, 굴 이상 국산", ["국간장", "굴"]), ("고야레몬주스(도미니카공화국산)", ["고야레몬주스"]),
    ("국산, 미국산, 외국산:미국,호주", []), ("브라질산50% 및 아르헨티나산50%", []),    # 원산지뿐이면 지금처럼 버린다
    ("감귤과즙(제주도 국산), 생강(모두국산), 숙지황(이상 국산), 돈육(후레쉬국내산)", ["감귤과즙", "생강", "숙지황", "돈육"]),
    ("밀가루(밀:마국산), 옥수수(믹국산)", [("밀가루", ["밀"]), "옥수수"]), ("쌀조청(쌀.국산)", [("쌀조청", ["쌀"])]),   # 마국산: 오타
])
def test_origin_glued_to_name(text, expected):
    assert tree(text) == expected


# ---------- 이음표·쌍점으로 붙은 원산지와 구성품 머리말 ----------
@pytest.mark.parametrize("text, expected", [
    ("밀-미국산, 대두:외국산, 검은깨-미얀마산, 대두-미국", ["밀", "대두", "검은깨", "대두"]),
    ("외국산-미국, 국산-중국, 프랑스산-계란, 중국산-브라질산과라나", ["계란", "과라나"]),
    ("면-소맥분(밀:미국산,호주산),팜유 스프-정제소금,설탕", [("면", [("소맥분", ["밀"]), "팜유"]), ("스프", ["정제소금", "설탕"])]),
    ("1면-밀가루(밀/호주산),볶은메밀가루", [("면", [("밀가루", ["밀"]), "볶은메밀가루"])]),
    ("녹차풍미액 스프-짜장시즈닝분말,정제염", ["녹차풍미액", ("스프", ["짜장시즈닝분말", "정제염"])]),
    ("비타민B2 *스프류/부대찌개분말,정제염", ["비타민B2", ("스프류", ["부대찌개분말", "정제염"])]),
    ("녹차풍미유 ·스프:백설탕,정제염", ["녹차풍미유", ("스프", ["백설탕", "정제염"])]),
    ("유청분말(우유) *소스/백설탕", [("유청분말", ["우유"]), ("소스", ["백설탕"])]),
    ("소스-A(간장)", [("소스", ["간장"])]),                         # 이음표 뒤가 관리 번호면 머리말이 아님
    ("L-글루타민산나트륨, DL-사과산, 5'-구아닐산이나트륨, d-토코페롤, 비타민B-1",   # 화합물 이름은 그대로
     ["L-글루타민산나트륨", "DL-사과산", "5'-구아닐산이나트륨", "d-토코페롤", "비타민B-1"]),
])
def test_hyphen_origin_and_group(text, expected):
    assert tree(text) == expected


def test_hyphen_header_is_group():
    nodes = parse_tree("면-소맥분, 팜유 스프-정제염")[0] + parse_tree("소스-A(간장)")[0]
    assert [(n.name, n.group) for n in nodes] == [("면", True), ("스프", True), ("소스", False)]


# ---------- 사진 글자: 비어 있는 표시란 ('없음'만 있고 머리말이 없으면 표시란이 아님) ----------
@pytest.mark.parametrize("text, decl, ingredients", [
    ("원재료명: 정제수, 설탕 알레르기 유발물질: 해당없음", "알레르기 유발물질: 해당없음", "정제수, 설탕"),
    ("원재료명: 정제수, 설탕 알레르기 유발 성분 없음", "알레르기 유발 성분 없음", "정제수, 설탕"),
    ("원재료명: 정제수, 설탕 [알레르기 유발물질] 해당 없음 내용량 100g", "[알레르기 유발물질] 해당 없음", "정제수, 설탕"),
    ("원재료명: 정제수, 설탕(방부제 없음)", None, "정제수, 설탕(방부제 없음)"),
])
def test_text_empty_declaration(text, decl, ingredients):
    r = parse_label(text)
    assert (r.declaration_text, r.declared, r.ingredients_text) == (decl, (), ingredients)


# ---------- 같은 시설 문구: 칸 입력에서도 떼어 facility_text에 담고, 끝나는 말에서 끊는다 ----------
@pytest.mark.parametrize("ingredients, names", [
    ("정제수, 설탕, 이 제품은 땅콩, 우유를 사용한 제품과 같은 제조시설에서 제조하고 있습니다.", ["정제수", "설탕"]),
    ("정제수, 이 제품은 같은 제조시설에서 우유, 대두, 조개류(굴, 전복 포함)를 사용한 제품을 제조하고 있습니다, 간장", ["정제수", "간장"]),
    ("정제수, 이 제품은 땅콩을 사용한 제품과 같은 제조시설에서 제조, 간장, 새우", ["정제수", "간장", "새우"]),
    ("정제수, 이 제품은 땅콩을 사용한 제품과 같은 시설, 간장", ["정제수", "간장"]),          # 끝나는 말이 없으면 첫 쉼표까지
    ("파슬리후레이크, ※이 제품은 난류, 우유, 새우를 사용한 제품과 같은 제조 시설에서 제조하고 있습니다.", ["파슬리후레이크"]),
])
def test_facility_end(ingredients, names):
    r = parse_label(ingredients=ingredients, declaration="밀 함유")
    assert [m[0] for m in r.mentions()] == names and "이 제품은" in r.facility_text and r.declared == ("밀",)


@pytest.mark.parametrize("text, declared, ingredients", [
    ("원재료명: 정제수, 이 제품은 땅콩을 사용한 제품과 같은 제조시설에서 제조, 간장, 새우 밀 함유", ("새우", "밀"), "정제수, 간장"),
    ("원재료명: 정제수, 설탕 이 제품은 메밀을 사용한 제품과 같은 시설에서 제조됩니다 밀, 대두 함유", ("밀", "대두"), "정제수, 설탕"),
    ("원재료명: 정제수 이 제품은 땅콩을 사용한 제품과 같은 시설에서 제조, 혼입될 수 있습니다 새우, 밀 함유", ("새우", "밀"), "정제수"),
])
def test_text_facility_does_not_eat_declaration(text, declared, ingredients):
    r = parse_label(text)
    assert (r.declared, r.ingredients_text) == (declared, ingredients)


# ---------- 칸 입력: 표시란 칸이 비었으면 원재료 칸 속 표시란을 쓴다 ----------
@pytest.mark.parametrize("ingredients, declared, kept", [
    ("당면32.0%[고구마전분(중국산)100%],후추가루,밀,대두,조개(굴)함유", ("밀", "대두", "조개"), "후추가루"),
    ("구연산, 우유,대두 함유 [레인보우아이스]정제수", ("우유", "대두"), "정제수"),
    ("정제수,순두부9.9%[대두99.79%(수입산),응고제,쌀, 대두,밀,새우함유", ("대두", "밀", "새우"), "쌀"),   # 깨진 괄호 뒤
    ("후추,조개류(굴포함)대두,밀,함유", ("조개류", "대두", "밀"), "후추"),
    ("미강유,복합소미식품 우유 밀 대두 함유", ("우유", "밀", "대두"), "복합소미식품"),
])
def test_fields_box_inside_ingredients(ingredients, declared, kept):
    r = parse_label(ingredients=ingredients, declaration="알수없음")
    assert r.declared == declared and kept in [m[0] for m in r.mentions()]
    assert "함유" not in r.ingredients_text


@pytest.mark.parametrize("ingredients, declaration", [
    ("정제수,파프리카추출색소 *스프중김치71%함유", "알수없음"),      # 원재료 칸의 함량 문구
    ("감미료(아스파탐), 페닐알라닌 함유", "알수없음"),
    ("수수,탄산칼슘,오징어11%(생물기준)함유", "알수없음"),
    ("정제수", "생선"), ("정제수", "분리대두단백"), ("정제수", "310g(고형량155g)"),
])
def test_not_a_box(ingredients, declaration):
    r = parse_label(ingredients=ingredients, declaration=declaration)
    assert (r.declaration_text, r.declared) == (None, ())


@pytest.mark.parametrize("kwargs, declared, names", [
    ({"ingredients": "정제수, 우유 함유", "declaration": "대두"}, ("대두",), ["정제수", "우유"]),    # 표시란 칸이 있으면 그것만
    ({"text": "원재료명: 정제수 알레르기 유발물질: 밀가루, 대두"}, ("밀", "대두"), ["정제수"]),
    ({"text": "원재료명: 정제수, 밀가루, 대두 함유"}, ("대두",), ["정제수", "밀가루"]),       # '함유' 앞 목록의 밀가루는 원재료
    ({"ingredients": "정제수, 정제소금 ※특정성분함량및원산지:후첨분말스프중닭고기0.62%(국내산)함유"}, (), ["정제수", "정제소금"]),
    ({"text": "원재료명: 정제수, 파프리카추출색소 *스프중김치71%함유"}, (), ["정제수", "파프리카추출색소"]),
])
def test_box_column_alias_and_note(kwargs, declared, names):
    r = parse_label(**kwargs)
    assert r.declared == declared and [m[0] for m in r.mentions()] == names


# ---------- 칸 입력: 표시란 칸 값의 변형 ----------
@pytest.mark.parametrize("declaration, declared", [
    ("대두 포함", ("대두",)), ("돼지고기 포함", ("돼지고기",)), ("우유 제품", ("우유",)), ("밀 40.3% 함유", ("밀",)),
    ("호두,대두,밀가루,우유,계란", ("호두", "대두", "밀", "우유", "계란")), ("밀가루", ("밀",)),    # 표시란의 '밀가루'는 밀
    ("우유, 대두 포함", ("우유", "대두")), ("밀.우유.땅콩 함유", ("밀", "우유", "땅콩")),
    ("대두, 땅콩 우유함유", ("대두", "땅콩", "우유")), ("알레르기 유발물질: 없음", ()),
    ("쇠고기,토마토,유당(우유),대두,밀 함유", ("쇠고기", "토마토", "우유", "대두", "밀")),
    ("밀,콩,땅콩 첨가제품", ("밀", "콩", "땅콩")), ("돼지고기,대두-유래원재료 함유", ("돼지고기", "대두")),
    ("※이 제품은 원재료에 알레르기 유발물질인 대두,밀,조개류(굴 포함)를 함유하고 있습니다.", ("대두", "밀", "조개류")),
    ("[호두쿠키] 밀,우유,호두 [검정콩쿠키] 밀,대두", ("밀", "우유", "호두", "대두")),
])
def test_field_variants(declaration, declared):
    r = parse_label(ingredients="정제수", declaration=declaration)
    assert r.declared == declared and r.declaration_text == declaration


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
