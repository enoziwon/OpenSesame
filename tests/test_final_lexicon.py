"""최종본 원재료 사전 테스트. 실행: python -m pytest -q

표(TSV)의 형식이 깨지지 않았는지, 헷갈리는 이름이 가이드대로 나오는지 본다.
"""
import csv
from pathlib import Path

import pytest

from src.final import lexicon
from src.final.lexicon import GRADES, SPECIAL, lookup, norm, strip_origin

TABLES = Path(lexicon.__file__).parent
US9 = {"milk", "egg", "wheat", "soy", "peanut", "sesame", "fish", "crustacean", "tree_nut"}
STATUSES = {"확인", "공전확인", "FDA확인", "공전·FDA확인", "보고자료확인", "조사확인", "시드확인", "시드검증필요", "검수요청"}


def rows(filename):
    with open(TABLES / filename, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


# ---------- 표의 형식 ----------
def test_source_table_maps_to_us9_or_nothing():
    for r in rows("sources.tsv"):
        assert r["us9"] in US9 | {""}, r
        assert r["en"] and r["ko"], r


def test_every_code_grade_and_status_in_entries_is_known():
    codes = {r["code"] for r in rows("sources.tsv")}
    for r in rows("entries.tsv"):
        for token in r["sources"].split():
            code, grade = token.rsplit(":", 1)
            assert code in codes, r["name"]
            assert grade in GRADES, r["name"]
        assert set(r["flags"]) <= set("OSBMVX"), r["name"]
        assert "S" not in r["flags"] or "O" in r["flags"], r["name"]         # 참깨 범위(S)는 속 모를 원료(O)에만 붙는다
        assert not ("O" in r["flags"] and "M" in r["flags"]), r["name"]     # 양념·국물 계열이면서 그 밖의 섞은 원료일 수는 없다
        assert r["status"] in STATUSES, r["name"]


def test_every_rule_uses_known_code_and_grade():
    codes = {r["code"] for r in rows("sources.tsv")}
    seen = set()
    for r in rows("rules.tsv"):
        assert r["id"] not in seen, r["id"]
        seen.add(r["id"])
        if r["id"] in SPECIAL:
            assert not r["source"] and not r["unless"], r["id"]
            continue
        assert r["source"] in codes and r["grade"] in GRADES and r["include"], r["id"]
    assert set(SPECIAL) <= seen


def test_entries_with_official_status_carry_a_basis():
    for r in rows("entries.tsv"):
        if r["status"] in {"공전확인", "FDA확인", "공전·FDA확인", "보고자료확인", "조사확인"}:
            assert r["basis"], r["name"]


def test_entry_names_are_unique_after_normalizing():
    names = [norm(r["name"]) for r in rows("entries.tsv")]
    assert len(names) == len(set(names))


def test_auto_tier_does_not_repeat_reviewed_entries():
    reviewed = {norm(r["name"]) for r in rows("entries.tsv")}
    assert not reviewed & {norm(r["name"]) for r in rows("entries_auto.tsv")}


def test_kr_box_words_point_to_known_codes():
    codes = {r["code"] for r in rows("sources.tsv")}
    box = lexicon.kr_box()
    assert {"우유", "알류", "밀", "대두", "땅콩", "고등어", "게", "새우", "호두", "잣"} <= set(box)
    assert all(v["source"] in codes for v in box.values())
    assert box["참깨"]["mandatory"] == "N"          # 참깨는 현행 한국 표시 의무가 아니다


# ---------- 헷갈리는 이름 (가이드 3·5·6장) ----------
CASES = [
    # 밀: 미국 기준은 Triticum 속 전체
    ("밀", {"wheat": "C"}), ("밀-미국산", {"wheat": "C"}), ("소맥분", {"wheat": "C"}), ("빵가루", {"wheat": "I"}),
    ("글루텐", {"wheat": "C"}), ("당밀", {}), ("오트밀분말", {}), ("메밀가루", {"wheat": "P"}), ("보리", {}), ("당면", {}),
    ("전분", {"wheat": "P"}), ("쌀국수", {"wheat": "I"}), ("스펠트밀", {"wheat": "C"}), ("라이밀", {"wheat": "C"}),
    ("호밀", {}), ("귀리", {}), ("만두피", {"wheat": "I"}), ("소백분", {"wheat": "C"}), ("합성팽창제", {"wheat": "P"}),
    ("생빵가루", {"wheat": "I"}), ("쌀빵가루", {}), ("우리밀빵가루", {"wheat": "C", "milk": "P"}), ("파스타", {"wheat": "I"}),
    # 대두와 정제유
    ("간장", {"soy": "C", "wheat": "I"}), ("한식간장", {"soy": "C"}), ("된장", {"soy": "C", "wheat": "I"}),
    ("산분해간장", {"soy": "I", "wheat": "P"}), ("아미노산간장", {"soy": "I"}), ("메주된장", {"soy": "C"}), ("고추장", {"soy": "I", "wheat": "I"}), ("대두유", {"soy": "R"}),
    ("d-토코페롤", {"soy": "R"}), ("DL-α-토코페롤", {}), ("식물성유지", {"soy": "F"}), ("레시틴", {"soy": "I"}),
    ("대두레시틴", {"soy": "C"}), ("유화제", {"soy": "P"}), ("콩나물", {"soy": "C"}), ("완두콩", {}), ("두유", {"soy": "C"}),
    ("ISP", {"soy": "C"}), ("탄산칼슘혼합제제", {"soy": "I"}), ("대두유액", {"soy": "I"}), ("두유액", {"soy": "C"}),
    # 땅콩
    ("땅콩버터", {"peanut": "C"}), ("땅콩호박", {}), ("땅콩기름", {"peanut": "I"}), ("낙화생유", {"peanut": "I"}),
    ("비타민A혼합제제", {"peanut": "P"}),
    # 우유: 미국 기준은 반추동물의 젖 전체
    ("코코아버터", {}), ("코코넛밀크", {}), ("카제인나트륨", {"milk": "C"}), ("유청분말", {"milk": "C"}), ("젖산", {}),
    ("유산균", {}), ("유산균배양액", {"milk": "I"}), ("카라멜분말", {"milk": "P"}), ("카라멜색소", {}), ("식물성크림", {"milk": "I", "soy": "F"}), ("산양유", {"milk": "C"}),
    ("염소젖", {"milk": "C"}), ("어패류", {"fish": "P"}), ("오곡분말", {"soy": "I", "sesame": "P"}), ("유당", {"milk": "C"}), ("화이트초콜릿", {"milk": "C"}), ("초콜릿", {"milk": "I"}),
    ("유단백가수분해물", {"milk": "C"}), ("헤미셀룰라아제", {"milk": "P"}),
    # 달걀
    ("난각칼슘", {"egg": "I"}), ("마요네즈", {"egg": "C"}), ("리소짐", {"egg": "C"}), ("메추리알", {"egg": "C"}),
    ("전락액", {"egg": "C"}), ("카라기난분말", {}), ("케익분말", {"wheat": "I", "egg": "I"}),
    # 참깨
    ("참기름", {"sesame": "C"}), ("추출참깨유", {"sesame": "I"}), ("깨", {"sesame": "C"}), ("들기름", {}), ("깻잎", {}),
    ("조미김", {"sesame": "I"}), ("만두", {"sesame": "I"}), ("만두시즈닝분말", {}),
    # 생선, 갑각류, 연체류
    ("멸치액젓", {"fish": "C"}), ("액젓", {"fish": "I"}), ("고등어", {"fish": "C"}), ("연육", {"fish": "C"}),
    ("게맛살", {"fish": "C", "crustacean": "I", "wheat": "I", "egg": "P"}), ("어묵", {"fish": "C", "wheat": "I"}), ("새우젓", {"crustacean": "C"}), ("크릴", {"crustacean": "C"}),
    ("오징어", {}), ("김치", {"fish": "I", "crustacean": "I"}), ("홍어", {"fish": "C"}), ("명란", {"fish": "C"}),
    ("육수", {"fish": "P"}), ("사골육수", {}), ("닭발육수", {}), ("팜에스테르화유", {}), ("쇼트닝", {"soy": "F"}),
    ("불고기양념장", {"soy": "I", "wheat": "P"}), ("콜라겐", {"fish": "P"}), ("콜라겐케이싱", {}),
    ("젤라틴", {}), ("어류젤라틴", {"fish": "C"}), ("간짜장페이스트", {"soy": "I", "wheat": "I"}),
    ("까나리액젓", {"fish": "C", "crustacean": "P"}), ("짬뽕분말", {"crustacean": "P"}),
    # 견과류: 미국 기준은 FDA 표 1의 12종만
    ("아몬드", {"tree_nut": "C"}), ("잣", {"tree_nut": "C"}), ("호두기름", {"tree_nut": "I"}), ("코코넛", {}), ("밤", {}),
    ("은행", {}), ("견과류", {"tree_nut": "I"}), ("시리얼", {"tree_nut": "P"}), ("씨리얼", {"tree_nut": "P"}),
    ("견과혼합페이스트", {"tree_nut": "I", "peanut": "I"}),
    # 규칙이 속기 쉬운 글자
    ("발아귀리", {}), ("차조기농축액", {}), ("수크랄로스", {}), ("커피시럽", {}), ("다시마엑기스", {}),
    ("대두단백가수분해물", {"soy": "C"}), ("조미김치분말", {"fish": "I", "crustacean": "I"}), ("종가집김치전용풀", {}), ("잣모양화과자", {"wheat": "I"}),
    # 화합물 이름과 상표
    ("L-글루타민산나트륨", {}), ("5'-구아닐산이나트륨", {}), ("DL-사과산", {}), ("L-아스코르빈산나트륨", {}),
    ("호스이엔알", {}), ("미감에스유", {"soy": "I"}), ("미트프로엠", {"soy": "I", "wheat": "I", "egg": "I", "milk": "I"}),
]


@pytest.mark.parametrize("name, expected", CASES)
def test_us9_verdict(name, expected):
    assert lookup(name).us == expected


def test_species_is_kept_for_display():
    assert dict(lookup("멸치액젓").sources) == {"fish:anchovy": "C"}      # 뭉뚱그린 '생선'은 종 코드가 있으면 뺀다
    assert dict(lookup("고등어").sources) == {"fish:mackerel": "C"}       # 한국 표시란이 덮는 유일한 생선
    assert dict(lookup("가다랑어분말").sources) == {"fish:bonito": "C"}
    assert dict(lookup("크릴새우").sources) == {"crustacean:krill": "C"}
    assert dict(lookup("오징어").sources)                                 # 미국 9개 밖이어도 무엇인지는 안다


def test_opaque_flavor_and_non_ingredient_flags():
    assert lookup("복합조미식품").opaque and lookup("맛베이스").opaque and lookup("혼합조미분말").opaque
    assert lookup("굴소스").opaque and lookup("굴소스").us == {"soy": "I", "wheat": "I"}
    assert lookup("합성착향료").flavor and not lookup("합성착향료").us
    assert lookup("알수없음").not_ingredient
    assert not lookup("다시마엑기스").opaque             # 원료 하나의 추출물은 속 모를 원료가 아니다
    assert lookup("채소밑국물").opaque and lookup("조미액").opaque


def test_sesame_scope_is_only_for_sauce_and_seasoning_paste_families():
    """가이드 v1 5장: 참깨 판정 불가는 양념·소스 계열에만 단다. 국물·조미 계열은 생선만."""
    for name in ("양념분말", "소스", "굴소스", "다대기", "혼합엑기스", "불고기양념장"):
        assert lookup(name).opaque and lookup(name).opaque_sesame, name
    for name in ("맛베이스", "혼합조미분말", "복합조미식품", "조미액", "스프류", "채소밑국물"):
        assert lookup(name).opaque and not lookup(name).opaque_sesame, name
    for name in ("풍미유", "향미유"):                                       # 식품공전: 향미유의 바탕 기름에서 압착참기름은 빠진다
        assert lookup(name).compound and not lookup(name).opaque, name


def test_meat_based_opaque_is_marked():
    """가이드 N14: 고기 바탕이 이름에 적힌 속 모를 원료는 생선 판정 불가의 근거가 아니다 (하위 원료가 적힌 사례의 0.5%)."""
    for name in ("쇠고기다시", "소고기베이스", "치킨스톡", "사골설렁탕분말스프", "비프조미분"):
        hit = lookup(name)
        assert hit.opaque and hit.opaque_meat and not hit.opaque_sesame, name
    for name in ("불고기양념", "갈비소스", "돼지갈비양념"):                   # 양념·소스 계열이면 참깨 범위는 그대로
        hit = lookup(name)
        assert hit.opaque and hit.opaque_meat and hit.opaque_sesame, name
    for name in ("맛베이스", "혼합조미분말", "양념분말", "해물베이스", "물고기소스"):
        assert lookup(name).opaque and not lookup(name).opaque_meat, name
    assert not lookup("쇠고기").opaque_meat and not lookup("사골엑기스").opaque_meat      # 속 모를 원료가 아니면 붙지 않는다
    assert not lookup("간짜장페이스트").opaque                               # 페이스트는 속 모를 원료의 낱말이 아니다


def test_goat_milk_has_its_own_code():
    for name in ("산양유", "산양유청", "산양분유", "염소젖", "양유"):
        hit = lookup(name)
        assert hit.us == {"milk": "C"} and dict(hit.sources) == {"milk:goat": "C"}, name
    assert lexicon.source_info("milk:goat")["kr_box"] == ""                 # 한국 표시란의 '우유'가 덮지 않는다
    assert not lookup("산양삼").us and not lookup("버팔로윙소스").us


def test_compound_is_not_a_seasoning_type_opaque():
    """가이드 v1 5장: 시즈닝·혼합제제·가공품·믹스는 섞은 원료지만 참깨·생선 판정 불가의 근거가 아니다."""
    for name in ("시즈닝", "혼합제제", "기타가공품", "허니버터시즈닝", "미트인헨서", "조미건조홍고추", "커피믹스"):
        hit = lookup(name)
        assert hit.compound and not hit.opaque, name
    for name in ("향료", "합성향료", "천연향료", "영양강화제", "향신료"):      # 일반 향료와 용도 이름은 어느 쪽도 아니다
        hit = lookup(name)
        assert not hit.opaque and not hit.compound, name
    assert lookup("조미씨즈닝").opaque and not lookup("조미씨즈닝").compound    # 둘 다 맞으면 양념·국물 계열


def test_flavored_names_are_downgraded():
    assert lookup("새우맛분말").us == {"crustacean": "I"}            # 맛 이름은 추정
    assert lookup("명란마요맛시즈닝").us["fish"] == "I"
    assert lookup("홍게맛살").us == {"fish": "C", "crustacean": "I", "wheat": "I"}     # 맛살류는 대개 밀 전분을 넣는다
    for name, allergen in (("헤이즐넛향", "tree_nut"), ("버터향", "milk"), ("땅콩향", "peanut"), ("참깨향", "sesame"),
                           ("초콜릿향", "milk")):
        hit = lookup(name)                                          # 향료 이름은 가능까지만 (땅콩향의 표시란 근거 7%)
        assert hit.flavor and hit.us == {allergen: "P"}, name


def test_origin_is_stripped_only_for_place_names():
    assert strip_origin("밀-미국산") == "밀" and strip_origin("대두:외국산") == "대두"
    assert strip_origin("프랑스산-계란") == "계란"
    assert strip_origin("L-글루타민산나트륨") == "L-글루타민산나트륨"      # '산'으로 끝나는 화합물은 원산지가 아니다
    assert strip_origin("DL-사과산") == "DL-사과산"
    assert lookup("검은깨-미얀마산").us == {"sesame": "C"}
    assert lookup("프랑스산-계란").us == {"egg": "C"}


def test_origin_lists_and_facility_statements_are_not_ingredients():
    for name in ("미국·캐나다·호주", "외국산-미국", "인도•미얀마•베트남", "이태리산"):
        hit = lookup(name)
        assert hit.not_ingredient and not hit.us, name
    hit = lookup("새우를사용한제품과같은제조시설에서제조하고있습니다")
    assert hit.not_ingredient and not hit.us            # 혼입 안내 문구를 '새우 확정'으로 읽으면 안 된다


def test_lookup_route():
    assert lookup("밀").via == "entry"
    assert lookup("볶음검정참깨분말").via == "rule"
    assert lookup("비피도박테리움브레베").via == "benign"
    assert lookup("글루콘산칼슘").via in {"benign", "entry"} and not lookup("글루콘산칼슘").us
    assert lookup("이름표에없는상표엑스").via == "unknown" and not lookup("이름표에없는상표엑스").us
    assert lookup("").via == "unknown"


def test_spacing_and_hyphens_do_not_matter():
    assert lookup("대두 레시틴").us == lookup("대두레시틴").us
    assert lookup("땅콩 또는 견과류가공품").us == lookup("땅콩또는견과류가공품").us


def test_rejects_non_string():
    with pytest.raises(TypeError):
        lookup(None)
