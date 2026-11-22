"""규칙의 짧은 낱말이 다른 이름 안에 걸리던 오류(사전 v1.2.1). 실행: python -m pytest -q

식약처 품목제조보고 원재료(C002) 20,000개 제품을 최종본에 돌려 찾은 이름들이다.
"""
import pytest

from src.final.lexicon import lookup
from src.final.resolve import Resolver


@pytest.mark.parametrize("name, wrong", [
    ("그린콩꼬투리", "soy"), ("통카콩", "soy"), ("오렌지콩크", "soy"),
    ("호두유", "soy"),            # 호두 기름: '두유'
    ("대두갈치", "soy"),          # 생선 이름: '대두'
    ("당밀추출물", "wheat"),      # 당밀: '밀추출'
    ("약모밀추출분말", "wheat"),  # 약모밀(어성초): '밀추출'
    ("모밀가루", "wheat"),        # 모밀 = 메밀
    ("돼지단백", "egg"),          # '지단'
    ("잉카피넛열매", "peanut"),   # 사차인치
    ("카프론산알릴", "crustacean"),  # 향료 성분: '프론'(prawn)
    ("밀크락톤", "milk"),         # 합성 향료 성분
])
def test_word_inside_word_is_not_an_allergen(name, wrong):
    assert wrong not in lookup(name).us


@pytest.mark.parametrize("name, allergen", [
    ("밀맥아분말", "wheat"), ("강력밀", "wheat"), ("박력밀", "wheat"), ("밀호분층", "wheat"),
    ("흑밀복", "fish"), ("까치복", "fish"), ("자주복", "fish"), ("졸복", "fish"),
    ("대두갈치", "fish"), ("호두유", "tree_nut"),
    ("밤콩", "soy"), ("속청", "soy"), ("검은콩속청", "soy"),   # 밤콩·속청은 재래 대두 (#27 리뷰)
])
def test_missing_names_are_found(name, allergen):
    assert allergen in lookup(name).us


def test_dalgogi_is_fish_not_chicken():
    # 달고기(John Dory)는 생선. 비슷한 이름 찾기가 '닭고기'로 바꾸던 것을 사전 항목으로 막는다
    r = Resolver(fuzzy=True)
    assert "fish" in r.resolve("달고기").us


@pytest.mark.parametrize("name, allergen", [
    ("두유", "soy"), ("검은콩", "soy"), ("콩가루", "soy"), ("새우", "crustacean"), ("프론", "crustacean"),
    ("밀가루", "wheat"), ("계란지단", "egg"), ("땅콩", "peanut"), ("피넛버터", "peanut"), ("복어", "fish"),
])
def test_existing_matches_still_work(name, allergen):
    assert allergen in lookup(name).us


@pytest.mark.parametrize("name", ["숙지황복합추출물", "복숭아", "황복숭아", "당밀"])
def test_no_new_false_alarm(name):
    assert not lookup(name).us
