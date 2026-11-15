"""imgs/pXX.jpg 에서 원재료명 칸만 잘라 crops/pXX.png 를 만든다 (비교 1의 입력).

좌표: crops.json  {"p01": [x0, y0, x1, y1], ...}
p08 은 기울어진 사진이라 crops_mask_p08.json 의 선 아래(포장재질 칸·워터마크)를 흰색으로 지운 뒤 자른다.
사진(imgs/)은 공유 드라이브 `데이터 사진`에서 받아 넣는다 (저장소에는 올리지 않음).
실행: python make_crops.py
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
boxes = json.loads((HERE / "crops.json").read_text(encoding="utf-8"))
masks = json.loads((HERE / "crops_mask_p08.json").read_text(encoding="utf-8"))
(HERE / "crops").mkdir(exist_ok=True)

for k, box in boxes.items():
    im = Image.open(HERE / "imgs" / f"{k}.jpg").convert("RGB")
    if k in masks:
        line = [tuple(p) for p in masks[k]["white_below"]]
        ImageDraw.Draw(im).polygon(line + [(im.width, im.height), (line[0][0], im.height)], fill="white")
    im.crop(tuple(box)).save(HERE / "crops" / f"{k}.png")
    print(k, box)
