"""EXP-005: LLM 크레딧이 허락하는 만큼 팀 1차를 정해 둔 순서대로 돌린다. 최종본은 무료라 --final로 언제든 전부 돌린다.

    python tools/run_exp005.py --status          # 단계마다 몇 개 했고 몇 개 남았는지 (LLM을 부르지 않는다)
    python tools/run_exp005.py --budget 25       # 이 키로 LLM을 최대 25번(제품 25개) 쓴다. 지난번에 멈춘 곳부터 이어서
    python tools/run_exp005.py --final           # 최종본만 전부 돌린다 (LLM을 부르지 않는다)

순서 (experiments/EXP-005-photo-1st-vs-final.md의 우선순위). 앞 단계를 다 끝내야 다음 단계로 넘어간다.
  P     사진 OCR 글자          experiments/EXP-005/results/clova_full/<id>.txt      -> team_llm_P.jsonl
  R     P를 한 번 더           같은 입력에 답이 흔들리는지                          -> team_llm_P_run2.jsonl
  T     같은 제품의 정답 글자  data/raw/gold/test_blank.jsonl의 그 제품 원재료명    -> team_llm_T.jsonl
  REST  시험 세트 나머지       data/raw/gold/test_blank.jsonl의 나머지 제품         -> team_llm_REST.jsonl
결과 폴더는 data/raw/eval/exp005/.

- 대상 제품은 experiments/EXP-005/included.txt(정답 대조를 끝낸 제품, 한 줄에 id 하나)에 적힌 것만이다.
  이 파일이 없으면 LLM을 부르지 않는다. 정답을 잠그기 전에 크레딧을 쓰지 않기 위해서다.
- 키는 각자 자기 .env에만 둔다. 다른 사람이 이어서 돌릴 때는 결과 폴더를 통째로 받아 같은 자리에 두고 같은 명령을 실행한다.
- 게이트웨이가 크레딧 부족(402)으로 거절하면 바로 멈춘다. 그때까지 쓴 결과는 남고, 다음 실행이 그 제품부터 다시 돈다.
- 예산은 제품 수로 센다. 제품 하나에 LLM을 한 번 부른다(원재료가 40개를 넘으면 나눠 보내 몇 번 더).
- 실행할 때마다 run_meta.json의 runs에 언제, 어느 커밋으로, 어느 단계를 몇 개 돌렸는지 덧붙인다. 키는 적지 않는다.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import run_final  # noqa: E402
import run_photo  # noqa: E402
import run_team  # noqa: E402
from src.final.eval import EvalInputError, load_gold  # noqa: E402

EXP = ROOT / "experiments" / "EXP-005"
TEST = ROOT / "data" / "raw" / "gold" / "test_blank.jsonl"
OUT = ROOT / "data" / "raw" / "eval" / "exp005"
FINAL_REPEAT = 3                       # 최종본은 같은 입력을 세 번 돌려 답이 같은지 본다 (EXP-004 S7)


class Stage(NamedTuple):
    name: str
    title: str
    out: str
    source: str                        # photo = 사진 OCR 글자, shot = 사진 찍은 제품의 정답 글자, rest = 나머지 제품


STAGES = (
    Stage("P", "사진 OCR 글자", "team_llm_P.jsonl", "photo"),
    Stage("R", "P를 한 번 더 (흔들림)", "team_llm_P_run2.jsonl", "photo"),
    Stage("T", "같은 제품의 정답 글자", "team_llm_T.jsonl", "shot"),
    Stage("REST", "시험 세트 나머지 글자", "team_llm_REST.jsonl", "rest"),
)


def included(exp):
    """정답 대조를 끝낸 제품 id 목록. 파일이 없으면 None."""
    path = exp / "included.txt"
    if not path.exists():
        return None
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def photo_items(exp, ids):
    """(id, 사진 OCR 글자). included.txt 순서. 글자 파일이 없는 id가 있으면 멈춘다."""
    folder = exp / "results" / "clova_full"
    missing = [i for i in ids if not (folder / f"{i}.txt").exists()]
    if missing:
        raise SystemExit(f"OCR 글자가 없는 제품 {len(missing)}개: {', '.join(missing[:5])} ({folder})")
    return [(i, (folder / f"{i}.txt").read_text(encoding="utf-8")) for i in ids]


def stage_items(stage, exp, test, ids):
    if stage.source == "photo":
        return photo_items(exp, ids)
    shot = set(ids)
    pick = [p for p in test.products if (p.id in shot) == (stage.source == "shot")]
    return [(p.id, run_team.team_text(p, False)) for p in pick]


def written(out):
    """지금까지 쓴 줄 수(분류 실패 포함). 예산을 셀 때 쓴다."""
    part = out.with_name(out.name + ".part")
    src = part if part.exists() else out
    if not src.exists():
        return 0
    return sum(1 for line in src.read_text(encoding="utf-8").splitlines() if line.strip())


def done_ids(out):
    return {json.loads(line)["id"] for line in run_team.read_done(out)}


def team_call(classifier, engine):
    from src.pipeline import analyze

    ocr = run_photo.TextOcr(engine)
    return lambda text: analyze(text.encode("utf-8"), "text/plain", ocr=ocr, classifier=classifier).model_dump(mode="json")


def status(exp, test, out_dir, ids):
    print(f"대상 제품(included.txt): {len(ids)}개")
    need = 0
    for st in STAGES:
        items = stage_items(st, exp, test, ids)
        done = len(done_ids(out_dir / st.out) & {i for i, _ in items})
        need += len(items) - done
        print(f"  {st.name:<4} {st.title:<16} {done:>3}/{len(items):<3} {out_dir / st.out}")
    print(f"남은 1차 호출: 제품 {need}개분")
    return need


def git_head():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def append_meta(out_dir, entry):
    path = out_dir / "run_meta.json"
    meta = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"experiment": "EXP-005", "runs": []}
    meta["runs"].append(entry)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def spend(budget, classifier, exp, test, out_dir, ids):
    """우선순위대로 예산만큼 돈다. (단계별 기록 목록, 멈춘 까닭 또는 None)."""
    left, report, stopped = budget, [], None
    for st in STAGES:
        if left <= 0:
            break
        items = stage_items(st, exp, test, ids)
        out = out_dir / st.out
        if not items or {i for i, _ in items} <= done_ids(out):
            continue
        before = len(run_team.read_done(out))
        engine = "clova" if st.source == "photo" else "text"
        try:
            _, failed, remaining = run_team.run_items(items, team_call(classifier, engine), out, resume=True,
                                                      limit=left, classifier=classifier)
        except SystemExit as e:
            used = written(out) - before
            report.append({"stage": st.name, "new": used, "stopped": str(e)})
            return report, str(e)
        used = written(out) - before
        left -= used
        report.append({"stage": st.name, "new": used, "failed": failed, "remaining": remaining})
        print(f"{st.name}: {used}개 돌림, 분류 실패 {len(failed)}개, 이 단계 남은 것 {remaining}개", flush=True)
        if remaining:
            break
    return report, stopped


def run_final_all(exp, test_path, out_dir, ids):
    """최종본: 사진 OCR 글자를 세 번, 시험 세트 글자 전부를 한 번. LLM을 부르지 않는다."""
    from src.final.pipeline import analyze_text

    items = photo_items(exp, ids)
    call = lambda text: analyze_text(text, ocr_engine="clova").model_dump(mode="json")  # noqa: E731
    for k in range(1, FINAL_REPEAT + 1):
        name = "final_P.jsonl" if k == 1 else f"final_P_run{k}.jsonl"
        run_team.run_items(items, call, out_dir / name)
    code = run_final.main(["--gold", str(test_path), "--out", str(out_dir / "final_test.jsonl")])
    print(f"최종본: 사진 {len(items)}개 x {FINAL_REPEAT}번, 시험 세트 글자 -> {out_dir}")
    return code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="EXP-005: 크레딧 예산만큼 1차를 우선순위대로, 최종본은 전부.")
    what = ap.add_mutually_exclusive_group(required=True)
    what.add_argument("--status", action="store_true", help="진행 상황만 본다 (LLM을 부르지 않는다)")
    what.add_argument("--budget", type=int, help="이번에 1차로 돌릴 최대 제품 수 (LLM 호출 수)")
    what.add_argument("--final", action="store_true", help="최종본만 돌린다 (LLM을 부르지 않는다)")
    ap.add_argument("--label", help="run_meta.json에 남길 실행 메모 (예: 누구 키). 키 값은 적지 말 것")
    ap.add_argument("--classifier", choices=("llm", "mock"), default="llm", help="1차 분류기 (mock은 시험용)")
    ap.add_argument("--retries", type=int, default=6, help="게이트웨이 거절 시 다시 보내는 횟수")
    ap.add_argument("--exp-dir", default=str(EXP))
    ap.add_argument("--test", default=str(TEST), help="시험 세트 빈 양식 (정답이 없어도 된다)")
    ap.add_argument("--out-dir", default=str(OUT))
    args = ap.parse_args(argv)
    exp, out_dir = Path(args.exp_dir), Path(args.out_dir)
    ids = included(exp)
    if ids is None:
        print(f"멈춤: {exp / 'included.txt'}가 없다. 사진 정답 대조를 끝내고 대상 제품을 적은 뒤에 돌린다. "
              "LLM을 부르지 않았다.", file=sys.stderr)
        return 2
    try:
        test = load_gold(args.test)
    except (OSError, EvalInputError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    unknown = [i for i in ids if i not in {p.id for p in test.products}]
    if unknown:
        print(f"오류: included.txt에 시험 세트에 없는 id {len(unknown)}개 ({', '.join(unknown[:5])})", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.status:
        status(exp, test, out_dir, ids)
        return 0
    if args.final:
        return run_final_all(exp, Path(args.test), out_dir, ids)
    if args.budget <= 0:
        ap.error("--budget은 1 이상")
    classifier = run_team.load_classifier(args.classifier, args.retries)
    started = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    report, stopped = spend(args.budget, classifier, exp, test, out_dir, ids)
    append_meta(out_dir, {
        "at": started, "git_head": git_head(), "label": args.label, "budget": args.budget,
        "classifier": args.classifier, "llm_model": os.getenv("LLM_MODEL") if args.classifier == "llm" else None,
        "llm_base_host": urlparse(os.getenv("LLM_BASE_URL") or "").hostname if args.classifier == "llm" else None,
        "stages": report, "stopped": stopped,
    })
    used = sum(r["new"] for r in report)
    print(f"이번에 1차 {used}개 돌림 (예산 {args.budget}).", flush=True)
    left = status(exp, test, out_dir, ids)
    if stopped:
        print(f"멈춤: {stopped}", file=sys.stderr)
        return 1
    return 0 if left == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
