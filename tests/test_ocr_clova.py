"""CLOVA 응답 -> 원재료명 칸 추출 테스트 (네트워크 호출 없음, 가짜 응답 사용)."""
from src.ocr.clova import extract_label


def _field(text, x, y, w=None, h=20, line_break=False):
    w = w or len(text) * 10
    return {"inferText": text, "lineBreak": line_break,
            "boundingPoly": {"vertices": [{"x": x, "y": y}, {"x": x + w, "y": y}, {"x": x + w, "y": y + h}, {"x": x, "y": y + h}]}}


def _line(words, x, y, gap=6):
    out = []
    for i, wd in enumerate(words):
        f = _field(wd, x, y, line_break=(i == len(words) - 1))
        out.append(f)
        x += len(wd) * 10 + gap
    return out


def _raw(fields):
    return {"images": [{"fields": fields}]}


def test_table_label_left_with_nutrition_column_right():
    # 왼쪽 항목명 칸 / 가운데 원재료명 / 오른쪽 영양정보 칸 (CLOVA는 칸마다 줄을 따로 준다)
    f = []
    f += _line(["제품명"], 10, 10) + _line(["테스트라면"], 120, 10)
    f += _line(["원재료명"], 10, 40)
    f += _line(["소맥분(밀:미국산),", "팜유(말레이시아산),", "고"], 120, 40) + _line(["나트륨", "800mg"], 600, 40)
    f += _line(["추가루,", "간장분말(대두,", "밀)"], 120, 64) + _line(["탄수화물", "50g"], 600, 64)
    f += _line(["밀,", "대두", "함유"], 120, 88)
    f += _line(["·이", "제품은", "땅콩,", "게를", "사용한", "제품과", "같은", "제조시설에서", "제조하고", "있습니다."], 10, 116)
    f += _line(["내용량"], 10, 140) + _line(["120g"], 120, 140)
    info = extract_label(_raw(f))
    assert info["text"] == "소맥분(밀:미국산), 팜유(말레이시아산), 고추가루, 간장분말(대두, 밀) 밀, 대두 함유"
    assert "땅콩" in info["facility"] and "같은 제조시설" in info["facility"]


def test_label_vertically_centered_content_above_and_below():
    f = []
    f += _line(["보관방법"], 10, 0) + _line(["실온보관"], 120, 0)
    f += _line(["정제수,", "양파(국내산),"], 120, 30)
    f += _line(["원재료명"], 10, 54) + _line(["카레분(밀,", "우유),"], 120, 54)
    f += _line(["강황분말"], 120, 78) + _line(["밀,", "우유", "함유"], 300, 78)
    info = extract_label(_raw(f))
    assert info["text"] == "정제수, 양파(국내산), 카레분(밀, 우유), 강황분말 밀, 우유 함유"


def _box_field(text, x, y, w, h):
    return {"inferText": text, "lineBreak": True,
            "boundingPoly": {"vertices": [{"x": x, "y": y}, {"x": x + w, "y": y}, {"x": x + w, "y": y + h}, {"x": x, "y": y + h}]}}


def test_tilted_photo_with_neighbor_column_bullets():
    # 구겨진 비닐(p08): 기울어져 위아래 줄 상자가 겹치고, 오른쪽 옆 칸의 '·마' 조각이 칸 경계에 걸침.
    # 함유 표시는 '밀, 대두,'가 오른쪽 위, '계란, 우유'가 아래 줄, '함유'가 그 오른쪽.
    f = [
        _box_field("원료명 *면:밀가루(밀),변성전분,감", 10, 0, 600, 40),
        _box_field("자전분,정제소금,로스팅조", 10, 24, 600, 40),
        _box_field("·마", 605, 30, 25, 16),
        _box_field("미분말,건파,건미역", 10, 48, 600, 40),
        _box_field("밀, 대두,", 540, 72, 60, 20),
        _box_field("계란, 우유", 10, 88, 300, 40),
        _box_field("함유", 560, 90, 40, 20),
        _box_field("내용량 120g", 10, 140, 200, 20),
    ]
    info = extract_label(_raw(f))
    assert info["text"] == "*면:밀가루(밀), 변성전분, 감자전분, 정제소금, 로스팅조미분말, 건파, 건미역 밀, 대두, 계란, 우유 함유"


def test_inline_label_stops_at_next_item():
    f = _line(["원재료명:", "설탕,", "코코아버터(카카오:가나산),", "유청분말(우유)"], 10, 10) + _line(["우유", "함유"], 10, 34)
    f += _line(["소비기한", "2027.01.01"], 10, 58)
    info = extract_label(_raw(f))
    assert info["text"] == "설탕, 코코아버터(카카오:가나산), 유청분말(우유) 우유 함유"
