"""같은 시설 문구 -> shared_facility (src/final/facility.py). 실행: python -m pytest -q

판정은 바꾸지 않고, 판정이 없는 알레르기만 고정 문장과 함께 따로 담는지 본다.
"""
from src.final.facility import facility_words, shared_facility
from src.final.pipeline import analyze_fields, analyze_text

# 동원고추참치 라벨의 문구 (EXP-006 사진)
GOCHU = ("이 제품은 알류, 우유, 메밀, 땅콩, 고등어, 새우, 게, 쇠고기, 돼지고기, 닭고기, 복숭아, 아황산류, 오징어, 잣, 호두, "
         "조개류(전복, 홍합 등 포함)를 사용한 제품과 같은 제조시설에서 제조하고 있습니다.")
LABEL = "원재료명: 가다랑어, 고추장(소맥분, 대두), 설탕\n알레르기 유발물질: 밀, 대두 함유\n"


def verdicts(res):
    return [(a.allergen.value, a.verdict.value, list(a.basis)) for a in res.allergens]


def test_words_are_mapped_to_us9_in_us9_order():
    assert facility_words(GOCHU) == {
        "milk": ("우유",), "egg": ("알류",), "fish": ("고등어",), "crustacean": ("새우", "게"),
        "tree_nut": ("잣", "호두"), "peanut": ("땅콩",),
    }                                    # 메밀·쇠고기·오징어·조개류처럼 미국 9개 밖은 뺀다


def test_josa_is_dropped_but_words_must_match_whole():
    text = "본 제품은 땅콩을 사용한 제품과 동일한 시설에서 생산, 밀과 대두를 쓰는 라인, 새우, 게를"
    assert facility_words(text) == {"crustacean": ("새우", "게"), "peanut": ("땅콩",), "wheat": ("밀",), "soy": ("대두",)}
    assert facility_words("이 제품은 같은 시설에서 제조하게 됩니다") == {}      # '하게'의 '게'는 낱말이 아니다
    assert facility_words("메밀, 오징어, 조개류를 사용한 제품과 같은 시설") == {}
    assert facility_words(None) == {} and facility_words("") == {}


def test_decided_allergens_are_left_out():
    notes = shared_facility(GOCHU, decided={"fish", "milk"})
    assert [n.allergen for n in notes] == ["egg", "crustacean", "tree_nut", "peanut"]


def test_sentence_says_not_an_ingredient_and_traces_possible():
    notes = {n.allergen: n for n in shared_facility(GOCHU)}
    assert notes["peanut"].reason_en == (
        "Peanuts are not listed as an ingredient, but this product is made in a facility that also handles peanuts, "
        "so traces are possible. Avoid it if your allergy is severe.")
    assert "handles shrimp and crab," in notes["crustacean"].reason_en           # 종을 아는 낱말은 그 종으로
    assert "handles pine nuts and walnuts," in notes["tree_nut"].reason_en
    assert "handles mackerel," in notes["fish"].reason_en and notes["fish"].reason_en.startswith("Fish is not")
    assert notes["crustacean"].reason_ko == ("원재료에 갑각류는 없지만, 새우, 게를 쓰는 제품과 같은 시설에서 만들어 "
                                             "미량이 섞일 수 있다. 알레르기가 심하면 피하는 것이 좋다.")


def test_facility_text_does_not_change_verdicts():
    plain, with_facility = analyze_text(LABEL), analyze_text(LABEL + GOCHU)
    assert verdicts(plain) == verdicts(with_facility)
    assert plain.shared_facility == []
    # 생선은 가다랑어로 이미 확정이라 빠진다 (문구의 고등어보다 판정이 강한 정보다)
    assert [f.allergen.value for f in with_facility.shared_facility] == ["milk", "egg", "crustacean", "tree_nut", "peanut"]
    assert any(n.startswith("같은 시설 문구(판정에 쓰지 않음)") for n in with_facility.notes)    # 참고 문장은 그대로


def test_fields_input_and_json_shape():
    res = analyze_fields("설탕, 소맥분, " + GOCHU, "밀")
    body = res.model_dump(mode="json")
    first = body["shared_facility"][0]
    assert first == {"allergen": "milk", "words": ["우유"], "reason_en": first["reason_en"], "reason_ko": first["reason_ko"]}
    assert "wheat" not in [f["allergen"] for f in body["shared_facility"]]
    assert all(a["explanation_en"] is None and a["read_as"] is None for a in body["allergens"])


# ---------- '이 제품은'이 없는 같은 시설 문구 (11/20, EXP-006 사진의 OCR 글자에서 나온 꼴) ----------
def facility_of(text):
    res = analyze_text(text)
    return res, {a.allergen.value: a.verdict.value for a in res.allergens}, [f.allergen.value for f in res.shared_facility]


def test_short_mix_form_is_not_read_as_ingredients():
    # 치토스 라벨: 짧은 꼴을 원재료로 읽으면 우유·땅콩·갑각류가 Contains로 잘못 나왔다
    res, got, fac = facility_of("원재료명: 설탕, 밀가루, 옥수수전분\n우유,땅콩,새우,돼지고기,토마토 혼입 가능")
    assert got == {"wheat": "confirmed"}
    assert fac == ["milk", "crustacean", "peanut"]
    assert res.ingredients_text == "설탕, 밀가루, 옥수수전분"


def test_mix_form_with_particle_and_long_ending():
    _, got, fac = facility_of("원재료명: 설탕, 소맥분\n땅콩, 호두가 혼입될 수 있습니다.")
    assert got == {"wheat": "confirmed"} and fac == ["tree_nut", "peanut"]


def test_same_plant_sentence_without_this_product():
    # 오징어짬뽕 OCR: 줄이 나뉘어 '이 제품은'이 빠지고 첫 낱말(메밀)이 '매일'로 깨졌다. 표시란 낱말부터 자른다
    _, got, fac = facility_of("원재료명: 설탕, 밀가루\n매일, 땅콩, 고등어, 게, 호두를 사용한 제품과 같은 시설에서 제조 하고 있습니다.")
    assert "peanut" not in got and "crustacean" not in got and "fish" not in got
    assert fac == ["fish", "crustacean", "tree_nut", "peanut"]


def test_only_allergen_words_before_the_notice_are_taken():
    # 앞의 원재료(설탕, 밀가루)는 남기고 바로 앞의 표시란 낱말만 문구로 본다 ('…, 밀, 대두 함유' 표시란과 같은 방법)
    res, got, fac = facility_of("원재료명: 설탕, 밀가루, 우유, 땅콩 혼입 가능")
    assert got == {"wheat": "confirmed"} and fac == ["milk", "peanut"]
    assert res.ingredients_text == "설탕, 밀가루"


def test_notice_ends_at_its_last_word():
    res, _, fac = facility_of("원재료명: 설탕\n땅콩 혼입 가능 내용량 100g")
    assert fac == ["peanut"] and "내용량" not in (res.notes[-1] if res.notes else "")


def test_other_mix_sentences_are_left_alone():
    # 표시란 낱말이 앞에 없으면 같은 시설 문구가 아니다
    _, got, fac = facility_of("원재료명: 설탕, 우유\n이물질이 혼입되지 않도록 주의하세요")
    assert got == {"milk": "confirmed"} and fac == []
    _, got, fac = facility_of("원재료명: 설탕, 우유, 땅콩")
    assert got == {"milk": "confirmed", "peanut": "confirmed"} and fac == []


def test_fields_input_short_form():
    res = analyze_fields("설탕, 밀가루, 땅콩 혼입가능", "밀")
    assert {a.allergen.value for a in res.allergens} == {"wheat"}
    assert [f.allergen.value for f in res.shared_facility] == ["peanut"]
