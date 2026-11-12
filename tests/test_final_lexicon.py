"""최종본 원재료 사전 테스트. 실행: python -m pytest -q

표(TSV)의 형식이 깨지지 않았는지, 헷갈리는 이름이 가이드대로 나오는지 본다.
"""
import csv
from pathlib import Path

import pytest

from src.final import lexicon
from src.final.lexicon import GRADES, lookup, norm

TABLES = Path(lexicon.__file__).parent
US9 = {"milk", "egg", "wheat", "soy", "peanut", "sesame", "fish", "crustacean", "tree_nut"}


def rows(filename):
    with open(TABLES / filename, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


# ---------- 표의 형식 ----------
def test_source_table_maps_to_us9_or_nothing():
    for r in rows("sources.tsv"):
        assert r["us9"] in US9 | {""}, r
        assert r["en"] and r["ko"], r


def test_every_code_and_grade_in_entries_is_known():
    codes = {r["code"] for r in rows("sources.tsv")}
    for r in rows("entries.tsv"):
        for token in r["sources"].split():
            code, grade = token.rsplit(":", 1)
            assert code in codes, r["name"]
            assert grade in GRADES, r["name"]
        assert set(r["flags"]) <= set("OVX"), r["name"]


def test_every_rule_uses_known_code_and_grade():
    codes = {r["code"] for r in rows("sources.tsv")}
    special = {"OPAQUE", "FLAVOR", "FLAVOR_END", "BENIGN"}
    seen = set()
    for r in rows("rules.tsv"):
        assert r["id"] not in seen, r["id"]
        seen.add(r["id"])
        if r["id"] in special:
            continue
        assert r["source"] in codes and r["grade"] in GRADES and r["include"], r["id"]
    assert special <= seen


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
    # 밀
    ("밀", {"wheat": "C"}), ("밀-미국산", {"wheat": "C"}), ("소맥분", {"wheat": "C"}), ("빵가루", {"wheat": "C"}),
    ("글루텐", {"wheat": "C"}), ("당밀", {}), ("오트밀분말", {}), ("메밀가루", {}), ("보리", {}), ("당면", {}),
    ("전분", {"wheat": "P"}), ("쌀국수", {"wheat": "I"}),
    # 대두와 정제유
    ("간장", {"soy": "C", "wheat": "I"}), ("한식간장", {"soy": "C"}), ("된장", {"soy": "C", "wheat": "I"}),
    ("고추장", {"soy": "I", "wheat": "I"}), ("대두유", {"soy": "R"}), ("d-토코페롤", {"soy": "R"}),
    ("DL-α-토코페롤", {}), ("식물성유지", {"soy": "F"}), ("레시틴", {"soy": "I"}), ("대두레시틴", {"soy": "C"}),
    ("유화제", {"soy": "P"}), ("콩나물", {"soy": "C"}), ("완두콩", {}), ("두유", {"soy": "C"}),
    # 땅콩, 우유, 달걀
    ("땅콩버터", {"peanut": "C"}), ("땅콩호박", {}), ("코코아버터", {}), ("코코넛밀크", {}),
    ("카제인나트륨", {"milk": "C"}), ("유청분말", {"milk": "C"}), ("젖산", {}), ("유산균", {}),
    ("식물성크림", {"milk": "I"}), ("난각칼슘", {"egg": "I"}), ("마요네즈", {"egg": "C"}),
    # 참깨
    ("참기름", {"sesame": "C"}), ("깨", {"sesame": "C"}), ("들기름", {}), ("깻잎", {}),
    # 생선, 갑각류, 연체류
    ("멸치액젓", {"fish": "C"}), ("액젓", {"fish": "I"}), ("고등어", {"fish": "C"}), ("연육", {"fish": "C"}),
    ("게맛살", {"fish": "C", "crustacean": "I"}), ("새우젓", {"crustacean": "C"}), ("크릴", {"crustacean": "C"}),
    ("오징어", {}), ("김치", {"fish": "I", "crustacean": "I"}),
    # 견과류
    ("아몬드", {"tree_nut": "C"}), ("잣", {"tree_nut": "C"}), ("호두기름", {"tree_nut": "I"}), ("코코넛", {}), ("밤", {}),
    # 규칙이 속기 쉬운 글자
    ("발아귀리", {}), ("차조기농축액", {}), ("수크랄로스", {}), ("커피시럽", {}), ("다시마엑기스", {}),
]


@pytest.mark.parametrize("name, expected", CASES)
def test_us9_verdict(name, expected):
    assert lookup(name).us == expected


def test_species_is_kept_for_display():
    assert dict(lookup("멸치액젓").sources).get("fish:anchovy") == "C"
    assert dict(lookup("고등어").sources) == {"fish:mackerel": "C"}       # 한국 표시란이 덮는 유일한 생선
    assert dict(lookup("오징어").sources)                                 # 미국 9개 밖이어도 무엇인지는 안다


def test_opaque_flavor_and_non_ingredient_flags():
    assert lookup("복합조미식품").opaque and lookup("맛베이스").opaque
    assert lookup("굴소스").opaque and lookup("굴소스").us == {"soy": "I", "wheat": "I"}
    assert lookup("합성착향료").flavor and not lookup("합성착향료").us
    assert lookup("헤이즐넛향").flavor and lookup("헤이즐넛향").us == {"tree_nut": "I"}
    assert lookup("알수없음").not_ingredient
    assert not lookup("다시마엑기스").opaque             # 원료 하나의 추출물은 속 모를 원료가 아니다


def test_flavored_names_are_downgraded():
    assert lookup("새우맛분말").us == {"crustacean": "I"}
    assert lookup("명란마요맛시즈닝").us["fish"] == "I"
    assert lookup("홍게맛살").us == {"fish": "C", "crustacean": "I"}
    assert lookup("초콜릿향").us == {"milk": "P"}


def test_lookup_route():
    assert lookup("밀").via == "entry"
    assert lookup("볶음검정참깨분말").via == "rule"
    assert lookup("비피도박테리움브레베").via == "benign"
    assert lookup("미감에스유").via == "unknown" and not lookup("미감에스유").us
    assert lookup("").via == "unknown"


def test_spacing_and_hyphens_do_not_matter():
    assert lookup("대두 레시틴").us == lookup("대두레시틴").us
    assert lookup("땅콩 또는 견과류가공품").us == lookup("땅콩또는견과류가공품").us


def test_rejects_non_string():
    with pytest.raises(TypeError):
        lookup(None)
