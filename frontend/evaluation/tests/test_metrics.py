import json
import subprocess
import sys
from pathlib import Path

import pytest

from frontend.evaluation.metrics import evaluate


def item(allergen, verdict="confirmed"):
    return {"allergen": allergen, "verdict": verdict}


def test_hand_calculated_metrics_and_unknowns():
    gold = [{"id": "a", "annotations": [item("milk"), item("soy", "inferable"), item("fish", "undecidable")]}]
    pred = [{"id": "a", "allergens": [item("milk"), item("wheat"), item("soy", "undecidable"), item("fish")]}]
    report = evaluate(gold, pred)
    assert report["overall"] == {
        "tp": 1, "fn": 1, "fp": 1, "tn": 5,
        "excluded_gold": 1, "predicted_undecidable": 1,
        "recall": 0.5, "false_positive_rate": 1 / 6,
    }
    assert report["per_allergen"]["fish"]["false_positive_rate"] is None


def test_empty_results_are_valid_but_empty_dataset_is_not():
    result = evaluate([{"id": "a", "annotations": []}], [{"id": "a", "allergens": []}])
    assert result["overall"]["recall"] is None
    assert result["overall"]["false_positive_rate"] == 0
    with pytest.raises(ValueError):
        evaluate([], [])


def test_matches_by_id_and_inferable_is_positive():
    gold = [{"id": "a", "annotations": [item("milk")]}, {"id": "b", "annotations": []}]
    pred = [{"id": "b", "allergens": []}, {"id": "a", "allergens": [item("milk", "inferable")]}]
    assert evaluate(gold, pred)["overall"]["recall"] == 1


@pytest.mark.parametrize("pred", [
    [{"id": "b", "allergens": []}],
    [{"id": "a", "allergens": []}, {"id": "a", "allergens": []}],
    [{"id": "a"}],
    [{"id": "a", "allergens": [item("milk"), item("milk")]}],
    [{"id": "a", "allergens": [item("invalid")]}],
    [{"id": "a", "allergens": [item("milk", "safe")]}],
])
def test_invalid_predictions_fail(pred):
    with pytest.raises(ValueError):
        evaluate([{"id": "a", "annotations": []}], pred)


def test_cli_schema_validation_output_and_input_protection(tmp_path):
    root = Path(__file__).resolve().parents[3]
    gold = json.loads((root / "data/schema/example_record.json").read_text(encoding="utf-8"))
    gold_path, pred_path, output = (tmp_path / name for name in ("gold.json", "pred.json", "report.json"))
    gold_path.write_text(json.dumps([gold]), encoding="utf-8")
    pred_path.write_text(json.dumps([{"id": gold["id"], "allergens": gold["annotations"]}]), encoding="utf-8")
    command = [sys.executable, "-m", "evaluation", "--gold", str(gold_path), "--predictions", str(pred_path)]
    run = subprocess.run(command + ["--output", str(output)], cwd=root / "frontend", capture_output=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["overall"]["recall"] == 1
    assert subprocess.run(command + ["--output", str(gold_path)], cwd=root / "frontend", capture_output=True).returncode == 2
    assert json.loads(gold_path.read_text(encoding="utf-8")) == [gold]
    gold_path.write_text('[{"id":"a","annotations":[]}]', encoding="utf-8")
    assert subprocess.run(command, cwd=root / "frontend", capture_output=True).returncode == 2
