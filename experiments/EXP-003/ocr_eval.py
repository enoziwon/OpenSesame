"""OCR 후보 비교표 만들기.

폴더 구조:
  gold/IMG01.txt ...                 사람이 직접 옮긴 원재료명 (정답, 10장)
  results/<엔진이름>/IMG01.txt ...    각 OCR 엔진이 읽은 원재료명
  results/<엔진이름>/meta.json        (선택) {"seconds": {"IMG01": 1.2, ...}, "cost": "1,000건당 ○원"}

실행: python ocr_eval.py  ->  비교표(마크다운) 출력 + ocr_compare.csv 저장
※ CER은 사진별 단순 평균이고 항목명까지 센다. EXP-003 표의 수치는 score.py 로 계산한다.
"""
import csv
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # 저장소 루트
from src.parser.core import check_brackets, OPEN_TO_CLOSE, CLOSERS  # noqa: E402

BRACKETS = set(OPEN_TO_CLOSE) | CLOSERS


def norm(t: str) -> str:
    t = t.replace("（", "(").replace("）", ")").replace("［", "[").replace("］", "]").replace("，", ",")
    return re.sub(r"\s+", "", t)


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(gold: str, pred: str) -> float:
    g, p = norm(gold), norm(pred)
    return edit_distance(g, p) / max(1, len(g))


def bracket_seq(t: str) -> str:
    return "".join(ch for ch in norm(t) if ch in BRACKETS)


def main(root="."):
    root = Path(root)
    gold = {p.stem: p.read_text(encoding="utf-8") for p in sorted((root / "gold").glob("*.txt"))}
    if not gold:
        sys.exit("gold/ 폴더에 정답 텍스트가 없습니다.")
    rows = []
    for eng_dir in sorted(p for p in (root / "results").iterdir() if p.is_dir()):
        meta = {}
        if (eng_dir / "meta.json").exists():
            meta = json.loads((eng_dir / "meta.json").read_text(encoding="utf-8"))
        cers, br_ok, br_same, secs, missing = [], 0, 0, [], 0
        for img, g in gold.items():
            f = eng_dir / f"{img}.txt"
            if not f.exists():
                missing += 1
                continue
            p = f.read_text(encoding="utf-8")
            cers.append(cer(g, p))
            br_ok += check_brackets(p)
            br_same += bracket_seq(p) == bracket_seq(g)
            if img in meta.get("seconds", {}):
                secs.append(meta["seconds"][img])
        n = len(cers)
        rows.append({
            "엔진": eng_dir.name,
            "처리 장수": f"{n}/{len(gold)}",
            "글자 오류율(CER)": f"{100 * sum(cers) / n:.1f}%" if n else "-",
            "최악 CER": f"{100 * max(cers):.1f}%" if n else "-",
            "괄호 짝 맞음": f"{br_ok}/{n}",
            "괄호 구조 정답과 동일": f"{br_same}/{n}",
            "평균 시간(초)": f"{sum(secs) / len(secs):.2f}" if secs else "-",
            "비용": meta.get("cost", "-"),
        })
    cols = list(rows[0].keys())
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join(r[c] for c in cols) + " |")
    with open(root / "ocr_compare.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
