"""원재료 사전 v1.2: 표기 변형과 국물·양념 낱말(가이드 N15). 실행: python -m pytest -q

사전 값이 바뀌어 여기가 깨지면 규칙이 아니라 사전 원본(구현/사전/tools/lex_src.py)을 먼저 확인한다.
"""
import pytest

from src.final.lexicon import lookup
from src.final.pipeline import analyze_fields


def verdicts(ingredients, declaration):
    return {a.allergen.value: a.verdict.value for a in analyze_fields(ingredients, declaration).allergens}


@pytest.mark.parametrize("name, allergen, grade", [
    ("헤즐너트페이스트", "tree_nut", "C"),       # EXP-007 표본의 확실한 놓침
    ("헤이즐럿분말", "tree_nut", "C"),
    ("헤즐너트향", "tree_nut", "P"),             # 알레르기 이름을 딴 향료는 가능 (N7)
    ("피캔", "tree_nut", "C"),
    ("요쿠르트분말혼합", "milk", "C"),
    ("락토오스", "milk", "C"),
    ("파르마산", "milk", "C"),                   # '산'으로 끝나도 유기산이 아니다
    ("고르곤졸라소스", "milk", "C"),
    ("가공유정분", "milk", "C"),
    ("소이소스파우더", "soy", "C"),
    ("소이소스파우더", "wheat", "I"),             # 간장과 같게 밀 추정
    ("판코", "wheat", "I"),                       # 빵가루와 같은 추정
    ("세서미", "sesame", "C"),
    ("슈림프", "crustacean", "C"),
    ("크레이피쉬", "crustacean", "C"),
    ("살몬", "fish", "C"),
])
def test_spelling_variants(name, allergen, grade):
    assert lookup(name).us.get(allergen) == grade


def test_crayfish_is_not_fish():
    assert "fish" not in lookup("크레이피쉬").us


@pytest.mark.parametrize("name, sesame, meat", [
    ("매운탕분말", False, False),
    ("부대찌개분말", False, False),
    ("부대찌게맛분말", False, False),            # 찌개의 다른 표기
    ("양지국물농축액", False, True),              # 고기 바탕이 적힌 것 (N14)
    ("비빔장", True, False),                     # 장 양념은 양념·소스 계열
    ("꿀맛전골장", True, False),
])
def test_new_opaque_words(name, sesame, meat):
    hit = lookup(name)
    assert hit.opaque and hit.opaque_sesame == sesame and hit.opaque_meat == meat


@pytest.mark.parametrize("name", ["찌개용묵은지", "부대찌개사리", "부대찌개햄모듬", "전골스파이스분말", "떡볶이분말", "물냉면육수"])
def test_left_out_on_purpose(name):
    # 찌개에 넣는 다른 원료, 근거가 모자란 낱말(전골, 떡볶이분말), 바탕이 적힌 육수(생선 0/113)는 속 모를 원료로 보지 않는다
    assert not lookup(name).opaque


def test_stew_powder_alone_makes_fish_undecidable():
    assert verdicts("매운탕분말, 정제소금", "밀").get("fish") == "undecidable"
    assert verdicts("부대찌개분말, 정제소금", "밀").get("fish") == "undecidable"


def test_jang_sauce_makes_sesame_and_fish_undecidable():
    got = verdicts("비빔장, 정제소금", "대두, 밀")
    assert got.get("sesame") == "undecidable" and got.get("fish") == "undecidable"


def test_meat_broth_concentrate_is_not_a_fish_reason():
    assert "fish" not in verdicts("양지국물농축액, 정제소금", "밀")
