"""사전에 없는 이름 처리 테스트 (자모, 끝 기호 떼기, 오타에 강한 맞추기, 보조 분류기). 실행: python -m pytest -q

실제 원재료 사전을 쓴다. 사전이 바뀌어 예시 이름이 사전에 들어가면(모르는 이름이 아니게 되면) 그 사례만 건너뛴다.
보조 분류기는 가짜로만 시험한다. 실제 LLM은 부르지 않는다.
"""
import unicodedata
from types import SimpleNamespace

import pytest

from src.common.schema import Allergen, AllergenMatch, IngredientClassification, Verdict
from src.final import resolve as R
from src.final.jamo import (N_CHO, N_JONG, N_JUNG, distance, is_syllable, join_syllable, split_syllable,
                            syllables, to_jamo)
from src.final.lexicon import lookup
from src.final.parser import parse_label
from src.final.verdict import judge


def unknown(name):
    if lookup(name).via != "unknown":
        pytest.skip(f"사전이 바뀌어 '{name}'이(가) 이제 모르는 이름이 아니다")
    return name


def got(j):
    return {v.allergen: v.verdict for v in j.allergens}


# ---------- 자모 ----------
def test_jamo_matches_unicode_decomposition():
    text = "탈지분유 깨 L-글루탐산"
    assert to_jamo(text) == unicodedata.normalize("NFD", text)
    assert split_syllable("분") == (7, 13, 4) and join_syllable(7, 13, 4) == "분"
    assert syllables("비타민B2") == 3 and not is_syllable("B")
    with pytest.raises(ValueError):
        split_syllable("a")


@pytest.mark.parametrize("a, b, d", [("탈지분유", "탈지븐유", 1), ("유화제", "유화재", 1), ("유자", "유장", 1),
                                     ("들깨", "참깨", 3), ("대두", "대구", 1), ("우유", "두유", 1)])
def test_jamo_distance(a, b, d):
    assert distance(to_jamo(a), to_jamo(b)) == d
    assert distance(to_jamo(a), to_jamo(b), limit=0) == 1          # 한도를 넘으면 한도 + 1


# ---------- 비슷한 이름 찾기: 받는 경우 ----------
@pytest.mark.parametrize("name, target, d", [("탈지븐유", "탈지분유", 1), ("난맥분말", "난백분말", 1), ("정세수", "정제수", 1),
                                             ("게란후레이크", "계란후레이크", 1), ("d-토콮페롤", "d-토코페롤", 1),
                                             ("다미사농축액", "다시마농축액", 2)])     # 6음절, 판정을 바꾸지 않는 항목
def test_typo_inherits_entry(name, target, d):
    m = R.nearest(unknown(name))
    assert m is not None and m.target == target and m.distance == d
    assert m.hit.name == name and m.hit.via == "fuzzy"
    assert R.verdict_key(m.hit) == R.verdict_key(lookup(target))      # 칸을 통째로 물려받는다


# ---------- 비슷한 이름 찾기: 받지 않는 경우 ----------
@pytest.mark.parametrize("name", ["대듀", "우뮤", "개", "물ㅡ", "밀크"])
def test_short_names_never_fuzzy(name):
    if lookup(name).via == "unknown":
        assert R.nearest(name) is None                              # 대두/대구, 우유/두유, 밀/물, 게/개는 3음절 조건에서 걸린다


@pytest.mark.parametrize("name, why", [
    ("카베인", "카제인(우유)·카세인·카페인이 모두 거리 1"),
    ("유잠분말", "유장분말(우유)과 유자분말(관계없음)이 모두 거리 1"),
    ("내우엑기스", "새우엑기스(새우)는 1, 무우엑기스(관계없음)는 2: 반경 2 안에서 판정이 갈린다"),
    ("쇼트님", "판정을 바꾸는 항목(쇼트닝)인데 3음절"),
    ("해골페이스트", "판정을 바꾸는 항목(해물페이스트)인데 자모 거리 2"),
    ("대추분말", "바뀐 음절을 품은 '대추'가 사전 이름 (대두분말이 아니다)"),
    ("단백분말", "'단백'은 사전 이름에 흔한 짝 (난백분말이 아니다)"),
    ("치자분말", "'치자'가 사전 이름 (치즈분말이 아니다)"),
    ("효모제제", "'효모'가 사전 이름 (효소제제가 아니다)"),
    ("파인소프트-씨", "제품 기호가 다르다 (파인소프트티)"),
    ("수수추출물", "새우추출물과 거리 2"),
    ("파인애플잼", "5음절에서 자모 거리 2 (파인애플즙이 아니다)"),
    ("초계엑기스", "5음절에서 자모 거리 2 (조개엑기스가 아니다)"),
])
def test_risky_inputs_not_inherited(name, why):
    assert R.nearest(unknown(name)) is None, why


def test_latin_and_digits_must_match():
    assert R.candidates("탈지븐유x") == []             # 영문·숫자는 그대로 같아야 한다
    assert R.nearest(unknown("탈지븐유x")) is None


def _between(a, b):
    """음절 a, b 둘 다와 자모 거리 1인 셋째 음절 (없으면 None)."""
    for slot, size in enumerate((N_CHO, N_JUNG, N_JONG)):
        for v in range(size):
            parts = list(split_syllable(a))
            parts[slot] = v
            s = join_syllable(*parts)
            if s not in (a, b) and distance(to_jamo(s), to_jamo(a)) == 1 == distance(to_jamo(s), to_jamo(b)):
                return s
    return None


def test_dictionary_pairs_with_different_verdicts_block_inputs_between_them():
    """사전 안에서 서로 거리 1인데 판정이 다른 짝(3음절 이상)을 전부 찾고, 둘 사이의 입력은 물려받지 않는지 본다."""
    idx = R._index()
    pairs = set()
    for i, name in enumerate(idx.names):
        for other, d in R.candidates(name):
            j = idx.names.index(other)
            if d == 1 and idx.tags[i] != idx.tags[j]:
                pairs.add(tuple(sorted((i, j))))
    assert pairs, "짝이 하나도 없으면 검사가 의미 없다 (카제인/카페인 등)"
    tried = 0
    for i, j in sorted(pairs):
        a, b = idx.keys[i], idx.keys[j]
        p = next(k for k in range(len(a)) if a[k] != b[k])
        mid = _between(a[p], b[p])
        if mid is None or lookup(a[:p] + mid + a[p + 1:]).via != "unknown":
            continue
        tried += 1
        assert R.nearest(a[:p] + mid + a[p + 1:]) is None, (idx.names[i], idx.names[j])
    assert tried > 0


# ---------- 끝 기호 떼기 ----------
@pytest.mark.parametrize("name, target", [("감자전분II", "감자전분"), ("감자전분Ⅱ", "감자전분"), ("혼합야채분말-HT", "혼합야채분말"),
                                          ("망고농축액53Bx", "망고농축액"), ("카레분TC", "카레분"), ("다시마엑기스TK", "다시마엑기스")])
def test_code_tail_is_stripped(name, target):
    m = R.without_code(unknown(name))
    assert m is not None and m.target == target and m.hit.via == "code" and m.hit.name == name


@pytest.mark.parametrize("name", ["비타민B", "엽산A", "물A", "게TK", "아무개분말TK"])
def test_code_tail_kept_or_refused(name):
    if lookup(name).via == "unknown":
        assert R.without_code(name) is None       # 비타민·엽산 뒤는 이름의 일부, 한 음절 이름, 사전에 없는 이름


@pytest.mark.parametrize("name", ["유화제II", "유화제CMC", "아미노MW"])
def test_code_tail_on_a_short_name_does_not_bring_a_verdict(name):
    """뗀 이름이 판정을 바꾸는 항목(유화제 대두 가능, 아미노 밀 추정)이면 4음절 이상일 때만 받는다."""
    assert R.without_code(unknown(name)) is None
    assert R.Resolver().resolve(name).via == "unknown"


def test_resolver_steps_can_be_turned_off_and_write_notes():
    r = R.Resolver()
    assert r.resolve(unknown("다시마엑기스TK")).via == "code" and r.resolve("다시마엑기스TK").us == {}
    assert r.resolve(unknown("탈지븐유")).us == {"milk": "C"}
    assert r.notes() == ["끝 기호를 떼고 맞춤: 다시마엑기스TK → 다시마엑기스", "오타로 보고 맞춤: 탈지븐유 → 탈지분유"]
    assert r.matched == {"다시마엑기스TK": "다시마엑기스", "탈지븐유": "탈지분유"}
    off = R.Resolver(fuzzy=False, codes=False)
    assert off.resolve("다시마엑기스TK").via == "unknown" and off.resolve("탈지븐유").via == "unknown"
    assert off.notes() == []
    with pytest.raises(TypeError):
        r.resolve(None)


def test_judge_uses_resolver():
    parsed = parse_label("원재료명: 탈지븐유, 설탕, 정세수")
    plain = judge(parsed)
    assert "milk" not in got(plain) and "탈지븐유" in plain.undecidable_ingredients
    r = R.Resolver()
    j = judge(parsed, resolve=r.resolve)
    assert got(j)["milk"] == "confirmed" and j.allergens[0].evidence == "탈지븐유"
    assert j.undecidable_ingredients == ()
    assert r.notes() == ["오타로 보고 맞춤: 탈지븐유 → 탈지분유", "오타로 보고 맞춤: 정세수 → 정제수"]


# ---------- 보조 분류기 ----------
class FakeClassifier:
    name = "fake"
    prompt_version = None

    def __init__(self, table=None, fail=False, extra=()):
        self.table, self.fail, self.extra, self.calls = table or {}, fail, extra, []

    def classify(self, ingredients):
        self.calls.append(list(ingredients))
        if self.fail:
            raise RuntimeError("연결 끊김")
        out = [IngredientClassification(ingredient=n, matches=[AllergenMatch(allergen=a, verdict=v) for a, v in ms],
                                        source_unknown=u)
               for n, (ms, u) in self.table.items() if n in ingredients]
        return out + list(self.extra)


def test_fallback_called_once_with_only_unknown_names():
    fake = FakeClassifier({
        "웰가에스피": ([(Allergen.milk, Verdict.confirmed), (Allergen.soy, Verdict.undecidable)], False),
        "케이디비타": ([], True),
    }, extra=[IngredientClassification(ingredient="설탕", matches=[AllergenMatch(allergen=Allergen.egg,
                                                                              verdict=Verdict.confirmed)])])
    names = [unknown("웰가에스피"), "설탕", unknown("탈지븐유"), unknown("케이디비타"), unknown("DOOLEMN-1"), "웰가에스피"]
    r = R.Resolver(fallback=fake)
    hits = r.resolve_many(names)
    assert fake.calls == [["웰가에스피", "케이디비타", "DOOLEMN-1"]]       # 사전·오타 맞추기로 찾은 이름은 묻지 않는다
    assert hits[0].via == "fallback" and hits[0].sources == (("milk", "I"), ("soy", "P"))   # 확정은 추정으로 낮춘다
    assert hits[1].via == "entry" and hits[1].sources == ()                 # 묻지 않은 이름의 답(설탕 달걀)은 버린다
    assert hits[3].via == "unknown" and hits[4].via == "unknown"           # source_unknown, 답 없음
    assert r.resolve("웰가에스피") is hits[0]
    r.resolve_many(names)
    assert len(fake.calls) == 1                                             # 한 번 물은 이름은 다시 묻지 않는다
    assert r.notes()[-1] == "사전에 없어 보조 분류기로 판단(확정은 추정으로 낮춤): 웰가에스피"


def test_fallback_saying_unrelated_keeps_the_name_unknown():
    """보조 분류기가 9개와 관계없다고 답해도 모르는 이름을 지우지 않는다 (확인할 수 없는 답이다)."""
    fake = FakeClassifier({"웰가에스피": ([], False)})
    r = R.Resolver(fallback=fake)
    assert r.resolve_many([unknown("웰가에스피")])[0].via == "unknown"
    assert r.notes() == []


def test_fallback_failure_or_broken_answer_keeps_unknown():
    r = R.Resolver(fallback=FakeClassifier(fail=True))
    assert r.resolve_many([unknown("웰가에스피")])[0].via == "unknown"
    assert r.notes() == ["보조 분류기 호출 실패(RuntimeError): 모르는 이름 1개를 그대로 둠"]
    broken = SimpleNamespace(ingredient="웰가에스피", source_unknown=False,
                             matches=[SimpleNamespace(allergen="celery", verdict="confirmed")])
    assert R.from_classification("웰가에스피", broken) is None
    with pytest.raises(TypeError):
        r.resolve_many("웰가에스피")


def test_fallback_from_env(monkeypatch):
    for key in (R.FALLBACK_ENV,) + R.KEY_ENVS:
        monkeypatch.delenv(key, raising=False)
    assert R.fallback_from_env() is None                                  # 기본은 꺼짐
    monkeypatch.setenv(R.FALLBACK_ENV, "llm")
    assert R.fallback_from_env() is None                                  # 키가 없으면 켜지 않는다
    monkeypatch.setenv("LLM_API_KEY", "test-not-a-real-key")
    import src.model
    monkeypatch.setattr(src.model, "get_classifier", lambda name: ("가짜", name))
    assert R.fallback_from_env() == ("가짜", "llm")
    monkeypatch.setenv(R.FALLBACK_ENV, "gpt")
    with pytest.raises(ValueError):
        R.fallback_from_env()
