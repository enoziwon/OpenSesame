"""클라우드 OCR 실행 (비교 1: crops/ 의 원재료명 칸 이미지를 읽음).
  Google Vision : python run_cloud.py google           (키: GOOGLE_API_KEY)
  CLOVA OCR     : python run_cloud.py clova            (키: CLOVA_URL, CLOVA_SECRET)
  일부만        : python run_cloud.py clova --only p08  (무료 한도 아끼기)
키는 저장소 루트 .env 또는 환경변수에서 읽는다.
결과는 results/<엔진>/pXX.txt, meta.json 에 저장 -> python score.py 로 EXP-003 표 갱신
"""
import base64, json, os, sys, time, uuid, urllib.request, urllib.error
from _env import load_env

def post(url, body, headers):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        sys.exit(f"API 오류 {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")

def google(img):
    b = base64.b64encode(img).decode()
    r = post(f"https://vision.googleapis.com/v1/images:annotate?key={os.environ['GOOGLE_API_KEY']}",
             {"requests": [{"image": {"content": b}, "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                            "imageContext": {"languageHints": ["ko"]}}]}, {})
    return r["responses"][0].get("fullTextAnnotation", {}).get("text", "")

def clova(img):
    body = {"version": "V2", "requestId": str(uuid.uuid4()), "timestamp": int(time.time() * 1000),
            "images": [{"format": "png", "name": "x", "data": base64.b64encode(img).decode()}]}
    r = post(os.environ["CLOVA_URL"], body, {"X-OCR-SECRET": os.environ["CLOVA_SECRET"]})
    out = []
    for f in r["images"][0]["fields"]:
        out.append(f["inferText"] + ("\n" if f.get("lineBreak") else " "))
    return "".join(out)

if __name__ == "__main__":
    load_env()
    eng = sys.argv[1]; fn = {"google": google, "clova": clova}[eng]
    only = sys.argv[sys.argv.index("--only") + 1:] if "--only" in sys.argv else None
    src = "crops"
    os.makedirs(f"results/{eng}", exist_ok=True)
    meta_path = f"results/{eng}/meta.json"
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    T = meta.get("seconds", {})
    for f in sorted(os.listdir(src)):
        k = f.rsplit(".", 1)[0]
        if only and k not in only:
            continue
        t = time.time()
        txt = fn(open(os.path.join(src, f), "rb").read()); T[k] = round(time.time() - t, 2)
        open(f"results/{eng}/{k}.txt", "w", encoding="utf-8").write(txt); print(k, T[k])
    cost = meta.get("cost") or {"google": "월 1,000건 무료", "clova": "월 100건 무료(General)"}[eng]
    json.dump({"seconds": T, "cost": cost}, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False)
