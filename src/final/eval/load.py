"""채점 입력 읽기: 정답 JSONL과 시스템 응답 JSONL. 읽으면서 형식을 검사한다.

    gold = load_gold("dev.jsonl")          # 정답 한 줄 = data/schema/label_record.schema.json 레코드
    pred = load_pred("a.jsonl", gold)      # 응답 한 줄 = {"id", "response": 팀 AnalyzeResponse JSON, "ms"}

정답 annotations와 응답 allergens에 없는 알레르기는 absent로 본다.
오류 문장에는 파일·줄 번호·id·칸 이름만 적고 원재료 글자는 적지 않는다(시험 세트 보호).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

ALLERGENS = ("milk", "egg", "fish", "crustacean", "tree_nut", "peanut", "wheat", "soy", "sesame")  # 팀 Allergen 순서
VERDICTS = ("confirmed", "inferable", "undecidable")
ABSENT = "absent"
CATEGORIES = VERDICTS + (ABSENT,)
PRODUCT_TYPES = ("snack", "sauce_seasoning", "instant", "frozen", "beverage_dairy", "other")
PACKAGE_MATERIALS = ("foil", "plastic_film", "paper", "can_bottle", "other")
MAX_ERRORS = 20          # 오류 문장은 이만큼만 보여 준다
MAX_IDS = 10             # id 목록도 이만큼만


class EvalInputError(ValueError):
    """정답·응답 파일이 형식에 맞지 않거나 두 파일의 id가 서로 맞지 않는다."""


@dataclass(frozen=True)
class Label:
    verdict: str
    evidence: str
    hidden: Optional[bool] = None      # 정답의 hidden_or_derived. 칸이 없으면 None
    declared: Optional[bool] = None    # 정답의 declared_in_kr. 칸이 없으면 None


@dataclass(frozen=True)
class GoldProduct:
    id: str
    ingredients_text: str
    declared: Tuple[str, ...]          # kr_declared_allergens 그대로
    labels: Dict[str, Label]           # 알레르기 -> 정답 (absent는 넣지 않는다)


@dataclass(frozen=True)
class GoldSet:
    path: str
    sha256: str
    products: Tuple[GoldProduct, ...]  # 파일 순서


@dataclass(frozen=True)
class PredProduct:
    id: str
    labels: Dict[str, Label]           # 알레르기 -> 응답 (absent는 없음)
    ms: Optional[float]                # 처리 시간. 없으면 None
    classifier: str                    # meta.classifier/prompt_version
    warned: bool                       # 응답 warnings가 비어 있지 않다


@dataclass(frozen=True)
class PredSet:
    path: str
    products: Dict[str, PredProduct]   # id -> 응답


def declaration_text(declared):
    """정답의 표시란 항목을 시스템 입력 글자로: ['밀', '대두'] -> '밀, 대두 함유', [] -> '없음'(읽었는데 비었다)."""
    return ", ".join(declared) + " 함유" if declared else "없음"


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def _raise_if(errors):
    if not errors:
        return
    shown = errors[:MAX_ERRORS]
    more = f"\n… 외 {len(errors) - MAX_ERRORS}개" if len(errors) > MAX_ERRORS else ""
    raise EvalInputError("\n".join(shown) + more)


def _short(value):
    return repr(value)[:30]


def _id_list(ids):
    more = f" … 외 {len(ids) - MAX_IDS}개" if len(ids) > MAX_IDS else ""
    return ", ".join(ids[:MAX_IDS]) + more


def read_jsonl(path):
    """[(줄 번호, dict)]. 빈 줄은 건너뛴다. JSON이 아니거나 객체가 아닌 줄이 있으면 오류."""
    rows: List[Tuple[int, dict]] = []
    errors: List[str] = []
    try:
        with open(path, encoding="utf-8-sig") as f:
            lines = list(f)
    except UnicodeDecodeError as e:
        raise EvalInputError(f"{path}: UTF-8 글자가 아님") from e
    for no, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"{path}:{no} JSON이 아님 ({e.msg})")
            continue
        if not isinstance(obj, dict):
            errors.append(f"{path}:{no} 한 줄이 객체가 아님")
            continue
        rows.append((no, obj))
    _raise_if(errors)
    return rows


def _where(path, no, obj):
    rid = obj.get("id")
    return f"{path}:{no}" + (f" (id={rid})" if isinstance(rid, str) else "")


def _check_annotation(ann, where):
    if not isinstance(ann, dict):
        return [f"{where}: 객체여야 함"]
    errors = []
    if ann.get("allergen") not in ALLERGENS:
        errors.append(f"{where} allergen: 미국 9개 이름이 아님 ({_short(ann.get('allergen'))})")
    if ann.get("verdict") not in VERDICTS:
        errors.append(f"{where} verdict: confirmed/inferable/undecidable이 아님 ({_short(ann.get('verdict'))})")
    for key in ("evidence_ingredient", "legal_basis"):
        if not isinstance(ann.get(key), str):
            errors.append(f"{where} {key}: 글자여야 함")
    for key in ("hidden_or_derived", "declared_in_kr"):
        if key in ann and not isinstance(ann[key], bool):
            errors.append(f"{where} {key}: true 또는 false여야 함")
    return errors


def _check_gold(obj, where):
    """정답 레코드 하나의 필수 칸과 값 범위 (스키마의 required·enum)."""
    errors = []
    if not isinstance(obj.get("id"), str) or not obj["id"].strip():
        errors.append(f"{where} id: 비어 있지 않은 글자여야 함")
    if obj.get("product_type") not in PRODUCT_TYPES:
        errors.append(f"{where} product_type: 스키마 값이 아님 ({_short(obj.get('product_type'))})")
    if obj.get("package_material") not in PACKAGE_MATERIALS:
        errors.append(f"{where} package_material: 스키마 값이 아님 ({_short(obj.get('package_material'))})")
    if not isinstance(obj.get("ingredients_text"), str):
        errors.append(f"{where} ingredients_text: 글자여야 함")
    declared = obj.get("kr_declared_allergens")
    if not isinstance(declared, list) or not all(isinstance(w, str) for w in declared):
        errors.append(f"{where} kr_declared_allergens: 글자 목록이어야 함")
    annotations = obj.get("annotations")
    if not isinstance(annotations, list):
        return errors + [f"{where} annotations: 목록이어야 함"]
    seen = set()
    for i, ann in enumerate(annotations):
        errors += _check_annotation(ann, f"{where} annotations[{i}]")
        allergen = ann.get("allergen") if isinstance(ann, dict) else None
        if allergen in ALLERGENS and allergen in seen:
            errors.append(f"{where} annotations[{i}]: {allergen}이(가) 두 번 나옴")
        seen.add(allergen)
    return errors


def _gold_product(obj):
    labels = {
        a["allergen"]: Label(a["verdict"], a["evidence_ingredient"], a.get("hidden_or_derived"), a.get("declared_in_kr"))
        for a in obj["annotations"]
    }
    return GoldProduct(obj["id"], obj["ingredients_text"], tuple(obj["kr_declared_allergens"]), labels)


def load_gold(path):
    """정답 파일을 읽고 검사한다. 문제가 하나라도 있으면 전부 모아 EvalInputError."""
    errors: List[str] = []
    products: List[GoldProduct] = []
    ids = set()
    for no, obj in read_jsonl(path):
        where = _where(path, no, obj)
        problems = _check_gold(obj, where)
        if not problems and obj["id"] in ids:
            problems = [f"{where}: id가 두 번 나옴"]
        errors += problems
        if not problems:
            ids.add(obj["id"])
            products.append(_gold_product(obj))
    _raise_if(errors)
    if not products:
        raise EvalInputError(f"{path}: 정답 레코드가 없음")
    return GoldSet(str(path), file_sha256(path), tuple(products))


def _check_allergen_items(items, where):
    errors, seen = [], set()
    for i, item in enumerate(items):
        w = f"{where} response.allergens[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{w}: 객체여야 함")
            continue
        if item.get("allergen") not in ALLERGENS:
            errors.append(f"{w} allergen: 미국 9개 이름이 아님 ({_short(item.get('allergen'))})")
        elif item["allergen"] in seen:
            errors.append(f"{w}: {item['allergen']}이(가) 두 번 나옴")
        seen.add(item.get("allergen"))
        if item.get("verdict") not in VERDICTS:
            errors.append(f"{w} verdict: confirmed/inferable/undecidable이 아님 ({_short(item.get('verdict'))})")
        if not isinstance(item.get("evidence_ingredient"), str):
            errors.append(f"{w} evidence_ingredient: 글자여야 함")
    return errors


def _check_pred(obj, where):
    errors = []
    if not isinstance(obj.get("id"), str) or not obj["id"].strip():
        errors.append(f"{where} id: 비어 있지 않은 글자여야 함")
    ms = obj.get("ms")
    if ms is not None and (isinstance(ms, bool) or not isinstance(ms, (int, float)) or not math.isfinite(ms) or ms < 0):
        errors.append(f"{where} ms: 0 이상의 숫자여야 함")
    response = obj.get("response")
    if not isinstance(response, dict) or not isinstance(response.get("allergens"), list):
        return errors + [f"{where} response.allergens: 목록이어야 함"]
    return errors + _check_allergen_items(response["allergens"], where)


def _pred_product(obj):
    response = obj["response"]
    labels = {a["allergen"]: Label(a["verdict"], a["evidence_ingredient"]) for a in response["allergens"]}
    meta = response.get("meta") if isinstance(response.get("meta"), dict) else {}
    classifier = "/".join(str(meta[k]) for k in ("classifier", "prompt_version") if meta.get(k))
    warnings = response.get("warnings")
    ms = obj.get("ms")
    return PredProduct(obj["id"], labels, None if ms is None else float(ms), classifier,
                       isinstance(warnings, list) and len(warnings) > 0)


def _check_ids(path, gold_ids, pred_ids):
    """두 파일의 id가 똑같아야 한다. 한쪽에만 있는 id를 알리고 멈춘다."""
    pred_set, gold_set = set(pred_ids), set(gold_ids)
    only_gold = [i for i in gold_ids if i not in pred_set]
    only_pred = [i for i in pred_ids if i not in gold_set]
    if not only_gold and not only_pred:
        return
    lines = [f"{path}: id가 정답 파일과 맞지 않음"]
    if only_gold:
        lines.append(f"  응답에 없는 정답 id {len(only_gold)}개: {_id_list(only_gold)}")
    if only_pred:
        lines.append(f"  정답에 없는 응답 id {len(only_pred)}개: {_id_list(only_pred)}")
    raise EvalInputError("\n".join(lines))


def load_pred(path, gold):
    """응답 파일을 읽고 검사한다. id는 정답 파일과 하나도 빠짐없이 같아야 한다."""
    errors: List[str] = []
    products: Dict[str, PredProduct] = {}
    for no, obj in read_jsonl(path):
        where = _where(path, no, obj)
        problems = _check_pred(obj, where)
        if not problems and obj["id"] in products:
            problems = [f"{where}: id가 두 번 나옴"]
        errors += problems
        if not problems:
            products[obj["id"]] = _pred_product(obj)
    _raise_if(errors)
    _check_ids(path, [p.id for p in gold.products], list(products))
    return PredSet(str(path), products)
