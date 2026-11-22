"""사진 경로의 같은 시설 칸(OcrResult.facility) -> 최종본 shared_facility. 실행: python -m pytest -q

OCR은 같은 시설 문장을 원재료 글자와 따로 넘긴다. 최종본은 같은 시설 문구로 보이는 조각만 쓰고, 판정은 바꾸지 않는다.
"""
import os

os.environ["OPENSESAME_OCR"] = "mock"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.common.schema import OcrResult  # noqa: E402
from src.final import app as server  # noqa: E402
from src.final.facility import merge_facility, ocr_facility_pieces  # noqa: E402
from src.final.pipeline import analyze_text  # noqa: E402

client = TestClient(server.app)

NOTICE = "이 제품은 우유, 땅콩, 새우를 사용한 제품과 같은 제조시설에서 제조하고 있습니다."
# 줄 끝 '혼'(호두혼|합견과페이스트) 때문에 OCR이 같은 시설 칸에 담은 제품명·원재료 덩어리 (EXP-006 N_19840415001356을 줄임)
JUNK = ("· 제품명 배지밀 검은콩 아몬드 & 호두 두유 · 식품의 유형 : 가공두유 · 원재료명: 원액두유 87%[대두], 설탕, "
        "호두혼 합견과페이스트 0.7%[땅콩 62%, 아몬드 30%, 호두 7%, 잣], 혼합제제")
LABEL = "원재료명: 밀가루, 설탕, 정제소금\n밀 함유"


def kinds(res):
    return [(a.allergen.value, a.verdict.value, list(a.basis)) for a in res.allergens]


def names(notes):
    return [getattr(n.allergen, "value", n.allergen) for n in notes]


def test_pieces_keep_real_notices_and_drop_junk():
    assert ocr_facility_pieces(JUNK) == []
    assert ocr_facility_pieces(NOTICE) == [NOTICE]
    assert ocr_facility_pieces("우유, 땅콩 혼 입 가능") == ["우유, 땅콩 혼 입 가능"]          # OCR이 띄어 읽은 '혼 입'
    assert ocr_facility_pieces(f"{NOTICE} {JUNK}") == [NOTICE]                          # 문장 끝 뒤에서 나눈다
    assert ocr_facility_pieces("우유·땅콩·대두 혼입 가능") == ["우유·땅콩·대두 혼입 가능"]   # 가운뎃점에서는 자르지 않는다
    assert ocr_facility_pieces(None) == [] and ocr_facility_pieces("") == []


def test_head_of_a_split_notice_is_kept():
    # 줄이 나뉘어 '이 제품은 …' 머리와 '… 같은 시설' 꼬리가 다른 조각이 된 경우 (EXP-006 N_19910492029552를 줄임)
    text = "잣을 사용한 제품과 같은 제조시설에서 제조하고 있습니다. ·이 제품은 메밀, 땅콩, 게 이해야 받을 수 있습니다. · 신고는 1399"
    assert ocr_facility_pieces(text) == ["잣을 사용한 제품과 같은 제조시설에서 제조하고 있습니다.",
                                         "·이 제품은 메밀, 땅콩, 게 이해야 받을 수 있습니다."]


def test_merge_keeps_each_sentence_once():
    assert merge_facility(NOTICE, [NOTICE.replace(" ", "")]) == NOTICE                  # 빈칸만 다른 같은 문장
    assert merge_facility(None, [NOTICE, NOTICE]) == NOTICE
    assert merge_facility("땅콩 혼입 가능", [NOTICE]) == f"땅콩 혼입 가능 {NOTICE}"
    assert merge_facility(None, []) is None and merge_facility("", []) is None


def test_analyze_text_uses_ocr_facility_without_changing_verdicts():
    base = analyze_text(LABEL, ocr_engine="clova")
    res = analyze_text(LABEL, ocr_engine="clova", facility=f"{NOTICE} {JUNK}")
    assert kinds(res) == kinds(base)
    assert res.undecidable_ingredients == base.undecidable_ingredients and res.warnings == base.warnings
    assert base.shared_facility == []
    assert names(res.shared_facility) == ["milk", "crustacean", "peanut"]      # 밀은 이미 판정이 있어서 뺀다
    assert any(NOTICE in n for n in res.notes)
    assert not any("제품명" in n for n in res.notes)                            # 버린 덩어리는 참고에도 남기지 않는다


def test_facility_found_in_the_text_and_from_ocr_is_counted_once():
    res = analyze_text(f"{LABEL}\n{NOTICE}", facility=NOTICE)
    assert names(res.shared_facility) == ["milk", "crustacean", "peanut"]
    assert sum(n.count("같은 제조시설") for n in res.notes) == 1


def test_facility_must_be_text():
    with pytest.raises(TypeError):
        analyze_text(LABEL, facility=123)


def test_too_long_facility_is_dropped_not_fatal():
    # 판정에 쓰지 않는 안내 칸이라, 너무 길면 버리고 분석은 계속한다(#24 리뷰)
    res = analyze_text(LABEL, facility="같은 시설 " * 5000)
    plain = analyze_text(LABEL)
    assert [(a.allergen, a.verdict) for a in res.allergens] == [(a.allergen, a.verdict) for a in plain.allergens]
    assert res.shared_facility == plain.shared_facility


def test_photo_path_passes_ocr_facility(monkeypatch):
    class FacilityOcr:
        name = "clova"

        def read_text(self, image, content_type):
            return OcrResult(text=LABEL, engine=self.name, facility=f"{NOTICE} {JUNK}")

    monkeypatch.setattr(server, "_ocr", FacilityOcr())
    r = client.post("/analyze", files={"file": ("label.jpg", b"photo", "image/jpeg")})
    assert r.status_code == 200
    body = r.json()
    assert [x["allergen"] for x in body["shared_facility"]] == ["milk", "crustacean", "peanut"]
    expected = analyze_text(LABEL, ocr_engine="clova")
    assert [(a["allergen"], a["verdict"]) for a in body["allergens"]] == \
        [(a.allergen.value, a.verdict.value) for a in expected.allergens]


def test_photo_path_without_facility_field(monkeypatch):
    class OldOcr:                      # facility 칸이 없는 OCR 결과도 그대로 받는다
        name = "clova"

        def read_text(self, image, content_type):
            class Result:
                text = LABEL
                warnings = []
            return Result()

    monkeypatch.setattr(server, "_ocr", OldOcr())
    r = client.post("/analyze", files={"file": ("label.jpg", b"photo", "image/jpeg")})
    assert r.status_code == 200
    assert r.json()["shared_facility"] == []
