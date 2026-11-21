"""may contain 항목의 LLM 설명 (src/final/explain.py, docs/10_may_contain.md 4절). 실행: python -m pytest -q"""
import json
import types

import pytest

from src.final import explain as ex
from src.final.pipeline import analyze_text
from src.final.response import FinalAnalyzeResponse

LABEL = ("원재료명: 밀가루, 해물양념분말, 간장, 대두유, 설탕 / 알레르기 유발물질: 밀, 대두 함유 / "
         "이 제품은 땅콩을 사용한 제품과 같은 제조시설에서 제조하고 있습니다.")

# docs/10 2절 응답 예 (LLM-FIX, LLM, OPAQUE)
DOC_EXAMPLE = {
    "ingredients_text": "밀가루, 회류, 헤즐너트페이스트, 해물양념분말, 설탕",
    "ingredients": [],
    "declaration_text": "밀 함유",
    "meta": {"ocr_engine": "none", "classifier": "final"},
    "allergens": [
        {"allergen": "wheat", "verdict": "confirmed", "evidence_ingredient": "밀가루", "basis": ["INGREDIENT", "KR-DECL"],
         "reason_en": "Contains wheat: “밀가루” (wheat flour)."},
        {"allergen": "fish", "verdict": "inferable", "evidence_ingredient": "회류", "other_evidence": ["해물양념분말"],
         "basis": ["LLM-FIX"], "read_as": "어류",
         "reason_en": "Likely contains fish: the label text “회류” looks like a misread of 어류 (fish)."},
        {"allergen": "tree_nut", "verdict": "inferable", "evidence_ingredient": "헤즐너트페이스트", "basis": ["LLM"],
         "reason_en": "Likely contains tree nuts: “헤즐너트페이스트” is not in our ingredient dictionary, and an AI model judged that it likely contains tree nuts."},
        {"allergen": "sesame", "verdict": "undecidable", "evidence_ingredient": "해물양념분말", "basis": ["OPAQUE"],
         "reason_en": "Cannot tell: “해물양념분말” is a seasoning blend whose contents are not listed, and Korean labels do not have to declare sesame."},
    ],
    "shared_facility": [{"allergen": "peanut", "words": ["땅콩"], "reason_en": "Peanuts are not listed as an ingredient, but ..."}],
}

GOOD = {
    "fish": "Part of the label was hard to read. “회류” is most likely 어류, the Korean word for fish.",
    "tree_nut": "“헤즐너트페이스트” appears to be a spelling variant of hazelnut paste, which is made from hazelnuts, a tree nut.",
    "sesame": "Seafood seasoning powders in Korea are often blends of salt, seafood extracts and spices, and some include sesame.",
}


def doc_response():
    return FinalAnalyzeResponse.model_validate(DOC_EXAMPLE)


class Fake:
    """가짜 LLM. 받은 입력을 기록하고, 정해 둔 설명을 돌려준다."""

    def __init__(self, answers=None, raise_exc=None):
        self.answers = GOOD if answers is None else answers
        self.raise_exc = raise_exc
        self.calls = []

    def __call__(self, system, user):
        self.calls.append(json.loads(user))
        if self.raise_exc:
            raise self.raise_exc
        return {"results": [{"allergen": a, "explanation": t} for a, t in self.answers.items()]}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    ex.clear_cache()
    monkeypatch.delenv(ex.ENV, raising=False)


def test_off_by_default_never_calls(monkeypatch):
    monkeypatch.setattr(ex, "_env_call", lambda: pytest.fail("꺼져 있으면 LLM을 부르면 안 된다"))
    res = doc_response()
    assert ex.explain(res) is res


def test_on_without_key_returns_unchanged(monkeypatch):
    monkeypatch.setenv(ex.ENV, "llm")
    for k in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(ex, "_default_call", None)
    res = doc_response()
    assert ex.explain(res) is res


def test_fills_only_may_contain_and_keeps_verdicts():
    res, fake = doc_response(), Fake()
    out = ex.explain(res, call=fake)
    got = {a.allergen.value: a for a in out.allergens}
    assert got["wheat"].explanation_en is None                      # confirmed는 설명하지 않는다
    assert got["fish"].explanation_en == GOOD["fish"]
    assert got["tree_nut"].explanation_en == GOOD["tree_nut"]
    assert got["sesame"].explanation_en == GOOD["sesame"]
    before = [a.model_dump(exclude={"explanation_en"}) for a in res.allergens]
    after = [a.model_dump(exclude={"explanation_en"}) for a in out.allergens]
    assert before == after                                          # 판정·근거·이유는 그대로
    assert out.shared_facility == res.shared_facility
    assert all(a.explanation_en is None for a in res.allergens)     # 원래 응답은 바꾸지 않는다


def test_one_call_per_product_with_decided_fields():
    fake = Fake()
    ex.explain(doc_response(), call=fake)
    assert len(fake.calls) == 1
    items = {i["allergen"]: i for i in fake.calls[0]["items"]}
    assert set(items) == {"fish", "tree_nut", "sesame"}             # confirmed는 보내지 않는다
    assert items["fish"]["read_as"] == "어류" and items["fish"]["basis"] == ["LLM-FIX"]
    assert fake.calls[0]["label"]["declaration_text"] == "밀 함유"


@pytest.mark.parametrize("text", [
    "This is safe for most people.", "It is allergen-free.", "Hazelnut paste is free of milk, so you can eat it.",
    "There is no risk here.", "You can safely enjoy this snack.",
])
def test_reassuring_words_are_dropped(text):
    out = ex.explain(doc_response(), call=Fake({"tree_nut": text}))
    assert {a.allergen.value: a.explanation_en for a in out.allergens}["tree_nut"] is None


def test_llm_fix_must_explain_read_as_not_a_new_guess():
    out = ex.explain(doc_response(), call=Fake({"fish": "“회류” is probably 회, raw sliced fish."}))
    assert {a.allergen.value: a.explanation_en for a in out.allergens}["fish"] is None


def test_undecidable_must_not_assert_contains():
    out = ex.explain(doc_response(), call=Fake({"sesame": "This seasoning definitely contains sesame."}))
    assert {a.allergen.value: a.explanation_en for a in out.allergens}["sesame"] is None


def test_too_long_empty_and_unknown_allergen_are_dropped():
    out = ex.explain(doc_response(), call=Fake({"sesame": "x" * 401, "tree_nut": "  ", "peanut": "Peanuts!", "milk": "Milk."}))
    got = {a.allergen.value: a.explanation_en for a in out.allergens}
    assert got["sesame"] is None and got["tree_nut"] is None and "peanut" not in got


@pytest.mark.parametrize("exc", [RuntimeError("402 Payment Required"), TimeoutError("slow")])
def test_failure_returns_original(exc):
    res = doc_response()
    assert ex.explain(res, call=Fake(raise_exc=exc)) is res


def test_cache_avoids_second_call():
    fake = Fake()
    ex.explain(doc_response(), call=fake)
    out = ex.explain(doc_response(), call=fake)
    assert len(fake.calls) == 1
    assert {a.allergen.value: a.explanation_en for a in out.allergens}["fish"] == GOOD["fish"]


def test_skips_when_warnings_or_no_targets():
    res = doc_response()
    res.warnings = ["원재료명 칸을 찾지 못함"]
    fake = Fake()
    assert ex.explain(res, call=fake) is res and fake.calls == []
    only_confirmed = analyze_text("원재료명: 밀가루, 설탕 / 밀 함유")
    assert ex.explain(only_confirmed, call=fake) is only_confirmed and fake.calls == []


def test_real_pipeline_response_opaque_and_possible():
    res = analyze_text(LABEL)
    fake = Fake({"fish": "Seafood seasoning powder is often made with anchovy or other fish extracts.",
                 "sesame": "Korean seasoning blends sometimes include sesame seeds or sesame oil."})
    out = ex.explain(res, call=fake)
    sent = {i["allergen"] for i in fake.calls[0]["items"]}
    assert sent == {a.allergen.value for a in res.allergens if a.verdict.value in ("inferable", "undecidable")}
    assert all(a.explanation_en for a in out.allergens if a.allergen.value in sent)
    assert [f.allergen for f in out.shared_facility] == [f.allergen for f in res.shared_facility]
    FinalAnalyzeResponse.model_validate(out.model_dump(mode="json"))      # JSON으로 나가도 형식 그대로


def test_openai_call_uses_auto_tool_choice_and_merges(monkeypatch):
    import openai

    parts = [{"allergen": a, "explanation": t} for a, t in GOOD.items()]
    msg = types.SimpleNamespace(content=None, tool_calls=[
        types.SimpleNamespace(function=types.SimpleNamespace(name="report_explanations", arguments=json.dumps({"results": parts[:1]}))),
        types.SimpleNamespace(function=types.SimpleNamespace(name="report_explanations", arguments=json.dumps({"results": parts[1:]}))),
    ])
    sent = {}

    class FakeOpenAI:
        def __init__(self, **kw):
            sent["client"] = kw
            create = lambda **k: (sent.update(k), types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)]))[1]
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=create))

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    out = ex.openai_call("http://x", "k", "m", 0.0, 20.0)("sys", "{}")
    assert len(out["results"]) == 3 and sent["tool_choice"] == "auto"
    assert sent["client"]["max_retries"] == 0 and sent["client"]["timeout"] == 20.0
