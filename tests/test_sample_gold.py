"""정답지 표본 도구 테스트. 실행: python -m pytest -q tests/test_sample_gold.py

작은 가짜 자료로 거르기 규칙, 층 배정, 제조사 분리, 결정성, 결과 파일을 본다.
"""
import collections
import csv
import json
from pathlib import Path

import pytest

from tools import sample_gold as sg

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "data" / "schema" / "label_record.schema.json")
                    .read_text(encoding="utf-8"))
KINDS = ("과자", "소스류", "즉석조리식품", "만두류", "혼합음료", "기타가공품")    # TYPES 순서와 같은 층


def item(no, kind="과자", maker="㈜가나식품 서울특별시 중구 1", raw="정제수, 설탕, 소금", allergy="밀, 대두 함유",
         gb="식품"):
    return {"prdlstReportNo": no, "prdlstNm": f"가짜제품{no}", "prdkind": kind, "manufacture": maker,
            "rawmtrl": raw, "allergy": allergy, "productGb": gb,
            "imgurl1": f"http://img.example/{no}_1.jpg", "imgurl2": f"http://img.example/{no}_2.jpg"}


def fake_data(n=360, makers=149, new_makers=16):
    """층마다 n/6개. 제조사 하나가 여러 층에 걸친다(149는 6의 배수가 아님).
    앞의 두 바퀴에서 0~new_makers-1번 제조사 제품은 새 제품이고, 세 번째 바퀴의 같은 제조사 제품은 2020년에 있다."""
    items, old = [], {}
    for k in range(n):
        no = f"2026{k:07d}"
        m = k % makers
        maker = f"㈜회사{m:03d} 경기도 수원시 영통구 1"
        items.append(item(no, KINDS[k % 6], maker))
        if not (m < new_makers and k < 2 * makers):
            old[no] = {sg.maker_key(maker)}
    return items, old


def pool_of(items, old):
    return sg.build_pool(items, old)[0]


# ---------- 제조사 열쇠, 층 표 ----------
@pytest.mark.parametrize("text, key", [
    ("㈜미드림/ 충북 충주시 엄정면 김생로 1758", "미드림"),
    ("매일유업㈜상하공장 전라북도 고창군 상하면 자룡리 399", "매일유업"),
    ("F1)㈜동원F&B/충북 진천군 광혜원면 광혜원 산단길 112", "동원fb"),
    ("한울푸드 032)655-9595 경기도 부천시 소사구 중동로 22", "한울푸드"),
    ("농업회사법인 ㈜해드림푸드 ", "해드림푸드"),
    ("롯데푸드㈜ 천안공장/충남 천안시 서북구 2공단 4로 19", "롯데푸드"),
    ("남양유업㈜ 나주공장-전남 나주시 금천면 촌곡리 278", "남양유업"),
    ("주식회사 가나다식품", "가나다식품"),
])
def test_maker_key_strips_legal_form_address_phone_factory(text, key):
    assert sg.maker_key(text) == key


@pytest.mark.parametrize("text", ["알수없음", "알수없음 ", "", "충남 논산시 지산길 64-4", "㈜"])
def test_maker_key_unknown(text):
    assert sg.maker_key(text) == sg.UNKNOWN_MAKER


@pytest.mark.parametrize("kind, ptype", [
    ("과자", "snack"), ("땅콩 또는 견과류가공품", "snack"), ("빵류(케이크)", "snack"),
    ("소스류", "sauce_seasoning"), ("양조간장", "sauce_seasoning"), ("조미된장", "sauce_seasoning"),
    ("유탕면류(봉지라면)", "instant"), ("즉석조리식품", "instant"), ("면-국수,스프-복합조미식품", "instant"),
    ("만두류", "frozen"), ("냉동식품, 어묵", "frozen"),
    ("혼합음료", "beverage_dairy"), ("과 · 채주스", "beverage_dairy"), ("두유", "beverage_dairy"),
    ("어묵", "other"), ("조미김", "other"), ("두부", "other"), ("알수없음", "other"), ("", "other"),
])
def test_product_type_table(kind, ptype):
    assert sg.product_type(kind) == ptype


# ---------- 거르기 ----------
@pytest.mark.parametrize("changes, reason", [
    ({"rawmtrl": "  "}, "원재료 없음"),
    ({"rawmtrl": "가" * 20001}, "파서 실패"),                       # 파서의 길이 제한을 넘는다
    ({"rawmtrl": "( )"}, "파서 실패"),                              # 이름이 하나도 안 나온다
    ({"rawmtrl": "정제수, 설탕"}, "원재료 3개 미만"),
    ({"rawmtrl": "혼합조미분말(멸치분말, 정제염, 설탕)"}, "원재료 3개 미만"),   # 맨 위 원재료만 센다
    ({"allergy": "알수없음"}, "표시란 확인 불가"),
    ({"allergy": "포장재: 폴리에틸렌"}, "표시란 확인 불가"),
    ({"productGb": "축산물"}, "식품 아님"),
    ({"manufacture": "알수없음"}, "제조사 확인 불가"),
    ({"allergy": "없음"}, None),                                    # 표시란을 읽었고 적힌 것이 없음
    ({"rawmtrl": "면: 소맥분, 팜유 / 스프: 정제소금, 설탕"}, None),       # 머리말은 풀어서 4개
])
def test_check_rules(changes, reason):
    it = dict(item("1"), **changes)
    got, parsed = sg.check(it)
    assert got == reason
    assert (parsed is None) == (reason is not None)


def test_build_pool_counts_each_stage_once_and_flags_2020():
    items = [item("1"), item("1"), item("2", raw=""), item("3", allergy="알수없음"), item("4", gb="축산물"),
             item("5"), item(" 6 ")]
    pool, counts = sg.build_pool(items, {"5": {"x"}})
    assert [c.no for c in pool] == ["1", "5", "6"]                 # 번호 앞뒤 공백은 뗀다
    assert [c.in_2020 for c in pool] == [False, True, False]
    assert pool[0].declared == ("밀", "대두")
    assert counts["품목보고번호 없음·중복"] == 1 and counts["원재료 없음"] == 1
    assert counts["표시란 확인 불가"] == 1 and counts["식품 아님"] == 1
    assert sum(counts.values()) + len(pool) == len(items)


# ---------- 층 배정 ----------
def test_allocate_keeps_minimum_and_proportion():
    sizes = {"snack": 1300, "sauce_seasoning": 600, "instant": 460, "frozen": 110, "beverage_dairy": 370,
             "other": 930}
    alloc = sg.allocate(sizes, sg.Settings())
    assert sum(alloc.values()) == 200
    assert min(alloc.values()) == 20 and alloc["frozen"] == 20
    assert alloc["snack"] > alloc["other"] > alloc["sauce_seasoning"] > alloc["instant"]


def test_allocate_stops_when_a_type_is_too_small():
    sizes = {t: 100 for t in sg.TYPES}
    sizes["frozen"] = 19
    with pytest.raises(ValueError):
        sg.allocate(sizes, sg.Settings())


def test_largest_remainder_sums_to_total():
    assert sg.largest_remainder({"a": 1, "b": 1, "c": 1}, 10) == {"a": 4, "b": 3, "c": 3}


# ---------- 뽑기 ----------
def test_draw_is_deterministic_for_same_seed():
    pool = pool_of(*fake_data())
    first, again = sg.draw(pool, sg.Settings()), sg.draw(list(reversed(pool)), sg.Settings())
    assert [c.no for c in first.dev] == [c.no for c in again.dev]       # 입력 순서와도 관계없다
    assert [c.no for c in first.test] == [c.no for c in again.test]
    other = sg.draw(pool, sg.Settings(seed=1))
    assert [c.no for c in other.test] != [c.no for c in first.test]


def test_draw_sizes_types_and_new_products():
    s = sg.Settings()
    sample = sg.draw(pool_of(*fake_data()), s)
    assert len(sample.dev) == s.dev and len(sample.test) == s.total - s.dev
    total = collections.Counter(c.ptype for c in sample.dev + sample.test)
    assert total == collections.Counter(sample.alloc) and min(total.values()) >= s.min_per_type
    assert sum(1 for c in sample.test if not c.in_2020) == s.new_in_test
    assert all(c.in_2020 for c in sample.dev)


def test_draw_separates_makers_and_caps_each_maker():
    s = sg.Settings()
    sample = sg.draw(pool_of(*fake_data()), s)
    dev_makers = {c.maker for c in sample.dev}
    assert not dev_makers & {c.maker for c in sample.test}
    assert not dev_makers & sample.new_makers                         # 새 제품을 낸 제조사는 모두 시험 쪽
    per_maker = collections.Counter(c.maker for c in sample.dev + sample.test)
    assert max(per_maker.values()) <= s.max_per_maker


def test_new_product_shortfall_is_filled_from_the_rest():
    s = sg.Settings()
    sample = sg.draw(pool_of(*fake_data(new_makers=4)), s)             # 새 제품 8개뿐
    assert sum(1 for c in sample.test if not c.in_2020) == 8
    assert len(sample.test) == s.total - s.dev


def test_draw_stops_when_maker_cap_makes_quota_impossible():
    items, old = fake_data(makers=40)                                  # 40곳 x 3개 = 최대 120개 < 200
    with pytest.raises(ValueError):
        sg.draw(pool_of(items, old), sg.Settings())


# ---------- 결과 레코드, heldout ----------
def test_blank_record_follows_schema():
    c = pool_of([item("77", allergy="우유, 대두, 밀 함유")], {})[0]
    rec = sg.blank_record(c, "B_test_001")
    props = SCHEMA["properties"]
    assert set(SCHEMA["required"]) <= set(rec) <= set(props)
    assert rec["product_type"] in props["product_type"]["enum"]
    assert rec["package_material"] in props["package_material"]["enum"]
    assert rec["annotations"] == [] and rec["annotator"] == "" and rec["report_number"] == "77"
    assert rec["ingredients_text"] == "정제수, 설탕, 소금"
    assert rec["kr_declared_allergens"] == ["우유", "대두", "밀"]
    assert rec["image_files"] == ["http://img.example/77_1.jpg", "http://img.example/77_2.jpg"]
    assert rec["notes"].split("\n") == ["제품명: 가짜제품77", "식품유형: 과자", "제조사: ㈜가나식품 서울특별시 중구 1",
                                        "표시란 원문: 우유, 대두, 밀 함유"]


def test_heldout_uses_both_sources_and_borrows_2026_maker():
    now_keys = {"1": "가", "2": "가", "3": "나", "4": sg.UNKNOWN_MAKER}
    old = {"1": {"가"}, "9": {"가"}, "4": {sg.UNKNOWN_MAKER}, "5": {sg.UNKNOWN_MAKER}, "2": {"다른이름"}}
    ids, borrowed = sg.heldout(frozenset({"가"}), now_keys, old)
    assert ids == ["1", "2", "9"] and borrowed == 1                   # '2'는 2026 제조사를 빌려 잇는다
    assert sg.heldout(frozenset({sg.UNKNOWN_MAKER}), now_keys, old) == ([], 0)


# ---------- 파일 읽기와 명령줄 ----------
def write_inputs(tmp_path, items, old):
    items_path = tmp_path / "items.jsonl"
    items_path.write_text("".join(json.dumps(it, ensure_ascii=False) + "\n" for it in items), encoding="utf-8")
    csv_path = tmp_path / "old.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rnum", "prdlstreportno", "manufacture"])
        for i, no in enumerate(sorted(old)):
            w.writerow([i, f" {no} ", f"㈜{sorted(old[no])[0]}"])       # 실제 자료처럼 번호 앞뒤에 공백
    return items_path, csv_path


def test_read_inputs_reject_broken_files(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"prdlstReportNo": "1"}\n{깨진 줄\n', encoding="utf-8")
    with pytest.raises(ValueError, match="2번째 줄"):
        sg.read_items(bad)
    no_col = tmp_path / "no_col.csv"
    no_col.write_text("rnum,manufacture\n1,가\n", encoding="utf-8")
    with pytest.raises(ValueError, match="prdlstreportno"):
        sg.read_old(no_col)


def test_main_writes_outputs_and_prints_only_counts(tmp_path, capsys):
    items_path, csv_path = write_inputs(tmp_path, *fake_data())
    out = tmp_path / "gold"
    argv = ["--items", str(items_path), "--old-csv", str(csv_path), "--out", str(out)]
    assert sg.main(argv) == 0
    printed = capsys.readouterr().out
    assert "가짜제품" not in printed and "정제수" not in printed and "회사" not in printed
    ids = (out / "gold_ids.txt").read_text(encoding="utf-8").splitlines()
    test_recs = [json.loads(x) for x in (out / "test_blank.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(ids) == len(set(ids)) == 200
    assert ids[60:] == [r["report_number"] for r in test_recs] and test_recs[0]["id"] == "B_test_001"
    held = set((out / "heldout_ids_test.txt").read_text(encoding="utf-8").split())
    assert set(ids[60:]) <= held and not set(ids[:60]) & held
    manifest = json.loads((out / "sample_manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == 20261113 and manifest["test"]["new"] == 30 and len(manifest["lists"]["in_2020"]) == 200
    before = {p.name: p.read_bytes() for p in out.iterdir() if p.name != "sample_manifest.json"}
    assert sg.main(argv) == 0                                         # 같은 입력·시드면 같은 파일
    assert {p.name: p.read_bytes() for p in out.iterdir() if p.name != "sample_manifest.json"} == before
    with pytest.raises(SystemExit):                                   # 다른 표본으로 덮어쓰려면 --force
        sg.main(argv + ["--seed", "1"])
    assert sg.main(argv + ["--seed", "1", "--force"]) == 0
