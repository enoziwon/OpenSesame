"""최종본 5단계의 앞부분: 원재료 이름 -> 무엇에서 왔는가 (정확 일치 사전과 키워드 규칙).

    from src.final.lexicon import lookup
    r = lookup("양조간장")
    r.us        # {'soy': 'C', 'wheat': 'I'}   미국 9개 수준에서 가장 강한 등급
    r.sources   # (('soy', 'C'), ('wheat', 'I'))  출처 코드와 등급
    r.via       # 'entry' 사전 / 'rule' 규칙 / 'benign' 관계없다고 아는 무리 / 'auto' 검수 전 자동 / 'unknown' 모르는 이름

등급: C 확정, I 추정, P 가능, R 정제유(대두, 세지 않음), F 종류 모를 유지(대두).
표는 같은 폴더의 TSV이고, 뜻과 만든 방법은 README.md에 적었다.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, NamedTuple, Tuple

HERE = Path(__file__).parent
ORDER = {"C": 5, "I": 4, "P": 3, "R": 2, "F": 1}      # R(이름에 대두유)이 F(종류 모를 유지)보다 구체적이다
GRADES = frozenset(ORDER)


@dataclass(frozen=True)
class Lookup:
    name: str
    sources: Tuple[Tuple[str, str], ...] = ()   # ((출처 코드, 등급), ...)
    opaque: bool = False                        # 속을 알 수 없는 복합 원료 (가이드 5장)
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


class _Tables(NamedTuple):
    sources: Dict[str, Dict[str, str]]
    rules: List[Tuple[str, str, str, Tuple[str, ...], Tuple[str, ...]]]
    words: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]]     # OPAQUE, FLAVOR, FLAVOR_END, BENIGN
    entries: Dict[str, Lookup]
    auto: frozenset
    kr_box: Dict[str, Dict[str, str]]


def norm(name: str) -> str:
    """맞추기 전에: 소문자로 바꾸고 이음표·가운뎃점·공백을 뺀다. 'DL-α-토코페롤' -> 'dlα토코페롤'"""
    return re.sub(r"[\s\-·.∙‧•,]", "", name).lower()


def _read(filename: str) -> List[Dict[str, str]]:
    with open(HERE / filename, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _split(text: str) -> Tuple[str, ...]:
    return tuple(x for x in text.split("|") if x)


def _parse_sources(text: str) -> Tuple[Tuple[str, str], ...]:
    out = []
    for token in text.split():
        code, grade = token.rsplit(":", 1)
        out.append((code, grade))
    return tuple(out)


@lru_cache(maxsize=1)
def _tables() -> _Tables:
    sources = {r["code"]: r for r in _read("sources.tsv")}
    rules, words = [], {}
    for r in _read("rules.tsv"):
        if r["source"]:
            rules.append((r["id"], r["source"], r["grade"], _split(r["include"]), _split(r["exclude"])))
        else:
            words[r["id"]] = (_split(r["include"]), _split(r["exclude"]))
    entries = {}
    for r in _read("entries.tsv"):
        entries[norm(r["name"])] = Lookup(
            name=r["name"], sources=_parse_sources(r["sources"]), opaque="O" in r["flags"], flavor="V" in r["flags"],
            not_ingredient="X" in r["flags"], via="entry", en=r["en"], note=r["note"], status=r["status"])
    auto = frozenset(norm(r["name"]) for r in _read("entries_auto.tsv"))
    kr_box = {r["word"]: r for r in _read("kr_box.tsv")}
    return _Tables(sources, rules, words, entries, auto, kr_box)


def _blank(text: str, words: Tuple[str, ...]) -> str:
    for w in words:
        text = text.replace(w, "\0" * len(w))      # 길이를 지켜 위치가 어긋나지 않게 한다
    return text


def _has(key: str, table_id: str) -> bool:
    inc, exc = _tables().words[table_id]
    text = _blank(key, exc)
    return any(k in text for k in inc)


def _is_flavor(key: str) -> bool:
    _, exc = _tables().words["FLAVOR"]
    ends = _tables().words["FLAVOR_END"][0]
    return _has(key, "FLAVOR") or _blank(key, exc).endswith(ends)


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


def _by_rules(key: str) -> Tuple[Dict[str, str], bool]:
    """키워드 규칙을 적용한다. ({출처 코드: 등급}, 향료인가)"""
    flavor = _is_flavor(key)
    found: Dict[str, str] = {}
    for _rid, code, grade, inc, exc in _tables().rules:
        text = _blank(key, exc)
        best = ""
        for k in inc:
            i = text.find(k)
            if i < 0:
                continue
            g = grade
            if g == "C" and (flavor or _taste_follows(key, i + len(k))):
                g = "I"                                # 맛·향 이름이면 한 단계 낮춘다
            elif g == "I" and flavor:
                g = "P"                                # 초콜릿향 -> 우유처럼 두 번 건너뛴 추정
            if not best or ORDER[g] > ORDER[best]:
                best = g
        if best and (code not in found or ORDER[best] > ORDER[found[code]]):
            found[code] = best
    return found, flavor


_ORIGIN = re.compile(
    r"^(.+?)[-:·∙.]\s*(?:[가-힣]{1,8}산|수입|외국|국내|미국|호주|중국|캐나다|러시아|베트남|태국|인도|독일|프랑스|이탈리아)"
    r"(?:[·∙,./ ]*[가-힣]{1,8}산?)*$")


def strip_origin(name: str) -> str:
    """'밀-미국산', '대두:외국산'처럼 원산지가 붙어 남은 이름에서 앞부분만. 아니면 그대로."""
    m = _ORIGIN.match(name)
    return m.group(1).strip() if m else name


@lru_cache(maxsize=65536)
def lookup(name: str) -> Lookup:
    """원재료 이름 하나를 찾는다. 사전 -> (원산지를 뗀) 사전 -> 규칙 -> 관계없는 무리 -> 자동 단 -> 모름."""
    if not isinstance(name, str):
        raise TypeError("이름에는 글자(str)만 넣을 수 있습니다")
    tables = _tables()
    key = norm(name)
    for k in (key, norm(strip_origin(name))):
        hit = tables.entries.get(k)
        if hit is not None:
            return hit
    found, flavor = _by_rules(key)
    opaque = _has(key, "OPAQUE")
    if found or opaque or flavor:
        return Lookup(name=name, sources=tuple(sorted(found.items())), opaque=opaque, flavor=flavor, via="rule")
    if _has(key, "BENIGN"):
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


__all__ = ["Lookup", "lookup", "norm", "strip_origin", "kr_box", "source_info", "ORDER", "GRADES"]
