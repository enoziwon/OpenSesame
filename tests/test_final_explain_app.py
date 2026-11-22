"""서버(/analyze-text)가 응답 직전에 설명을 붙이는지. 기본은 꺼짐. 실행: python -m pytest -q"""
from fastapi.testclient import TestClient

from src.final import explain as ex
from src.final.app import app

client = TestClient(app)
TEXT = "원재료명: 밀가루, 해물양념분말, 설탕 / 알레르기 유발물질: 밀 함유"


def _may(body):
    return {a["allergen"]: a for a in body["allergens"] if a["verdict"] in ("inferable", "undecidable")}


def test_off_by_default_explanation_is_null(monkeypatch):
    monkeypatch.delenv(ex.ENV, raising=False)
    body = client.post("/analyze-text", json={"text": TEXT}).json()
    assert _may(body) and all(a["explanation_en"] is None for a in _may(body).values())


def test_on_fills_explanation_both_input_forms(monkeypatch):
    ex.clear_cache()
    monkeypatch.setenv(ex.ENV, "llm")
    calls = []

    def fake(system, user):
        calls.append(user)
        return {"results": [{"allergen": a, "explanation": f"Seasoning blends like this sometimes include {a}."}
                            for a in ("fish", "sesame")]}

    monkeypatch.setattr(ex, "_default_call", fake)
    for payload in ({"text": TEXT}, {"ingredients": "밀가루, 해물양념분말, 설탕", "declaration": "밀"}):
        body = client.post("/analyze-text", json=payload).json()
        may = _may(body)
        assert may and all(a["explanation_en"] for a in may.values())
        assert all(a["explanation_en"] is None for a in body["allergens"] if a["verdict"] == "confirmed")
    assert len(calls) >= 1
