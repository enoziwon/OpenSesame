from src.common.schema import AllergenMatch, IngredientClassification as IC
from src.model import MockClassifier
from src.ocr import MockOcr
from src.pipeline import aggregate, analyze, validate


def test_strongest_verdict_wins():
    results = [
        IC(ingredient="간장", matches=[AllergenMatch(allergen="soy", verdict="inferable")]),
        IC(ingredient="대두", matches=[AllergenMatch(allergen="soy", verdict="confirmed")]),
    ]
    allergens, _ = aggregate(results)
    soy = allergens[0]
    assert (soy.allergen.value, soy.verdict.value, soy.evidence_ingredient) == ("soy", "confirmed", "대두")
    assert soy.other_evidence == ["간장"]


def test_hallucinated_ingredient_dropped():
    results = [IC(ingredient="땅콩", matches=[AllergenMatch(allergen="peanut", verdict="confirmed")])]
    checked, warnings = validate(["설탕"], results)
    allergens, unknown = aggregate(checked)
    assert allergens == []
    assert unknown == ["설탕"]  # 답이 없던 원재료는 판정 불가로
    assert any("땅콩" in w for w in warnings)


def test_mock_end_to_end():
    res = analyze(b"x", "image/jpeg", MockOcr(), MockClassifier())
    got = {a.allergen.value: a.verdict.value for a in res.allergens}
    assert got == {"milk": "confirmed", "fish": "confirmed", "wheat": "confirmed", "soy": "confirmed", "sesame": "confirmed"}
    assert "향료" in res.undecidable_ingredients


class Boom:
    name = "boom"
    prompt_version = None

    def classify(self, ingredients):
        raise RuntimeError("api down")


def test_classifier_failure_asserts_nothing():
    res = analyze(b"x", "image/jpeg", MockOcr(), Boom())
    assert res.allergens == []
    assert any("분류 실패" in w for w in res.warnings)
    assert len(res.undecidable_ingredients) > 0


class _TextOcr:
    name = "text"

    def __init__(self, text):
        self.text = text

    def read_text(self, image, content_type):
        from src.common.schema import OcrResult

        return OcrResult(text=self.text, engine=self.name, confidence=None)


class _Spy:
    """분류기에 넘어간 이름을 기록하고, 아무 알레르기도 답하지 않는다."""
    name = "spy"
    prompt_version = None

    def __init__(self):
        self.seen = []

    def classify(self, ingredients):
        self.seen = list(ingredients)
        return [IC(ingredient=n) for n in ingredients]


def test_korean_declaration_becomes_confirmed_evidence():
    # 원재료에 근거가 없어도 표시란의 '달걀, 우유, 대두'는 확정. 미국 9개가 아닌 쇠고기는 쓰지 않는다
    res = analyze(b"x", "image/jpeg", _TextOcr("통옥수수, 설탕, 시즈닝 밀, 달걀, 우유, 대두, 쇠고기 함유"), _Spy())
    got = {a.allergen.value: (a.verdict.value, a.evidence_ingredient) for a in res.allergens}
    assert got == {"egg": ("confirmed", "달걀 (함유 표시)"), "milk": ("confirmed", "우유 (함유 표시)"),
                   "wheat": ("confirmed", "밀 (함유 표시)"), "soy": ("confirmed", "대두 (함유 표시)")}


def test_ingredient_evidence_stays_first(monkeypatch):
    # 원재료에도 확정 근거가 있으면 그 원재료가 대표 근거, 표시란은 기타 근거
    res = analyze(b"x", "image/jpeg", _TextOcr("소맥분, 설탕 밀 함유"), MockClassifier())
    wheat = next(a for a in res.allergens if a.allergen.value == "wheat")
    assert (wheat.evidence_ingredient, wheat.other_evidence) == ("소맥분", ["밀 (함유 표시)"])


def test_korean_declaration_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("OPENSESAME_KR_DECL", "0")
    res = analyze(b"x", "image/jpeg", _TextOcr("설탕 밀, 우유 함유"), _Spy())
    assert res.allergens == []


def test_alias_is_sent_to_classifier():
    # '연육/어육': 응답 트리에는 '연육'만 있지만 분류기에는 '어육'도 보낸다
    spy = _Spy()
    res = analyze(b"x", "image/jpeg", _TextOcr("연육/어육, 설탕"), spy)
    assert spy.seen == ["연육", "어육", "설탕"]
    assert [n.name for n in res.ingredients] == ["연육", "설탕"]
