import json
import types

import pytest

from src.model import llm
from src.model.llm import LLMClassifier, extract_json, parse_tool_output


def test_invalid_allergen_becomes_unknown():
    raw = {"results": [{"ingredient": "코코넛", "matches": [{"allergen": "coconut", "verdict": "confirmed"}], "source_unknown": False}]}
    out = parse_tool_output(raw)
    assert out[0].matches == [] and out[0].source_unknown is True


def test_classifier_sends_names_only():
    seen = {}

    def fake_call(system, user):
        seen["user"] = user
        return {"results": [{"ingredient": "참기름", "matches": [{"allergen": "sesame", "verdict": "confirmed"}], "source_unknown": False}]}

    out = LLMClassifier(call=fake_call, model="fake").classify(["참기름"])
    assert out[0].matches[0].allergen.value == "sesame"
    assert "참기름" in seen["user"]


def test_garbage_output_is_empty():
    assert parse_tool_output({"oops": 1}) == []
    assert parse_tool_output("not a dict") == []


def test_extract_json_from_text():
    assert extract_json('```json\n{"results": []}\n```') == {"results": []}
    assert extract_json('답: {"results": [1]} 끝') == {"results": [1]}
    assert extract_json("JSON 아님") == {}


def _fake_openai(response_message):
    class FakeClient:
        def __init__(self, base_url, api_key):
            self.sent = None
            outer = self

            class Completions:
                def create(self, **kwargs):
                    outer.sent = kwargs
                    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=response_message)])

            self.chat = types.SimpleNamespace(completions=Completions())

    return FakeClient


def test_openai_tool_call(monkeypatch):
    import openai

    msg = types.SimpleNamespace(
        content=None,
        tool_calls=[types.SimpleNamespace(function=types.SimpleNamespace(
            name="report_allergens",
            arguments='{"results": [{"ingredient": "탈지분유", "matches": [{"allergen": "milk", "verdict": "confirmed"}], "source_unknown": false}]}',
        ))],
    )
    monkeypatch.setattr(openai, "OpenAI", _fake_openai(msg))
    call = llm._openai_call("http://x", "k", "m", use_tools=True, temperature=0)
    assert call("s", "u")["results"][0]["ingredient"] == "탈지분유"


def test_openai_json_only_mode(monkeypatch):
    import openai

    msg = types.SimpleNamespace(content='```json\n{"results": []}\n```', tool_calls=None)
    monkeypatch.setattr(openai, "OpenAI", _fake_openai(msg))
    call = llm._openai_call("http://x", "k", "m", use_tools=False, temperature=0)
    assert call("s", "u") == {"results": []}


def test_from_env_requires_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "http://x")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        LLMClassifier.from_env()


def test_openai_default_tool_choice_is_auto(monkeypatch):
    import openai

    msg = types.SimpleNamespace(content='{"results": []}', tool_calls=None)
    fake = _fake_openai(msg)
    created = {}

    class Capture(fake):
        def __init__(self, base_url, api_key):
            super().__init__(base_url, api_key)
            created["client"] = self

    monkeypatch.setattr(openai, "OpenAI", Capture)
    call = llm._openai_call("http://x", "k", "m", use_tools=True, temperature=0)
    assert call("s", "u") == {"results": []}  # tool 대신 글(JSON)로 답해도 받아들인다
    sent = created["client"].sent
    assert sent["tool_choice"] == "auto"
    assert "report_allergens" in sent["messages"][0]["content"]


def test_multiple_tool_calls_are_merged(monkeypatch):
    import openai

    def tc(name):
        return types.SimpleNamespace(function=types.SimpleNamespace(
            name="report_allergens",
            arguments='{"results": [{"ingredient": "%s", "matches": [], "source_unknown": false}]}' % name,
        ))

    msg = types.SimpleNamespace(content=None, tool_calls=[tc("정제수"), tc("설탕")])
    monkeypatch.setattr(openai, "OpenAI", _fake_openai(msg))
    call = llm._openai_call("http://x", "k", "m", use_tools=True, temperature=0)
    got = [r["ingredient"] for r in call("s", "u")["results"]]
    assert got == ["정제수", "설탕"]


def test_classify_splits_into_batches():
    calls = []

    def fake_call(system, user):
        names = json.loads(user.split("\n", 1)[1])
        calls.append(names)
        return {"results": [{"ingredient": n, "matches": [], "source_unknown": False} for n in names]}

    clf = LLMClassifier(call=fake_call, model="fake", batch_size=2)
    out = clf.classify(["a", "b", "c", "d", "e"])
    assert [len(c) for c in calls] == [2, 2, 1]
    assert [r.ingredient for r in out] == ["a", "b", "c", "d", "e"]


def test_openai_sets_max_tokens(monkeypatch):
    import openai

    msg = types.SimpleNamespace(content='{"results": []}', tool_calls=None)
    created = {}
    fake = _fake_openai(msg)

    class Capture(fake):
        def __init__(self, base_url, api_key):
            super().__init__(base_url, api_key)
            created["c"] = self

    monkeypatch.setattr(openai, "OpenAI", Capture)
    llm._openai_call("http://x", "k", "m", use_tools=True, temperature=0, max_tokens=1234)("s", "u")
    assert created["c"].sent["max_tokens"] == 1234


def _sent_schema(monkeypatch, **kw):
    """_openai_call이 게이트웨이에 보내는 도구 정의(parameters)를 꺼낸다."""
    import openai

    msg = types.SimpleNamespace(content='{"results": []}', tool_calls=None)
    fake = _fake_openai(msg)
    created = {}

    class Capture(fake):
        def __init__(self, base_url, api_key):
            super().__init__(base_url, api_key)
            created["client"] = self

    monkeypatch.setattr(openai, "OpenAI", Capture)
    llm._openai_call("http://x", "k", "m", use_tools=True, temperature=0, **kw)("s", "u")
    return created["client"].sent["tools"][0]["function"]["parameters"]


def test_classify_request_has_no_corrected_field(monkeypatch):
    # 1차 분류(classify_v1) 요청의 도구 정의는 오인식 보정 전과 같아야 한다 (1차 기준선)
    items = _sent_schema(monkeypatch)["properties"]["results"]["items"]["properties"]
    assert set(items) == {"ingredient", "matches", "source_unknown"}


def test_ocr_fix_request_has_corrected_field(monkeypatch):
    items = _sent_schema(monkeypatch, schema=llm.OCR_FIX_TOOL_SCHEMA)["properties"]["results"]["items"]["properties"]
    assert "corrected" in items
    assert "corrected" not in llm.TOOL_SCHEMA["properties"]["results"]["items"]["properties"]  # 원본은 그대로


def test_from_env_uses_separate_call_for_ocr_fix(monkeypatch):
    # 분류는 TOOL_SCHEMA, 오인식 보정은 OCR_FIX_TOOL_SCHEMA로 부른다
    seen = []
    monkeypatch.setattr(llm, "_openai_call", lambda *a, schema=None, **k: (lambda s, u: seen.append(schema) or {"results": []}))
    for k, v in {"LLM_PROVIDER": "openai", "LLM_API_KEY": "k", "LLM_BASE_URL": "http://x", "LLM_MODEL": "m"}.items():
        monkeypatch.setenv(k, v)
    c = llm.LLMClassifier.from_env()
    c.classify(["설탕"])
    c.correct_and_classify(["설탕"])
    assert seen == [None, llm.OCR_FIX_TOOL_SCHEMA]
