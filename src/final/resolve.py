"""사전에 없는 원재료 이름 다루기: 사전 조회 -> 끝 기호 떼기 -> 오타에 강한 맞추기 -> (켰을 때만) 보조 분류기.

    from src.final.resolve import Resolver
    r = Resolver()
    r.resolve("탈지븐유").us      # {'milk': 'C'}  탈지분유의 판정을 물려받는다 (via 'fuzzy')
    r.resolve("다시마엑기스TK").via   # 'code'  끝 기호를 떼면 사전의 다시마엑기스다
    r.notes()                     # ['오타로 보고 맞춤: 탈지븐유 → 탈지분유', '끝 기호를 떼고 맞춤: 다시마엑기스TK → 다시마엑기스']
    judge(parsed, resolve=r.resolve)

끝 기호 떼기: '혼합야채분말-HT', '망고농축액53Bx'처럼 끝에 붙은 영문·숫자 기호를 떼서 정확 일치 사전 항목이나
관계없는 무리로 찾아질 때만 받는다. 비타민·오메가·코엔자임·엽산 뒤의 글자는 이름의 일부라 떼지 않는다(파서와 같다).
뗀 이름이 알레르기 판정을 바꾸는 항목이면 4음절 이상일 때만 받는다. '유화제CMC'(유화제, 대두 가능), '아미노MW'(아미노, 밀 추정)처럼
짧은 이름에 붙은 글자는 기호가 아니라 다른 원료의 이름일 수 있다.

비슷한 이름 찾기는 틀리게 맞추는 것이 못 맞추는 것보다 나쁘다고 보고 보수적으로 한다.
1. 사전(lexicon.lookup)이 모르는 이름(via 'unknown')만, 한글 3음절 이상만 본다. 대두/대구, 우유/두유 같은 짧은 짝을 피한다.
2. 자모 거리 1까지 받는다(6음절 이상이고 판정을 바꾸지 않는 항목이면 2까지). 후보는 5음절 이상이면 거리 2까지 본다.
   음절 수와 영문·숫자는 그대로 같아야 한다.
3. 그 반경 안의 후보(정확 일치 사전과 자동 단 이름)끼리 판정이 갈리면 맞추지 않는다.
4. 물려주는 것은 정확 일치 사전(entries.tsv) 항목뿐이다. 원재료가 아닌 표기로는 맞추지 않는다.
5. 알레르기 판정을 바꾸는 항목(9개 출처, 속 모를·섞은 원료)은 4음절 이상, 자모 거리 1일 때만 물려준다.
6. 라벨 이름이 오타가 아니라 다른 실제 이름으로 보이면 맞추지 않는다 (looks_real).
보조 분류기(팀 Classifier, 예: LLM)는 resolve_many에서 끝까지 모르는 이름만 모아 한 번 부르고, 확정은 추정으로 낮춘다.
보조 분류기가 '9개와 관계없다'고 답한 이름은 모르는 이름으로 그대로 둔다. 확인할 수 없는 답으로 모르는 이름을 지우지 않는다.
"""
from __future__ import annotations

import csv
import dataclasses
import logging
import os
import re
import unicodedata
from functools import lru_cache
from typing import Dict, FrozenSet, List, NamedTuple, Optional, Sequence, Tuple

from src.final.jamo import distance, is_syllable, syllables, to_jamo
from src.final.lexicon import HERE, ORDER, Lookup, lookup, norm, strip_origin
from src.final.parser.names import KEEP_CODE_RE

# 정규화한 이름(소문자, 이음표·공백 없음) 끝의 관리 기호: tk, ii, ht / 53bx, 2 / s101
CODE_TAIL_RE = re.compile(r"(?<=[가-힣])(?:[a-z]{1,3}\d{0,2}|\d{1,2}[a-z]{0,2}|[a-z]\d{1,3})$")
CODE_VIA = ("entry", "benign")       # 기호를 뗀 이름이 이것으로 찾아질 때만 받는다
NOTE_HEAD = {"code": "끝 기호를 떼고 맞춤", "fuzzy": "오타로 보고 맞춤"}
MIN_SYLLABLES = 3          # 이보다 짧은 이름은 맞추지 않는다
MIN_SYLLABLES_RISKY = 4    # 알레르기 판정을 바꾸는 항목으로 맞출 때의 최소 음절 수
LONG_SYLLABLES = 5         # 이 음절 수부터 자모 거리 2까지 후보로 본다 (판정이 갈리는지 살피는 범위)
FAR_SYLLABLES = 6          # 이 음절 수부터 자모 거리 2로도 물려준다 (판정을 바꾸지 않는 항목만)
LETTERS = frozenset("비씨디지피큐티")      # 영문 글자를 읽은 음절. 제품 기호가 다른 것 (파인소프트씨/티)
FALLBACK_ENV = "OPENSESAME_FINAL_FALLBACK"
KEY_ENVS = ("LLM_API_KEY", "ANTHROPIC_API_KEY")
US9 = frozenset({"milk", "egg", "fish", "crustacean", "tree_nut", "peanut", "wheat", "soy", "sesame"})
# 보조 분류기의 판정 -> 사전 등급. 근거 없이 믿지 않도록 확정(C)은 추정(I)으로 낮춘다
VERDICT_GRADE = {"confirmed": "C", "inferable": "I", "undecidable": "P"}
FALLBACK_CAP = {"C": "I"}
_NOT_VERDICT = frozenset({"name", "via", "en", "note", "status"})    # 판정에 쓰이지 않는 칸

log = logging.getLogger(__name__)


class Match(NamedTuple):
    """비슷한 이름 찾기의 결과."""
    name: str            # 라벨에 적힌 이름
    target: str          # 맞춘 사전 항목 이름
    distance: int        # 자모 거리
    hit: Lookup          # 물려준 결과 (name은 라벨 이름, via는 'fuzzy')


class _Index(NamedTuple):
    names: Tuple[str, ...]              # 사전에 적힌 이름 (3음절 이상)
    keys: Tuple[str, ...]               # 정규화한 이름
    jamo: Tuple[str, ...]               # 정규화한 이름을 자모로 푼 것
    hits: Tuple[Lookup, ...]            # 그 이름의 사전 결과
    tags: Tuple[tuple, ...]             # 판정 꼬리표 (verdict_key)
    target: Tuple[bool, ...]            # 물려줄 수 있는 항목인가
    by_mask: Dict[str, Tuple[int, ...]]    # 음절 한두 자리를 가린 꼴 -> 이름 번호들
    known: FrozenSet[str]               # 사전에 있는 2음절 이상 이름 전부 (정규화)
    pairs: FrozenSet[str]               # 사전 이름에 나오는 이웃한 두 음절


# ---------- 판정 꼬리표와 색인 ----------
def verdict_key(hit) -> tuple:
    """판정에 쓰이는 칸(출처·등급, 속 모를 원료·섞은 원료·향료·원재료 아님 표시)만 모은 꼬리표.
    Lookup에 칸이 늘어도 저절로 들어간다."""
    out = []
    for f in dataclasses.fields(hit):
        if f.name in _NOT_VERDICT:
            continue
        value = getattr(hit, f.name)
        out.append((f.name, tuple(sorted(value)) if f.name == "sources" else value))
    return tuple(out)


def changes_verdict(hit) -> bool:
    """물려받으면 알레르기 판정이 바뀔 수 있는가: 미국 9개 출처, 속 모를 원료, 섞은 원료."""
    return bool(hit.us) or bool(hit.opaque) or bool(getattr(hit, "compound", False))


def _radius(n_syllables: int) -> int:
    return 2 if n_syllables >= LONG_SYLLABLES else 1


def _hide(key: str, spots: Tuple[int, ...]) -> str:
    return "".join("\0" if i in spots else ch for i, ch in enumerate(key))


def _masks(key: str, radius: int) -> List[str]:
    """한글 음절 한 자리(반경 2면 두 자리까지)를 가린 꼴들.
    자모 하나가 틀리면 음절 하나만 바뀌므로, 거리 안의 두 이름은 가린 꼴 하나를 반드시 함께 가진다."""
    spots = [i for i, ch in enumerate(key) if is_syllable(ch)]
    out = [_hide(key, (i,)) for i in spots]
    if radius >= 2:
        out += [_hide(key, (i, j)) for a, i in enumerate(spots) for j in spots[a + 1:]]
    return out


def _pairs(key: str) -> List[str]:
    """이웃한 한글 두 음절들. '탈지분유' -> ['탈지', '지분', '분유']"""
    return [key[i:i + 2] for i in range(len(key) - 1) if is_syllable(key[i]) and is_syllable(key[i + 1])]


def _read_names(filename: str) -> List[str]:
    with open(HERE / filename, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    if rows and "name" not in rows[0]:
        raise ValueError(f"{filename}에 name 칸이 없습니다")
    return [r["name"] for r in rows if r["name"]]


@lru_cache(maxsize=1)
def _index() -> _Index:
    """정확 일치 사전과 자동 단 이름으로 색인을 한 번 만든다. 후보는 3음절 이상 이름이다."""
    names, keys, hits = [], [], []
    known, pairs, seen = set(), set(), set()
    by_mask: Dict[str, List[int]] = {}
    for filename in ("entries.tsv", "entries_auto.tsv"):
        for name in _read_names(filename):
            key = norm(name)
            n = syllables(key)
            pairs.update(_pairs(key))
            if n >= 2:
                known.add(key)
            if n < MIN_SYLLABLES or key in seen:
                continue
            seen.add(key)
            for mask in _masks(key, _radius(n)):
                by_mask.setdefault(mask, []).append(len(names))
            names.append(name)
            keys.append(key)
            hits.append(lookup(name))
    target = tuple(h.via == "entry" and not h.not_ingredient for h in hits)    # 자동 단은 막는 데만 쓴다
    return _Index(tuple(names), tuple(keys), tuple(to_jamo(k) for k in keys), tuple(hits),
                  tuple(verdict_key(h) for h in hits), target,
                  {m: tuple(ids) for m, ids in by_mask.items()}, frozenset(known), frozenset(pairs))


# ---------- 비슷한 이름 찾기 ----------
def _key(name: str) -> str:
    """사전이 보는 꼴: 원산지를 떼고 소문자로, 이음표·가운뎃점·공백을 뺀다."""
    return norm(strip_origin(name))


@lru_cache(maxsize=65536)
def _near(key: str) -> Tuple[Tuple[int, int], ...]:
    """반경 안 후보들의 (이름 번호, 자모 거리). 반경은 음절 수로 정한다."""
    n = syllables(key)
    if n < MIN_SYLLABLES:
        return ()
    radius = _radius(n)
    idx = _index()
    query = to_jamo(key)
    found: Dict[int, int] = {}
    for mask in _masks(key, radius):
        for i in idx.by_mask.get(mask, ()):
            if i not in found:
                found[i] = distance(query, idx.jamo[i], radius)
    return tuple(sorted((i, d) for i, d in found.items() if d <= radius))


def candidates(name: str) -> List[Tuple[str, int]]:
    """이름 하나의 반경 안 후보 (사전 이름, 자모 거리). 사전 조회 결과와 관계없이 본다 (설명·검사용).
    자기 자신(거리 0)은 뺀다."""
    idx = _index()
    return [(idx.names[i], d) for i, d in _near(_key(name)) if d > 0]


def _holds_known(key: str, spot: int, known: FrozenSet[str]) -> bool:
    """spot 자리 음절을 품은 부분(두 음절 이상, 이름 전체는 빼고)이 사전 이름인가. 대추분말의 '대추'."""
    for a in range(spot + 1):
        for b in range(spot + 1, len(key) + 1):
            if 2 <= b - a < len(key) and key[a:b] in known:
                return True
    return False


def looks_real(key: str, target_key: str) -> bool:
    """라벨 이름(정규화)이 사전 항목의 오타가 아니라 다른 실제 이름으로 보이는가. 바뀐 음절마다 본다.

    - 바뀐 음절을 품은 사전 이름이 라벨 이름 안에 있다 (대추분말의 '대추', 효모제제의 '효모')
    - 바뀐 음절이 이웃 음절과 만드는 짝이 모두 사전 이름에 나오는 짝이다 (단백분말의 '단백').
      오타는 대개 실제 이름에 없는 짝을 만든다 (탈지븐유의 '지븐')
    - 양쪽 음절이 모두 영문 글자를 읽은 음절이다 (제품 기호: 파인소프트씨/파인소프트티)
    """
    idx = _index()
    for i, (a, b) in enumerate(zip(key, target_key)):
        if a == b:
            continue
        if a in LETTERS and b in LETTERS:
            return True
        around = _pairs(key[max(i - 1, 0):i + 2])          # 바뀐 음절과 앞·뒤 음절의 짝
        if (around and all(p in idx.pairs for p in around)) or _holds_known(key, i, idx.known):
            return True
    return False


def nearest(name: str) -> Optional[Match]:
    """사전이 모르는 이름을 사전 항목과 맞춘다. 조건(모듈 설명 1~6)에 맞지 않으면 None."""
    if lookup(name).via != "unknown":
        return None
    key = _key(name)
    near = _near(key)
    idx = _index()
    if not near or len({idx.tags[i] for i, _ in near}) > 1:
        return None                          # 후보가 없거나, 반경 안 후보끼리 판정이 갈린다 (우유향/두유향 사이)
    best = min(d for _, d in near)
    tops = [i for i, d in near if d == best and idx.target[i]]
    if best == 0 or not tops:
        return None                          # 가장 가까운 것이 자동 단이나 원재료 아님뿐이다
    i = min(tops)                            # 판정이 같은 동점이면 사전에 먼저 적힌 항목 (대개 더 흔한 이름)
    hit = idx.hits[i]
    if changes_verdict(hit) and (best > 1 or syllables(key) < MIN_SYLLABLES_RISKY):
        return None
    if best > 1 and syllables(key) < FAR_SYLLABLES:
        return None                          # 5음절에서 자모 둘이 다르면 다른 이름인 경우가 많다 (파인애플잼/파인애플즙)
    if looks_real(key, idx.keys[i]):
        return None
    return Match(name, idx.names[i], best, dataclasses.replace(hit, name=name, via="fuzzy"))


# ---------- 끝 기호 떼기 ----------
def without_code(name: str) -> Optional[Match]:
    """끝에 붙은 영문·숫자 기호를 떼면 사전 항목이나 관계없는 무리로 찾아지는가. '유화제II' -> 유화제.
    뗀 이름이 두 음절보다 짧거나 원재료가 아닌 표기면 받지 않는다. 거리 칸은 0으로 둔다."""
    if lookup(name).via != "unknown" or KEEP_CODE_RE.search(name):
        return None
    key = _key(unicodedata.normalize("NFKC", name))       # 'Ⅱ' -> 'II'
    base = CODE_TAIL_RE.sub("", key)
    if base == key or syllables(base) < 2:
        return None
    hit = lookup(base)
    if hit.via not in CODE_VIA or hit.not_ingredient:
        return None
    if changes_verdict(hit) and syllables(base) < MIN_SYLLABLES_RISKY:
        return None                          # 유화제CMC, 아미노MW: 짧은 이름 뒤 글자는 다른 원료 이름일 수 있다
    return Match(name, hit.name, 0, dataclasses.replace(hit, name=name, via="code"))


# ---------- 보조 분류기 ----------
def from_classification(name: str, result) -> Optional[Lookup]:
    """팀 IngredientClassification -> Lookup(via 'fallback'). 등급은 사전의 뭉뚱그린 코드(milk …)에 단다.
    source_unknown이거나, 9개와 관계없다는 답이거나, 형식이 틀린 답이면 None(모르는 이름 그대로)."""
    if result.source_unknown or not result.matches:
        return None
    best: Dict[str, str] = {}
    for m in result.matches:
        code = str(getattr(m.allergen, "value", m.allergen))
        verdict = str(getattr(m.verdict, "value", m.verdict))
        if code not in US9 or verdict not in VERDICT_GRADE:
            return None                              # 팀 파이프라인처럼 깨진 답은 모르는 이름으로 둔다
        grade = VERDICT_GRADE[verdict]
        grade = FALLBACK_CAP.get(grade, grade)
        if code not in best or ORDER[grade] > ORDER[best[code]]:
            best[code] = grade
    return Lookup(name=name, sources=tuple(sorted(best.items())), via="fallback")


def fallback_from_env():
    """OPENSESAME_FINAL_FALLBACK=llm이고 LLM 키가 있으면 팀 LLM 분류기, 아니면 None(꺼짐). 기본은 꺼짐."""
    want = os.environ.get(FALLBACK_ENV, "").strip().lower()
    if want in ("", "0", "off", "none"):
        return None
    if want != "llm":
        raise ValueError(f"{FALLBACK_ENV}에는 llm만 쓸 수 있습니다")
    if not any(os.environ.get(k) for k in KEY_ENVS):
        log.warning("%s=llm이지만 LLM 키가 없어 보조 분류기를 켜지 않음", FALLBACK_ENV)
        return None
    from src.model import get_classifier
    return get_classifier("llm")


# ---------- 묶음 ----------
class Resolver:
    """사전 조회 -> 끝 기호 떼기 -> 비슷한 이름 찾기 -> 보조 분류기. 라벨(요청) 하나마다 새로 만든다 (색인은 함께 쓴다).

    codes: 끝 기호 떼기를 쓸지. fuzzy: 비슷한 이름 찾기를 쓸지.
    fallback: 팀 Classifier 인터페이스(classify)를 지키는 객체 또는 None.
    보조 분류기는 resolve_many에서만 부른다. resolve는 사전, 끝 기호 떼기, 비슷한 이름 찾기만 쓴다.
    """

    def __init__(self, fuzzy: bool = True, fallback=None, codes: bool = True):
        self.fuzzy = fuzzy
        self.codes = codes
        self.fallback = fallback
        self._cache: Dict[str, Lookup] = {}
        self._matched: Dict[str, str] = {}           # 라벨 이름 -> 맞춘 사전 항목 (처음 본 순서)
        self._asked: set = set()
        self._notes: List[str] = []

    def resolve(self, name: str) -> Lookup:
        """이름 하나 -> Lookup. verdict.judge의 resolve 인자로 넘긴다."""
        hit = self._cache.get(name)
        if hit is None:
            hit = lookup(name)                       # 글자가 아니면 여기서 TypeError
            for on, step in ((self.codes, without_code), (self.fuzzy, nearest)):
                m = step(name) if on and hit.via == "unknown" else None
                if m is not None:
                    hit = m.hit
                    self._matched[name] = m.target
            self._cache[name] = hit
        return hit

    def resolve_many(self, names: Sequence[str]) -> List[Lookup]:
        """여러 이름을 한꺼번에. 보조 분류기가 있으면 끝까지 모르는 이름만 모아 한 번 부른다."""
        if isinstance(names, str):
            raise TypeError("이름 목록(list[str])을 넣어 주세요")
        for n in names:
            self.resolve(n)
        if self.fallback is not None:
            todo = [n for n in dict.fromkeys(names) if self._cache[n].via == "unknown" and n not in self._asked]
            if todo:
                self._ask(todo)
        return [self._cache[n] for n in names]

    def _ask(self, todo: List[str]) -> None:
        self._asked.update(todo)
        try:
            results = list(self.fallback.classify(todo))
        except Exception as e:      # LLM 장애 등: 모르는 이름으로 두고 참고에 남긴다 (오류 내용은 옮기지 않는다)
            log.warning("보조 분류기 호출 실패: %s", type(e).__name__)
            self._notes.append(f"보조 분류기 호출 실패({type(e).__name__}): 모르는 이름 {len(todo)}개를 그대로 둠")
            return
        asked, answers = set(todo), {}
        for r in results:
            name = getattr(r, "ingredient", None)
            if name in asked and name not in answers:        # 묻지 않은 이름의 답은 버린다 (지어낸 근거 차단)
                answers[name] = r
        used = []
        for name in todo:
            hit = from_classification(name, answers[name]) if name in answers else None
            if hit is not None:
                self._cache[name] = hit
                used.append(name)
        if used:
            self._notes.append(f"사전에 없어 보조 분류기로 판단(확정은 추정으로 낮춤): {', '.join(used)}")

    @property
    def matched(self) -> Dict[str, str]:
        """끝 기호 떼기나 비슷한 이름으로 맞춘 것: {라벨 이름: 사전 항목}."""
        return dict(self._matched)

    def notes(self) -> List[str]:
        """응답 notes에 더할 문장. 맞춘 이름마다 한 줄('오타로 보고 맞춤: 탈지븐유 → 탈지분유'), 그다음 보조 분류기 참고."""
        lines = [f"{NOTE_HEAD[self._cache[n].via]}: {n} → {t}" for n, t in self._matched.items()]
        return lines + list(self._notes)


__all__ = ["FALLBACK_ENV", "FAR_SYLLABLES", "LONG_SYLLABLES", "MIN_SYLLABLES", "MIN_SYLLABLES_RISKY", "Match",
           "Resolver", "candidates", "changes_verdict", "fallback_from_env", "from_classification", "looks_real",
           "nearest", "verdict_key", "without_code"]
