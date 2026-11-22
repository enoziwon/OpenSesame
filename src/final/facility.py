"""같은 시설 문구 -> 미국 9개 알레르기. 판정이 아니라 화면에 따로 보여 줄 안내다.

    from src.final.facility import shared_facility
    shared_facility("이 제품은 땅콩, 새우를 사용한 제품과 같은 제조시설에서 제조하고 있습니다.", decided={"crustacean"})
    # [FacilityNote(allergen='peanut', words=('땅콩',), reason_en='Peanuts are not listed as an ingredient, ...')]

'같은 제조시설에서 제조하고 있습니다' 문구는 원재료가 아니라 섞여 들어갈 수 있다는 안내다. 한국은 같은 제조 과정에서
알레르기 원료를 다루면 이 문구를 적게 해서 라벨 대부분에 붙어 있다(EXP-006 사진 14개 중 12개, 땅콩만 11개).
그래서 판정(confirmed·inferable·undecidable)은 바꾸지 않고(가이드: FDA D.8) 응답의 shared_facility 칸에 따로 담는다.
화면은 이것을 may contain 안의 가장 낮은 단계로 보여 준다(docs/10_may_contain.md).

- 판정이 이미 있는 알레르기는 넣지 않는다. 고추참치는 문구에 고등어가 있지만 가다랑어 때문에 생선이 이미 confirmed다.
- 문장은 고정이다(LLM을 쓰지 않는다). 원재료에는 없다는 것과 미량이 섞일 수 있다는 것을 함께 말한다.
- 사진은 OCR이 같은 시설 문장을 원재료 글자와 따로 넘긴다(OcrResult.facility). ocr_facility_pieces가 그중 같은 시설
  문구로 보이는 조각만 남기고, merge_facility가 파서가 글자 속에서 찾은 문구와 합친다(같은 문장은 한 번만).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from src.final.parser import MAX_CHARS
from src.final.verdict import ALLERGENS, box_codes, code_info

# 문구를 낱말로 자른다. '조개류(전복, 홍합 등 포함)를'의 괄호도 자른다
SPLIT_RE = re.compile(r"[,，、/·ㆍ\s()\[\]{}<>]+")
# 낱말 끝에 붙는 조사. '땅콩을', '밀과', '게를', '홍합등'
JOSA = ("을", "를", "이", "가", "은", "는", "과", "와", "의", "도", "등")
SUBJECT_EN = {"milk": "Milk is", "egg": "Egg is", "fish": "Fish is", "crustacean": "Crustacean shellfish are",
              "tree_nut": "Tree nuts are", "peanut": "Peanuts are", "wheat": "Wheat is", "soy": "Soy is",
              "sesame": "Sesame is"}
THING_EN = {"milk": "milk", "egg": "eggs", "fish": "fish", "crustacean": "shellfish", "tree_nut": "tree nuts",
            "peanut": "peanuts", "wheat": "wheat", "soy": "soybeans", "sesame": "sesame"}
NAME_KO = {"milk": "우유", "egg": "달걀", "fish": "생선", "crustacean": "갑각류", "tree_nut": "견과류",
           "peanut": "땅콩", "wheat": "밀", "soy": "대두", "sesame": "참깨"}


@dataclass(frozen=True)
class FacilityNote:
    allergen: str                 # 미국 9개 이름 (milk …)
    words: Tuple[str, ...]        # 문구에 적힌 한국어 낱말 (적힌 순서). 예: ('새우', '게')
    reason_en: str
    reason_ko: str


def _box_word(token: str) -> Optional[str]:
    """낱말 하나 -> 한국 표시란 낱말 (조사를 뗀다). 없으면 None. '게'처럼 한 글자 낱말도 낱말 전체가 같아야 한다."""
    token = token.strip(" .。")
    if token in box_codes():
        return token
    for josa in JOSA:
        if token.endswith(josa) and token[: -len(josa)] in box_codes():
            return token[: -len(josa)]
    return None


def facility_words(text: Optional[str]) -> Dict[str, Tuple[str, ...]]:
    """같은 시설 문구 속 한국 표시 낱말 -> {미국 9개: 낱말들}. 메밀·오징어처럼 9개 밖은 뺀다. 미국 9개 순서."""
    found: Dict[str, List[str]] = {}
    for token in SPLIT_RE.split(text or ""):
        word = _box_word(token)
        if word is None:
            continue
        allergen = code_info(box_codes()[word])[0]
        if allergen and word not in found.setdefault(allergen, []):
            found[allergen].append(word)
    return {a: tuple(found[a]) for a in ALLERGENS if a in found}


def shared_facility(text: Optional[str], decided: Iterable[str] = ()) -> List[FacilityNote]:
    """판정이 없는 알레르기만 안내로 만든다. decided: 판정(confirmed·inferable·undecidable)이 있는 알레르기."""
    skip = set(decided)
    return [_note(a, words) for a, words in facility_words(text).items() if a not in skip]


# ---------- OCR이 따로 넘긴 같은 시설 칸 ----------
# OCR(src/ocr/clova.py)은 같은 시설 문장들을 빈칸 하나로 이어 붙여 넘긴다. 문장 끝은 OCR이 문장을 끊는 끝말과 같게 본다.
# 가운뎃점(·)에서는 자르지 않는다. '우유·땅콩 혼입 가능'처럼 목록을 나누는 데도 쓰여 낱말을 잃는다.
SENTENCE_END_RE = re.compile(r"(?:니다|있음|가능)\.?(?=\s)")
# 같은 시설 문구의 핵심 낱말. OCR 쪽 정규식(clova.py FACILITY_RE)에서 줄 끝 '혼'만 뺐다. 줄이 '호두혼|합견과페이스트'처럼
# 나뉘면 OCR이 그 줄을 같은 시설 문장으로 잡아 제품명·원재료 덩어리가 통째로 들어오기 때문이다.
CORE_RE = re.compile(r"(?:같은|동일한?)\s*(?:제조\s*)?(?:시설|공장|라인)|혼\s*입")
# 문구가 줄 바꿈으로 나뉘어 핵심 낱말이 뒤 조각으로 간 경우의 앞머리: '이 제품은 메밀, 땅콩, …'
OPENER_RE = re.compile(r"^\W*(?:이|본)\s*제품은")


def ocr_facility_pieces(text: Optional[str]) -> List[str]:
    """OCR이 넘긴 같은 시설 칸 -> 같은 시설 문구로 보이는 조각들(적힌 순서).

    문장 끝에서 조각으로 나누고, 핵심 낱말('같은 … 시설', '혼입')도 '이 제품은' 머리도 없는 조각은 버린다.
    """
    if text is None:
        return []
    if not isinstance(text, str):
        raise TypeError("facility에는 글자(str)만 넣을 수 있습니다")
    if len(text) > MAX_CHARS:
        raise ValueError(f"facility가 너무 깁니다 (최대 {MAX_CHARS}자)")
    cuts = [0] + [m.end() for m in SENTENCE_END_RE.finditer(text)] + [len(text)]
    pieces = [text[a:b].strip() for a, b in zip(cuts, cuts[1:])]
    return [p for p in pieces if p and (CORE_RE.search(p) or OPENER_RE.match(p))]


def merge_facility(own: Optional[str], pieces: Iterable[str]) -> Optional[str]:
    """파서가 글자 속에서 찾은 문구(own)에 OCR 조각을 더한다. 빈칸만 다른 같은 문장은 한 번만 넣는다."""
    parts = [own] if own else []
    seen = [_squash(own)] if own else []
    for piece in pieces:
        key = _squash(piece)
        if key and not any(key in done for done in seen):
            parts.append(piece)
            seen.append(key)
    return " ".join(parts) or None


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _things_en(allergen: str, words: Tuple[str, ...]) -> str:
    """문구에 적힌 것의 영어 이름. 종을 아는 낱말(새우, 고등어, 호두)은 그 종으로 쓴다."""
    names: List[str] = []
    for word in words:
        code = box_codes()[word]
        name = code_info(code)[1] if ":" in code else THING_EN[allergen]
        if allergen == "tree_nut" and ":" in code and not name.endswith("s"):
            name += "s"                      # walnuts, pine nuts
        if name not in names:
            names.append(name)
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + ", and " + names[-1]


def _josa(word: str, with_final: str, without_final: str) -> str:
    last = word[-1:]
    if not ("가" <= last <= "힣"):
        return f"{with_final}({without_final})"
    return with_final if (ord(last) - 0xAC00) % 28 else without_final


def _note(allergen: str, words: Tuple[str, ...]) -> FacilityNote:
    things = _things_en(allergen, words)
    en = (f"{SUBJECT_EN[allergen]} not listed as an ingredient, but this product is made in a facility that also "
          f"handles {things}, so traces are possible. Avoid it if your allergy is severe.")
    name, listed = NAME_KO[allergen], ", ".join(words)
    ko = (f"원재료에 {name}{_josa(name, '은', '는')} 없지만, {listed}{_josa(listed, '을', '를')} 쓰는 제품과 같은 시설에서 "
          f"만들어 미량이 섞일 수 있다. 알레르기가 심하면 피하는 것이 좋다.")
    return FacilityNote(allergen, words, en, ko)


__all__ = ["FacilityNote", "facility_words", "merge_facility", "ocr_facility_pieces", "shared_facility"]
