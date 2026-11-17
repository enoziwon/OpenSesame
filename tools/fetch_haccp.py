"""HACCP 제품이미지·포장지표기정보 API(공공데이터포털 15033307)에서 전체 목록을 받아 쪽 단위로 저장한다.

    python tools/fetch_haccp.py                 # data/raw/haccp_<오늘>/ 에 저장. 끊기면 다시 실행해 이어받는다
    python tools/fetch_haccp.py --pages 2       # 시험 삼아 두 쪽만

- 키는 환경 변수나 .env의 DATA_GO_KR_API_KEY에서 읽는다. 키와 요청 주소는 어디에도 찍지 않는다.
- 받은 원본은 저장소에 올리지 않는다 (.gitignore의 data/raw).
- 다 받으면 items.jsonl(제품 한 줄에 하나)과 manifest.json(받은 날, 건수, 해시)을 만든다.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

URL = "https://apis.data.go.kr/B553748/CertImgListServiceV3/getCertImgListServiceV3"
ROOT = Path(__file__).resolve().parents[1]
WAITS = (10, 30, 60, 120)          # 다시 시도하기 전에 쉬는 시간(초)


def read_key() -> str:
    key = os.environ.get("DATA_GO_KR_API_KEY", "")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATA_GO_KR_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key or "여기에" in key:
        raise SystemExit("DATA_GO_KR_API_KEY가 없다. .env를 확인할 것.")
    return urllib.parse.unquote(key) if "%" in key else key      # Encoding 키로 저장했어도 받는다


def fetch_page(key: str, page: int, rows: int) -> Optional[dict]:
    """한 쪽을 받아 dict로 돌려준다. 끝내 실패하면 None."""
    query = urllib.parse.urlencode({"ServiceKey": key, "returnType": "json", "pageNo": page, "numOfRows": rows})
    for attempt, wait in enumerate((0,) + WAITS):
        if wait:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(URL + "?" + query, timeout=180) as r:
                data = json.loads(r.read().decode("utf-8"))
            if data.get("header", {}).get("resultCode") == "OK":
                return data
            reason = str(data.get("header", {}))[:120]
        except urllib.error.HTTPError as e:
            reason = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ValueError, ConnectionError) as e:
            reason = type(e).__name__                          # 주소에 키가 있으므로 오류 내용은 찍지 않는다
        print(f"  {page}쪽 {attempt + 1}번째 실패: {reason}", flush=True)
    return None


def items_of(data: dict) -> list:
    return [x.get("item", x) for x in data.get("body", {}).get("items", [])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--rows", type=int, default=100)
    ap.add_argument("--pages", type=int, default=0, help="받을 쪽 수. 0이면 끝까지")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()
    today = datetime.date.today().strftime("%Y%m%d")
    out = Path(args.out) if args.out else ROOT / "data" / "raw" / f"haccp_{today}"
    out.mkdir(parents=True, exist_ok=True)
    key = read_key()

    total, page, failed = None, 1, []
    while True:
        path = out / f"page_{page:04d}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            started = time.time()
            data = fetch_page(key, page, args.rows)
            if data is None:
                failed.append(page)
            else:
                path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                print(f"{page}쪽 {len(items_of(data))}건 {time.time() - started:.0f}초", flush=True)
            time.sleep(args.delay)
        if data is not None and total is None:
            total = int(data["body"]["totalCount"])
        last = -(-total // args.rows) if total else page          # 올림 나눗셈
        if (args.pages and page >= args.pages) or page >= last or (total is None and len(failed) >= 3):
            break
        page += 1

    if failed:
        print(f"못 받은 쪽: {failed}. 다시 실행하면 이어받는다.")
        return 1
    seen, lines = set(), []
    for path in sorted(out.glob("page_*.json")):
        for item in items_of(json.loads(path.read_text(encoding="utf-8"))):
            line = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if line not in seen:
                seen.add(line)
                lines.append(line)
    text = "\n".join(lines) + "\n"
    (out / "items.jsonl").write_text(text, encoding="utf-8")
    manifest = dict(source="data.go.kr 15033307 CertImgListServiceV3", fetched=today, total_count=total,
                    pages=page, rows_per_page=args.rows, items=len(lines),
                    sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
