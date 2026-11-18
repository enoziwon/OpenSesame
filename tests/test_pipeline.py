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
