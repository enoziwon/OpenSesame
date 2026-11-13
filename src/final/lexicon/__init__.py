"""최종본 5단계의 앞부분: 원재료 이름 -> 무엇에서 왔는가 (정확 일치 사전과 키워드 규칙).

    from src.final.lexicon import lookup
    r = lookup("양조간장")
    r.us        # {'soy': 'C', 'wheat': 'I'}   미국 9개 수준에서 가장 강한 등급
    r.sources   # (('soy', 'C'), ('wheat', 'I'))  출처 코드와 등급
    r.via       # 'entry' 사전 / 'rule' 규칙 / 'benign' 관계없다고 아는 무리 / 'auto' 검수 전 자동 / 'unknown' 모르는 이름

등급: C 확정, I 추정, P 가능, R 정제유(대두, 세지 않음), F 종류 모를 유지(대두).
표시: opaque 속을 알 수 없는 양념·국물 계열 복합 원료(생선 판정 불가의 근거), opaque_sesame 그중 양념·소스 계열(참깨도),
compound 그 밖의 섞은 원료, flavor 일반 향료, not_ingredient 원재료가 아닌 표기.
표는 같은 폴더의 TSV이고, 뜻과 만든 방법은 README.md에 적었다.
"""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, NamedTuple, Pattern, Tuple

# 표가 있는 폴더. 평가 때 다른 판의 사전(시험 세트 제조사를 가린 사전 등)으로 바꿔 끼울 수 있게 환경 변수로 덮어쓴다
HERE = Path(os.environ.get("OPENSESAME_LEXICON_DIR") or Path(__file__).parent)
ORDER = {"C": 5, "I": 4, "P": 3, "R": 2, "F": 1}      # R(이름에 대두유)이 F(종류 모를 유지)보다 구체적이다
GRADES = frozenset(ORDER)
SPECIAL = ("OPAQUE", "OPAQUE_SESAME", "COMPOUND", "FLAVOR", "FLAVOR_END", "BENIGN", "BENIGN_END", "STATEMENT", "ORIGIN", "ORIGIN_WORD")   # rules.tsv의 낱말 줄


@dataclass(frozen=True)
class Lookup:
    name: str
    sources: Tuple[Tuple[str, str], ...] = ()   # ((출처 코드, 등급), ...)
    opaque: bool = False                        # 속을 알 수 없는 양념·국물 계열 복합 원료 (가이드 5장). 생선 판정 불가의 근거
    opaque_sesame: bool = False                 # 그중 양념·소스 계열. 참깨 판정 불가의 근거도 된다
    compound: bool = False                      # 그 밖의 섞은 원료 (시즈닝, 혼합제제, 가공품, 믹스). 표시란이 없을 때만 근거가 된다
    flavor: bool = False                        # 일반 향료 (가이드 D5)
    not_ingredient: bool = False                # 원산지·기준 문구처럼 원재료가 아닌 표기
    via: str = "unknown"
    en: str = ""
    note: str = ""
    status: str = ""

    @property
    def us(self) -> Dict[str, str]:
        """미국 9개 수준으로 모은 {알레르기: 등급}. 같은 알레르기면 가장 강한 등급."""
        table = _tables().sources
        out: Dict[str, str] = {}
        for code, grade in self.sources:
            allergen = table[code]["us9"]
            if allergen and (allergen not in out or ORDER[grade] > ORDER[out[allergen]]):
                out[allergen] = grade
        return out


class Rule(NamedTuple):
    id: str
    source: str
    grade: str
    include: Tuple[str, ...]
    exclude: Tuple[str, ...]      # 이름에서 먼저 지우는 말 ('땅콩버터'의 버터는 우유가 아니다)
    unless: Tuple[str, ...]       # 이름 어디에든 있으면 이 규칙을 쓰지 않는 말 ('사골…육수'는 생선 육수가 아니다)


class RuleSet(NamedTuple):
    rules: Tuple[Rule, ...]
    words: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]]     # SPECIAL 줄: (포함어, 제외어)
    origin_tail: Pattern      # '밀-미국산'
    origin_head: Pattern      # '프랑스산-계란'
    origin_only: Pattern      # '미국·캐나다·호주'


class RuleHit(NamedTuple):
    sources: Dict[str, str]
    rule_ids: Tuple[str, ...]
    opaque: bool
    flavor: bool
    benign: bool
    compound: bool = False
    opaque_sesame: bool = False


class _Tables(NamedTuple):
    sources: Dict[str, Dict[str, str]]
    ruleset: RuleSet
    entries: Dict[str, Lookup]
    auto: frozenset
    kr_box: Dict[str, Dict[str, str]]


def norm(name: str) -> str:
    """맞추기 전에: 소문자로 바꾸고 이음표·가운뎃점·공백을 뺀다. 'DL-α-토코페롤' -> 'dlα토코페롤'"""
    return re.sub(r"[\s\-·.∙‧•,]", "", name).lower()


def _split(text: str) -> Tuple[str, ...]:
    return tuple(x for x in text.split("|") if x)


def make_ruleset(rule_rows: List[Dict[str, str]]) -> RuleSet:
    """rules.tsv의 줄(dict)들로 규칙 묶음을 만든다. 사전을 조립하는 도구도 이 함수를 쓴다."""
    rules, words = [], {}
    for r in rule_rows:
        if r.get("source"):
            rules.append(Rule(r["id"], r["source"], r["grade"], _split(r["include"]), _split(r["exclude"]),
                              _split(r.get("unless") or "")))
        else:
            words[r["id"]] = (_split(r["include"]), _split(r["exclude"]))
    for key in SPECIAL:
        words.setdefault(key, ((), ()))
    places = sorted(words["ORIGIN"][0], key=len, reverse=True)          # '인도네시아'를 '인도'보다 먼저 본다
    fixed = sorted(words["ORIGIN_WORD"][0], key=len, reverse=True)
    token = "(?:(?:%s)산?|%s)등?" % ("|".join(map(re.escape, places)) or "(?!)",
                                    "|".join(map(re.escape, fixed)) or "(?!)")
    gap = r"[-:·∙•‧,./\s]+"
    return RuleSet(
        tuple(rules), words,
        re.compile(r"^(.+?)\s*[-:·∙.]\s*%s(?:%s%s)*$" % (token, gap, token)),
        re.compile(r"^%s(?:[·∙•‧,./\s]+%s)*\s*[-:]\s*(.+)$" % (token, token)),
        re.compile(r"^%s(?:%s%s)*$" % (token, gap, token)))


def _blank(text: str, words: Tuple[str, ...]) -> str:
    for w in words:
        text = text.replace(w, "\0" * len(w))      # 길이를 지켜 위치가 어긋나지 않게 한다
    return text


def _has(key: str, rs: RuleSet, table_id: str) -> bool:
    inc, exc = rs.words[table_id]
    text = _blank(key, exc)
    return any(k in text for k in inc)


def _is_flavor(key: str, rs: RuleSet) -> bool:
    ends = rs.words["FLAVOR_END"][0]
    return _has(key, rs, "FLAVOR") or (bool(ends) and _blank(key, rs.words["FLAVOR"][1]).endswith(ends))


_TASTE_LATER = re.compile(r"맛(?:시즈닝|씨즈닝|분말|분$|조미|소스|베이스|스낵|칩|오일|엑기스|가루|풍미|스프|후레이크|$)")


def _taste_follows(key: str, end: int) -> bool:
    """키워드 뒤가 맛·향·풍미이면 맛을 낸 이름이다. '새우맛분말', '버터향', '새우풍미유', '홍게맛살'."""
    nxt = key[end:end + 2]
    if nxt[:1] == "향":
        return not nxt.startswith(("향신", "향미"))
    if nxt == "풍미" or nxt == "맛살":
        return True
    if nxt[:1] == "맛":
        return nxt not in ("맛술", "맛간", "맛소", "맛김", "맛기")
    return bool(_TASTE_LATER.search(key[end:]))        # '명란마요맛시즈닝'처럼 뒤쪽에 '맛'이 붙는 조미 이름


def match_rules(key: str, rs: RuleSet) -> RuleHit:
    """정규화한 이름에 키워드 규칙을 적용한다."""
    flavor = _is_flavor(key, rs)
    found: Dict[str, str] = {}
    used: List[str] = []
    for rule in rs.rules:
        if any(w in key for w in rule.unless):
            continue
        text = _blank(key, rule.exclude)
        best = ""
        for k in rule.include:
            i = text.find(k)
            if i < 0:
                continue
            g = rule.grade
            if flavor and g in ("C", "I"):
                g = "P"                                # 향료 이름: 실제 원료가 들었는지 알 수 없다 (땅콩향의 표시란 근거 7%)
            elif g == "C" and _taste_follows(key, i + len(k)):
                g = "I"                                # 맛 이름(새우맛분말)은 한 단계 낮춘다
            if not best or ORDER[g] > ORDER[best]:
                best = g
        if not best:
            continue
        used.append(rule.id)
        if rule.source not in found or ORDER[best] > ORDER[found[rule.source]]:
            found[rule.source] = best
    # 종류까지 아는 코드가 있으면 같은 계열의 뭉뚱그린 코드는 뺀다. '멸치액젓'은 생선(액젓)이 아니라 멸치다
    for code in [c for c in found if ":" not in c]:
        kinds = [found[c] for c in found if c.startswith(code + ":")]
        if kinds and max(ORDER[g] for g in kinds) >= ORDER[found[code]]:
            del found[code]
    ends = rs.words["BENIGN_END"][0]
    benign = not found and (_has(key, rs, "BENIGN") or (bool(ends) and key.endswith(ends)))
    opaque = _has(key, rs, "OPAQUE")
    compound = not opaque and _has(key, rs, "COMPOUND")     # 둘 다 맞으면 양념·국물 계열로 본다
    sesame = opaque and _has(key, rs, "OPAQUE_SESAME")      # 양념·소스 계열이면 참깨도 판정 불가 범위
    return RuleHit(found, tuple(used), opaque, flavor, benign, compound, sesame)


def strip_origin_with(name: str, rs: RuleSet) -> str:
    m = rs.origin_tail.match(name) or rs.origin_head.match(name)
    return m.group(1).strip() if m else name


def is_not_ingredient_with(name: str, rs: RuleSet) -> bool:
    """원산지만 늘어놓은 표기이거나 제조시설 안내 문구인가."""
    return bool(rs.origin_only.match(name.strip())) or _has(norm(name), rs, "STATEMENT")


def _read(filename: str) -> List[Dict[str, str]]:
    with open(HERE / filename, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _parse_sources(text: str) -> Tuple[Tuple[str, str], ...]:
    out = []
    for token in text.split():
        code, grade = token.rsplit(":", 1)
        out.append((code, grade))
    return tuple(out)


@lru_cache(maxsize=1)
def _tables() -> _Tables:
    sources = {r["code"]: r for r in _read("sources.tsv")}
    entries = {}
    for r in _read("entries.tsv"):
        entries[norm(r["name"])] = Lookup(
            name=r["name"], sources=_parse_sources(r["sources"]), opaque="O" in r["flags"],
            opaque_sesame="S" in r["flags"], compound="M" in r["flags"],
            flavor="V" in r["flags"], not_ingredient="X" in r["flags"], via="entry", en=r["en"], note=r["note"],
            status=r["status"])
    auto = frozenset(norm(r["name"]) for r in _read("entries_auto.tsv"))
    kr_box = {r["word"]: r for r in _read("kr_box.tsv")}
    return _Tables(sources, make_ruleset(_read("rules.tsv")), entries, auto, kr_box)


def strip_origin(name: str) -> str:
    """'밀-미국산', '대두:외국산', '프랑스산-계란'처럼 원산지가 붙어 남은 이름에서 원재료 부분만. 아니면 그대로.

    'L-글루타민산나트륨', 'DL-사과산'처럼 '산'으로 끝나는 화합물 이름은 원산지가 아니므로 나라 이름표로만 가린다.
    """
    return strip_origin_with(name, _tables().ruleset)


@lru_cache(maxsize=65536)
def lookup(name: str) -> Lookup:
    """원재료 이름 하나를 찾는다. 사전 -> (원산지를 뗀) 사전 -> 원재료 아님 -> 규칙 -> 관계없는 무리 -> 자동 단 -> 모름."""
    if not isinstance(name, str):
        raise TypeError("이름에는 글자(str)만 넣을 수 있습니다")
    tables = _tables()
    rs = tables.ruleset
    base = strip_origin_with(name, rs)
    for key in (norm(name), norm(base)):
        hit = tables.entries.get(key)
        if hit is not None:
            return hit
    if is_not_ingredient_with(name, rs):
        return Lookup(name=name, not_ingredient=True, via="rule")
    key = norm(base)                                   # 원산지 글자가 규칙에 걸리지 않게 뗀 이름으로 본다
    hit = match_rules(key, rs)
    if hit.sources or hit.opaque or hit.compound or hit.flavor:
        return Lookup(name=name, sources=tuple(sorted(hit.sources.items())), opaque=hit.opaque,
                      opaque_sesame=hit.opaque_sesame, compound=hit.compound, flavor=hit.flavor, via="rule")
    if hit.benign:
        return Lookup(name=name, via="benign")
    if key in tables.auto:
        return Lookup(name=name, via="auto")
    return Lookup(name=name)


def kr_box() -> Dict[str, Dict[str, str]]:
    """한국 표시란 낱말 -> {'source': 출처 코드, 'mandatory': 'Y'/'N', 'note': ...}"""
    return dict(_tables().kr_box)


def source_info(code: str) -> Dict[str, str]:
    """출처 코드 -> {'us9', 'kr_box', 'en', 'ko'}"""
    return dict(_tables().sources[code])


__all__ = ["Lookup", "lookup", "norm", "strip_origin", "kr_box", "source_info", "ORDER", "GRADES", "SPECIAL"]
