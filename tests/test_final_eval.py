"""최종본 채점 코드 테스트. 실행: python -m pytest -q tests/test_final_eval.py

손으로 계산한 제품 4개짜리 가상의 예(GOLD, 시스템 PRED_A·PRED_B)로 모든 지표 값을 고정한다.
A가 틀린 곳: p1 fish C→없음(놓침), p1 wheat C→I, p1 milk 없음→I(헛경고), p2 egg I→없음(놓침), p2 fish U→C,
p3 soy 없음→U(헛경고 아님), p4 peanut 없음→C(헛경고). 근거는 p2 sesame '맛베이스'와 '조미분말'만 불일치.
혼동 행렬(행 정답, 열 A; C I U absent): C [4 1 0 1], I [0 1 0 1], U [1 0 1 0], absent [1 1 1 23].
B = A에서 p1 soy(놓침)·p2 fish(정답 U라 놓침 아님)·p4 peanut을 지우고, p1 fish C·p2 egg I를 더한 것.
"""
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from src.final.eval import EvalInputError, load_gold, load_pred, render, score_all, score_system
from src.final.eval.__main__ import main as eval_main, system_names
from src.final.eval.evidence import evidence_matches
from src.final.eval.load import ALLERGENS, CATEGORIES, PACKAGE_MATERIALS, PRODUCT_TYPES, VERDICTS
from src.final.eval.score import Unit, build_units, product_rows
from src.final.eval.stats import binom_two_sided, bootstrap, cohen_kappa, percentile_95

ROOT = Path(__file__).resolve().parents[1]


def ann(allergen, verdict, evidence, hidden=False, declared=False):
    """정답 칸 하나. hidden·declared에 None을 주면 그 칸을 뺀다."""
    a = {"allergen": allergen, "verdict": verdict, "evidence_ingredient": evidence, "legal_basis": "테스트",
         "hidden_or_derived": hidden, "declared_in_kr": declared}
    return {k: v for k, v in a.items() if v is not None}


def record(rid, annotations, declared=(), text=None):
    return {"id": rid, "product_type": "other", "package_material": "other", "report_number": None,
            "ingredients_text": text or f"{rid} 원재료", "kr_declared_allergens": list(declared), "annotations": annotations}


def resp(rid, items, ms, warnings=()):
    allergens = [{"allergen": a, "verdict": v, "evidence_ingredient": e, "other_evidence": []} for a, v, e in items]
    return {"id": rid, "ms": ms, "response": {
        "ingredients_text": "", "ingredients": [], "allergens": allergens, "undecidable_ingredients": [],
        "warnings": list(warnings), "meta": {"ocr_engine": "text", "classifier": "fake", "prompt_version": None}}}


GOLD = [
    record("p1", [ann("soy", "confirmed", "간장(대두, 밀)", declared=True),
                  ann("wheat", "confirmed", "간장(대두, 밀)", hidden=True, declared=True),
                  ann("sesame", "confirmed", "참기름 3%"),
                  ann("fish", "confirmed", "혼합조미분말(멸치분말, 정제소금)", hidden=True)], declared=("대두", "밀")),
    record("p2", [ann("milk", "confirmed", "표시란: 우유", declared=True), ann("egg", "inferable", "난각칼슘"),
                  ann("sesame", "undecidable", "맛베이스"), ann("fish", "undecidable", "맛베이스")], declared=("우유",)),
    record("p3", [ann("crustacean", "confirmed", "새우젓", declared=True),
                  ann("wheat", "inferable", "간장", hidden=None, declared=None)], declared=("새우",)),   # 두 칸 없음
    record("p4", []),
]
PRED_A = [
    resp("p1", [("soy", "confirmed", "대두"), ("wheat", "inferable", "간장"), ("sesame", "confirmed", "참기름"),
                ("milk", "inferable", "유청")], 1.0),
    resp("p2", [("milk", "confirmed", "표시란: 우유"), ("sesame", "undecidable", "조미분말"),
                ("fish", "confirmed", "멸치")], 2.0),
    resp("p3", [("crustacean", "confirmed", "새우젓"), ("wheat", "inferable", "간장 "),
                ("soy", "undecidable", "맛베이스")], 3.0, warnings=("경고 하나",)),
    resp("p4", [("peanut", "confirmed", "땅콩")], 6.0),
]
PRED_B = [
    resp("p1", [("wheat", "inferable", "간장"), ("sesame", "confirmed", "참기름"), ("milk", "inferable", "유청"),
                ("fish", "confirmed", "멸치분말")], 10.0),
    resp("p2", [("milk", "confirmed", "표시란: 우유"), ("sesame", "undecidable", "조미분말"), ("egg", "inferable", "난각칼슘")], 10.0),
    resp("p3", [("crustacean", "confirmed", "새우젓"), ("wheat", "inferable", "간장 "), ("soy", "undecidable", "맛베이스")], 10.0),
    resp("p4", [], 10.0),
]


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


def nd(r):
    return r["num"], r["den"]


@pytest.fixture
def files(tmp_path):
    return (write_jsonl(tmp_path / "gold.jsonl", GOLD), write_jsonl(tmp_path / "a.jsonl", PRED_A),
            write_jsonl(tmp_path / "b.jsonl", PRED_B))


@pytest.fixture
def m(files):
    gold = load_gold(files[0])
    return score_system(gold, load_pred(files[1], gold), "a")


# ---------- 지표 (손 계산) ----------
def test_confusion_matrix(m):
    rows = {"confirmed": (4, 1, 0, 1), "inferable": (0, 1, 0, 1), "undecidable": (1, 0, 1, 0), "absent": (1, 1, 1, 23)}
    assert {g: tuple(m["confusion"][g][p] for p in CATEGORIES) for g in CATEGORIES} == rows
    assert (m["products"], m["units"]) == (4, 36)


def test_accuracy_kappa_and_per_class(m):
    assert nd(m["accuracy"]) == (29, 36)
    assert m["kappa"] == pytest.approx(0.58)          # (29·36 − 696) / (36² − 696) = 348 / 600
    pc = m["per_class"]
    assert [nd(pc[c]["precision"]) for c in CATEGORIES] == [(4, 6), (1, 3), (1, 2), (23, 25)]
    assert [nd(pc[c]["recall"]) for c in CATEGORIES] == [(4, 6), (1, 2), (1, 2), (23, 26)]


def test_misses_false_alarms_and_weighted_recall(m):
    assert (nd(m["miss"]), nd(m["miss_confirmed"])) == ((2, 8), (1, 6))      # p1 fish(C), p2 egg(I)
    assert nd(m["weighted_recall"]) == (11, 14)       # 1 − (2·1 + 1·1) / (2·6 + 1·2)
    assert m["weighted_recall"]["value"] == pytest.approx(1 - 3 / 14)
    assert m["misses"] == [
        {"id": "p1", "allergen": "fish", "gold": "confirmed", "gold_evidence": "혼합조미분말(멸치분말, 정제소금)"},
        {"id": "p2", "allergen": "egg", "gold": "inferable", "gold_evidence": "난각칼슘"}]
    assert nd(m["false_alarm_unit"]) == (2, 26)       # p1 milk(I), p4 peanut(C). p3 soy(U)는 세지 않는다
    assert nd(m["false_alarm_product"]) == (2, 4)
    assert [(x["id"], x["allergen"], x["pred"], x["pred_evidence"]) for x in m["false_alarms"]] == [
        ("p1", "milk", "inferable", "유청"), ("p4", "peanut", "confirmed", "땅콩")]


def test_alerts_undecidable_evidence_and_time(m):
    assert (nd(m["alert_recall"]), nd(m["alert_precision"])) == ((8, 10), (8, 11))
    u = m["undecidable"]
    assert [nd(u[k]) for k in ("precision", "recall", "pred_rate", "gold_rate")] == [(1, 2), (1, 2), (2, 36), (2, 36)]
    assert (nd(m["evidence"]["match"]), m["evidence"]["gold_empty"]) == ((5, 6), 0)    # p2 sesame의 '조미분말'만 불일치
    assert m["time_ms"] == {"mean": 3.0, "n": 4, "products": 4}
    assert m["warned_products"] == 1 and m["classifiers"] == ["fake"]


def test_subsets(m):
    h, d = m["subsets"]["hidden_or_derived"], m["subsets"]["not_declared_in_kr"]
    assert (h["n"], nd(h["accuracy"]), nd(h["miss"]), nd(h["alert_recall"]), h["missing_field"]) == \
        (2, (0, 2), (1, 2), (1, 2), 1)
    assert (d["n"], nd(d["accuracy"]), nd(d["miss"]), nd(d["alert_recall"]), d["missing_field"]) == \
        (5, (2, 5), (2, 3), (3, 5), 1)


PER_ALLERGEN = {   # 정답 C/I/U/absent, 정확도, 놓침, 헛경고, 경고 재현율, 경고 정밀도
    "milk": ((1, 0, 0, 3), (3, 4), (0, 1), (1, 3), (1, 1), (1, 2)),
    "egg": ((0, 1, 0, 3), (3, 4), (1, 1), (0, 3), (0, 1), (0, 0)),
    "fish": ((1, 0, 1, 2), (2, 4), (1, 1), (0, 2), (1, 2), (1, 1)),
    "crustacean": ((1, 0, 0, 3), (4, 4), (0, 1), (0, 3), (1, 1), (1, 1)),
    "tree_nut": ((0, 0, 0, 4), (4, 4), (0, 0), (0, 4), (0, 0), (0, 0)),
    "peanut": ((0, 0, 0, 4), (3, 4), (0, 0), (1, 4), (0, 0), (0, 1)),
    "wheat": ((1, 1, 0, 2), (3, 4), (0, 2), (0, 2), (2, 2), (2, 2)),
    "soy": ((1, 0, 0, 3), (3, 4), (0, 1), (0, 3), (1, 1), (1, 2)),
    "sesame": ((1, 0, 1, 2), (4, 4), (0, 1), (0, 2), (2, 2), (2, 2)),
}


@pytest.mark.parametrize("allergen", ALLERGENS)
def test_per_allergen(m, allergen):
    x = m["per_allergen"][allergen]
    got = (tuple(x["gold"][c] for c in CATEGORIES),) + tuple(
        nd(x[k]) for k in ("accuracy", "miss", "false_alarm_unit", "alert_recall", "alert_precision"))
    assert got == PER_ALLERGEN[allergen]


def test_product_rows_add_up_to_totals(files):
    gold = load_gold(files[0])
    rows = product_rows(build_units(gold, load_pred(files[1], gold)))
    assert [r["accuracy"] for r in rows] == [(6, 9), (7, 9), (8, 9), (8, 9)]
    assert [r["false_alarm_product"] for r in rows] == [(1, 1), (0, 1), (0, 1), (1, 1)]
    assert [r["weighted_recall"] for r in rows] == [(6, 8), (2, 3), (3, 3), (0, 0)]
    full = [Unit("q", a, "confirmed", "confirmed") for a in ALLERGENS]     # 정답 absent가 없는 제품은 제품 헛경고 분모에서 빠진다
    assert product_rows(full)[0]["false_alarm_product"] == (0, 0)


def test_mcnemar_between_systems(files):
    gold = load_gold(files[0])
    res = score_all(gold, [load_pred(files[1], gold), load_pred(files[2], gold)], ["a", "b"], n_boot=0)
    (c,) = res["comparisons"]
    assert (c["a"], c["b"]) == ("a", "b")
    assert c["correct"] == {"both": 28, "a_only": 1, "b_only": 3, "neither": 4, "p": pytest.approx(10 / 16)}
    assert c["caught"] == {"both": 5, "a_only": 1, "b_only": 2, "neither": 0, "p": 1.0}
    b = res["systems"][1]
    assert (nd(b["accuracy"]), nd(b["miss"]), nd(b["false_alarm_unit"])) == ((31, 36), (1, 8), (1, 26))
    assert b["time_ms"]["mean"] == 10.0 and b["accuracy"]["ci"] is None
    assert [(x["id"], x["allergen"]) for x in b["misses"]] == [("p1", "soy")]   # 정답 U -> absent는 놓침 목록에 없다


# ---------- 통계 ----------
def test_small_statistics_by_hand():
    assert binom_two_sided(3, 0) == binom_two_sided(0, 3) == 0.25       # 2 · (1/2)³
    assert binom_two_sided(5, 1) == pytest.approx(14 / 64)              # 2 · (1 + 6) / 2⁶
    assert binom_two_sided(2, 2) == 1.0 and binom_two_sided(0, 0) == 1.0
    assert binom_two_sided(1500, 0) == 0.0 and 0 < binom_two_sided(700, 640) < 1   # 큰 수에서도 넘치지 않는다
    assert cohen_kappa({"x": {"x": 3, "y": 0}, "y": {"x": 0, "y": 2}}, ("x", "y")) == 1.0
    assert cohen_kappa({"x": {"x": 5, "y": 0}, "y": {"x": 0, "y": 0}}, ("x", "y")) is None   # 한 범주뿐
    assert percentile_95(list(range(2000))) == [50, 1949] and percentile_95([7]) == [7, 7] and percentile_95([]) is None


def test_bootstrap_by_hand():
    two = [{"x": (9, 9)}, {"x": (0, 9)}]       # 표본 값은 0, 0.5, 1 셋뿐이고 양 끝이 각각 약 1/4
    assert bootstrap(two, 2000, 1) == {"x": {"ci": [0.0, 1.0], "ci_valid": 2000}}
    assert bootstrap([{"x": (1, 2)}] * 3, 500, 1)["x"]["ci"] == [0.5, 0.5] and bootstrap(two, 0, 1) == {}
    holes = bootstrap([{"x": (1, 1)}, {"x": (0, 0)}], 2000, 1)["x"]   # 분모 0인 표본은 뺀다
    assert holes["ci"] == [1.0, 1.0] and 1000 < holes["ci_valid"] < 2000


def test_bootstrap_is_seeded_and_brackets_the_estimate(files):
    gold = load_gold(files[0])
    pred = load_pred(files[1], gold)
    first, again = score_system(gold, pred, seed=7), score_system(gold, pred, seed=7)
    for key in ("accuracy", "miss", "miss_confirmed", "weighted_recall", "false_alarm_unit", "false_alarm_product"):
        assert first[key]["ci"] == again[key]["ci"]
        lo, hi = first[key]["ci"]
        assert lo <= first[key]["value"] <= hi
    assert first["accuracy"]["ci_valid"] == 2000


# ---------- 근거 일치 ----------
@pytest.mark.parametrize("gold, pred, same", [
    ("간장(대두, 밀)", "간장", True), ("간장(대두, 밀)", "대두", True), ("간장(대두, 밀)", "밀", True),
    ("간장(대두, 밀)", "간장(대두)", True), ("간장(대두, 밀)", "된장", False), ("참기름 3%", "참기름", True),
    ("참기름3%", "참 기름", True), ("대두 레시틴", "대두레시틴", True), ("비타민B1 0.5%", "비타민B1", True),
    ("소맥분 (밀:미국산)", "소맥분", True), ("혼합조미분말[멸치분말(멸치), 정제소금]", "멸치분말", True),
    ("혼합조미분말[멸치분말(멸치), 정제소금]", "멸치", True),           # 덩어리 안이면 깊이는 따지지 않는다
    ("크래미[연육(미국산), 소맥전분(밀:미국산), 정제염]", "소맥전분", True), ("크래미[연육(미국산), 소맥전분(밀:미국산)]", "밀", True),
    ("찌개양념베이스3", "찌개양념베이스", True), ("치즈복합시즈닝-2", "치즈복합시즈닝", True),      # 뒤에 붙은 번호
    ("소맥분(미국산,호주산)", "면-소맥분", True),                       # 시스템 이름 앞에 남은 머리말
    ("연유(우유)", "밀크런치", False), ("우리밀", "밀현미", False), ("밀가루", "밀", False),    # 한 글자 이름은 같을 때만
    ("혼합조미분말（멸치분말）", "멸치분말", True),
    ("멸치분말", "혼합조미분말(멸치분말)", False),                      # 시스템 쪽 자식은 보지 않는다
    ("맛베이스", "맛베이스#6", True), ("맛베이스", "조미분말", False), ("표시란: 우유", "표시란: 우유", True), ("표시란: 우유", "표시란:우유", False),
    ("표시란: 우유", "우유", False), ("우유", "표시란: 우유", False), ("", "", False), ("간장", "", False),
])
def test_evidence_rules(gold, pred, same):
    assert evidence_matches(gold, pred) is same


# ---------- 입력 검사 ----------
@pytest.mark.parametrize("change, words", [
    (lambda r: r.pop("annotations"), "annotations"), (lambda r: r.pop("package_material"), "package_material"),
    (lambda r: r["annotations"][0].update(verdict="maybe"), "verdict"),
    (lambda r: r["annotations"][0].update(allergen="nuts"), "allergen"),
    (lambda r: r["annotations"].append(dict(r["annotations"][0])), "두 번"),
    (lambda r: r["annotations"][0].update(hidden_or_derived="yes"), "hidden_or_derived"),
    (lambda r: r["annotations"][0].pop("legal_basis"), "legal_basis"),
    (lambda r: r.update(product_type="candy"), "product_type"),
    (lambda r: r.update(kr_declared_allergens="대두"), "kr_declared_allergens"),
    (lambda r: r.update(ingredients_text=None), "ingredients_text"),
])
def test_gold_file_is_checked(tmp_path, change, words):
    rows = copy.deepcopy(GOLD)
    change(rows[0])
    with pytest.raises(EvalInputError, match=words) as e:
        load_gold(write_jsonl(tmp_path / "g.jsonl", rows))
    assert "id=p1" in str(e.value)


def test_gold_duplicate_id_bad_json_and_empty(tmp_path):
    with pytest.raises(EvalInputError, match="id가 두 번"):
        load_gold(write_jsonl(tmp_path / "g.jsonl", [GOLD[0], GOLD[0]]))
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps(GOLD[0], ensure_ascii=False) + "\n{oops\n", encoding="utf-8")
    with pytest.raises(EvalInputError, match="bad.jsonl:2 JSON이 아님"):
        load_gold(bad)
    (tmp_path / "empty.jsonl").write_text("\n", encoding="utf-8")
    with pytest.raises(EvalInputError, match="정답 레코드가 없음"):
        load_gold(tmp_path / "empty.jsonl")


@pytest.mark.parametrize("change, words", [
    (lambda r: r["response"]["allergens"][0].update(verdict="absent"), "verdict"),
    (lambda r: r["response"]["allergens"][0].update(allergen="nuts"), "allergen"),
    (lambda r: r["response"]["allergens"].append(dict(r["response"]["allergens"][0])), "두 번"),
    (lambda r: r["response"]["allergens"][0].pop("evidence_ingredient"), "evidence_ingredient"),
    (lambda r: r["response"].pop("allergens"), "response.allergens"),
    (lambda r: r.update(ms=-1), "ms"), (lambda r: r.update(ms=float("nan")), "ms"), (lambda r: r.update(ms=True), "ms"),
])
def test_pred_file_is_checked(files, tmp_path, change, words):
    gold = load_gold(files[0])
    rows = copy.deepcopy(PRED_A)
    change(rows[0])
    with pytest.raises(EvalInputError, match=words):
        load_pred(write_jsonl(tmp_path / "x.jsonl", rows), gold)


def test_pred_ids_must_match_gold(files, tmp_path):
    gold = load_gold(files[0])
    with pytest.raises(EvalInputError) as e:
        load_pred(write_jsonl(tmp_path / "x.jsonl", PRED_A[:3] + [dict(PRED_A[3], id="p9")]), gold)
    assert "응답에 없는 정답 id 1개: p4" in str(e.value) and "정답에 없는 응답 id 1개: p9" in str(e.value)
    with pytest.raises(EvalInputError, match="id가 두 번"):
        load_pred(write_jsonl(tmp_path / "y.jsonl", PRED_A + PRED_A[:1]), gold)


def test_names_match_team_and_gold_schema(tmp_path):
    from src.common.schema import Allergen, Verdict
    assert ALLERGENS == tuple(a.value for a in Allergen) and VERDICTS == tuple(v.value for v in Verdict)
    schema = json.loads((ROOT / "data/schema/label_record.schema.json").read_text(encoding="utf-8"))
    item = schema["properties"]["annotations"]["items"]["properties"]
    assert list(ALLERGENS) == item["allergen"]["enum"] and list(VERDICTS) == item["verdict"]["enum"]
    assert list(PRODUCT_TYPES) == schema["properties"]["product_type"]["enum"]
    assert list(PACKAGE_MATERIALS) == schema["properties"]["package_material"]["enum"]
    example = json.loads((ROOT / "data/schema/example_record.json").read_text(encoding="utf-8"))
    gold = load_gold(write_jsonl(tmp_path / "ex.jsonl", [example]))
    assert set(gold.products[0].labels) == {"soy", "wheat", "sesame", "fish"}


# ---------- 보고서와 실행 ----------
def test_report_has_header_and_tables_but_no_item_text(files):
    gold = load_gold(files[0])
    result = score_all(gold, [load_pred(files[1], gold), load_pred(files[2], gold)], ["a", "b"], n_boot=200)
    header = {"gold": "gold.jsonl", "gold_sha256": gold.sha256, "products": 4, "units": 36,
              "run_at": "2026-11-13 18:00:00 +0900", "boot": 200, "seed": 1}
    text = render(result, header)
    assert gold.sha256 in text and "2026-11-13 18:00:00 +0900" in text and "| 제품 수 | 4 |" in text
    assert "80.6% (29/36)" in text and "25.0% (2/8)" in text and "| Cohen's κ (네 범주) | 0.580 |" in text
    assert "가중 재현율(누락 가중 재현율): 1 − (2 × 놓친 confirmed" in text
    assert "## 4. 시스템 비교" in text and "| a vs b | 판정 일치 (전체 단위) | 28 | 1 | 3 | 4 | 0.6250 |" in text
    for secret in ("혼합조미분말", "난각칼슘", "유청", "땅콩"):         # 근거 글자는 보고서에 없다
        assert secret not in text


def test_cli_writes_report_and_json(files, tmp_path, capsys):
    g, a, b = files
    out, js = tmp_path / "r" / "report.md", tmp_path / "r" / "metrics.json"
    args = ["--gold", str(g), "--pred", str(a), "--pred", str(b), "--out", str(out), "--json", str(js), "--boot", "100"]
    assert eval_main(args) == 0 and out.exists()
    data = json.loads(js.read_text(encoding="utf-8"))
    assert (data["header"]["products"], data["header"]["units"]) == (4, 36)
    assert data["header"]["gold_sha256"] == hashlib.sha256(g.read_bytes()).hexdigest()
    assert [s["name"] for s in data["systems"]] == ["a", "b"] and len(data["systems"][0]["misses"]) == 2
    assert data["comparisons"][0]["correct"]["b_only"] == 3
    assert "a: 놓침 25.0% (2/8)" in capsys.readouterr().out


def test_cli_no_items_id_mismatch_and_names(files, tmp_path, capsys):
    g, a, _ = files
    js = tmp_path / "m.json"
    assert eval_main(["--gold", str(g), "--pred", str(a), "--json", str(js), "--boot", "0", "--no-items"]) == 0
    system = json.loads(js.read_text(encoding="utf-8"))["systems"][0]
    assert "misses" not in system and "false_alarms" not in system
    capsys.readouterr()
    short = write_jsonl(tmp_path / "short.jsonl", PRED_A[:3])
    assert eval_main(["--gold", str(g), "--pred", str(short)]) == 2
    assert "응답에 없는 정답 id 1개: p4" in capsys.readouterr().err
    blank = write_jsonl(tmp_path / "blank.jsonl", [dict(r, annotations=[]) for r in GOLD])      # 빈 정답 파일을 잘못 준 경우
    assert eval_main(["--gold", str(blank), "--pred", str(a), "--boot", "0", "--out", str(tmp_path / "r.md")]) == 0
    assert "annotations가 모두 비어" in capsys.readouterr().err
    assert system_names(["x/a.jsonl", "y/a.jsonl", "b.jsonl"]) == ["x/a.jsonl", "y/a.jsonl", "b"]


# ---------- 실행 도구 ----------
def _tool(name):
    spec = importlib.util.spec_from_file_location(f"tool_{name}", ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_final_feeds_fields_and_writes_lines(files, tmp_path):
    run_final = _tool("run_final")
    gold = load_gold(files[0])
    calls = []

    def fake(ingredients, declaration):
        calls.append((ingredients, declaration))
        return {"allergens": [], "warnings": [], "meta": {"classifier": "fake-final"}}

    out = tmp_path / "final.jsonl"
    assert len(run_final.run(gold.products, fake, out)) == 4
    assert calls == [("p1 원재료", "대두, 밀 함유"), ("p2 원재료", "우유 함유"), ("p3 원재료", "새우 함유"), ("p4 원재료", "없음")]
    assert not (tmp_path / "final.jsonl.part").exists()
    assert load_pred(out, gold).products["p1"].classifier == "fake-final"      # 채점 코드가 그대로 읽는다


def test_run_final_can_drop_the_declaration(files, tmp_path):
    run_final = _tool("run_final")
    gold = load_gold(files[0])
    seen = []

    def fake(ingredients, declaration):
        seen.append(declaration)
        return {"ingredients_text": ingredients, "ingredients": [], "allergens": [], "undecidable_ingredients": [],
                "warnings": [], "meta": {"ocr_engine": "text", "classifier": "fake", "prompt_version": None}}

    run_final.run(gold.products, fake, tmp_path / "nobox.jsonl", use_box=False)
    assert seen == [None] * len(gold.products)


def test_run_final_stops_with_id_but_without_text(files, tmp_path, monkeypatch):
    run_final = _tool("run_final")
    gold = load_gold(files[0])

    def boom(ingredients, declaration):
        raise KeyError("비밀 원재료")

    with pytest.raises(SystemExit) as e:
        run_final.run(gold.products, boom, tmp_path / "x.jsonl")
    assert "p1" in str(e.value) and "KeyError" in str(e.value) and "비밀 원재료" not in str(e.value)
    assert not (tmp_path / "x.jsonl").exists()
    monkeypatch.setitem(sys.modules, "src.final.pipeline", None)       # 파이프라인을 가져오지 못하는 상황
    with pytest.raises(SystemExit, match="src.final.pipeline.analyze_fields"):
        run_final.load_system()


def test_run_team_with_mock_classifier(tmp_path):
    run_team = _tool("run_team")
    gold_path = write_jsonl(tmp_path / "g.jsonl", [record("t1", [], declared=("밀", "대두"), text="소맥분, 참기름 3%, 간장"),
                                                  record("t2", [], text="정제수, 향료")])
    plain, boxed = tmp_path / "plain.jsonl", tmp_path / "boxed.jsonl"
    assert run_team.main(["--gold", str(gold_path), "--out", str(plain)]) == 0
    assert run_team.main(["--gold", str(gold_path), "--out", str(boxed), "--with-box"]) == 0
    t1 = load_pred(plain, load_gold(gold_path)).products["t1"]
    assert {a: x.verdict for a, x in t1.labels.items()} == {"wheat": "confirmed", "soy": "inferable", "sesame": "confirmed"}
    assert t1.classifier == "mock" and t1.ms is not None and t1.ms >= 0
    rows = [json.loads(line) for line in boxed.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["response"]["ingredients_text"] == "소맥분, 참기름 3%, 간장, 밀, 대두 함유"
    assert rows[1]["response"]["ingredients_text"] == "정제수, 향료"       # 표시란 항목이 없으면 붙이지 않는다
    assert rows[0]["response"]["meta"]["ocr_engine"] == "text"
