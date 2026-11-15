"""제품 × 알레르겐 단위의 초기 평가. 지표 정책은 README.md 참고."""
from __future__ import annotations

ALLERGENS = ("milk", "egg", "fish", "crustacean", "tree_nut", "peanut", "wheat", "soy", "sesame")
VERDICTS = {"confirmed", "inferable", "undecidable"}
POSITIVE = {"confirmed", "inferable"}


def index_records(records: list[dict], field: str) -> dict[str, dict[str, str]]:
    if not isinstance(records, list) or not records:
        raise ValueError("입력은 비어 있지 않은 JSON 레코드 배열이어야 합니다.")
    indexed = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("각 레코드는 객체여야 합니다.")
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("각 레코드에 비어 있지 않은 id가 필요합니다.")
        if identifier in indexed:
            raise ValueError(f"중복 id: {identifier}")
        items = record.get(field)
        if not isinstance(items, list):
            raise ValueError(f"{identifier}: {field} 배열이 필요합니다.")
        verdicts = {}
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{identifier}: 판정은 객체여야 합니다.")
            allergen, verdict = item.get("allergen"), item.get("verdict")
            if not isinstance(allergen, str) or allergen not in ALLERGENS:
                raise ValueError(f"{identifier}: 잘못된 allergen: {allergen}")
            if not isinstance(verdict, str) or verdict not in VERDICTS:
                raise ValueError(f"{identifier}: 잘못된 verdict: {verdict}")
            if allergen in verdicts:
                raise ValueError(f"{identifier}: 중복 allergen: {allergen}")
            verdicts[allergen] = verdict
        indexed[identifier] = verdicts
    return indexed


def summarize(counts: dict[str, int]) -> dict:
    tp, fn, fp, tn = (counts[k] for k in ("tp", "fn", "fp", "tn"))
    return {
        **counts,
        "recall": tp / (tp + fn) if tp + fn else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
    }


def evaluate(gold: list[dict], predictions: list[dict]) -> dict:
    expected = index_records(gold, "annotations")
    actual = index_records(predictions, "allergens")
    if expected.keys() != actual.keys():
        missing = sorted(expected.keys() - actual.keys())
        extra = sorted(actual.keys() - expected.keys())
        raise ValueError(f"id 불일치: 예측 누락={missing}, gold에 없는 예측={extra}")
    counts = {
        a: dict(tp=0, fn=0, fp=0, tn=0, excluded_gold=0, predicted_undecidable=0)
        for a in ALLERGENS
    }
    for identifier, labels in expected.items():
        for allergen in ALLERGENS:
            counter = counts[allergen]
            truth = labels.get(allergen)
            prediction = actual[identifier].get(allergen)
            if truth == "undecidable":
                counter["excluded_gold"] += 1
                continue
            if prediction == "undecidable":
                counter["predicted_undecidable"] += 1
            positive = truth in POSITIVE
            detected = prediction in POSITIVE
            key = ("tp" if detected else "fn") if positive else ("fp" if detected else "tn")
            counter[key] += 1
    total = {key: sum(c[key] for c in counts.values()) for key in counts[ALLERGENS[0]]}
    return {
        "policy": "presence_v1",
        "products": len(expected),
        "overall": summarize(total),
        "per_allergen": {a: summarize(c) for a, c in counts.items()},
    }
