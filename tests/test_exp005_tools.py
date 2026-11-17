"""EXP-005 도구 테스트: 이어서 돌리기·개수 제한(run_team, run_photo), 예산 실행기(run_exp005), CLOVA 한 번만 읽기(run_raw).
네트워크와 LLM을 부르지 않는다. 실행: python -m pytest -q
"""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
EXP3 = ROOT / "experiments" / "EXP-003"


def load(path, name):
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tool(name):
    return load(TOOLS / f"{name}.py", f"exp5_{name}")


def gold_row(rid, text, declared=()):
    return {"id": rid, "product_type": "other", "package_material": "other", "report_number": None,
            "image_files": [], "ingredients_text": text, "kr_declared_allergens": list(declared), "annotations": []}


TEXTS = {"B_test_901": "밀가루(밀:미국산), 설탕, 참기름", "B_test_902": "정제수, 설탕, 정제소금",
         "B_test_903": "탈지분유, 설탕", "B_test_904": "대두유, 정제소금"}


def write_gold(path):
    path.write_text("".join(json.dumps(gold_row(k, v), ensure_ascii=False) + "\n" for k, v in TEXTS.items()),
                    encoding="utf-8")
    return path


def ids_in(path):
    return [json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------- run_team: --limit, --resume, --ids ----------
def test_team_limit_then_resume(tmp_path):
    rt = tool("run_team")
    gold, out = write_gold(tmp_path / "g.jsonl"), tmp_path / "o.jsonl"
    assert rt.main(["--gold", str(gold), "--out", str(out), "--limit", "3"]) == 3
    assert not out.exists() and ids_in(tmp_path / "o.jsonl.part") == list(TEXTS)[:3]
    assert rt.main(["--gold", str(gold), "--out", str(out), "--resume"]) == 0
    assert ids_in(out) == list(TEXTS) and not (tmp_path / "o.jsonl.part").exists()
    assert rt.main(["--gold", str(gold), "--out", str(out), "--resume"]) == 0      # 다 했으면 그대로
    assert ids_in(out) == list(TEXTS)


def test_team_resume_redoes_failed_rows(tmp_path):
    rt = tool("run_team")
    gold, out = write_gold(tmp_path / "g.jsonl"), tmp_path / "o.jsonl"
    assert rt.main(["--gold", str(gold), "--out", str(out)]) == 0
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    rows[1]["response"]["warnings"] = ["분류 실패(RuntimeError): 알레르기를 판단하지 못함"]
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert [json.loads(x)["id"] for x in rt.read_done(out)] == ["B_test_901", "B_test_903", "B_test_904"]
    assert rt.main(["--gold", str(gold), "--out", str(out), "--resume"]) == 0
    redone = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert sorted(r["id"] for r in redone) == sorted(TEXTS) and not any(rt.failed_row(r) for r in redone)


def test_team_ids_filter(tmp_path):
    rt = tool("run_team")
    gold, out = write_gold(tmp_path / "g.jsonl"), tmp_path / "o.jsonl"
    (tmp_path / "ids.txt").write_text("B_test_903\nB_test_901\n", encoding="utf-8")
    assert rt.main(["--gold", str(gold), "--out", str(out), "--ids", str(tmp_path / "ids.txt")]) == 0
    assert ids_in(out) == ["B_test_901", "B_test_903"]                              # 정답 파일 순서
    (tmp_path / "bad.txt").write_text("B_test_999\n", encoding="utf-8")
    assert rt.main(["--gold", str(gold), "--out", str(out), "--ids", str(tmp_path / "bad.txt")]) == 2


# ---------- run_photo: 시험 세트 id 그대로, --pattern, --limit, --resume ----------
def test_photo_ids_as_is_with_limit(tmp_path):
    rp = tool("run_photo")
    exp = tmp_path / "EXP-005"
    (exp / "results" / "clova_full").mkdir(parents=True)
    for k in ("B_test_901", "B_test_903"):
        (exp / "results" / "clova_full" / f"{k}.txt").write_text(TEXTS[k] + " 밀 함유", encoding="utf-8")
    out = tmp_path / "f.jsonl"
    base = ["--system", "final", "--cond", "clova", "--exp-dir", str(exp), "--pattern", "B_test_*.txt", "--out", str(out)]
    assert rp.main(base + ["--limit", "1"]) == 3
    assert rp.main(base + ["--resume"]) == 0
    assert ids_in(out) == ["B_test_901", "B_test_903"]
    assert rp.photo_id("p01") == "photo_p01" and rp.photo_id("B_test_085") == "B_test_085"


# ---------- run_exp005: 예산 실행기 ----------
def make_exp5(tmp_path, shot=("B_test_902", "B_test_904")):
    exp = tmp_path / "EXP-005"
    (exp / "results" / "clova_full").mkdir(parents=True)
    for k in shot:
        (exp / "results" / "clova_full" / f"{k}.txt").write_text(TEXTS[k], encoding="utf-8")
    return exp


def args5(tmp_path, exp, *more, photo_blank=None):
    return ["--exp-dir", str(exp), "--test", str(write_gold(tmp_path / "test_blank.jsonl")),
            "--photo-blank", str(photo_blank or tmp_path / "no_photo_blank.jsonl"),
            "--out-dir", str(tmp_path / "out"), "--classifier", "mock", *more]


def test_exp005_needs_included_list(tmp_path):
    ex = tool("run_exp005")
    exp = make_exp5(tmp_path)
    assert ex.main(args5(tmp_path, exp, "--budget", "5")) == 2                    # included.txt 없음: LLM 안 부름
    assert not (tmp_path / "out" / "team_llm_P.jsonl").exists()


def test_exp005_spends_budget_in_priority_order(tmp_path):
    ex = tool("run_exp005")
    exp = make_exp5(tmp_path)
    (exp / "included.txt").write_text("# 대조 끝\nB_test_904\nB_test_902\n", encoding="utf-8")
    out = tmp_path / "out"
    assert ex.main(args5(tmp_path, exp, "--budget", "3")) == 3                    # P 2개 + R 1개
    assert ids_in(out / "team_llm_P.jsonl") == ["B_test_904", "B_test_902"]      # included.txt 순서
    assert ids_in(out / "team_llm_P_run2.jsonl.part") == ["B_test_904"]
    assert not (out / "team_llm_T.jsonl").exists()
    assert ex.main(args5(tmp_path, exp, "--budget", "100", "--label", "둘째 키")) == 0
    assert ids_in(out / "team_llm_P_run2.jsonl") == ["B_test_904", "B_test_902"]
    assert ids_in(out / "team_llm_T.jsonl") == ["B_test_904", "B_test_902"]      # 사진 찍은 제품의 정답 글자 (included 순서)
    assert ids_in(out / "team_llm_REST.jsonl") == ["B_test_901", "B_test_903"]   # 나머지
    meta = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))
    assert [r["budget"] for r in meta["runs"]] == [3, 100] and meta["runs"][1]["label"] == "둘째 키"
    assert sum(s["new"] for r in meta["runs"] for s in r["stages"]) == 2 + 2 + 2 + 2


def test_exp005_stops_on_credit_shortage(tmp_path):
    ex = tool("run_exp005")
    from src.model import get_classifier

    class CreditLimited:                     # 두 번째 호출에서 402가 난 것처럼 (팀 파이프라인은 예외를 경고로 바꾼다)
        name, prompt_version = "llm", None

        def __init__(self):
            self.inner, self.calls, self.out_of_credit = get_classifier("mock"), 0, False

        def classify(self, names):
            self.calls += 1
            if self.calls >= 2:
                self.out_of_credit = True
                raise RuntimeError("402")
            return self.inner.classify(names)

    exp = make_exp5(tmp_path)
    (exp / "included.txt").write_text("B_test_902\nB_test_904\n", encoding="utf-8")
    test = ex.load_gold(str(write_gold(tmp_path / "test_blank.jsonl")))
    out = tmp_path / "out"
    out.mkdir()
    report, stopped = ex.spend(10, CreditLimited(), exp, test, out, ["B_test_902", "B_test_904"])
    assert stopped and "402" in stopped and report[0]["new"] == 2
    assert [json.loads(x)["id"] for x in tool("run_team").read_done(out / "team_llm_P.jsonl")] == ["B_test_902"]


def test_exp005_status_and_final_without_llm(tmp_path, capsys):
    ex = tool("run_exp005")
    exp = make_exp5(tmp_path)
    (exp / "included.txt").write_text("B_test_902\nB_test_904\n", encoding="utf-8")
    assert ex.main(args5(tmp_path, exp, "--status")) == 0
    assert "남은 1차 호출: 제품 8개분" in capsys.readouterr().out
    assert ex.main(args5(tmp_path, exp, "--final")) == 0
    out = tmp_path / "out"
    runs = [(out / n).read_text(encoding="utf-8") for n in ("final_P.jsonl", "final_P_run2.jsonl", "final_P_run3.jsonl")]
    strip = lambda t: [{k: v for k, v in json.loads(x).items() if k != "ms"} for x in t.splitlines()]  # noqa: E731
    assert strip(runs[0]) == strip(runs[1]) == strip(runs[2])                     # 최종본은 세 번 다 같은 답
    assert ids_in(out / "final_test.jsonl") == list(TEXTS)


# ---------- EXP-005 run_raw: CLOVA는 사진마다 한 번만 ----------
def raw_tool():
    return load(ROOT / "experiments" / "EXP-005" / "run_raw.py", "exp5_run_raw")


def test_run_raw_from_saved_response_matches_exp003(tmp_path):
    rr = raw_tool()
    (tmp_path / "raw").mkdir()
    shutil.copy(EXP3 / "raw" / "p01.json", tmp_path / "raw" / "B_test_901__1.json")
    assert rr.main(["--from-raw"], exp=tmp_path) == 0
    got = (tmp_path / "results" / "clova_full" / "B_test_901.txt").read_text(encoding="utf-8")
    assert got == (EXP3 / "results" / "clova_full" / "p01.txt").read_text(encoding="utf-8")
    assert (tmp_path / "results" / "clova_lines" / "B_test_901.txt").read_text(encoding="utf-8").strip()


def test_run_raw_calls_each_photo_once(tmp_path, monkeypatch):
    rr = raw_tool()
    photos = tmp_path / "photos"
    for pid, n in (("B_test_901", 2), ("B_test_902", 1)):
        (photos / pid).mkdir(parents=True)
        for k in range(1, n + 1):
            (photos / pid / f"{k}.jpg").write_bytes(b"fake")
    saved = json.loads((EXP3 / "raw" / "p02.json").read_text(encoding="utf-8"))
    calls = []

    def fake(image, fmt, url, secret):
        calls.append(fmt)
        return saved

    monkeypatch.setenv("CLOVA_URL", "https://example.invalid/ocr")
    monkeypatch.setenv("CLOVA_SECRET", "test")
    exp, env = tmp_path / "exp", tmp_path / "none.env"                                     # 저장소 .env는 읽지 않는다
    run = lambda *a: rr.main(["--photos", str(photos), *a], call=fake, exp=exp, env_file=env)  # noqa: E731
    assert run("--dry-run") == 0 and calls == []
    assert run("--limit", "2") == 3                                                         # 한 장 남음
    assert run() == 0 and len(calls) == 3                                                   # 3장, 한 번씩
    assert run() == 0 and len(calls) == 3                                                   # 다시 부르지 않음
    one = (EXP3 / "results" / "clova_full" / "p02.txt").read_text(encoding="utf-8")
    assert (exp / "results" / "clova_full" / "B_test_901.txt").read_text(encoding="utf-8") == one + "\n" + one
    (photos / "B_test_902" / "2.heic").write_bytes(b"x")
    with pytest.raises(SystemExit):
        run()


# ---------- run_exp005 --key-file, EXP-005 lookup ----------
def test_key_file_overrides_env_and_stays_outside_repo(tmp_path, monkeypatch):
    ex = tool("run_exp005")
    for k in ex.KEY_VARS:
        monkeypatch.delenv(k, raising=False)
    (tmp_path / "a.env").write_text("# 진영\nLLM_API_KEY=fake_a\nLLM_MODEL=claude-sonnet-5-5\nOTHER=x\n", encoding="utf-8")
    assert ex.apply_key_file(tmp_path / "a.env") == ["LLM_API_KEY", "LLM_MODEL"]
    import os
    assert os.environ["LLM_API_KEY"] == "fake_a" and "OTHER" not in os.environ
    (tmp_path / "b.key").write_text("fake_b\n", encoding="utf-8")            # 키 한 줄만 있는 파일
    ex.apply_key_file(tmp_path / "b.key")
    assert os.environ["LLM_API_KEY"] == "fake_b"
    (tmp_path / "c.env").write_text("LLM_MODEL=x\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ex.apply_key_file(tmp_path / "c.env")
    with pytest.raises(ValueError):
        ex.apply_key_file(ROOT / ".env.example")                            # 저장소 안의 파일은 쓰지 않는다


def test_lookup_marks_test_dev_and_new(tmp_path, capsys):
    lk = load(ROOT / "experiments" / "EXP-005" / "lookup.py", "exp5_lookup")
    items = tmp_path / "items.jsonl"
    rows = [{"prdlstReportNo": "19860309018704", "prdlstNm": "진짬뽕", "manufacture": "오뚜기", "rawmtrl": "소맥분(밀)", "allergy": "밀"},
            {"prdlstReportNo": "19860309018710", "prdlstNm": "오뚜기 진짬뽕", "manufacture": "오뚜기", "rawmtrl": "x", "allergy": ""},
            {"prdlstReportNo": "11112222", "prdlstNm": "개발과자", "manufacture": "m", "rawmtrl": "y", "allergy": ""}]
    items.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "test.jsonl").write_text(json.dumps({"id": "B_test_085", "report_number": "19860309018704"}) + "\n", encoding="utf-8")
    (gold / "dev.jsonl").write_text(json.dumps({"id": "B_dev_001", "report_number": "11112222"}) + "\n", encoding="utf-8")
    assert lk.main(["진짬뽕"], items_path=items, gold_dir=gold) == 0
    out = capsys.readouterr().out
    assert "시험 세트 B_test_085" in out and "새 제품" in out
    assert lk.main(["1986-0309-018704"], items_path=items, gold_dir=gold) == 0  # 하이픈이 있어도 번호로 찾는다
    assert "시험 세트 B_test_085" in capsys.readouterr().out
    assert lk.main(["11112222"], items_path=items, gold_dir=gold) == 0
    assert "개발 세트 B_dev_001" in capsys.readouterr().out


def test_exp005_new_products_from_photo_blank(tmp_path):
    ex = tool("run_exp005")
    exp = make_exp5(tmp_path, shot=("B_test_902",))
    (exp / "results" / "clova_full" / "N_11112222.txt").write_text("우유, 설탕 우유 함유", encoding="utf-8")
    (exp / "included.txt").write_text("B_test_902\nN_11112222\n", encoding="utf-8")
    blank = tmp_path / "exp005_photo_blank.jsonl"
    blank.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in
                             (gold_row("B_test_902", TEXTS["B_test_902"]), gold_row("N_11112222", "우유, 설탕", ["우유"]))),
                     encoding="utf-8")
    assert ex.main(args5(tmp_path, exp, "--budget", "100", photo_blank=blank)) == 0
    out = tmp_path / "out"
    assert ids_in(out / "team_llm_T.jsonl") == ["B_test_902", "N_11112222"]          # included.txt 순서
    assert ids_in(out / "team_llm_REST.jsonl") == ["B_test_901", "B_test_903", "B_test_904"]
    assert ex.main(args5(tmp_path, exp, "--final", photo_blank=blank)) == 0
    assert ids_in(out / "final_T.jsonl") == ["B_test_902", "N_11112222"]
    (exp / "included.txt").write_text("B_test_902\nN_99999999\n", encoding="utf-8")
    assert ex.main(args5(tmp_path, exp, "--status", photo_blank=blank)) == 2           # 입력 파일에 없는 id
