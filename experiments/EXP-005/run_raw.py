"""EXP-005: 촬영한 라벨 사진을 CLOVA로 한 번씩 읽어 raw/에 저장하고, 원재료명 칸 자동 추출 결과를 results/에 저장한다.

  python experiments/EXP-005/run_raw.py --photos data/raw/photos/exp005 --dry-run    부를 횟수만 센다
  python experiments/EXP-005/run_raw.py --photos data/raw/photos/exp005 --limit 40   CLOVA를 최대 40번 부른다
  python experiments/EXP-005/run_raw.py --from-raw                                   API 호출 없이 저장된 raw/에서 다시 추출

- 사진 폴더: <photos>/<시험 세트 id>/<순서>.jpg (예: B_test_085/1.jpg). jpg·png만 받는다. HEIC는 먼저 jpg로 바꾼다.
- raw/<id>__<순서>.json이 이미 있으면 다시 부르지 않는다(CLOVA 월 100건 한도). 키는 저장소 루트 .env의 CLOVA_URL, CLOVA_SECRET.
- 추출은 저장소의 src/ocr/clova.py(extract_label)로 한다. 제품 서버(OPENSESAME_OCR=clova)가 파서에 넘기는 글자와 같다.
- 한 제품 사진이 여러 장이면 파일 이름 순서대로 추출한 글자를 줄을 바꿔 이어 붙인다. 앱은 사진 한 장을 받으므로 그런 제품은 README에 적는다.
- results/clova_full/<id>.txt = 실험 입력, results/clova_lines/<id>.txt = 사진 속 모든 줄(정답 대조용).
- 화면에는 제품 id와 글자 수만 찍는다. 키와 응답 내용은 찍지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from src.ocr.clova import call_clova, extract_label  # noqa: E402

FORMATS = {".jpg": "jpg", ".jpeg": "jpg", ".png": "png"}


def load_env(path=ROOT / ".env"):
    """이미 있는 환경 변수는 덮어쓰지 않고, 값은 찍지 않는다."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def photo_plan(photos: Path):
    """[(id, [(raw 이름, 사진 경로)])]. 폴더 이름이 id, 사진은 파일 이름 순서."""
    plan, bad = [], []
    for folder in sorted(p for p in photos.iterdir() if p.is_dir()):
        images = sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))
        bad += [str(p) for p in images if p.suffix.lower() not in FORMATS]
        good = [p for p in images if p.suffix.lower() in FORMATS]
        if good:
            plan.append((folder.name, [(f"{folder.name}__{p.stem}", p) for p in good]))
    if bad:
        raise SystemExit(f"jpg·png가 아닌 파일 {len(bad)}개 (예: {bad[0]}). HEIC는 jpg로 바꿔 넣을 것")
    return plan


def extract(raw_paths):
    """raw 응답들 -> (실험 입력 글자, 모든 줄)."""
    texts, lines = [], []
    for path in raw_paths:
        info = extract_label(json.loads(path.read_text(encoding="utf-8")))
        if info["text"].strip():
            texts.append(info["text"])
        lines += info["lines"]
    return "\n".join(texts), "\n".join(lines)


def write_results(exp: Path, pid: str, raw_paths) -> int:
    text, lines = extract(raw_paths)
    for sub, body in (("clova_full", text), ("clova_lines", lines)):
        (exp / "results" / sub).mkdir(parents=True, exist_ok=True)
        (exp / "results" / sub / f"{pid}.txt").write_text(body, encoding="utf-8")
    return len(text)


def main(argv=None, call=call_clova, exp: Path = HERE, env_file: Path = ROOT / ".env") -> int:
    ap = argparse.ArgumentParser(description="EXP-005 사진을 CLOVA로 한 번씩 읽고 원재료명 칸을 뽑는다.")
    ap.add_argument("--photos", help="사진 폴더 (<photos>/<id>/<순서>.jpg)")
    ap.add_argument("--limit", type=int, help="이번에 CLOVA를 부를 최대 횟수")
    ap.add_argument("--dry-run", action="store_true", help="부를 횟수만 센다")
    ap.add_argument("--from-raw", action="store_true", help="API 호출 없이 raw/에서 다시 추출")
    args = ap.parse_args(argv)
    raw_dir = exp / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if args.from_raw:
        groups = {}
        for path in sorted(raw_dir.glob("*.json")):
            groups.setdefault(path.stem.split("__")[0], []).append(path)
        for pid, paths in groups.items():
            print(pid, write_results(exp, pid, paths), "자")
        return 0
    if not args.photos:
        ap.error("--photos 또는 --from-raw가 필요하다")
    plan = photo_plan(Path(args.photos))
    todo = [(name, img) for _, shots in plan for name, img in shots if not (raw_dir / f"{name}.json").exists()]
    print(f"제품 {len(plan)}개, 사진 {sum(len(s) for _, s in plan)}장, 새로 읽을 사진 {len(todo)}장")
    if args.dry_run:
        return 0
    if args.limit is not None:
        todo = todo[:max(args.limit, 0)]
    if todo:
        load_env(env_file)
        url, secret = os.environ.get("CLOVA_URL"), os.environ.get("CLOVA_SECRET")
        if not url or not secret:
            print("멈춤: 저장소 루트 .env에 CLOVA_URL, CLOVA_SECRET이 필요하다. CLOVA를 부르지 않았다.", file=sys.stderr)
            return 2
        for name, img in todo:
            try:
                raw = call(img.read_bytes(), FORMATS[img.suffix.lower()], url, secret)
            except (OSError, RuntimeError) as e:      # 응답 내용은 찍지 않는다
                print(f"멈춤: {name}에서 CLOVA 실패 ({type(e).__name__}). 다시 실행하면 이 사진부터 읽는다.", file=sys.stderr)
                return 1
            (raw_dir / f"{name}.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    missing = 0
    for pid, shots in plan:
        paths = [raw_dir / f"{name}.json" for name, _ in shots]
        if all(p.exists() for p in paths):
            print(pid, write_results(exp, pid, paths), "자")
        else:
            missing += 1
    if missing:
        print(f"아직 읽지 않은 사진이 있는 제품 {missing}개. 다시 실행하면 이어서 읽는다.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
