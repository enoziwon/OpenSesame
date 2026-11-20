import os

os.environ["OPENSESAME_OCR"] = "mock"
os.environ["OPENSESAME_CLASSIFIER"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from src.app.main import app  # noqa: E402

client = TestClient(app)


def test_analyze_mock():
    r = client.post("/analyze", files={"file": ("a.jpg", b"fake", "image/jpeg")})
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"ingredients_text", "ingredients", "allergens", "undecidable_ingredients", "warnings", "meta"}
    assert all(a["allergen"] in {"milk","egg","fish","crustacean","tree_nut","peanut","wheat","soy","sesame"} for a in body["allergens"])


def test_rejects_non_image():
    r = client.post("/analyze", files={"file": ("a.txt", b"hi", "text/plain")})
    assert r.status_code == 400


def test_photo_ocr_names_reach_classifier_and_change_verdicts(monkeypatch):
    from src.app import main
    from src.common.schema import OcrResult
    from src.model import MockClassifier

    class PhotoOcr:
        name = "clova"

        def read_text(self, image, content_type):
            assert content_type == "image/jpeg"
            return OcrResult(text=image.decode("utf-8"), engine=self.name)

    class RecordingClassifier(MockClassifier):
        name = "llm"

        def classify(self, ingredients):
            seen.append(ingredients)
            return super().classify(ingredients)

    seen = []
    monkeypatch.setattr(main, "_ocr", PhotoOcr())
    monkeypatch.setattr(main, "_classifier", RecordingClassifier())
    for text, expected in [("소맥분", {"wheat"}), ("탈지분유", {"milk"}), ("설탕", set())]:
        r = client.post("/analyze", files={"file": ("label.jpg", text.encode("utf-8"), "image/jpeg")})
        assert r.status_code == 200
        body = r.json()
        assert body["ingredients_text"] == text
        assert {a["allergen"] for a in body["allergens"]} == expected
        assert seen[-1] == [text]


def test_ocr_failure_returns_error_instead_of_sample(monkeypatch):
    from src.app import main

    def fail(*args, **kwargs):
        raise RuntimeError("OCR unavailable")

    monkeypatch.setattr(main, "analyze", fail)
    r = client.post("/analyze", files={"file": ("label.jpg", b"photo", "image/jpeg")})
    assert r.status_code == 502
    assert "allergens" not in r.json()


def test_profile_is_not_accepted():
    # 프로필을 같이 보내도 서버는 읽지 않는다 (응답에 흔적이 없어야 함)
    r = client.post("/analyze", files={"file": ("a.jpg", b"fake", "image/jpeg")}, data={"profile": "peanut"})
    assert r.status_code == 200
    assert "profile" not in r.text
