"""LLM이 정한 근거의 표시(LLM-FIX, LLM)와 추정 상한. 실행: python -m pytest -q

- LLM이 고친 이름(via 'ocrfix', #15)은 사전에서 확정이어도 추정으로 낮춘다. 표시란 규칙은 그대로 적용된다.
- 사전에 없는 이름을 LLM이 판단한 것(via 'fallback')은 basis가 LLM이다.
- 같은 알레르기에 사전 근거가 있으면 대표 근거는 사전 근거다.
"""
import pytest

from src.common.schema import Allergen, AllergenMatch, IngredientClassification, Verdict
from src.final import pipeline
from src.final.lexicon import Lookup, lookup
from src.final.parser import parse_label
from src.final.pipeline import _result, analyze_text
from src.final.resolve import Resolver
from src.final.verdict import judge


def unknown(name):
    assert lookup(name).via == "unknown", f"사전이 '{name}'을 알게 됐다. 테스트 이름을 바꿀 것"
    return name


def resolver_with(table):
    """table의 이름은 정해 준 Lookup으로, 나머지는 사전으로."""
    return lambda name: table.get(name) or lookup(name)


def by_allergen(j):
    return {v.allergen: v for v in j.allergens}


FIX = {"유우": Lookup(name="유우", sources=(("milk", "C"),), via="ocrfix", en="milk")}


def test_fixed_name_is_likely_not_confirmed():
    j = judge(parse_label(ingredients=unknown("유우") + ", 설탕"), resolve=resolver_with(FIX))
    v = by_allergen(j)["milk"]
    assert (v.verdict, v.basis, v.evidence) == ("inferable", ("LLM-FIX",), "유우")


def test_box_still_decides_box_covered_allergens():
    with_milk = by_allergen(judge(parse_label(ingredients="유우, 설탕", declaration="우유"), resolve=resolver_with(FIX)))
    assert (with_milk["milk"].verdict, with_milk["milk"].basis) == ("confirmed", ("KR-DECL",))
    assert with_milk["milk"].other_evidence == ("유우",)
    # 표시란을 읽었는데 우유가 없으면 LLM 추측은 다른 추정 근거처럼 지운다 (R2)
    without = by_allergen(judge(parse_label(ingredients="유우, 설탕", declaration="대두"), resolve=resolver_with(FIX)))
    assert "milk" not in without


def test_dictionary_evidence_is_preferred_as_representative():
    table = dict(FIX, 가나다라=Lookup(name="가나다라", sources=(("milk", "I"),), via="entry"))
    v = by_allergen(judge(parse_label(ingredients="유우, 가나다라"), resolve=resolver_with(table)))["milk"]
    assert (v.evidence, v.basis, v.other_evidence) == ("가나다라", ("LIKELY",), ("유우",))


def test_llm_guess_marks():
    table = {"헤즐너트페이스트": Lookup(name="헤즐너트페이스트", sources=(("tree_nut", "I"),), via="fallback"),
             "알에프비케이": Lookup(name="알에프비케이", sources=(("sesame", "P"),), via="fallback")}
    got = by_allergen(judge(parse_label(ingredients="헤즐너트페이스트, 알에프비케이"), resolve=resolver_with(table)))
    assert (got["tree_nut"].verdict, got["tree_nut"].basis) == ("inferable", ("LLM",))
    assert (got["sesame"].verdict, got["sesame"].basis) == ("undecidable", ("LLM",))


def test_reason_names_the_fix_and_the_ai():
    j = judge(parse_label(ingredients="유우, 설탕"), resolve=resolver_with(FIX))
    v = by_allergen(j)["milk"]
    res = _result(v, {"유우": "우유"})
    assert res.read_as == "우유" and res.explanation_en is None
    assert res.reason_en == "Likely contains milk: the label text “유우” looks like a misread of 우유 (milk)."
    assert res.reason_ko == "라벨 글자 “유우”는 우유를 잘못 읽은 것으로 보인다."
    plain = _result(v)                                           # 고친 이름을 모를 때
    assert plain.read_as is None and plain.reason_en.endswith("a misread of an ingredient that contains milk.")


class FakeLLM:
    """팀 Classifier 인터페이스(classify)를 지키는 가짜 LLM 분류기."""
    name, prompt_version = "fake", None

    def __init__(self, table):
        self.table = table

    def classify(self, names):
        return [IngredientClassification(ingredient=n, matches=[AllergenMatch(allergen=a, verdict=v)])
                for n, (a, v) in self.table.items() if n in names]


def test_end_to_end_with_fallback_on(monkeypatch):
    fake = FakeLLM({unknown("헤즐너트페이스트"): (Allergen.tree_nut, Verdict.confirmed)})
    monkeypatch.setattr(pipeline, "_fallback", lambda: fake)
    res = analyze_text("원재료명: 설탕, 헤즐너트페이스트, 코코아분말")
    nut = next(a for a in res.allergens if a.allergen.value == "tree_nut")
    assert (nut.verdict.value, nut.basis) == ("inferable", ["LLM"])               # LLM의 확정은 추정으로 낮춘다
    assert nut.reason_en == ("Likely contains tree nuts: “헤즐너트페이스트” is not in our ingredient dictionary, "
                             "and an AI model judged that it likely contains tree nuts.")


class FakeFixLLM(FakeLLM):
    """#15의 correct_and_classify: (분류, 고친 이름) 짝을 돌려준다."""

    def __init__(self, table, fixes):
        super().__init__(table)
        self.fixes = fixes

    def correct_and_classify(self, names):
        return [(r, self.fixes.get(r.ingredient, "")) for r in self.classify(names)]


@pytest.mark.skipif(not hasattr(Resolver, "_ask_with_fix"), reason="#15(오인식 보정)가 들어온 뒤에 돈다")
def test_end_to_end_ocr_fix_is_likely_with_read_as(monkeypatch):
    fake = FakeFixLLM({unknown("유우"): (Allergen.milk, Verdict.confirmed)}, {"유우": "우유"})
    monkeypatch.setattr(pipeline, "_fallback", lambda: fake)
    res = analyze_text("원재료명: 유우, 설탕")
    milk = next(a for a in res.allergens if a.allergen.value == "milk")
    assert (milk.verdict.value, milk.basis, milk.read_as) == ("inferable", ["LLM-FIX"], "우유")
    assert "misread of 우유" in milk.reason_en
