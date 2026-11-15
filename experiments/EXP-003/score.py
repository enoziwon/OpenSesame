"""EXP-003 표의 수치를 계산한다. API 호출 없음.

비교 1 (원재료명 칸만 잘라 입력): results/<엔진>/pXX.txt 와 gold/pXX.txt
  - CER(글자 가중) = 10장의 편집 거리 합 / 정답 글자 수 합 (띄어쓰기·줄바꿈 제외)
  - 상세페이지 4장(p01–p04) / 휴대폰 사진 6장(p05–p10)
  - 괄호 구조 일치: 괄호만 뽑은 순서가 정답과 같은 사진 수
  - 괄호 깊이 일치: 괄호 종류 무시, 열고 닫힌 순서만 비교
비교 2 (사진 전체 입력): raw/pXX.json 을 저장소의 src/ocr/clova.py 로 추출한 결과와 정답 (항목명 제외)

실행: python score.py
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
from ocr_eval import edit_distance, norm  # noqa: E402
from src.ocr.clova import extract_label  # noqa: E402

OPEN, CLOSE = set("([{（［｛"), set(")]}）］｝")
IDS = [f"p{i:02d}" for i in range(1, 11)]
DETAIL, PHOTO = IDS[:4], IDS[4:]
ENGINES = ["tesseract", "tesseract_2x", "easyocr", "easyocr_2x", "google", "clova"]
gold = {k: (HERE / "gold" / f"{k}.txt").read_text(encoding="utf-8") for k in IDS}


def bseq(t):
    return "".join(c for c in norm(t) if c in OPEN | CLOSE)


def depth(t):
    return "".join("(" if c in OPEN else ")" for c in bseq(t))


def micro(pairs):
    e = n = 0
    for g, p in pairs:
        g, p = norm(g), norm(p)
        e += edit_distance(g, p)
        n += len(g)
    return 100 * e / max(1, n)


def cer(g, p):
    return 100 * edit_distance(norm(g), norm(p)) / max(1, len(norm(g)))


print("## 비교 1 (원재료명 칸만 입력)")
print("| 엔진 | CER(글자 가중) | 상세페이지 4장 | 휴대폰 사진 6장 | 괄호 구조 일치 | 괄호 깊이 일치 |")
print("|---|---|---|---|---|---|")
per_image = {}
for eng in ENGINES:
    pred = {k: (HERE / "results" / eng / f"{k}.txt").read_text(encoding="utf-8") for k in IDS}
    per_image[eng] = {k: cer(gold[k], pred[k]) for k in IDS}
    print(f"| {eng} | {micro([(gold[k], pred[k]) for k in IDS]):.1f}% "
          f"| {micro([(gold[k], pred[k]) for k in DETAIL]):.1f}% "
          f"| {micro([(gold[k], pred[k]) for k in PHOTO]):.1f}% "
          f"| {sum(bseq(gold[k]) == bseq(pred[k]) for k in IDS)}/10 "
          f"| {sum(depth(gold[k]) == depth(pred[k]) for k in IDS)}/10 |")

print("\n※ tesseract·easyocr 의 p08 결과는 예전 잘라 낸 칸(면 원료만)으로 읽은 것이라 지금 정답과 맞지 않아 높게 나온다.")
print("  EXP-003 표의 오픈소스 행(†)은 예전 p08 정답 기준 값이다.")
print("\n사진별 CER")
print("| ID | " + " | ".join(ENGINES) + " |")
print("|---|" + "---|" * len(ENGINES))
for k in IDS:
    print(f"| {k} | " + " | ".join(f"{per_image[e][k]:.0f}%" for e in ENGINES) + " |")

print("\n## 비교 2 (사진 전체 입력 → 원재료명 칸 자동 추출, CLOVA)")
strip = lambda t: re.sub(r"^\s*(원재료명|원료명)(\s*및\s*함량)?", "", t)
pairs = []
for k in IDS:
    raw = json.loads((HERE / "raw" / f"{k}.json").read_text(encoding="utf-8"))
    pairs.append((strip(gold[k]), extract_label(raw)["text"]))
print(" ".join(f"{k}:{cer(g, p):.1f}%" for k, (g, p) in zip(IDS, pairs)))
print(f"전체(글자 가중) {micro(pairs):.1f}%")
