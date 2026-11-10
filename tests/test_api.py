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


def test_profile_is_not_accepted():
    # 프로필을 같이 보내도 서버는 읽지 않는다 (응답에 흔적이 없어야 함)
    r = client.post("/analyze", files={"file": ("a.jpg", b"fake", "image/jpeg")}, data={"profile": "peanut"})
    assert r.status_code == 200
    assert "profile" not in r.text
