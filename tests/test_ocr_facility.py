"""OCR이 같은 시설 문장을 원재료 글자와 따로 넘기는지 (네트워크 호출 없음, 가짜 CLOVA 응답)."""
from src.common.schema import OcrResult


def _line(words, x, y, gap=6):
    out = []
    for i, wd in enumerate(words):
        w = len(wd) * 10
        out.append({"inferText": wd, "lineBreak": i == len(words) - 1,
                    "boundingPoly": {"vertices": [{"x": x, "y": y}, {"x": x + w, "y": y},
                                                  {"x": x + w, "y": y + 20}, {"x": x, "y": y + 20}]}})
        x += w + gap
    return out


def test_read_text_passes_facility_separately(monkeypatch):
    # 같은 시설 문장은 OcrResult.facility로 따로 넘기고, 원재료 글자(text)에는 넣지 않는다
    import src.ocr.clova as clova

    f = _line(["원재료명:", "소맥분,", "설탕"], 10, 10)
    f += _line(["이", "제품은", "땅콩,", "게를", "사용한", "제품과", "같은", "제조시설에서", "제조하고", "있습니다."], 10, 40)
    monkeypatch.setattr(clova, "call_clova", lambda *a, **k: {"images": [{"fields": f}]})
    res = clova.ClovaOcr("x", "x").read_text(b"photo", "image/jpeg")
    assert "같은 제조시설" in res.facility and "땅콩" in res.facility
    assert "제조시설" not in res.text and "땅콩" not in res.text
    assert res.text == "소맥분, 설탕"


def test_ocr_result_facility_defaults_empty():
    assert OcrResult(text="설탕", engine="mock").facility == ""
