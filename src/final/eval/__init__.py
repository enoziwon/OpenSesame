"""최종본 채점: 정답(JSONL) + 시스템 응답(JSONL) -> 지표. 어떤 시스템의 출력이든 같은 방식으로 잰다.

    python -m src.final.eval --gold dev.jsonl --pred a.jsonl [--pred b.jsonl …] --out report.md --json metrics.json

    from src.final.eval import load_gold, load_pred, score_system
    gold = load_gold("dev.jsonl")          # data/schema/label_record.schema.json 레코드. 필수 칸과 값 범위를 검사한다
    pred = load_pred("a.jsonl", gold)      # {"id", "response": 팀 AnalyzeResponse JSON, "ms"}. id가 정답과 같아야 한다
    m = score_system(gold, pred)           # 지표 dict. m["miss"]["value"] = 놓침률

판정 단위는 제품 × 미국 9개 알레르기. 목록에 없는 알레르기는 absent로 본다.
응답 파일은 tools/run_final.py(최종본)와 tools/run_team.py(팀 1차 파이프라인)가 만든다.
표준 라이브러리만 쓴다.
"""
from .load import (
    ABSENT,
    ALLERGENS,
    CATEGORIES,
    VERDICTS,
    EvalInputError,
    GoldSet,
    PredSet,
    declaration_text,
    load_gold,
    load_pred,
)
from .report import render
from .score import build_units, compare_systems, score_all, score_system

__all__ = [
    "ABSENT", "ALLERGENS", "CATEGORIES", "VERDICTS", "EvalInputError", "GoldSet", "PredSet",
    "declaration_text", "load_gold", "load_pred", "render", "build_units", "compare_systems",
    "score_all", "score_system",
]
