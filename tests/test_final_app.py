"""최종본 서버 테스트. 실행: python -m pytest -q"""
import os

os.environ["OPENSESAME_OCR"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from src.final.app import MAX_BYTES, app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "ocr": "mock", "classifier": "final-lexicon-v1"}


def test_analyze_photo_with_mock_ocr():
    r = client.post("/analyze", files={"file": ("a.jpg", b"fake", "image/jpeg")})
    assert r.status_code == 200
    body = r.json()
    assert body["meta"] == {"ocr_engine": "mock", "classifier": "final-lexicon-v1", "prompt_version": None}
    assert {a["allergen"] for a in body["allergens"]} == {"milk", "fish", "wheat", "soy", "sesame"}


def test_analyze_rejects_bad_files():
    assert client.post("/analyze", files={"file": ("a.txt", b"hi", "text/plain")}).status_code == 400
    assert client.post("/analyze", files={"file": ("a.jpg", b"", "image/jpeg")}).status_code == 400
    big = b"0" * (MAX_BYTES + 1)
    assert client.post("/analyze", files={"file": ("a.jpg", big, "image/jpeg")}).status_code == 413


def test_analyze_text_whole_label():
    r = client.post("/analyze-text", json={"text": "원재료명: 간장, 설탕, 대두 함유"})
    assert r.status_code == 200
    body = r.json()
    assert [(a["allergen"], a["verdict"]) for a in body["allergens"]] == [("soy", "confirmed")]
    assert body["declared"] == ["대두"] and body["warnings"] == []


def test_analyze_text_fields():
    r = client.post("/analyze-text", json={"ingredients": "액젓, 고춧가루", "declaration": "없음"})
    assert r.status_code == 200
    assert [(a["allergen"], a["verdict"]) for a in r.json()["allergens"]] == [("fish", "inferable")]


def test_analyze_text_fields_without_declaration():
    r = client.post("/analyze-text", json={"ingredients": "간장, 설탕"})
    assert r.status_code == 200
    assert len(r.json()["warnings"]) == 1


def test_analyze_text_rejects_bad_bodies():
    bad = [
        {},                                               # 둘 다 없음
        {"text": "   "},                                  # 빈 글자
        {"text": 123},                                    # 글자가 아님
        {"ingredients": ["간장"]},
        {"text": "가" * 20001},                            # 너무 김
        {"text": "간장", "ingredients": "설탕"},              # 둘 다 있음
        {"text": "간장", "declaration": "대두 함유"},          # 표시란은 ingredients와 함께만
        {"ingredients": "간장", "declaration": 5},
    ]
    for body in bad:
        assert client.post("/analyze-text", json=body).status_code == 422, body


def test_profile_is_not_read():
    r = client.post("/analyze-text", json={"text": "간장, 설탕", "profile": "peanut"})
    assert r.status_code == 200
    assert "profile" not in r.text
