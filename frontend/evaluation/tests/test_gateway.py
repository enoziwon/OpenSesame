import sys
import types

from frontend.evaluation.gateway_pr7 import _openai_call, parse_tool_output


def test_gateway_uses_configured_credentials_and_merges_calls(monkeypatch):
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        calls = [types.SimpleNamespace(function=types.SimpleNamespace(
            name="report_allergens",
            arguments='{"results":[{"ingredient":"%s","matches":[],"source_unknown":false}]}' % name,
        )) for name in ("설탕", "소금")]
        return types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(tool_calls=calls, content=None))])

    def client(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=create)))

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=client))
    call = _openai_call("https://api.baze.co/v1/gateway", "test-key", "test-model", True, 0)
    results = parse_tool_output(call("system", "ingredients"))
    assert [r.ingredient for r in results] == ["설탕", "소금"]
    assert captured["base_url"] == "https://api.baze.co/v1/gateway"
    assert captured["api_key"] == "test-key"
    assert captured["tool_choice"] == "auto"
