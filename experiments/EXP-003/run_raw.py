"""비교 2: 사진 전체를 CLOVA로 읽어 raw/ 에 저장하고, 원재료명 칸 자동 추출 결과를 results/clova_full/ 에 저장.

  python run_raw.py             imgs/ 의 사진 전체를 CLOVA로 다시 읽음 (CLOVA 무료 한도 10건 사용)
  python run_raw.py --from-raw  API 호출 없이 저장된 raw/*.json 에서 추출만 다시 함

키: 저장소 루트 .env 의 CLOVA_URL, CLOVA_SECRET. 추출 코드는 저장소의 src/ocr/clova.py.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from _env import load_env  # noqa: E402
from src.ocr.clova import call_clova, extract_label  # noqa: E402

(HERE / "raw").mkdir(exist_ok=True)
(HERE / "results" / "clova_full").mkdir(parents=True, exist_ok=True)

if "--from-raw" in sys.argv:
    keys = sorted(p.stem for p in (HERE / "raw").glob("*.json"))
else:
    load_env()
    url, secret = os.environ.get("CLOVA_URL"), os.environ.get("CLOVA_SECRET")
    if not url or not secret:
        sys.exit("저장소 루트 .env 에 CLOVA_URL, CLOVA_SECRET 이 필요합니다")
    keys = []
    for img in sorted((HERE / "imgs").glob("*.jpg")):
        raw = call_clova(img.read_bytes(), "jpg", url, secret)
        (HERE / "raw" / f"{img.stem}.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        keys.append(img.stem)

for k in keys:
    raw = json.loads((HERE / "raw" / f"{k}.json").read_text(encoding="utf-8"))
    text = extract_label(raw)["text"]
    (HERE / "results" / "clova_full" / f"{k}.txt").write_text(text, encoding="utf-8")
    print(k, len(text), "자")
