"""규칙으로 찾은 이름의 앞부분 오타 (src/final/resolve.py 모듈 설명 7, 8). 팀 리뷰에서 나온 예. 실행: python -m pytest -q"""
from src.final.lexicon import unexplained_parts
from src.final.pipeline import analyze_fields
from src.final.resolve import Resolver, suspect_typo, typo_behind_rule


def verdicts(ingredients, box):
    r = analyze_fields(ingredients, box)
    return {a.allergen.value: a.verdict.value for a in r.allergens}, list(r.undecidable_ingredients), list(r.notes)


def test_whole_name_typo_of_entry_is_matched():
    # 땅공버터: 끝의 '버터' 규칙만 걸려 우유로 읽히던 이름. 땅콩버터로 맞추면 땅콩이고 우유가 아니다
    got, unclear, notes = verdicts("설탕, 땅공버터, 정제소금", None)
    assert got.get("peanut") == "confirmed" and "milk" not in got
    assert "오타로 보고 맞춤: 땅공버터 → 땅콩버터" in notes
    assert typo_behind_rule("땅공버터").target == "땅콩버터"


def test_typo_in_allergen_word_becomes_possible_and_is_listed():
    # 피너버터, 땅공크림: 사전에 이름 전체가 없어 맞추지 못한다. 땅콩을 '가능'으로 더하고 판정 불가 원재료에 넣는다
    for name in ("피너버터", "땅공크림"):
        got, unclear, notes = verdicts(f"설탕, {name}, 정제소금", None)          # 표시란을 못 읽었다
        assert got.get("peanut") == "undecidable", name
        assert name in unclear
        assert any(n.startswith(f"오타일 수 있음: {name}") for n in notes)
    assert suspect_typo("피너버터").word == "피넛"


def test_box_settles_the_suspected_allergen():
    got, unclear, _ = verdicts("설탕, 피너버터", "땅콩, 우유 함유")
    assert got.get("peanut") == "confirmed"                     # 표시란에 땅콩: 확인됨 (R1)
    got, unclear, _ = verdicts("설탕, 땅공크림", "우유 함유")
    assert "peanut" not in got and "땅공크림" in unclear          # 표시란을 읽었는데 땅콩이 없다: 지운다 (R2), 이름은 남긴다


def test_ordinary_rule_names_are_left_alone():
    # 규칙 밖 조각('가루', '연성', '양조')이 알레르기 낱말과 가깝지 않으면 아무것도 더하지 않는다
    for name, allergen in (("새우가루", "crustacean"), ("연성치즈", "milk"), ("강력밀가루", "wheat")):
        got, unclear, notes = verdicts(name, None)
        assert got.get(allergen) == "confirmed" and name not in unclear and not any("오타" in n for n in notes), name
    # 진짜 낱말끼리 자모 하나 차이(단백/난백, 고기/조기, 그릴/크릴)는 오타로 보지 않는다
    for name in ("분리대두단백", "다진돼지고기", "그릴치킨농축액"):
        assert suspect_typo(name) is None and typo_behind_rule(name) is None, name
    assert unexplained_parts("땅콩버터") == ()


def test_fuzzy_off_turns_it_off():
    r = Resolver(fuzzy=False)
    assert r.resolve("땅공버터").via == "rule" and not r.suspects and not r.matched


def test_whole_name_typo_wins_over_part_typo():
    # 대두산백은 대두단백의 오타다. '산백'을 '난백'의 오타로 보아 달걀을 더하면 안 된다
    assert suspect_typo("대두산백") is None
    got, unclear, _ = verdicts("대두산백, 설탕", None)
    assert "egg" not in got


def test_two_syllable_parts_only_against_allergen_heads():
    # 2026년 자료에서 잘못 걸렸던 두 음절 조각: 육장/유장, 버거/버터, 타요/마요, 에쓰/에그
    for name in ("쇠고기육장", "실속햄버거스테이크시즈닝", "타요견과라니", "존쿡델리미트씨즈닝에쓰"):
        assert suspect_typo(name) is None, name
    # 대표 이름의 오타는 잡는다
    assert suspect_typo("땅공크림").word == "땅콩"
    assert suspect_typo("모타렐라씨즈닝").word == "모짜렐라"      # 세 음절 이상은 모든 알레르기 낱말과 견준다
