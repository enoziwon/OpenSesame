"""최종본 6단계: 파싱된 라벨 + 원재료 사전 -> 미국 9개 알레르기 판정.

    from src.final.parser import parse_label
    from src.final.verdict import judge
    j = judge(parse_label("간장, 설탕, 대두 함유"))
    [(v.allergen, v.verdict, v.evidence) for v in j.allergens]     # [('soy', 'confirmed', '간장')]

규칙은 정답지 가이드 v1을 따른다. 1) 원재료마다 근거를 모으고 2) 한국 표시란을 읽고
3) 속 모를 원료가 만드는 판정 불가 후보를 정한 뒤 4) 알레르기마다 차례로 판정한다.
순수 함수다. 사전 조회 함수(resolve)를 인자로 받으므로 테스트에서는 가짜 조회로 규칙만 따로 검사한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Tuple

from src.common.schema import Allergen
from src.final.lexicon import kr_box, lookup, source_info

ALLERGENS = tuple(a.value for a in Allergen)                   # 출력 순서 (팀 형식과 같다)
FULL = frozenset({"milk", "egg", "wheat", "soy", "peanut"})      # 한국 표시란이 전부 덮는 알레르기 (R2)
# 종을 모르는 갑각류 근거(해물, 키토산)는 게·새우가 덮는다고 본다 (가이드 N12: 게·새우 외 갑각류는 자료에서 0.0%)
GENERIC_COVERED = {"crustacean": ("crustacean:shrimp", "crustacean:crab")}
OPAQUE_NO_BOX = frozenset({"milk", "egg", "wheat", "soy", "crustacean"})    # 표시란을 못 읽었을 때 속 모를 원료가 더하는 것
COMPOUND_NO_BOX = frozenset({"milk", "egg", "wheat", "soy"})
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


@dataclass(frozen=True)
class Evidence:
    """근거 하나. name은 라벨에 적힌 원재료 이름(Node.name)이다."""
    name: str
    code: str                 # 출처 코드 (fish:anchovy)
    grade: str                # C 확정 / I 추정 / P 가능 / R 정제유 / F 종류 모를 유지
    order: int                # 라벨 순서
    en: str = ""              # 원재료의 영어 이름 (사전 en)
    word: str = ""            # '원재료(알레르기)' 꼴의 괄호 속 낱말. 혼합조미분말(대두)의 대두
    labelled: bool = False    # 대두 표시가 붙은 종류 모를 유지. 식물성유지(대두)


@dataclass(frozen=True)
class Leaf:
    """잎으로 다룬 원재료. 속 모를 원료·일반 향료·모르는 이름을 가려낼 때 쓴다."""
    name: str
    order: int
    en: str = ""
    opaque: bool = False      # 속 모를 양념·국물 원료 (생선 판정 불가의 근거)
    opaque_sesame: bool = False  # 그중 양념·소스 계열 (참깨 판정 불가의 근거도 된다)
    opaque_meat: bool = False  # 그중 고기 바탕이 이름에 적힌 것 (생선 판정 불가의 근거가 아니다, 가이드 N14)
    compound: bool = False    # 그 밖의 섞은 원료
    flavor_only: bool = False  # 일반 향료 (출처 없는 향료). 어떤 판정의 근거도 아니다
    unknown: bool = False     # 사전에 없는 이름


@dataclass(frozen=True)
class AllergenVerdict:
    allergen: str                         # 미국 9개 이름 (milk …)
    verdict: str                          # confirmed / inferable / undecidable
    evidence: str                         # 근거 원재료 이름 또는 "표시란: 새우"
    other_evidence: Tuple[str, ...]       # 나머지 근거 이름 (강한 것 먼저)
    basis: Tuple[str, ...]                # INGREDIENT, KR-DECL, R1-1, LIKELY, POSSIBLE, OPAQUE, COMPOUND
    species: Tuple[str, ...]              # 종까지 아는 출처 코드 (fish:anchovy)
    evidence_en: Optional[str]            # 근거 원료의 영어 이름. 없으면 None
    word: str = ""                        # 괄호 속 낱말 또는 표시란 낱말 (문장을 만들 때 쓴다)


@dataclass(frozen=True)
class Judgement:
    allergens: Tuple[AllergenVerdict, ...]     # Allergen 순서. 없는 알레르기는 '검출 안 됨'
    undecidable_ingredients: Tuple[str, ...]   # 속 모를 원료, 일반 향료, 모르는 이름 (라벨 순서)
    notes: Tuple[str, ...]                     # 판정에 쓰지 않은 참고 (US-OIL, R1-1, 표시란 누락 의심)
    box_read: bool                             # 한국 알레르기 표시란을 찾았나
    read_any: bool                             # 원재료를 하나라도 읽었나


@dataclass(frozen=True)
class Box:
    """읽은 표시란. 미국 9개 밖이거나 모르는 낱말은 이미 뺐다."""
    read: bool
    words: Dict[str, str]          # 미국 9개 -> 표시란에 처음 적힌 낱말 (적힌 순서)
    codes: Tuple[str, ...]         # 표시란 낱말의 출처 코드 (적힌 순서)


# ---------- 사전 표 ----------
@lru_cache(maxsize=None)
def code_info(code: str) -> Tuple[str, str, str, str]:
    """출처 코드 -> (미국 9개, 영어 이름, 한국어 이름, 한국 표시란 낱말). 9개 밖이면 첫 칸이 ''."""
    info = source_info(code)
    return info["us9"], info["en"], info["ko"], info["kr_box"]


@lru_cache(maxsize=1)
def box_codes() -> Dict[str, str]:
    """한국 표시란 낱말 -> 출처 코드. 대두 -> soy, 새우 -> crustacean:shrimp"""
    return {word: row["source"] for word, row in kr_box().items()}


def _us9(code: str) -> str:
    return code_info(code)[0]


def _is_soy_oil(hit) -> bool:
    """대두 R(정제유)·F(종류 모를 유지) 근거를 가진 기름·유지인가. 사전에서 R·F는 대두 기름에만 쓴다."""
    return any(_us9(code) == "soy" and grade in ("R", "F") for code, grade in hit.sources)


def _make_leaf(name: str, order: int, hit) -> Leaf:
    flavor_only = bool(hit.flavor) and not hit.sources       # 일반 향료가 이긴다 (바닐라향베이스)
    opaque = bool(hit.opaque) and not flavor_only
    return Leaf(name, order, hit.en,
                opaque=opaque, opaque_sesame=opaque and bool(getattr(hit, "opaque_sesame", False)),
                opaque_meat=opaque and bool(getattr(hit, "opaque_meat", False)),
                compound=bool(getattr(hit, "compound", False)) and not flavor_only,
                flavor_only=flavor_only, unknown=hit.via == "unknown")


# ---------- 1절: 원재료마다 근거 모으기 ----------
class _Collector:
    """나무를 위에서부터 돌며 근거(Evidence)와 잎(Leaf)을 모은다."""

    def __init__(self, resolve: Callable):
        self.resolve = resolve
        self.evidence: List[Evidence] = []
        self.leaves: List[Leaf] = []
        self.count = 0                     # 본 원재료 수. 라벨 순서로도 쓴다

    def visit_all(self, nodes) -> None:
        for node in nodes:
            self.visit(node)

    def visit(self, node) -> None:
        if node.group:                     # 면·스프 머리말은 건너뛰고 자식만 본다
            self.visit_all(node.children)
            return
        hit = self.resolve(node.name)
        if hit.not_ingredient:             # 원산지·기준 문구: 노드는 버리고 자식은 계속 본다
            self.visit_all(node.children)
            return
        kids = self.real_children(node)
        if not kids:
            self.add_leaf(node.name, hit, ())
        elif all(self.is_box_leaf(k) for k in kids):       # 원재료(알레르기) 꼴: 소맥분(밀)
            self.add_leaf(node.name, hit, tuple(k.name for k in kids))
        else:                                               # 속이 공개된 원료
            self.add_parent(node.name, hit, kids)

    def real_children(self, node) -> list:
        """원재료가 아닌 자식은 빼고, 그 자식의 자식은 이 자리로 올린다."""
        out = []
        for child in node.children:
            if child.group or self.resolve(child.name).not_ingredient:
                out.extend(self.real_children(child))
            else:
                out.append(child)
        return out

    def is_box_leaf(self, node) -> bool:
        """한국 표시란 낱말(대두, 밀, 우유 …) 하나로 된 잎인가."""
        return node.name in box_codes() and not self.real_children(node)

    def is_soy_leaf(self, node) -> bool:
        return self.is_box_leaf(node) and _us9(box_codes()[node.name]) == "soy"

    def next_order(self) -> int:
        self.count += 1
        return self.count

    def add_leaf(self, name: str, hit, words: Tuple[str, ...]) -> None:
        """잎(또는 원재료(알레르기) 꼴의 부모): 사전 결과를 그대로 쓰고 괄호 속 낱말을 확정 근거로 더한다."""
        order = self.next_order()
        oil = _is_soy_oil(hit)
        soy_word = any(_us9(box_codes()[w]) == "soy" for w in words)
        for code, grade in hit.sources:
            labelled = oil and soy_word and grade == "F"
            self.evidence.append(Evidence(name, code, grade, order, hit.en, labelled=labelled))
        for word in words:
            code = box_codes()[word]
            if oil and _us9(code) == "soy":
                continue                   # 기름 예외: 대두유(대두)의 대두는 확정 근거가 아니다
            self.evidence.append(Evidence(name, code, "C", order, hit.en, word=word))
        self.leaves.append(_make_leaf(name, order, hit))

    def is_partial(self, hit, kids: list) -> bool:
        """가이드 N13: 속 모를 원료의 괄호에 대표 원료 하나와 함량(100% 미만)만 적혀 있으면 배합을 밝힌 것이 아니다.

        '누룽지맛베이스(누룽지분말 42.47%)'처럼 제품 이름에 쓴 원료의 함량만 적은 경우다.
        """
        if len(kids) != 1 or not (hit.opaque or getattr(hit, "compound", False)):
            return False
        m = PERCENT_RE.search(kids[0].raw or "")
        return bool(m) and float(m.group(1)) < 100

    def add_parent(self, name: str, hit, kids: list) -> None:
        """속이 공개된 원료: 부모 이름에서는 확정(C) 근거만 남기고 자식으로 판단한다."""
        order = self.next_order()
        if self.is_partial(hit, kids):
            self.leaves.append(_make_leaf(name, order, hit))       # 속 모를 원료로도 남긴다
        oil = _is_soy_oil(hit) and any(self.is_soy_leaf(k) for k in kids)
        for code, grade in hit.sources:
            keep_oil = oil and _us9(code) == "soy" and grade in ("R", "F")
            if grade == "C" or keep_oil:
                self.evidence.append(Evidence(name, code, grade, order, hit.en, labelled=grade == "F"))
        for kid in kids:
            if oil and self.is_soy_leaf(kid):
                continue                   # 기름 예외: 식물성유지(팜유, 대두)의 대두
            self.visit(kid)


# ---------- 2절: 표시란 ----------
def read_box(parsed) -> Box:
    """표시란 낱말을 출처 코드와 미국 9개로 잇는다. 9개 밖(돼지고기, 오징어 …)이나 모르는 낱말은 무시한다."""
    words: Dict[str, str] = {}
    codes: List[str] = []
    for word in parsed.declared:
        code = box_codes().get(word)
        if code is None or not _us9(code):
            continue
        words.setdefault(_us9(code), word)
        if code not in codes:
            codes.append(code)
    return Box(parsed.declaration_text is not None, words, tuple(codes))


def covered(code: str) -> bool:
    """한국 표시란이 덮는 출처 코드인가. 사전 출처표에 표시란 낱말이 적힌 코드다.

    우유·달걀·밀·대두·땅콩은 전부, 생선은 고등어, 갑각류는 게·새우, 견과류는 호두·잣만 덮는다.
    산양유(milk:goat)는 미국 기준으로 우유지만 한국 표시란의 '우유'가 덮지 않는다.
    """
    return bool(code_info(code)[3]) or code in GENERIC_COVERED


def in_box(code: str, box: Box) -> bool:
    if code in GENERIC_COVERED:
        return any(c in box.codes for c in GENERIC_COVERED[code])
    us9 = _us9(code)
    return us9 in box.words if us9 in FULL else code in box.codes


def _erased(e: Evidence, box: Box) -> bool:
    """R2·R4: 표시란을 읽었고 덮는 코드인데 표시란에 없으면 추정·가능 근거를 지운다."""
    return box.read and covered(e.code) and not in_box(e.code, box)


# ---------- 4절: 알레르기마다 판정 ----------
def _names(names: List[str], skip: str = "") -> Tuple[str, ...]:
    """중복을 빼고 순서를 지킨다. skip(대표 근거)은 뺀다."""
    return tuple(n for n in dict.fromkeys(names) if n != skip)


def _species(evs: List[Evidence]) -> Tuple[str, ...]:
    return tuple(dict.fromkeys(e.code for e in evs if ":" in e.code))


def _box_species(allergen: str, box: Box) -> Tuple[str, ...]:
    return tuple(c for c in box.codes if ":" in c and _us9(c) == allergen)


def _confirmed(allergen: str, cs: List[Evidence], weaker: List[Evidence], box: Box) -> AllergenVerdict:
    first = cs[0]
    basis = ("INGREDIENT", "KR-DECL") if allergen in box.words else ("INGREDIENT",)
    species = tuple(dict.fromkeys(_species(cs) + _box_species(allergen, box)))
    return AllergenVerdict(allergen, "confirmed", first.name, _names([e.name for e in cs[1:] + weaker], first.name),
                           basis, species, first.en or None, first.word)


def _from_box(allergen: str, others: List[str], box: Box, verdict: str = "confirmed",
              basis: Tuple[str, ...] = ("KR-DECL",)) -> AllergenVerdict:
    word = box.words[allergen]
    en = code_info(box_codes()[word])[1]
    return AllergenVerdict(allergen, verdict, "표시란: " + word, _names(others), basis,
                           _box_species(allergen, box), en or None, word)


def _from_weak(allergen: str, verdict: str, basis: str, evs: List[Evidence], more: List[str]) -> AllergenVerdict:
    first = evs[0]
    return AllergenVerdict(allergen, verdict, first.name, _names([e.name for e in evs[1:]] + more, first.name),
                           (basis,), _species(evs), first.en or None, first.word)


def _blind_leaves(allergen: str, leaves: List[Leaf], box_read: bool) -> List[Leaf]:
    """3절: 이 알레르기를 판정 불가 후보로 만드는 속 모를 잎."""
    no_box = not box_read and allergen in OPAQUE_NO_BOX
    by_compound = not box_read and allergen in COMPOUND_NO_BOX
    out = []
    for leaf in leaves:
        by_fish = allergen == "fish" and not leaf.opaque_meat          # 고기 바탕이 적힌 것은 생선 범위 밖 (N14)
        by_opaque = by_fish or (allergen == "sesame" and leaf.opaque_sesame) or no_box
        if (leaf.opaque and by_opaque) or (leaf.compound and by_compound):
            out.append(leaf)
    return out


def _undecidable(allergen: str, ps: List[Evidence], blind: List[Leaf]) -> AllergenVerdict:
    """가능 근거와 속 모를 원료는 같은 세기다. 라벨에서 먼저 나온 것을 대표 근거로 삼는다 (가이드 7장)."""
    items = [(e.order, 0, "POSSIBLE", e.name, e.en) for e in ps]          # 같은 원재료면 가능 근거를 앞에 둔다
    items += [(leaf.order, 1, "OPAQUE" if leaf.opaque else "COMPOUND", leaf.name, leaf.en) for leaf in blind]
    items.sort(key=lambda item: item[:2])
    _, _, _, name, en = items[0]
    kinds = tuple(dict.fromkeys(item[2] for item in items))
    word = next((e.word for e in ps if e.name == name), "")
    return AllergenVerdict(allergen, "undecidable", name, _names([item[3] for item in items], name),
                           kinds, _species(ps), en or None, word)


def _missing_notes(cs: List[Evidence], box: Box) -> List[str]:
    """R3: 원재료에 확정 근거가 있는데 표시란에 그 낱말이 없다."""
    if not box.read:
        return []
    found: Dict[str, List[str]] = {}
    for e in cs:
        if covered(e.code) and not in_box(e.code, box):
            word = code_info(e.code)[3] or code_info(e.code)[2]
            found.setdefault(word, []).append(e.name)
    return [f"표시란 누락 의심: {word} (원재료: {', '.join(_names(names))})" for word, names in found.items()]


def _goat_notes(allergen: str, cs: List[Evidence], box: Box) -> List[str]:
    """산양유·양유는 미국 기준으로 우유인데 한국 표시란에는 '우유'로 적히지 않을 수 있다."""
    goats = _names([e.name for e in cs if e.code == "milk:goat"])
    if allergen != "milk" or not goats or "milk" in box.words:
        return []
    return [f"한·미 차이: 소가 아닌 반추동물의 젖도 미국 기준으로는 우유다 (원재료: {', '.join(goats)})"]


def _labelled_fat(mine: List[Evidence], ps: List[Evidence]) -> Tuple[Optional[AllergenVerdict], List[str]]:
    """표시란에 대두가 없어도 '식물성유지(대두)'처럼 라벨이 대두에서 온 유지라고 밝힌 경우: 추정 (R1-1과 같은 이유)."""
    fats = [e for e in mine if e.labelled]
    if not fats:
        return None, []
    others = _names([e.name for e in fats[1:] + ps], fats[0].name)
    note = f"R1-1: 대두 표시가 붙은 종류 모를 유지라 대두를 추정으로 둠 (근거 후보: {', '.join(_names([e.name for e in fats]))})"
    verdict = AllergenVerdict("soy", "inferable", fats[0].name, others, ("R1-1",), (), fats[0].en or None)
    return verdict, [note] + _oil_note("soy", mine)


def _oil_note(allergen: str, mine: List[Evidence]) -> List[str]:
    """US-OIL: 미국 기준으로 세지 않은 정제유."""
    oils = _names([e.name for e in mine if e.grade == "R"])
    if allergen != "soy" or not oils:
        return []
    return [f"US-OIL: {', '.join(oils)} (고도 정제유는 미국 기준 알레르기로 세지 않음)"]


def _soy_with_box(mine: List[Evidence], is_: List[Evidence], ps: List[Evidence], leaves: List[Leaf],
                  box: Box) -> Tuple[Optional[AllergenVerdict], List[str]]:
    """R1-1: 한국은 정제유도 표시하므로 표시란의 대두는 기름 때문에 적혔을 수 있다."""
    fats = [e for e in mine if e.grade == "F"]
    if is_ or not (fats or any(e.grade == "R" for e in mine)):
        return _from_box("soy", [e.name for e in is_ + ps], box), []
    mixed = [leaf.name for leaf in leaves if leaf.opaque or leaf.compound]
    if not (fats or ps or mixed):
        return None, _oil_note("soy", mine)                  # 정제유만 있다
    others = list(_names([e.name for e in ps] + [e.name for e in fats] + mixed))
    note = f"R1-1: 표시란의 대두가 정제유·유지 때문일 수 있어 대두를 추정으로 둠 (근거 후보: {', '.join(others)})"
    return _from_box("soy", others, box, "inferable", ("R1-1",)), [note] + _oil_note("soy", mine)


def _decide(allergen: str, evidence: List[Evidence], leaves: List[Leaf],
            box: Box) -> Tuple[Optional[AllergenVerdict], List[str]]:
    """한 알레르기의 판정과 참고 사항. 순서대로 처음 맞는 규칙을 쓴다 (가이드 v1 4절)."""
    mine = [e for e in evidence if _us9(e.code) == allergen]
    cs = [e for e in mine if e.grade == "C"]
    is_ = [e for e in mine if e.grade == "I" and not _erased(e, box)]
    ps = [e for e in mine if e.grade == "P" and not _erased(e, box)]
    if cs:
        return _confirmed(allergen, cs, is_ + ps, box), _missing_notes(cs, box) + _goat_notes(allergen, cs, box)
    if allergen in box.words:
        if allergen == "soy":
            return _soy_with_box(mine, is_, ps, leaves, box)
        return _from_box(allergen, [e.name for e in is_ + ps], box), []
    if is_:
        return _from_weak(allergen, "inferable", "LIKELY", is_, [e.name for e in ps]), _oil_note(allergen, mine)
    if allergen == "soy":
        verdict, notes = _labelled_fat(mine, ps)
        if verdict is not None:
            return verdict, notes
    blind = _blind_leaves(allergen, leaves, box.read)
    if ps or blind:
        return _undecidable(allergen, ps, blind), _oil_note(allergen, mine)
    return None, _oil_note(allergen, mine)


# ---------- 5절: 판정 불가 원재료 ----------
def _unclear_names(leaves: List[Leaf], box_read: bool) -> Tuple[str, ...]:
    """속 모를 원료, 일반 향료, 모르는 이름. 표시란을 못 읽었으면 섞은 원료도."""
    names = [leaf.name for leaf in leaves
             if leaf.opaque or leaf.flavor_only or leaf.unknown or (leaf.compound and not box_read)]
    return _names(names)


def judge(parsed, resolve: Callable = lookup) -> Judgement:
    """파싱된 라벨(ParsedLabel) 하나를 판정한다. resolve: 원재료 이름 -> lexicon.Lookup과 같은 칸을 가진 결과."""
    collector = _Collector(resolve)
    collector.visit_all(parsed.tree)
    box = read_box(parsed)
    verdicts: List[AllergenVerdict] = []
    notes: List[str] = []
    for allergen in ALLERGENS:
        verdict, more = _decide(allergen, collector.evidence, collector.leaves, box)
        if verdict is not None:
            verdicts.append(verdict)
        notes.extend(n for n in more if n not in notes)
    return Judgement(tuple(verdicts), _unclear_names(collector.leaves, box.read), tuple(notes),
                     box.read, collector.count > 0)


__all__ = ["ALLERGENS", "AllergenVerdict", "Box", "Evidence", "Judgement", "Leaf", "code_info", "covered",
           "in_box", "judge", "read_box"]
