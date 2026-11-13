"""최종본 파이프라인 통합 테스트 (실제 원재료 사전 사용). 실행: python -m pytest -q

작업 사양서의 '꼭 넣을 테스트 사례' 15개와 응답 형식, 팀 분류기 인터페이스를 본다.
사전 판정이 바뀌어 여기가 깨지면 규칙이 아니라 사전 값을 먼저 확인한다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.common.schema import AnalyzeResponse
from src.final.classifier import FinalClassifier
from src.final.pipeline import NO_BOX, NO_INGREDIENTS, analyze_fields, analyze_text, split_facility
from src.ocr import MockOcr
from src.pipeline import analyze as team_analyze

REPO = Path(__file__).resolve().parents[1]


def got(res):
    return {a.allergen.value: a.verdict.value for a in res.allergens}


def one(res, allergen):
    return next(a for a in res.allergens if a.allergen.value == allergen)


# ---------- 사양서의 사례 1~15 ----------
def test_case01_team_mock_sample():
    res = analyze_text(MockOcr.SAMPLE)
    assert got(res) == {"milk": "confirmed", "fish": "confirmed", "wheat": "confirmed", "soy": "confirmed",
                        "sesame": "confirmed"}
    assert [one(res, a).evidence_ingredient for a in ("milk", "fish", "wheat", "sesame")] == \
        ["탈지분유", "멸치분말", "소맥분", "참기름"]
    soy = one(res, "soy")
    assert "식물성유지" not in [soy.evidence_ingredient] + soy.other_evidence     # 식물성유지(팜유)는 대두 근거가 아니다
    assert res.warnings == [NO_BOX]


def test_case02_opaque_with_box():
    res = analyze_text("정제수, 맛베이스, 정제소금, 대두, 밀 함유")
    assert got(res) == {"soy": "confirmed", "wheat": "confirmed", "fish": "undecidable"}     # 국물·조미 계열: 생선만
    assert one(res, "soy").evidence_ingredient == "표시란: 대두"
    res = analyze_text("정제수, 양념분말, 정제소금, 대두, 밀 함유")                          # 양념·소스 계열: 참깨도
    assert got(res) == {"soy": "confirmed", "wheat": "confirmed", "sesame": "undecidable", "fish": "undecidable"}


def test_case03_refined_soybean_oil():
    res = analyze_text("정제수, 대두유, 정제소금, 대두 함유")
    assert "soy" not in got(res)
    assert any(n.startswith("US-OIL") for n in res.notes)


def test_case04_shortening_r1_1():
    res = analyze_text("밀가루, 쇼트닝, 설탕, 밀, 대두 함유")
    assert got(res) == {"wheat": "confirmed", "soy": "inferable"}
    assert one(res, "soy").basis == ["R1-1"]


def test_case05_soy_sauce():
    assert got(analyze_text("간장, 설탕, 대두 함유")) == {"soy": "confirmed"}         # 밀은 R2로 지운다
    res = analyze_text("간장, 설탕")
    assert got(res) == {"soy": "confirmed", "wheat": "inferable"}
    assert len(res.warnings) == 1


def test_case06_lecithin_erased_by_box():
    res = analyze_text("레시틴, 설탕, 우유 함유")
    assert got(res) == {"milk": "confirmed"}
    assert one(res, "milk").evidence_ingredient == "표시란: 우유"


def test_case07_fish_sauce_and_kimchi():
    assert got(analyze_fields("액젓, 고춧가루", "없음")) == {"fish": "inferable"}
    res = analyze_text("김치, 정제소금, 밀 함유")
    assert got(res) == {"fish": "inferable", "wheat": "confirmed"}               # 새우가 표시란에 없다


def test_case08_possible_ingredients():
    assert got(analyze_fields("육수, 정제소금", "없음")) == {"fish": "undecidable"}
    assert got(analyze_fields("전분, 설탕", "없음")) == {}
    assert got(analyze_text("전분, 설탕")) == {"wheat": "undecidable"}


def test_case09_opaque_parent_with_box_words():
    res = analyze_text("혼합조미분말(대두, 밀), 설탕, 대두, 밀 함유")
    assert got(res) == {"soy": "confirmed", "wheat": "confirmed", "fish": "undecidable"}


def test_case10_oil_with_soy_in_parentheses():
    assert "soy" not in got(analyze_text("대두유(대두), 설탕, 대두 함유"))
    assert got(analyze_text("식물성유지(대두), 설탕, 대두 함유")) == {"soy": "inferable"}


def test_case11_disclosed_parent_keeps_confirmed():
    res = analyze_fields("멸치액젓(식염), 설탕", "없음")
    assert got(res) == {"fish": "confirmed"}
    assert one(res, "fish").species == ["anchovy"]


def test_case12_nut_oils():
    assert got(analyze_fields("호두기름, 설탕", "없음")) == {}
    assert got(analyze_fields("아몬드오일, 설탕", "없음")) == {"tree_nut": "inferable"}


def test_case13_box_words():
    res = analyze_text("정제수, 설탕, 새우 함유")
    assert got(res) == {"crustacean": "confirmed"}
    assert one(res, "crustacean").evidence_ingredient == "표시란: 새우"
    assert got(analyze_text("정제수, 설탕, 돼지고기 함유")) == {}


def test_case14_facility_sentence_is_only_a_note():
    text = "원재료명: 정제수, 설탕. 이 제품은 메밀, 땅콩을 사용한 제품과 같은 제조시설에서 제조하고 있습니다. 밀 함유"
    res = analyze_text(text)
    assert got(res) == {"wheat": "confirmed"}
    assert any("땅콩을 사용한 제품과 같은 제조시설" in n for n in res.notes)


def test_case14_facility_sentence_in_ingredient_field():
    res = analyze_fields("정제수, 설탕, 이 제품은 땅콩, 우유를 사용한 제품과 같은 제조시설에서 제조하고 있습니다.", "밀 함유")
    assert got(res) == {"wheat": "confirmed"}
    assert any("땅콩, 우유를 사용한" in n for n in res.notes)
    assert "땅콩" not in res.ingredients_text


def test_facility_sentence_without_period_keeps_following_ingredients():
    res = analyze_fields("정제수, 이 제품은 땅콩을 사용한 제품과 같은 제조시설에서 제조, 간장, 새우", "밀 함유")
    assert got(res) == {"crustacean": "confirmed", "wheat": "confirmed", "soy": "confirmed"}
    assert any("같은 제조시설에서 제조" in n for n in res.notes)


def test_case15_same_input_same_json():
    a = analyze_text(MockOcr.SAMPLE).model_dump_json()
    b = analyze_text(MockOcr.SAMPLE).model_dump_json()
    assert a == b


def test_case15_same_json_across_processes():
    """문자열 해시 순서가 달라도(PYTHONHASHSEED) 글자까지 같다."""
    code = ("import sys; from src.final.pipeline import analyze_text; "
            "sys.stdout.write(analyze_text(sys.argv[1]).model_dump_json())")
    text = "혼합조미분말(대두, 밀), 김치, 육수, 대두유, 새우, 꽃게 함유"
    outs = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        done = subprocess.run([sys.executable, "-c", code, text], cwd=REPO, env=env, capture_output=True,
                              check=True, timeout=60)
        outs.append(done.stdout)
    assert outs[0] == outs[1]


# ---------- 응답 형식 ----------
def test_response_extends_team_format():
    res = analyze_text("원재료명: 멸치액젓, 간장, 설탕, 대두 함유")
    body = json.loads(res.model_dump_json())
    assert set(body) >= {"ingredients_text", "ingredients", "allergens", "undecidable_ingredients", "warnings",
                         "meta", "declaration_text", "declared", "notes"}
    team = AnalyzeResponse.model_validate(body)                 # 팀 형식으로 읽어도 통과한다
    assert [a.allergen.value for a in team.allergens] == ["fish", "soy"]
    assert body["meta"] == {"ocr_engine": "text", "classifier": "final-lexicon-v1", "prompt_version": None}
    assert body["declaration_text"] == "대두 함유" and body["declared"] == ["대두"]
    fish = body["allergens"][0]
    assert set(fish) >= {"basis", "species", "evidence_en", "reason_en", "reason_ko"}
    assert fish["reason_en"].startswith("Contains fish: “멸치액젓”")


@pytest.mark.parametrize("text, allergen, start", [
    ("정제수, 설탕, 새우 함유", "crustacean", "Listed in the Korean allergen statement: 새우 (shrimp)."),
    ("간장, 설탕", "wheat", "Likely contains wheat: “간장” is usually made with wheat."),
    ("육수, 설탕, 밀 함유", "fish", "Cannot tell: “육수” sometimes contains fish."),
    ("양념분말, 설탕, 밀 함유", "sesame", "Cannot tell: “양념분말” is a seasoning blend whose contents are not listed, "
                                          "and Korean labels do not have to declare sesame."),
])
def test_reason_sentences(text, allergen, start):
    a = one(analyze_text(text), allergen)
    assert a.reason_en == start
    assert a.reason_ko.endswith("다.")


def test_group_headers_marked_in_tree():
    res = analyze_text("면: 소맥분, 정제소금 / 스프: 간장")
    assert [(n.name, n.group) for n in res.ingredients] == [("면", True), ("스프", True)]
    assert res.ingredients[0].children[0].group is False


def test_nothing_read_warns_twice():
    res = analyze_text("")
    assert res.allergens == [] and res.warnings == [NO_INGREDIENTS, NO_BOX]


def test_fields_without_declaration_means_box_not_found():
    res = analyze_fields("간장, 설탕", "알수없음")
    assert res.declaration_text is None and res.warnings == [NO_BOX]


def test_split_facility_checks_input():
    assert split_facility(None) == ("", None)
    assert split_facility("정제수, 설탕") == ("정제수, 설탕", None)
    with pytest.raises(TypeError):
        split_facility(123)
    with pytest.raises(ValueError):
        split_facility("가" * 20001)


def test_bracket_repairs_are_noted():
    res = analyze_text("소스(간장, 설탕")
    assert any("괄호 짝을 1번" in n for n in res.notes)


# ---------- 팀 분류기 인터페이스 ----------
def test_final_classifier_grades():
    names = ["간장", "대두유", "맛베이스", "참기름", "멸치액젓", "향료", "모르는원재료xyz"]
    out = {r.ingredient: r for r in FinalClassifier().classify(names)}
    assert [r.ingredient for r in FinalClassifier().classify(names)] == names
    matches = {n: {m.allergen.value: m.verdict.value for m in r.matches} for n, r in out.items()}
    assert matches["간장"] == {"soy": "confirmed", "wheat": "inferable"}
    assert matches["대두유"] == {} and not out["대두유"].source_unknown
    assert matches["맛베이스"] == {"fish": "undecidable", "sesame": "undecidable"}
    assert matches["참기름"] == {"sesame": "confirmed"}
    assert matches["멸치액젓"] == {"fish": "confirmed"}
    assert out["향료"].source_unknown and out["모르는원재료xyz"].source_unknown


def test_final_classifier_in_team_pipeline():
    res = team_analyze(b"x", "image/jpeg", MockOcr(), FinalClassifier())
    assert res.meta.classifier == "final-lexicon"
    assert {"milk", "fish", "wheat", "soy", "sesame"} <= {a.allergen.value for a in res.allergens}


def test_final_classifier_rejects_plain_string():
    with pytest.raises(TypeError):
        FinalClassifier().classify("간장")
