"""PaddleOCR(한국어) 실행 - 각자 PC에서 (이 작업 환경은 모델 다운로드 서버가 막혀 실행 못함)
pip install paddlepaddle paddleocr  ->  python run_paddle.py
"""
import os, time, json
from paddleocr import PaddleOCR
ocr = PaddleOCR(lang="korean", use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
os.makedirs("results/paddle", exist_ok=True); T = {}
for f in sorted(os.listdir("crops")):
    k = f.rsplit(".", 1)[0]; t = time.time()
    r = ocr.predict(os.path.join("crops", f))[0]; T[k] = round(time.time() - t, 2)
    open(f"results/paddle/{k}.txt", "w", encoding="utf-8").write("\n".join(r["rec_texts"])); print(k, T[k])
json.dump({"seconds": T, "cost": "무료(오픈소스, CPU)"}, open("results/paddle/meta.json", "w", encoding="utf-8"), ensure_ascii=False)
