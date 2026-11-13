"""정답 파일의 원재료명·표시란을 최종본(src.final.pipeline.analyze_fields)에 넣어 응답 파일을 만든다.

    python tools/run_final.py --gold data/raw/gold/dev.jsonl --out data/raw/eval/final_dev.jsonl
    python -m src.final.eval --gold data/raw/gold/dev.jsonl --pred data/raw/eval/final_dev.jsonl --out report.md

- 입력은 정답 레코드의 ingredients_text와 kr_declared_allergens뿐이다. annotations는 보지 않는다(빈 정답 파일로도 돌린다).
- 표시란 글자: 항목이 있으면 "밀, 대두 함유", 없으면 "없음"(표시란을 읽었는데 비었다는 뜻. 정답지는 표시란을 확인한 제품만 담는다).
- 출력 한 줄: {"id", "response": 응답 JSON, "ms": analyze_fields에 걸린 시간}. 끝까지 돌아야 --out 파일이 생긴다.
- 화면에는 건수와 시간만 찍는다. 원재료 글자는 찍지 않는다(시험 세트 보호).
- --no-box를 주면 표시란을 넘기지 않는다. 표시란 규칙을 끈 수치를 견줄 때 쓴다(EXP-004 가설 4).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))          # python tools/run_final.py 로 실행해도 src를 찾게 한다

from src.final.eval import EvalInputError, declaration_text, load_gold  # noqa: E402


def load_system():
    """최종본 파이프라인의 analyze_fields를 가져온다. 아직 없으면 알기 쉬운 오류로 멈춘다."""
    try:
        from src.final.pipeline import analyze_fields
    except ImportError as e:
        raise SystemExit(
            f"최종본 파이프라인을 가져오지 못함: src.final.pipeline.analyze_fields ({type(e).__name__}: {e}).\n"
            "src/final/pipeline.py가 아직 없거나 그 안의 import가 실패했다."
        ) from e
    return analyze_fields


def to_json(res):
    """pydantic 응답이면 JSON용 dict로 바꾼다. dict면 그대로."""
    if hasattr(res, "model_dump"):
        return res.model_dump(mode="json")
    if isinstance(res, dict):
        return res
    raise TypeError(f"응답 형식을 모름: {type(res).__name__}")


def run(products, analyze, out, use_box=True):
    """제품마다 analyze(원재료, 표시란)를 불러 한 줄씩 쓴다. 실패하면 그 id와 오류 종류만 알리고 멈춘다.

    use_box가 False면 표시란 자리에 None을 넘긴다(표시란을 찾지 못한 라벨과 같다).

    쓰는 동안은 <out>.part에 쓰고, 끝까지 가면 <out>으로 바꾼다. 처리 시간 목록(ms)을 돌려준다.
    """
    part = out.with_name(out.name + ".part")
    times = []
    with open(part, "w", encoding="utf-8") as f:
        for p in products:
            try:
                start = time.perf_counter()
                res = analyze(p.ingredients_text, declaration_text(p.declared) if use_box else None)
                ms = (time.perf_counter() - start) * 1000
                row = {"id": p.id, "response": to_json(res), "ms": round(ms, 3)}
            except Exception as e:     # 원재료 글자가 섞일 수 있어 오류 내용은 찍지 않는다
                raise SystemExit(f"{p.id}에서 실패: {type(e).__name__}. 쓰다 만 파일: {part}") from e
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            times.append(ms)
    part.replace(out)
    return times


def main(argv=None):
    ap = argparse.ArgumentParser(description="정답 파일의 입력을 최종본에 넣어 응답 JSONL을 만든다.")
    ap.add_argument("--gold", required=True, help="정답 JSONL (빈 정답 *_blank.jsonl도 된다)")
    ap.add_argument("--out", required=True, help="응답 JSONL 경로 (예: data/raw/eval/final_dev.jsonl)")
    ap.add_argument("--no-box", action="store_true", help="표시란을 넘기지 않는다 (표시란 규칙을 끈 비교용)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.resolve() == Path(args.gold).resolve():
        print("오류: --out이 --gold와 같은 파일이다", file=sys.stderr)
        return 2
    try:
        gold = load_gold(args.gold)
    except (OSError, EvalInputError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    analyze = load_system()
    out.parent.mkdir(parents=True, exist_ok=True)
    times = run(gold.products, analyze, out, use_box=not args.no_box)
    print(f"{len(times)}개 제품 -> {out} (제품당 평균 {sum(times) / len(times):.2f} ms, 최대 {max(times):.2f} ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
