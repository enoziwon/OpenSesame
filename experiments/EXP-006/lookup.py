"""EXP-006: 찍어 온 제품을 HACCP 자료(data/raw/haccp_20261112/items.jsonl, 14,653개)에서 찾는다.
목록 밖 제품의 공식 원재료명·알레르기 글자를 얻을 때 쓴다.

    python experiments/EXP-006/lookup.py 19830358021427      품목보고번호 (숫자만 본다)
    python experiments/EXP-006/lookup.py 진짬뽕               제품명 일부
    python experiments/EXP-006/lookup.py 진짬뽕 --show        원재료명·알레르기 칸 글자까지

- 시험 세트 제품이면 그 id를 알린다(기존 정답을 쓴다).
- 개발 세트 제품이면 알린다. 사전을 고칠 때 본 제품이라 사진 세트에서 뺀다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ITEMS = ROOT / "data" / "raw" / "haccp_20261112" / "items.jsonl"
GOLD = ROOT / "data" / "raw" / "gold"


def digits(text) -> str:
    return re.sub(r"\D", "", str(text or ""))


def gold_index(gold_dir=GOLD) -> dict:
    """품목보고번호 -> (세트 이름, id)."""
    index = {}
    for split in ("test", "dev"):
        path = gold_dir / f"{split}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                index[digits(row.get("report_number"))] = (split, row["id"])
    return index


def find(query: str, items) -> list:
    q = digits(query)
    if len(q) >= 8 and re.fullmatch(r"[\d\s\-]+", query):          # 번호에 띄어쓰기·하이픈이 있어도 된다
        return [i for i in items if digits(i.get("prdlstReportNo")) == q]
    return [i for i in items if query in (i.get("prdlstNm") or "")]


def main(argv=None, items_path: Path = ITEMS, gold_dir: Path = GOLD) -> int:
    ap = argparse.ArgumentParser(description="찍어 온 제품을 HACCP 자료에서 찾는다.")
    ap.add_argument("query", help="품목보고번호 또는 제품명 일부")
    ap.add_argument("--show", action="store_true", help="원재료명·알레르기 칸 글자까지 찍는다")
    args = ap.parse_args(argv)
    if not items_path.exists():
        print(f"HACCP 자료가 없다: {items_path}", file=sys.stderr)
        return 2
    items = [json.loads(line) for line in items_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    hits = find(args.query, items)
    index = gold_index(gold_dir)
    for i in hits[:30]:
        where = index.get(digits(i.get("prdlstReportNo")))
        tag = {"test": f"시험 세트 {where[1]} (기존 정답)", "dev": f"개발 세트 {where[1]} (사진 세트에서 뺌)"}.get(
            where[0], "") if where else "새 제품 (정답을 새로 단다)"
        print(f"{i.get('prdlstReportNo')}  {i.get('prdlstNm')}  | {(i.get('manufacture') or '')[:20]}  | {tag}")
        if args.show:
            print(f"    원재료명: {i.get('rawmtrl')}\n    알레르기: {i.get('allergy')}")
    if len(hits) > 30:
        print(f"… {len(hits)}개 중 30개만. 품목보고번호로 찾으면 하나로 좁혀진다.")
    if not hits:
        print("HACCP 자료에 없다. 사진 글자를 옮겨 적어 정답을 단다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
