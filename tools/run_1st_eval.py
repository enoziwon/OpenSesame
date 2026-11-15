"""팀 1차(LLM 분류기)를 평가용 입력에 한 번에 돌려 응답 파일을 한 폴더에 모은다. LLM 키가 있는 사람이 돌린다.

    python tools/run_1st_eval.py                 # 사진 10장(전사·CLOVA) + 시험 세트 140개
    python tools/run_1st_eval.py --with-dev      # 개발 세트 60개도
    python tools/run_1st_eval.py --stages test   # 한 단계만 다시

- 필요한 것: 저장소 루트 .env의 LLM_PROVIDER, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (키는 찍지 않는다).
  시험·개발 세트 입력은 data/raw/gold/test_blank.jsonl, dev_blank.jsonl (정답이 없는 빈 양식, 공유 드라이브에서 받는다).
  사진 입력은 experiments/EXP-003(민재 님 PR #8)의 정답 전사와 CLOVA 결과다.
- 결과: data/raw/eval/1st_<날짜시각>/ 아래 응답 JSONL과 run_meta.json. 이 폴더를 통째로 보내 주면 채점은 받은 쪽에서 한다.
- LLM 호출 수: 사진 20번, 시험 세트 140번, 개발 세트 60번(--with-dev). 제품 하나에 한 번이다.
- 분류에 실패한 제품이 있으면 끝에 알린다. 그 단계만 --stages로 다시 돌리면 된다.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import run_photo  # noqa: E402
import run_team  # noqa: E402

GOLD = ROOT / "data" / "raw" / "gold"
STAGES = ("photo", "test", "dev")


def git_head() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def meta(out_dir: Path, results: dict) -> None:
    """실행 정보. 키는 적지 않고, 게이트웨이는 호스트 이름만 적는다."""
    info = {
        "run_at": datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        "git_head": git_head(),
        "llm_model": os.getenv("LLM_MODEL"),
        "llm_provider": os.getenv("LLM_PROVIDER"),
        "llm_base_host": urlparse(os.getenv("LLM_BASE_URL") or "").hostname,
        "llm_temperature": os.getenv("LLM_TEMPERATURE", "0"),
        "stages": results,
    }
    (out_dir / "run_meta.json").write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def run_stage(name: str, out_dir: Path) -> dict:
    start = time.perf_counter()
    if name == "photo":
        codes = [run_photo.main(["--system", "team", "--classifier", "llm", "--cond", c,
                                 "--out", str(out_dir / f"team_llm_photo_{c}.jsonl")]) for c in ("clean", "clova")]
        code = max(codes)
    else:
        gold = GOLD / f"{name}_blank.jsonl"
        if not gold.exists():
            print(f"{name}: 입력 파일이 없다 ({gold}). 이 단계는 건너뛴다.", file=sys.stderr)
            return {"status": "skipped (no input)"}
        code = run_team.main(["--gold", str(gold), "--out", str(out_dir / f"team_llm_{name}.jsonl"), "--classifier", "llm"])
    return {"status": "ok" if code == 0 else "some products failed", "seconds": round(time.perf_counter() - start, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="팀 1차(LLM)를 평가용 입력에 한 번에 돌린다.")
    ap.add_argument("--with-dev", action="store_true", help="개발 세트 60개도 돌린다")
    ap.add_argument("--stages", help="쉼표로 고른 단계만 (photo,test,dev)")
    ap.add_argument("--out-dir", help="결과 폴더 (기본 data/raw/eval/1st_<날짜시각>)")
    args = ap.parse_args(argv)
    run_team.load_dotenv(ROOT / ".env")
    missing = [k for k in ("LLM_API_KEY", "LLM_MODEL") if not os.getenv(k)]
    if missing:
        print(f"멈춤: .env에 {', '.join(missing)}이(가) 없다. LLM을 부르지 않았다.", file=sys.stderr)
        return 2
    stages = args.stages.split(",") if args.stages else (["photo", "test"] + (["dev"] if args.with_dev else []))
    bad = [s for s in stages if s not in STAGES]
    if bad:
        ap.error(f"모르는 단계: {bad}")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "data" / "raw" / "eval" / f"1st_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for name in stages:
        print(f"== {name}", flush=True)
        results[name] = run_stage(name, out_dir)
        meta(out_dir, results)
    print(f"끝. 이 폴더를 보내 주세요: {out_dir}")
    failed = [s for s, r in results.items() if r["status"] != "ok"]
    if failed:
        print(f"다시 돌릴 단계: {', '.join(failed)} (python tools/run_1st_eval.py --stages {','.join(failed)} --out-dir {out_dir})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
