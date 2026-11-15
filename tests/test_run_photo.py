"""tools/run_photo.py, tools/run_1st_eval.py 테스트. 네트워크와 LLM을 부르지 않는다. 실행: python -m pytest -q"""
import importlib.util
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def load(name):
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location(f"tool_{name}", TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_exp(tmp_path):
    exp = tmp_path / "EXP-003"
    (exp / "gold").mkdir(parents=True)
    (exp / "results" / "clova_full").mkdir(parents=True)
    (exp / "gold" / "p01.txt").write_text("원재료명 소맥분(밀:미국산), 설탕, 참기름 밀 함유", encoding="utf-8")
    (exp / "results" / "clova_full" / "p01.txt").write_text("소맥분(밀:미국산), 설탕, 참기 름 밀 함유", encoding="utf-8")
    (exp / "gold" / "p02.txt").write_text("원재료명 정제수, 설탕, 정제소금", encoding="utf-8")
    (exp / "results" / "clova_full" / "p02.txt").write_text("정제수, 설탕, 정제소금", encoding="utf-8")
    return exp


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_final_on_photo_texts(tmp_path):
    tool = load("run_photo")
    exp = make_exp(tmp_path)
    for cond in ("clean", "clova"):
        out = tmp_path / f"final_{cond}.jsonl"
        assert tool.main(["--system", "final", "--cond", cond, "--out", str(out), "--exp-dir", str(exp)]) == 0
        got = rows(out)
        assert [r["id"] for r in got] == ["photo_p01", "photo_p02"]
        verdicts = {a["allergen"]: a["verdict"] for a in got[0]["response"]["allergens"]}
        assert verdicts["wheat"] == "confirmed" and verdicts["sesame"] == "confirmed"
        assert got[1]["response"]["allergens"] == []


def test_team_mock_on_photo_texts(tmp_path):
    tool = load("run_photo")
    exp = make_exp(tmp_path)
    out = tmp_path / "team.jsonl"
    assert tool.main(["--system", "team", "--classifier", "mock", "--cond", "clean", "--out", str(out),
                      "--exp-dir", str(exp)]) == 0
    got = rows(out)
    assert len(got) == 2 and got[0]["response"]["meta"]["classifier"] == "mock"


def test_1st_eval_stops_without_key(tmp_path, monkeypatch):
    tool = load("run_1st_eval")
    monkeypatch.setattr(tool.run_team, "load_dotenv", lambda path: None)   # 저장소 .env의 키를 읽지 않게
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert tool.main(["--out-dir", str(tmp_path / "out")]) == 2
    assert not (tmp_path / "out").exists()


class FakeGatewayError(Exception):
    """openai SDK의 오류처럼 보이게 모듈 이름만 바꾼 가짜 오류 (호출 한도 429)."""

    status_code = 429


FakeGatewayError.__module__ = "openai._exceptions"


class Flaky:
    name = "llm"
    prompt_version = "classify_v1"

    def __init__(self, fails, error):
        self.fails, self.error, self.calls = fails, error, 0

    def classify(self, names):
        self.calls += 1
        if self.calls <= self.fails:
            raise self.error
        return ["ok"]


def test_retry_resends_after_gateway_rejection():
    tool = load("run_team")
    waits = []
    inner = Flaky(2, FakeGatewayError())
    clf = tool.RetryingClassifier(inner, retries=3, wait=15, sleep=waits.append, log=lambda m: None)
    assert clf.classify(["간장"]) == ["ok"]
    assert inner.calls == 3 and waits == [15, 30] and clf.retried == 2
    assert clf.name == "llm" and clf.prompt_version == "classify_v1"


def test_retry_does_not_resend_broken_answers():
    tool = load("run_team")
    waits = []
    inner = Flaky(1, ValueError("LLM 답을 읽지 못함"))
    clf = tool.RetryingClassifier(inner, retries=3, sleep=waits.append, log=lambda m: None)
    try:
        clf.classify(["간장"])
        raised = False
    except ValueError:
        raised = True
    assert raised and inner.calls == 1 and waits == []


def test_retry_gives_up_after_limit():
    tool = load("run_team")
    waits = []
    inner = Flaky(10, FakeGatewayError())
    clf = tool.RetryingClassifier(inner, retries=2, wait=10, max_wait=15, sleep=waits.append, log=lambda m: None)
    try:
        clf.classify(["간장"])
        raised = False
    except FakeGatewayError:
        raised = True
    assert raised and inner.calls == 3 and waits == [10, 15]


class FakeCreditError(Exception):
    status_code = 402


FakeCreditError.__module__ = "openai._exceptions"


def test_retry_stops_on_credit_shortage():
    tool = load("run_team")
    waits = []
    inner = Flaky(5, FakeCreditError())
    clf = tool.RetryingClassifier(inner, retries=3, sleep=waits.append, log=lambda m: None)
    try:
        clf.classify(["간장"])
        raised = False
    except FakeCreditError:
        raised = True
    assert raised and inner.calls == 1 and waits == [] and clf.out_of_credit
