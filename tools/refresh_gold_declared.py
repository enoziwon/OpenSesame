"""정답 파일의 kr_declared_allergens를 지금 파서로 다시 채운다. 표본(id와 품목보고번호)은 그대로 둔다.

    python tools/refresh_gold_declared.py --gold data/raw/gold/test_blank.jsonl            # 바뀔 건수만 본다
    python tools/refresh_gold_declared.py --gold data/raw/gold/test_blank.jsonl --write    # 파일을 고친다

파서가 표시란 낱말 읽는 법을 고친 뒤에 쓴다('밀가루'를 밀로 읽지 못하던 것 등).
표본을 다시 뽑으면 걸러지는 제품이 달라져 표본이 바뀔 수 있으므로, 뽑힌 제품은 그대로 두고 이 칸만 다시 읽는다.
화면에는 건수와 새 SHA-256만 찍는다. 원재료나 표시란 글자는 찍지 않는다(시험 세트 보호).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))            # python tools/refresh_gold_declared.py 로 돌려도 src를 찾게 한다

from src.final.parser import parse_label  # noqa: E402

DEFAULT_ITEMS = ROOT / "data" / "raw" / "haccp_20261112" / "items.jsonl"


def read_jsonl(path: Path) -> List[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path.name} {n}번째 줄이 JSON이 아니다 ({e.msg})") from e
            if not isinstance(row, dict):
                raise ValueError(f"{path.name} {n}번째 줄이 객체가 아니다")
            rows.append(row)
    return rows


def text(item: dict, key: str) -> str:
    value = item.get(key)
    return value if isinstance(value, str) else ""


def declared_now(item: dict) -> Optional[List[str]]:
    """지금 파서가 읽은 표시란 항목. 표시란을 찾지 못하면 None."""
    parsed = parse_label(ingredients=text(item, "rawmtrl"), declaration=text(item, "allergy"))
    if parsed.declaration_text is None:
        return None
    return list(parsed.declared)


def refresh(records: List[dict], items: Dict[str, dict]) -> Dict[str, int]:
    """레코드의 kr_declared_allergens를 제자리에서 고친다. 건수를 돌려준다."""
    count = {"records": len(records), "changed": 0, "same": 0, "no_item": 0, "no_box": 0}
    for rec in records:
        item = items.get(str(rec.get("report_number") or ""))
        if item is None:
            count["no_item"] += 1                 # 자료에 없는 번호: 건드리지 않는다
            continue
        new = declared_now(item)
        if new is None:
            count["no_box"] += 1                  # 새 파서가 표시란을 못 읽는다: 건드리지 않고 알린다
            continue
        if new == rec.get("kr_declared_allergens"):
            count["same"] += 1
        else:
            rec["kr_declared_allergens"] = new
            count["changed"] += 1
    return count


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="정답 파일의 kr_declared_allergens를 지금 파서로 다시 채운다")
    p.add_argument("--gold", required=True, type=Path, help="정답 JSONL (빈 표본이든 단 것이든)")
    p.add_argument("--items", type=Path, default=DEFAULT_ITEMS, help="HACCP items.jsonl")
    p.add_argument("--write", action="store_true", help="파일을 고친다. 없으면 건수만 본다")
    args = p.parse_args(argv)
    try:
        records = read_jsonl(args.gold)
        items = {text(it, "prdlstReportNo").strip(): it for it in read_jsonl(args.items)}
        count = refresh(records, items)
    except (OSError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records).encode("utf-8")
    print(json.dumps(dict(count, file=args.gold.name, sha256=hashlib.sha256(data).hexdigest(),
                          written=bool(args.write and count["changed"])), ensure_ascii=False))
    if args.write and count["changed"]:
        args.gold.write_bytes(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
