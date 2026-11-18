"""최종본 오인식 보정: 사전에 없음 -> 자모 1개 맞추기 -> LLM 보정 -> 사전 다시 확인 -> 없으면 LLM 판정(추정까지).
가짜 LLM을 쓴다 (네트워크 호출 없음)."""
from src.common.schema import AllergenMatch, IngredientClassification as IC
from src.final.resolve import Resolver, plausible_fix


class FakeFixer:
    """correct_and_classify를 흉내 낸다. answers: {이름: (바로잡은 이름, [(알레르겐, 판정)], source_unknown)}"""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def correct_and_classify(self, names):
        self.calls.append(list(names))
        out = []
        for n in names:
            fixed, matches, unknown = self.answers.get(n, ("", [], True))
            ms = [AllergenMatch(allergen=a, verdict=v) for a, v in matches]
            out.append((IC(ingredient=n, matches=ms, source_unknown=unknown), fixed))
        return out


def test_fixed_name_found_in_dictionary_uses_dictionary():
    # CLOVA가 '첨가'를 '첨ㅏ'로 쪼개 읽음 -> LLM이 바로잡음 -> 사전 항목이라 사전 판정
    fx = FakeFixer({"면류첨ㅏ알칼리제": ("면류첨가알칼리제", [("soy", "confirmed")], False)})
    r = Resolver(fallback=fx)
    hit = r.resolve_many(["면류첨ㅏ알칼리제", "설탕"])[0]
    assert hit.via == "ocrfix"
    assert hit.sources == r.resolve("면류첨가알칼리제").sources  # LLM의 soy가 아니라 사전 판정
    assert "오인식 보정(LLM): 면류첨ㅏ알칼리제 → 면류첨가알칼리제" in r.notes()


def test_fixed_but_still_unknown_uses_llm_capped_to_likely():
    # 바로잡아도 사전에 없음 -> LLM이 알려 준 대로, 확정은 추정으로 낮춤 (화면 may contain)
    fx = FakeFixer({"침맛양지육수분말": ("참맛양지육수분말", [("fish", "confirmed")], False)})
    r = Resolver(fallback=fx)
    hit = r.resolve_many(["침맛양지육수분말"])[0]
    assert hit.via == "fallback"
    assert dict(hit.sources) == {"fish": "I"}
    assert any("침맛양지육수분말 → 참맛양지육수분말" in n for n in r.notes())


def test_llm_says_unrelated_stays_unknown():
    # 9개와 관계없다는 답으로 모르는 이름을 지우지 않는다 (판정 불가 원재료 목록에 남는다)
    fx = FakeFixer({"침맛양지육수분말": ("참맛양지육수분말", [], False)})
    r = Resolver(fallback=fx)
    assert r.resolve_many(["침맛양지육수분말"])[0].via == "unknown"


def test_implausible_fix_is_dropped():
    # 모양과 상관없는 답(다른 원재료로 바꿈)은 버리고, 그 답의 알레르겐도 쓰지 않는다
    fx = FakeFixer({"면류첨ㅏ알칼리제": ("땅콩버터", [("peanut", "confirmed")], False)})
    r = Resolver(fallback=fx)
    assert r.resolve_many(["면류첨ㅏ알칼리제"])[0].via == "unknown"
    assert any("오인식 보정을 버림" in n for n in r.notes())


def test_only_unknown_names_go_to_llm_once():
    # 사전·규칙·자모 맞추기로 찾은 이름은 보내지 않고, 라벨 하나에 한 번만 부른다
    fx = FakeFixer({})
    r = Resolver(fallback=fx)
    r.resolve_many(["설탕", "탈지븐유", "면류첨ㅏ알칼리제", "침맛양지육수분말"])
    assert fx.calls == [["면류첨ㅏ알칼리제", "침맛양지육수분말"]]


def test_llm_failure_keeps_unknown():
    class Boom:
        def correct_and_classify(self, names):
            raise RuntimeError("gateway down")

    r = Resolver(fallback=Boom())
    assert r.resolve_many(["면류첨ㅏ알칼리제"])[0].via == "unknown"
    assert any("오인식 보정 호출 실패" in n for n in r.notes())


def test_plausible_fix_guard():
    assert plausible_fix("침맛양지육수분말", "참맛양지육수분말")
    assert plausible_fix("l1로인산나트륨", "피로인산나트륨")
    assert not plausible_fix("설탕", "땅콩버터")
    assert not plausible_fix("통옥수수", "통옥수수가루")


def test_end_to_end_final_pipeline(monkeypatch):
    # 최종본 파이프라인: 모르는 이름의 LLM 판정은 추정(화면 may contain), 표시란 규칙은 그대로
    import src.final.pipeline as fp

    fx = FakeFixer({"침맛양지육수분말": ("참맛양지육수분말", [("fish", "confirmed")], False)})
    monkeypatch.setattr(fp, "_fallback", lambda: fx)
    res = fp.analyze_text("원재료명: 설탕, 침맛양지육수분말 밀 함유")
    got = {a.allergen.value: a.verdict.value for a in res.allergens}
    assert got["fish"] == "inferable" and got["wheat"] == "confirmed"
    assert any("참맛양지육수분말" in n for n in res.notes)
