"""CLOVA OCR(General) 엔진 + 원재료명 칸 추출.

담당: 김민재. 사진 10장 비교 결과는 experiments/EXP-003-ocr-compare.md.
처리 순서
  1) CLOVA 호출 -> 글자 덩어리(field)와 좌표, CLOVA가 끊어 준 줄(lineBreak)
  2) 줄 단위(segment)로 묶는다. 칸(열)이 다르면 줄도 따로 나온다.
  3) '원재료명/원료명' 항목명을 찾고, 그 내용 칸만 위아래로 모은다.
     다른 항목명(내용량, 소비기한 ...), '·' 안내문, 표의 다른 행이 나오면 멈춘다. '... 함유' 줄에서 끝.
  4) 줄바꿈으로 끊긴 단어를 잇는다 (고 / 추가루 -> 고추가루)
  '같은 제조시설'/'혼입 가능' 문장은 따로 뽑는다 (extract_label 결과의 facility).
환경변수: CLOVA_SECRET, CLOVA_URL (.env, 커밋 금지)
"""
from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
import uuid

START_RE = re.compile(r"^[\s·•*ㆍ\-]*(원\s*재\s*료\s*명|원\s*료\s*명|원\s*재\s*료)(\s*및\s*함\s*량)?\s*[:：]?")
# 원재료명 다음에 오는 표시사항 항목명들 (이 줄이 시작되면 원재료명 끝)
STOP_WORDS = [
    "내용량", "중량", "유통기한", "소비기한", "품질유지기한", "보관방법", "보관상", "품목보고번호", "품목제조보고",
    "영양정보", "영양성분", "제조원", "제조사", "판매원", "판매처", "수입원", "유통전문판매원", "소재지", "업소명",
    "포장재질", "반품", "교환", "주의사항", "부정불량", "식품유형", "식품의 유형", "제품명", "원산지표시",
]
STOP_RE = re.compile(r"^\s*(" + "|".join(re.escape(w) for w in STOP_WORDS) + r")")
FACILITY_RE = re.compile(r"(같은|동일한?)\s*(제조\s*)?(시설|공장|라인)|혼\s*입|혼\s*$")
ALLERGEN_TAIL_RE = re.compile(r"함\s*유\s*[)\]]?\s*[.·]?\s*$")


# ---------- 1) CLOVA 호출 ----------
def call_clova(image_bytes: bytes, fmt: str, url: str, secret: str, lang: str = "ko") -> dict:
    body = {
        "version": "V2", "requestId": str(uuid.uuid4()), "timestamp": int(time.time() * 1000), "lang": lang,
        "images": [{"format": fmt, "name": "label", "data": base64.b64encode(image_bytes).decode()}],
    }
    req = urllib.request.Request(url, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "X-OCR-SECRET": secret})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"CLOVA 오류 {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")


# ---------- 2) CLOVA 줄(segment) 만들기 ----------
def _box(field):
    xs = [v.get("x", 0) for v in field["boundingPoly"]["vertices"]]
    ys = [v.get("y", 0) for v in field["boundingPoly"]["vertices"]]
    return min(xs), min(ys), max(xs), max(ys)


def segments(fields: list) -> list:
    """CLOVA가 lineBreak로 끊어 준 '한 줄' 단위. 칸(열)이 다르면 줄도 따로 나온다."""
    out, cur = [], []
    for f in fields:
        cur.append(f)
        if f.get("lineBreak"):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    segs = []
    for s in out:
        bs = [_box(f) for f in s]
        x0, y0 = min(b[0] for b in bs), min(b[1] for b in bs)
        x1, y1 = max(b[2] for b in bs), max(b[3] for b in bs)
        segs.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "h": max(1.0, y1 - y0),
                     "text": " ".join(f["inferText"] for f in s)})
    return segs


def group_lines(fields: list) -> list:
    """(호환용) 전체 텍스트를 위->아래 줄 목록으로."""
    return [s["text"] for s in sorted(segments(fields), key=lambda s: (s["y0"], s["x0"]))]


# ---------- 3) 원재료명 칸 찾기 ----------
def _xoverlap(a, b):
    return max(0.0, min(a["x1"], b["x1"]) - max(a["x0"], b["x0"]))


def _yoverlap(a, b):
    return max(0.0, min(a["y1"], b["y1"]) - max(a["y0"], b["y0"]))


def _is_stop(text):
    return bool(STOP_RE.match(re.sub(r"^[\s·•*\-ㆍ]+", "", text)))


def _facility_sentences(segs):
    """'같은 제조시설' 문장: 여러 줄에 걸치면 같은 칸의 앞뒤 줄까지 이어 붙인다."""
    out, used = [], set()
    for s in segs:
        if id(s) in used or not FACILITY_RE.search(s["text"]):
            continue
        col = sorted([o for o in segs if _xoverlap(o, s) > 0.5 * min(o["x1"] - o["x0"], s["x1"] - s["x0"])],
                     key=lambda o: o["y0"])
        i = col.index(s)
        a = i
        while (a > 0 and not re.match(r"^[\s·•※*\-ㆍ]", col[a]["text"]) and col[a]["y0"] - col[a - 1]["y1"] < 1.0 * s["h"]
               and not re.search(r"(다|요)\.?\s*$", col[a - 1]["text"]) and not ALLERGEN_TAIL_RE.search(col[a - 1]["text"])):
            a -= 1
        b = i
        while (b < len(col) - 1 and not re.search(r"(니다|습니다|있음|가능)\.?\s*$", col[b]["text"])
               and col[b + 1]["y0"] - col[b]["y1"] < 1.0 * s["h"] and b - i < 3):
            b += 1
        text = " ".join(o["text"] for o in col[a:b + 1])
        # 앞 문장 꼬리 / 뒤 문장 머리 잘라내기
        m = re.search(r"[^·•※]*?((같은|동일한?)\s*(제조\s*)?(시설|공장|라인)|혼\s*입)[^·•※]*?(니다\.?|있음\.?|가능|$)", text)
        sent = text
        if m:
            start = max(text.rfind("·", 0, m.start()), text.rfind("※", 0, m.start()), text.rfind(". ", 0, m.start()) + 1)
            sent = text[start + 1 if start >= 0 and text[start] in "·※" else max(start, 0):m.end()].strip()
        out.append(sent)
        used.update(id(o) for o in col[a:b + 1])
    return out


def extract_section(segs: list) -> dict:
    facility = _facility_sentences(segs)
    label = None
    for s in segs:
        m = START_RE.search(s["text"])
        if m:
            label, rest = s, s["text"][m.end():].strip()
            break
    if label is None:  # 원재료명 부분만 찍은 사진: 전체를 위->아래로
        body = [s for s in segs if not FACILITY_RE.search(s["text"])]
        body.sort(key=lambda s: ((s["y0"] + s["y1"]) / 2, s["x0"]))
        return {"body": [s["text"] for s in body], "facility": facility}

    others = [s for s in segs if s is not label]
    if rest:  # '원재료명 소맥분(...' 처럼 같은 줄에 내용이 이어짐 -> 그 줄이 기준
        seed, col, first_text, up = label, (label["x0"], label["x1"]), rest, False
    else:     # 항목명이 왼쪽 칸에 따로 있음 -> 오른쪽(같은 높이) 또는 바로 아래 줄이 내용
        right = [s for s in others if s["x0"] >= label["x1"] - label["h"] * 0.5 and _yoverlap(s, label) > 0]
        below = [s for s in others if s["y0"] >= label["y1"] - label["h"] * 0.3 and _xoverlap(s, label) > 0]
        if right:
            seed = min(right, key=lambda s: s["x0"] - label["x1"])
            up = True
        elif below:
            seed = min(below, key=lambda s: s["y0"])
            up = False
        else:
            return {"body": [], "facility": facility}
        col, first_text = (seed["x0"], seed["x1"]), seed["text"]
    # 내용 칸 너비: 기준 줄과 겹치는 줄들의 폭으로 넓힌다
    cx0, cx1 = col
    def in_col(s):
        w = max(1.0, s["x1"] - s["x0"])
        return _xoverlap(s, {"x0": cx0, "x1": cx1}) > 0.5 * w or (s["x0"] >= cx0 - s["h"] and s["x1"] <= cx1 + 3 * s["h"] and s["x0"] < cx1)
    cand = [s for s in others if s is not seed and in_col(s) and not FACILITY_RE.search(s["text"])]
    cand.sort(key=lambda s: s["y0"])
    picked = [seed]
    lab_parts = re.compile(r"^[\s및함량:：()]*$")

    def row_has_other_label(s):
        """같은 높이에 왼쪽 항목명 칸(label 열)에 다른 글자가 있으면 표의 다른 행"""
        if label is seed:
            return False
        for o in others:
            if o is s or o is seed or lab_parts.match(o["text"]):
                continue
            if _xoverlap(o, label) > 0 and o["x0"] < s["x0"] - o["h"] and _yoverlap(o, s) > 0.3 * min(o["h"], s["h"]):
                return True
        return False

    if label is not seed:
        picked += [o for o in others if o is not seed and o["x0"] >= seed["x1"] - seed["h"]
                   and _yoverlap(o, seed) > 0.5 * min(o["h"], seed["h"]) and ALLERGEN_TAIL_RE.search(o["text"])]
    bottom, last_h = seed["y1"], seed["h"]
    if not ALLERGEN_TAIL_RE.search(seed["text"]):
        for s in [c for c in cand if (c["y0"] + c["y1"]) / 2 > (seed["y0"] + seed["y1"]) / 2]:
            t = s["text"].strip()
            if _is_stop(t) or START_RE.match(t) or re.match(r"^[·•ㆍ※]", t) or row_has_other_label(s):
                break
            if s["y0"] - bottom > 1.2 * max(last_h, s["h"]):
                break
            picked.append(s)
            bottom, last_h = max(bottom, s["y1"]), s["h"]
            if ALLERGEN_TAIL_RE.search(t):  # '... 함유' 줄에서 원재료명 끝 (같은 행의 옆 칸은 포함)
                picked += [c for c in cand if c not in picked and _yoverlap(c, s) > 0.5 * min(c["h"], s["h"])]
                break
    if up:  # 항목명이 세로 가운데 정렬된 표: 위쪽 줄도 같은 칸이면 포함
        top = seed["y0"]
        for s in sorted([c for c in cand if (c["y0"] + c["y1"]) / 2 < (seed["y0"] + seed["y1"]) / 2], key=lambda s: -s["y1"]):
            if (_is_stop(s["text"]) or top - s["y1"] > 1.2 * s["h"] or row_has_other_label(s)
                    or s["x0"] < cx0 - s["h"]):
                break
            picked.append(s)
            top = min(top, s["y0"])
    # 같은 행 오른쪽에 붙은 '○○ 함유' 표시란 (칸 폭 밖이어도 포함)
    for s in list(picked):
        for o in others:
            if (o not in picked and o["x0"] >= s["x1"] - s["h"] and o["x0"] - s["x1"] < 8 * s["h"]
                    and _yoverlap(o, s) > 0.5 * min(o["h"], s["h"]) and ALLERGEN_TAIL_RE.search(o["text"])):
                picked.append(o)
    # 줄 정렬: 세로로 절반 이상 겹치면 같은 행, 행 안에서는 왼->오
    picked.sort(key=lambda s: s["y0"])
    rows = []
    for s in picked:
        if rows and _yoverlap(rows[-1][-1], s) > 0.5 * min(rows[-1][-1]["h"], s["h"]):
            rows[-1].append(s)
        else:
            rows.append([s])
    ordered = [s for r in rows for s in sorted(r, key=lambda s: s["x0"])]
    texts = [first_text if s is seed else s["text"] for s in ordered]
    return {"body": [t for t in texts if t.strip()], "facility": facility}


# ---------- 4) 줄 잇기 ----------
def join_lines(body: list) -> str:
    out = ""
    for ln in body:
        ln = ln.strip()
        if not out:
            out = ln
        elif ALLERGEN_TAIL_RE.search(ln):           # '밀, 대두 함유' 같은 표시란 줄은 띄어서
            out += " " + ln
        elif re.search(r"[,，、)\]}]$", out) or re.match(r"^[(\[{]", ln):
            out += ln if out.endswith((",", "，", "、")) else " " + ln
        else:                                        # 단어 중간 줄바꿈: 붙인다 (고 / 추가루 -> 고추가루)
            out += ln
    out = re.sub(r"\s*,\s*", ", ", out)
    return re.sub(r"\s+", " ", out).strip()



def extract_label(raw: dict) -> dict:
    """CLOVA 응답(dict) -> {'text': 원재료명, 'facility': 같은 시설 문장, 'lines': 전체 줄}"""
    fields = raw["images"][0].get("fields", [])
    segs = segments(fields)
    sec = extract_section(segs)
    return {
        "text": join_lines(sec["body"]),
        "facility": " ".join(sec["facility"]),
        "lines": [s["text"] for s in sorted(segs, key=lambda s: (s["y0"], s["x0"]))],
    }


_FMT = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "application/pdf": "pdf", "image/tiff": "tiff"}


class ClovaOcr:
    name = "clova"

    def __init__(self, url: str, secret: str):
        self.url, self.secret = url, secret

    @classmethod
    def from_env(cls) -> "ClovaOcr":
        import os

        url, secret = os.getenv("CLOVA_URL"), os.getenv("CLOVA_SECRET")
        if not url or not secret:
            raise RuntimeError("CLOVA_URL, CLOVA_SECRET 환경변수가 필요합니다 (.env)")
        return cls(url, secret)

    def read_text(self, image: bytes, content_type: str):
        from src.common.schema import OcrResult

        raw = call_clova(image, _FMT.get(content_type, "jpg"), self.url, self.secret)
        fields = raw["images"][0].get("fields", [])
        conf = [f.get("inferConfidence") for f in fields if f.get("inferConfidence") is not None]
        info = extract_label(raw)
        return OcrResult(text=info["text"], engine=self.name, confidence=(sum(conf) / len(conf)) if conf else None)
