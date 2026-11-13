"""tools/refresh_gold_declared.py 테스트. 실행: python -m pytest -q"""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "refresh_gold_declared", Path(__file__).resolve().parents[1] / "tools" / "refresh_gold_declared.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def write(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def make(tmp_path):
    items = [
        {"prdlstReportNo": "1", "rawmtrl": "소맥분, 설탕, 대두유", "allergy": "밀, 대두 함유"},
        {"prdlstReportNo": "2", "rawmtrl": "쌀, 설탕, 소금", "allergy": "없음"},
        {"prdlstReportNo": "3", "rawmtrl": "쌀, 설탕, 소금", "allergy": "알수없음"},
    ]
    gold = [
        {"id": "a", "report_number": "1", "kr_declared_allergens": ["밀"], "annotations": []},     # 대두가 빠져 있다
        {"id": "b", "report_number": "2", "kr_declared_allergens": [], "annotations": []},
        {"id": "c", "report_number": "3", "kr_declared_allergens": ["우유"], "annotations": []},   # 표시란을 못 읽는 제품
        {"id": "d", "report_number": "9", "kr_declared_allergens": ["땅콩"], "annotations": []},   # 자료에 없는 번호
    ]
    write(tmp_path / "items.jsonl", items)
    write(tmp_path / "gold.jsonl", gold)
    return tmp_path / "items.jsonl", tmp_path / "gold.jsonl"


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_dry_run_reports_counts_and_keeps_the_file(tmp_path, capsys):
    items, gold = make(tmp_path)
    before = gold.read_bytes()
    assert tool.main(["--gold", str(gold), "--items", str(items)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["records"], out["changed"], out["same"], out["no_item"], out["no_box"]) == (4, 1, 1, 1, 1)
    assert out["written"] is False and gold.read_bytes() == before


def test_write_updates_only_the_declared_field(tmp_path, capsys):
    items, gold = make(tmp_path)
    assert tool.main(["--gold", str(gold), "--items", str(items), "--write"]) == 0
    out = json.loads(capsys.readouterr().out)
    rows = read(gold)
    assert out["written"] is True and [r["id"] for r in rows] == ["a", "b", "c", "d"]
    assert rows[0]["kr_declared_allergens"] == ["밀", "대두"]
    assert rows[2]["kr_declared_allergens"] == ["우유"] and rows[3]["kr_declared_allergens"] == ["땅콩"]   # 건드리지 않는다


def test_output_never_prints_label_text(tmp_path, capsys):
    items, gold = make(tmp_path)
    tool.main(["--gold", str(gold), "--items", str(items)])
    out = capsys.readouterr().out
    assert "소맥분" not in out and "대두" not in out


def test_bad_json_is_an_error(tmp_path, capsys):
    items, gold = make(tmp_path)
    gold.write_text("{깨진 줄\n", encoding="utf-8")
    assert tool.main(["--gold", str(gold), "--items", str(items)]) == 2
    assert "JSON" in capsys.readouterr().err
