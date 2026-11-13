"""최종본 파이프라인: 라벨 글자 -> 파서 -> 원재료 사전(+ 모르는 이름 맞추기) -> 판정 -> 팀 응답 형식(넓힌 판).

    from src.final.pipeline import analyze_fields, analyze_text
    analyze_text("원재료명: 간장, 설탕, 대두 함유")          # 사진에서 읽은 글자 전체
    analyze_fields("간장, 설탕", "대두 함유")                # HACCP API처럼 원재료명과 표시란이 따로 온 경우

LLM을 쓰지 않는다. 같은 글자를 넣으면 늘 같은 결과가 나온다.
사전이 모르는 이름은 끝에 붙은 기호를 떼거나 자모 하나가 틀린 오타로 보고 사전 항목과 맞춰 본다(src/final/resolve.py).
맞춘 것은 참고(notes)에 '오타로 보고 맞춤: 탈지븐유 → 탈지분유'처럼 남는다. 환경 변수 OPENSESAME_FINAL_FUZZY=0이면 끈다.
OPENSESAME_FINAL_FALLBACK=llm이고 LLM 키가 있을 때만 끝까지 모르는 이름을 팀 LLM 분류기에 묻는다(기본은 꺼짐).
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional, Tuple

from src.common.schema import AnalyzeMeta
from src.final.parser import parse_label
from src.final.resolve import Resolver, fallback_from_env
from src.final.response import FinalAllergenResult, FinalAnalyzeResponse
from src.final.verdict import AllergenVerdict, Judgement, code_info, judge

CLASSIFIER_NAME = "final-lexicon-v1"
NO_INGREDIENTS = "원재료를 읽지 못함. 원재료명이 잘 보이게 다시 찍어 주세요."      # 팀 파이프라인과 같은 문구
NO_BOX = "알레르기 표시란을 찾지 못함. 우유·달걀·밀·대두·땅콩·게·새우·호두·잣·고등어는 표시란으로 확인하지 못했음."

NAME_EN = {"milk": "milk", "egg": "egg", "fish": "fish", "crustacean": "crustacean shellfish",
           "tree_nut": "tree nuts", "peanut": "peanuts", "wheat": "wheat", "soy": "soy", "sesame": "sesame"}
NAME_KO = {"milk": "우유", "egg": "달걀", "fish": "생선", "crustacean": "갑각류", "tree_nut": "견과류",
           "peanut": "땅콩", "wheat": "밀", "soy": "대두", "sesame": "참깨"}
# 속 모를 원료가 판정 불가가 되는 까닭 (참깨·생선은 한국 표시 의무 밖, 나머지는 표시란을 못 읽었을 때만)
BLIND_EN = {"sesame": "Korean labels do not have to declare sesame",
            "fish": "Korean labels only have to declare mackerel among fish"}
BLIND_KO = {"sesame": "한국 라벨은 참깨를 표시하지 않아도 된다",
            "fish": "한국 라벨은 생선 중 고등어만 표시한다"}
NO_BOX_EN = "the Korean allergen statement was not found"
NO_BOX_KO = "알레르기 표시란을 찾지 못했다"
FUZZY_ENV = "OPENSESAME_FINAL_FUZZY"      # 0·off·false·no면 모르는 이름 맞추기(끝 기호 떼기, 오타 맞추기)를 끈다


# ---------- 입력 ----------
def analyze_text(text: str, ocr_engine: str = "text") -> FinalAnalyzeResponse:
    """사진에서 읽은 글자 전체(원재료명, 알레르기 표시란, 같은 시설 문구)를 판정한다."""
    parsed = parse_label(text)
    return _respond(parsed, ocr_engine, parsed.facility_text)


def analyze_fields(ingredients: Optional[str], declaration: Optional[str] = None) -> FinalAnalyzeResponse:
    """원재료명(ingredients)과 표시란(declaration)이 따로 온 경우. HACCP API의 rawmtrl, allergy.

    원재료 칸에 섞여 온 같은 시설 문구와 표시란 칸이 비었을 때 원재료 칸 끝에 적힌 표시란은 파서가 떼어 낸다.
    """
    parsed = parse_label(ingredients="" if ingredients is None else ingredients, declaration=declaration)
    return _respond(parsed, "text", parsed.facility_text)


# ---------- 응답 ----------
def _fuzzy_on() -> bool:
    return os.environ.get(FUZZY_ENV, "").strip().lower() not in ("0", "off", "false", "no")


@lru_cache(maxsize=1)
def _fallback():
    """보조 분류기(기본은 없음). 환경 변수는 처음 쓸 때 한 번만 읽는다."""
    return fallback_from_env()


def _respond(parsed, ocr_engine: str, facility: Optional[str]) -> FinalAnalyzeResponse:
    on = _fuzzy_on()
    resolver = Resolver(fuzzy=on, codes=on, fallback=_fallback())     # 라벨 하나마다 새로 만든다
    if resolver.fallback is not None:
        resolver.resolve_many([m[0] for m in parsed.mentions()])
    j = judge(parsed, resolve=resolver.resolve)
    return FinalAnalyzeResponse(
        ingredients_text=parsed.ingredients_text,
        ingredients=[n.to_dict() for n in parsed.tree],
        allergens=[_result(v) for v in j.allergens],
        undecidable_ingredients=list(j.undecidable_ingredients),
        warnings=_warnings(j),
        meta=AnalyzeMeta(ocr_engine=ocr_engine, classifier=CLASSIFIER_NAME, prompt_version=None),
        declaration_text=parsed.declaration_text,
        declared=list(parsed.declared),
        notes=_notes(j, facility, parsed.repairs) + resolver.notes(),
    )


def _warnings(j: Judgement) -> List[str]:
    """비어 있지 않으면 화면이 결과를 단정하지 않는다."""
    out = []
    if not j.read_any:
        out.append(NO_INGREDIENTS)
    if not j.box_read:
        out.append(NO_BOX)
    return out


def _notes(j: Judgement, facility: Optional[str], repairs: int) -> List[str]:
    notes = list(j.notes)
    if facility:
        notes.append(f"같은 시설 문구(판정에 쓰지 않음): {facility}")
    if repairs:
        notes.append(f"괄호 짝을 {repairs}번 고쳐 읽음. 라벨이나 OCR 글자가 깨졌을 수 있음")
    return notes


def _result(v: AllergenVerdict) -> FinalAllergenResult:
    en, ko = reason(v)
    return FinalAllergenResult(
        allergen=v.allergen, verdict=v.verdict, evidence_ingredient=v.evidence,
        other_evidence=list(v.other_evidence), basis=list(v.basis),
        species=[code_info(c)[1] for c in v.species], evidence_en=v.evidence_en,
        reason_en=en, reason_ko=ko,
    )


# ---------- 이유 문장 ----------
def _josa(word: str, with_final: str, without_final: str) -> str:
    """받침이 있으면 앞 조사(이·은), 없으면 뒤 조사(가·는). 한글로 끝나지 않으면 '이(가)'처럼 둘 다."""
    last = word[-1:]
    if not ("가" <= last <= "힣"):
        return f"{with_final}({without_final})"
    return with_final if (ord(last) - 0xAC00) % 28 else without_final


def _target(v: AllergenVerdict) -> Tuple[str, str]:
    """문장에 쓸 알레르기 이름. 종 하나만 알면 그 종(새우, 아몬드)으로 쓴다."""
    if len(v.species) == 1:
        _, en, ko, _ = code_info(v.species[0])
        return en, ko.split("·")[0]
    return NAME_EN[v.allergen], NAME_KO[v.allergen]


def reason(v: AllergenVerdict) -> Tuple[str, str]:
    """판정 하나의 이유를 (영어, 한국어) 한 문장씩."""
    kind = v.basis[0]
    name, word = v.evidence, v.word
    t_en, t_ko = _target(v)
    if kind == "INGREDIENT" and word:
        return (f"Contains {NAME_EN[v.allergen]}: “{name}” lists {word} ({t_en}) in parentheses.",
                f"원재료 “{name}”의 괄호 속에 {word}{_josa(word, '이', '가')} 적혀 있다.")
    if kind == "INGREDIENT":
        gloss = v.evidence_en or ", ".join(code_info(c)[1] for c in v.species)
        return (f"Contains {NAME_EN[v.allergen]}: “{name}”" + (f" ({gloss})." if gloss else "."),
                f"원재료 “{name}”에 {NAME_KO[v.allergen]}{_josa(NAME_KO[v.allergen], '이', '가')} 들어 있다.")
    if kind == "KR-DECL":
        return (f"Listed in the Korean allergen statement: {word}" + (f" ({v.evidence_en})." if v.evidence_en else "."),
                f"한국 알레르기 표시란에 {word}{_josa(word, '이', '가')} 적혀 있다.")
    if kind == "R1-1" and not word:          # 표시란 없이 '식물성유지(대두)'처럼 유지에 대두 표시가 붙은 경우
        return (f"Likely contains soy: “{name}” is a fat or oil labelled as coming from soybeans. Refined soybean oil "
                f"is not counted, but it could contain soy protein.",
                f"“{name}”{_josa(name, '은', '는')} 대두에서 온 유지로 적혀 있다. 정제 대두유는 세지 않지만 대두 단백질이 있을 수 있다.")
    if kind == "R1-1":
        first = v.other_evidence[0] if v.other_evidence else ""
        return (f"Likely contains soy: the Korean allergen statement lists {word}, which may only mean refined "
                f"soybean oil, but “{first}” could contain soy protein.",
                f"표시란에 {word}{_josa(word, '이', '가')} 있지만 정제 대두유 때문일 수 있고, “{first}”에 대두 단백질이 있을 수 있다.")
    if kind == "LIKELY":
        return (f"Likely contains {NAME_EN[v.allergen]}: “{name}” is usually made with {t_en}.",
                f"“{name}”에는 대개 {t_ko}{_josa(t_ko, '이', '가')} 들어간다.")
    if kind == "POSSIBLE":
        return (f"Cannot tell: “{name}” sometimes contains {t_en}.",
                f"“{name}”에는 {t_ko}{_josa(t_ko, '이', '가')} 들어 있을 수 있다.")
    return _blind_reason(v, kind)


def _blind_reason(v: AllergenVerdict, kind: str) -> Tuple[str, str]:
    """속 모를 원료(OPAQUE)나 섞은 원료(COMPOUND) 때문에 판정할 수 없을 때."""
    name = v.evidence
    tail_en = BLIND_EN.get(v.allergen, NO_BOX_EN)
    tail_ko = BLIND_KO.get(v.allergen, NO_BOX_KO)
    if kind == "OPAQUE":
        what_en, what_ko = "a seasoning blend", "속을 알 수 없는 양념·국물 원료"
    else:
        what_en, what_ko = "a mixed ingredient", "속을 알 수 없는 섞은 원료"
    return (f"Cannot tell: “{name}” is {what_en} whose contents are not listed, and {tail_en}.",
            f"“{name}”{_josa(name, '은', '는')} {what_ko}이고, {tail_ko}.")


__all__ = ["CLASSIFIER_NAME", "NO_BOX", "NO_INGREDIENTS", "analyze_fields", "analyze_text", "reason"]
