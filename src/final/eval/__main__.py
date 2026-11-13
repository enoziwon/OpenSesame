"""채점 실행 (저장소 루트에서):

    python -m src.final.eval --gold dev.jsonl --pred a.jsonl [--pred b.jsonl …] --out report.md --json metrics.json

- 정답·응답 파일의 형식이 틀리거나 id가 서로 맞지 않으면 무엇이 틀렸는지 알리고 2로 끝난다.
- 화면과 보고서에는 집계 숫자만 나온다. 놓침·헛경고 목록(제품 id와 근거 글자)은 --json 파일에만 들어간다.
  시험 세트를 채점할 때는 --no-items로 그 목록도 빼서 시험 세트의 글자가 어떤 파일에도 남지 않게 한다.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from .load import ALLERGENS, EvalInputError, load_gold, load_pred
from .report import pct, render
from .score import score_all
from .stats import N_BOOT, SEED


def system_names(paths):
    """보고서에 쓸 시스템 이름: 파일 이름(확장자 뺌). 이름이 겹치면 준 경로 그대로."""
    stems = [Path(p).stem for p in paths]
    return [stem if stems.count(stem) == 1 else str(p) for stem, p in zip(stems, paths)]


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="python -m src.final.eval", description="정답과 시스템 응답을 비교해 지표를 낸다.")
    ap.add_argument("--gold", required=True, help="정답 JSONL (data/schema/label_record.schema.json 레코드)")
    ap.add_argument("--pred", required=True, action="append", help="시스템 응답 JSONL. 여러 번 줄 수 있다")
    ap.add_argument("--out", help="마크다운 보고서 경로. 없으면 화면에 찍는다")
    ap.add_argument("--json", dest="json_path", help="지표 JSON 경로")
    ap.add_argument("--boot", type=int, default=N_BOOT, help=f"부트스트랩 횟수 (기본 {N_BOOT}, 0이면 구간을 내지 않는다)")
    ap.add_argument("--seed", type=int, default=SEED, help=f"부트스트랩 시드 (기본 {SEED})")
    ap.add_argument("--no-items", action="store_true", help="놓침·헛경고 목록을 JSON에 넣지 않는다 (시험 세트용)")
    args = ap.parse_args(argv)
    if args.boot < 0:
        ap.error("--boot는 0 이상이어야 한다")
    return args


def _write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def main(argv=None):
    args = parse_args(argv)
    try:
        gold = load_gold(args.gold)
        preds = [load_pred(p, gold) for p in args.pred]
    except (OSError, EvalInputError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    if not any(p.labels for p in gold.products):
        print("경고: 정답 파일의 annotations가 모두 비어 있다. 빈 정답 파일(*_blank.jsonl)이 아닌지 확인할 것.", file=sys.stderr)
    names = system_names(args.pred)
    result = score_all(gold, preds, names, n_boot=args.boot, seed=args.seed, items=not args.no_items)
    header = {
        "gold": args.gold, "gold_sha256": gold.sha256,
        "preds": [{"file": p, "name": n} for p, n in zip(args.pred, names)],
        "products": len(gold.products), "units": len(gold.products) * len(ALLERGENS),
        "run_at": datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        "boot": args.boot, "seed": args.seed,
    }
    text = render(result, header)
    try:
        if args.out:
            _write(args.out, text)
        if args.json_path:
            _write(args.json_path, json.dumps(dict(header=header, **result), ensure_ascii=False, indent=1) + "\n")
    except OSError as e:
        print(f"오류: 결과를 쓰지 못함: {e}", file=sys.stderr)
        return 2
    if not args.out:
        print(text)
    for s in result["systems"]:
        print(f"{s['name']}: 놓침 {pct(s['miss'])} · 헛경고 {pct(s['false_alarm_unit'])} · 정확도 {pct(s['accuracy'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
