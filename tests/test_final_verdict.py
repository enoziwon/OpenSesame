"""최종본 판정 규칙 테스트 (정답지 가이드 v1의 1~5절). 실행: python -m pytest -q

사전 내용은 바뀔 수 있어서 이름 -> 사전 결과를 손으로 정한 가짜 조회 함수를 쓴다.
파서(src.final.parser)와 한국 표시란 낱말표(kr_box)는 그대로 쓴다.
"""
from dataclasses import dataclass

import pytest

from src.final.parser import parse_label
from src.final.verdict import judge


@dataclass(frozen=True)
class Fake:
    """lexicon.Lookup과 같은 칸을 가진 가짜 사전 결과."""
    name: str
    sources: tuple = ()
    opaque: bool = False
    opaque_sesame: bool = False
    compound: bool = False
    flavor: bool = False
    not_ingredient: bool = False
    via: str = "entry"
    en: str = ""


TABLE = {f.name: f for f in [
    Fake("간장", (("soy", "C"), ("wheat", "I"))),
    Fake("소맥분", (("wheat", "C"),)),
    Fake("밀", (("wheat", "C"),), en="wheat"),
    Fake("대두", (("soy", "C"),)),
    Fake("콩", (("soy", "C"),)),
    Fake("우유", (("milk", "C"),)),
    Fake("탈지분유", (("milk", "C"),)),
    Fake("새우", (("crustacean:shrimp", "C"),), en="shrimp"),
    Fake("꽃게", (("crustacean:crab", "C"),)),
    Fake("크릴", (("crustacean:krill", "C"),)),
    Fake("참기름", (("sesame", "C"),)),
    Fake("멸치액젓", (("fish:anchovy", "C"),), en="anchovy fish sauce"),
    Fake("대두유", (("soy", "R"),)),
    Fake("토코페롤", (("soy", "R"),)),
    Fake("식물성유지", (("soy", "F"),)),
    Fake("쇼트닝", (("soy", "F"),)),
    Fake("마가린", (("milk", "P"), ("soy", "F"))),
    Fake("레시틴", (("soy", "I"),)),
    Fake("유화제", (("soy", "P"),)),
    Fake("액젓", (("fish", "I"),)),
    Fake("육수", (("fish", "P"),)),
    Fake("전분", (("wheat", "P"),)),
    Fake("김치", (("crustacean:shrimp", "I"), ("fish", "I"))),
    Fake("호두기름", (("tree_nut:walnut", "I"),)),
    Fake("아몬드오일", (("tree_nut:almond", "I"),)),
    Fake("고등어맛분말", (("fish:mackerel", "I"),)),
    Fake("땅콩유", (("peanut", "I"),)),
    Fake("맛베이스", opaque=True),                          # 국물·조미 계열: 생선만
    Fake("혼합조미분말", opaque=True),
    Fake("양념분말", opaque=True, opaque_sesame=True),      # 양념·소스 계열: 생선과 참깨
    Fake("해물", (("crustacean", "P"), ("fish", "P"))),
    Fake("키토산", (("crustacean", "I"),)),
    Fake("산양유", (("milk:goat", "C"),)),
    Fake("시즈닝", compound=True),
    Fake("향료", flavor=True),
    Fake("버터향", (("milk", "P"),), flavor=True),
    Fake("바닐라향베이스", opaque=True, flavor=True),
    Fake("원산지", not_ingredient=True),
    Fake("팜유"), Fake("설탕"), Fake("정제수"), Fake("정제소금"), Fake("식염"), Fake("돼지고기"),
]}


def fake(name):
    return TABLE.get(name) or Fake(name, via="unknown")


def run(text, declaration=None):
    """declaration을 주면 칸 입력(원재료명 + 표시란), 아니면 라벨 글자 전체로 본다."""
    if declaration is None:
        return judge(parse_label(text), resolve=fake)
    return judge(parse_label(ingredients=text, declaration=declaration), resolve=fake)


def got(j):
    return {v.allergen: v.verdict for v in j.allergens}


def one(j, allergen):
    return next(v for v in j.allergens if v.allergen == allergen)


# ---------- 1절: 원재료마다 근거 모으기 ----------
def test_leaf_uses_every_source():
    j = run("간장, 설탕")
    assert got(j) == {"wheat": "inferable", "soy": "confirmed"}


def test_parent_with_box_words_keeps_parent_flags_and_adds_confirmed():
    j = run("혼합조미분말(대두, 밀), 설탕", "없음")
    assert got(j) == {"fish": "undecidable", "wheat": "confirmed", "soy": "confirmed"}     # 국물·조미 계열이라 참깨는 없다
    soy = one(j, "soy")
    assert soy.evidence == "혼합조미분말" and soy.word == "대두"      # 근거 이름은 부모


def test_disclosed_parent_keeps_only_confirmed():
    j = run("간장(대두, 정제소금), 설탕")
    assert got(j) == {"soy": "confirmed"}                   # 간장의 밀 추정은 버리고 자식으로 본다


def test_disclosed_parent_drops_opaque_and_fat_flags():
    assert got(run("맛베이스(정제소금, 설탕), 설탕", "없음")) == {}
    j = run("식물성유지(팜유), 설탕", "대두 함유")
    assert one(j, "soy").verdict == "confirmed"            # 팜유라고 밝혔으니 유지는 대두 근거가 아니다


def test_disclosed_parent_still_keeps_confirmed_name():
    j = run("멸치액젓(식염), 설탕", "없음")
    assert got(j) == {"fish": "confirmed"}
    assert one(j, "fish").species == ("fish:anchovy",)


@pytest.mark.parametrize("text, expected", [
    ("대두유(대두), 설탕", {}),                                  # 정제유는 그대로 세지 않는다
    ("식물성유지(대두), 설탕", {"soy": "inferable"}),            # 대두 표시가 붙은 종류 모를 유지
    ("식물성유지(팜유, 대두), 설탕", {"soy": "inferable"}),
    ("토코페롤(대두, 정제소금), 설탕", {}),
    ("간장(대두, 밀), 설탕", {"soy": "confirmed", "wheat": "confirmed"}),   # 기름이 아니면 확정
])
def test_oil_exception_with_box(text, expected):
    assert got(run(text, "대두 함유")) == expected


def test_oil_exception_without_box():
    j = run("식물성유지(팜유, 대두), 설탕")                  # 표시란이 없어도 라벨이 대두에서 온 유지라고 밝혔다 -> 추정
    assert got(j) == {"soy": "inferable"} and one(j, "soy").basis == ("R1-1",)
    assert one(j, "soy").evidence == "식물성유지"
    j = run("대두유(대두), 설탕")                            # 정제유는 그래도 세지 않는다
    assert got(j) == {} and any(n.startswith("US-OIL: 대두유") for n in j.notes)


def test_not_ingredient_child_is_dropped():
    assert got(run("간장(원산지), 설탕")) == {"soy": "confirmed", "wheat": "inferable"}   # 간장은 잎


def test_not_ingredient_grandchildren_move_up():
    j = run("간장(원산지(대두, 밀)), 설탕")
    assert got(j) == {"soy": "confirmed", "wheat": "confirmed"}


def test_group_headers_are_skipped():
    j = run("면: 소맥분, 정제소금 / 스프: 간장, 설탕")
    assert got(j) == {"wheat": "confirmed", "soy": "confirmed"}
    assert one(j, "wheat").evidence == "소맥분" and one(j, "wheat").other_evidence == ("간장",)


# ---------- 2절과 4절: 표시란 ----------
def test_box_words_confirm_and_ignore_non_us9():
    j = run("정제수, 설탕", "새우, 돼지고기, 오징어 함유")
    assert got(j) == {"crustacean": "confirmed"}
    v = one(j, "crustacean")
    assert (v.evidence, v.basis, v.species, v.evidence_en) == ("표시란: 새우", ("KR-DECL",), ("crustacean:shrimp",),
                                                               "shrimp")


def test_r2_box_erases_likely_and_possible():
    assert got(run("간장, 설탕", "대두 함유")) == {"soy": "confirmed"}          # 밀 추정 삭제
    assert got(run("레시틴, 설탕", "우유 함유")) == {"milk": "confirmed"}       # 대두 추정 삭제
    assert got(run("전분, 설탕", "없음")) == {}                                 # 밀 가능 삭제
    assert got(run("마가린, 설탕", "없음")) == {}                               # 우유 가능 삭제


def test_r4_box_erases_only_covered_species():
    assert got(run("김치, 정제소금", "밀 함유")) == {"fish": "inferable", "wheat": "confirmed"}
    assert got(run("고등어맛분말", "없음")) == {}
    assert got(run("호두기름, 설탕", "없음")) == {}
    assert got(run("아몬드오일, 설탕", "없음")) == {"tree_nut": "inferable"}
    assert got(run("액젓, 설탕", "없음")) == {"fish": "inferable"}


def test_without_box_nothing_is_erased():
    assert got(run("김치, 전분")) == {"fish": "inferable", "crustacean": "inferable", "wheat": "undecidable"}


def test_r3_confirmed_ingredient_missing_from_box_is_noted():
    j = run("탈지분유, 꽃게, 크릴, 설탕", "땅콩 함유")
    assert got(j) == {"milk": "confirmed", "crustacean": "confirmed", "peanut": "confirmed"}
    assert "표시란 누락 의심: 우유 (원재료: 탈지분유)" in j.notes
    assert "표시란 누락 의심: 게 (원재료: 꽃게)" in j.notes
    assert not any("크릴" in n for n in j.notes)              # 크릴은 표시란이 덮지 않는다


def test_confirmed_ingredient_also_in_box():
    v = one(run("간장, 설탕", "대두 함유"), "soy")
    assert (v.evidence, v.basis) == ("간장", ("INGREDIENT", "KR-DECL"))


def test_box_confirms_non_soy_with_weaker_as_other_evidence():
    v = one(run("마가린, 설탕", "우유 함유"), "milk")
    assert (v.verdict, v.evidence, v.other_evidence) == ("confirmed", "표시란: 우유", ("마가린",))


# ---------- 4절 R1-1: 표시란의 대두 ----------
@pytest.mark.parametrize("text, expected", [
    ("정제수, 설탕", "confirmed"),            # 기름이 없으면 표시란대로
    ("대두유, 설탕", None),                   # 정제유만 있으면 세지 않는다
    ("쇼트닝, 설탕", "inferable"),            # 종류 모를 유지
    ("대두유, 맛베이스", "inferable"),         # 속 모를 원료
    ("대두유, 시즈닝", "inferable"),           # 섞은 원료
    ("대두유, 유화제", "inferable"),           # 가능 근거
    ("대두유, 레시틴", "confirmed"),           # 추정 근거가 있으면 확정
    ("맛베이스, 설탕", "confirmed"),           # 기름이 없으면 속 모를 원료가 있어도 확정
])
def test_r1_1_soy_in_box(text, expected):
    j = run(text, "대두 함유")
    assert got(j).get("soy") == expected


def test_r1_1_notes_and_other_evidence():
    j = run("대두유, 유화제, 쇼트닝, 맛베이스", "대두 함유")
    v = one(j, "soy")
    assert v.basis == ("R1-1",) and v.evidence == "표시란: 대두"
    assert v.other_evidence == ("유화제", "쇼트닝", "맛베이스")
    assert any(n.startswith("R1-1:") for n in j.notes)
    assert any(n.startswith("US-OIL: 대두유") for n in j.notes)


def test_refined_oil_only_is_noted():
    j = run("정제수, 대두유, 토코페롤", "대두 함유")
    assert got(j) == {}
    assert j.notes == ("US-OIL: 대두유, 토코페롤 (고도 정제유는 미국 기준 알레르기로 세지 않음)",)


def test_soy_without_box_ignores_oil_and_fat():
    assert got(run("대두유, 식물성유지, 설탕")) == {}


# ---------- 3절과 4절: 추정·판정 불가 ----------
def test_possible_makes_undecidable():
    v = one(run("육수, 정제소금", "없음"), "fish")
    assert (v.verdict, v.evidence, v.basis) == ("undecidable", "육수", ("POSSIBLE",))
    assert got(run("전분, 설탕")) == {"wheat": "undecidable"}


def test_opaque_with_box_targets_fish_and_sesame_by_family():
    j = run("맛베이스, 설탕", "없음")                         # 국물·조미 계열: 생선만 (참깨는 자료에서 2% 미만)
    assert got(j) == {"fish": "undecidable"} and one(j, "fish").basis == ("OPAQUE",)
    j = run("양념분말, 설탕", "없음")                         # 양념·소스 계열: 생선과 참깨
    assert got(j) == {"fish": "undecidable", "sesame": "undecidable"}
    assert one(j, "sesame").basis == ("OPAQUE",)


def test_opaque_without_box_adds_box_allergens():
    expected = {a: "undecidable" for a in ("milk", "egg", "fish", "crustacean", "wheat", "soy")}
    assert got(run("맛베이스, 설탕")) == expected               # 땅콩·견과류는 넣지 않는다
    assert got(run("양념분말, 설탕")) == dict(expected, sesame="undecidable")


def test_generic_crustacean_is_settled_by_crab_and_shrimp_words():
    """가이드 N12: 어느 갑각류인지 모르는 근거는 표시란에 게와 새우가 둘 다 없으면 지운다."""
    assert got(run("해물, 설탕", "없음")) == {"fish": "undecidable"}             # 생선은 표시란이 가리지 못한다
    assert got(run("키토산, 설탕", "없음")) == {}
    assert got(run("키토산, 설탕", "새우 함유")) == {"crustacean": "confirmed"}
    assert got(run("키토산, 설탕")) == {"crustacean": "inferable"}               # 표시란이 없으면 그대로
    assert got(run("크릴, 설탕", "없음")) == {"crustacean": "confirmed"}          # 이름에 적힌 갑각류는 확인됨


def test_goat_milk_is_milk_but_not_covered_by_korean_box():
    j = run("산양유, 설탕", "없음")
    assert got(j) == {"milk": "confirmed"}
    assert not any(n.startswith("표시란 누락 의심") for n in j.notes)             # 한국 '우유' 표시는 산양유를 덮지 않는다
    assert any(n.startswith("한·미 차이") for n in j.notes)


def test_compound_counts_only_without_box():
    assert got(run("시즈닝, 설탕", "없음")) == {}
    j = run("시즈닝, 설탕")
    assert got(j) == {a: "undecidable" for a in ("milk", "egg", "wheat", "soy")}
    assert one(j, "milk").basis == ("COMPOUND",)


def test_general_flavor_is_never_evidence():
    j = run("향료, 바닐라향베이스, 설탕")
    assert got(j) == {}
    assert j.undecidable_ingredients == ("향료", "바닐라향베이스")


def test_flavor_with_source_is_evidence():
    assert got(run("버터향, 설탕")) == {"milk": "undecidable"}


def test_strongest_wins_and_others_follow_strength():
    v = one(run("육수, 액젓, 멸치액젓, 맛베이스", "없음"), "fish")
    assert (v.verdict, v.evidence) == ("confirmed", "멸치액젓")
    assert v.other_evidence == ("액젓", "육수")


def test_undecidable_lists_possible_then_opaque():
    v = one(run("맛베이스, 육수, 혼합조미분말", "없음"), "fish")
    assert (v.evidence, v.other_evidence, v.basis) == ("육수", ("맛베이스", "혼합조미분말"), ("POSSIBLE", "OPAQUE"))


def test_first_confirmed_in_label_order():
    v = one(run("설탕, 간장, 대두"), "soy")
    assert v.evidence == "간장" and v.other_evidence == ("대두",)


# ---------- 5절: 나머지 칸 ----------
def test_undecidable_ingredients_order_and_compound_rule():
    j = run("모르는것, 맛베이스, 향료, 시즈닝, 맛베이스, 설탕")
    assert j.undecidable_ingredients == ("모르는것", "맛베이스", "향료", "시즈닝")
    j = run("모르는것, 맛베이스, 향료, 시즈닝, 설탕", "없음")
    assert j.undecidable_ingredients == ("모르는것", "맛베이스", "향료")


def test_read_flags():
    j = run("")
    assert not j.read_any and not j.box_read and j.allergens == ()
    j = run("원산지", "없음")
    assert not j.read_any and j.box_read


def test_output_follows_allergen_order():
    j = run("참기름, 땅콩유, 새우, 탈지분유")
    assert [v.allergen for v in j.allergens] == ["milk", "crustacean", "peanut", "sesame"]
