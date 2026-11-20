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
import math
import re
import statistics
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
def skew_angle(fields: list) -> float:
    """글자 상자 윗변의 기울기 중앙값(라디안). 손에 들고 비스듬히 찍은 사진(썬칩 약 25도) 보정용."""
    angles = []
    for f in fields:
        v = f["boundingPoly"]["vertices"]
        dx = v[1].get("x", 0) - v[0].get("x", 0)
        dy = v[1].get("y", 0) - v[0].get("y", 0)
        if math.hypot(dx, dy) > 20:  # 너무 짧은 글자 상자는 기울기가 부정확
            angles.append(math.atan2(dy, dx))
    return statistics.median(angles) if angles else 0.0


def _box(field, cos_a=1.0, sin_a=0.0):
    """글자 상자를 (기울기만큼 되돌린 좌표에서) 축에 맞춘 사각형으로."""
    pts = [(v.get("x", 0), v.get("y", 0)) for v in field["boundingPoly"]["vertices"]]
    xs = [x * cos_a + y * sin_a for x, y in pts]
    ys = [-x * sin_a + y * cos_a for x, y in pts]
    return min(xs), min(ys), max(xs), max(ys)


def segments(fields: list) -> list:
    """CLOVA가 lineBreak로 끊어 준 '한 줄' 단위. 칸(열)이 다르면 줄도 따로 나온다.
    사진이 2도 넘게 기울어 있으면 좌표를 똑바로 돌려서 계산한다 (위아래·같은 높이 판단이 기울기에 깨지지 않게).
    """
    a = skew_angle(fields)
    cos_a, sin_a = (math.cos(a), math.sin(a)) if abs(math.degrees(a)) >= 2 else (1.0, 0.0)
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
        bs = [_box(f, cos_a, sin_a) for f in s]
        x0, y0 = min(b[0] for b in bs), min(b[1] for b in bs)
        x1, y1 = max(b[2] for b in bs), max(b[3] for b in bs)
        segs.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "h": max(1.0, y1 - y0),
                     "text": " ".join(f["inferText"] for f in s), "fields": s})
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
        return {"body": [s["text"] for s in body], "facility": facility, "found": False, "picked": body}

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
            return {"body": [], "facility": facility, "found": False, "picked": []}
        col, first_text = (seed["x0"], seed["x1"]), seed["text"]
    # 내용 칸 너비: 기준 줄과 겹치는 줄들의 폭으로 넓힌다
    cx0, cx1 = col
    def in_col(s):
        w = max(1.0, s["x1"] - s["x0"])
        return _xoverlap(s, {"x0": cx0, "x1": cx1}) > 0.5 * w or (s["x0"] >= cx0 - s["h"] and s["x1"] <= cx1 + 3 * s["h"] and s["x0"] < cx1)

    def neighbor_overhang(s):
        """오른쪽 옆 칸의 글자 조각('·마', '·소' ...)이 칸 경계에 걸친 것. 원재료명 칸의 줄이 아니다."""
        return s["x1"] > cx1 + 0.5 * s["h"] and s["x0"] > cx1 - 3 * s["h"]
    cand = [s for s in others if s is not seed and in_col(s) and not neighbor_overhang(s)
            and not FACILITY_RE.search(s["text"])]
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
    # 줄 정렬: 세로로 절반 이상 겹치고 옆으로 나란히 있으면 같은 행, 행 안에서는 왼->오.
    # 기울어진 사진은 위아래 줄의 상자가 크게 겹치므로, 가로로 포개진 줄은 다른 행으로 본다.
    def same_row(a, b):
        side_by_side = _xoverlap(a, b) < 0.5 * min(a["x1"] - a["x0"], b["x1"] - b["x0"])
        return side_by_side and _yoverlap(a, b) > 0.5 * min(a["h"], b["h"])

    picked.sort(key=lambda s: s["y0"])
    rows = []
    for s in picked:
        if rows and same_row(rows[-1][-1], s):
            rows[-1].append(s)
        else:
            rows.append([s])
    ordered = [s for r in rows for s in sorted(r, key=lambda s: s["x0"])]
    body, spaced = [], []
    for s in ordered:
        t = first_text if s is seed else s["text"]
        if t.strip():
            body.append(t)
            # 칸 왼쪽 끝에서 시작하지 않는 줄은 앞 줄에서 넘어온 단어가 아니다 (따로 떨어진 덩어리)
            spaced.append(s is not seed and s["x0"] > cx0 + 3 * s["h"])
    return {"body": body, "spaced": spaced, "facility": facility, "found": True, "picked": ordered}


# ---------- 4) 줄 잇기 ----------
def join_lines(body: list, spaced=None) -> str:
    """spaced[i]가 참이면 i번째 줄은 앞 줄과 떨어진 덩어리라 붙이지 않고 띄운다."""
    out = ""
    for i, ln in enumerate(body):
        ln = ln.strip()
        if not out:
            out = ln
        elif ALLERGEN_TAIL_RE.search(ln) or (spaced and spaced[i]):  # '밀, 대두 함유' 표시란·떨어진 덩어리는 띄어서
            out += " " + ln
        elif re.search(r"[,，、)\]}]$", out) or re.match(r"^[(\[{]", ln):
            out += ln if out.endswith((",", "，", "、")) else " " + ln
        else:                                        # 단어 중간 줄바꿈: 붙인다 (고 / 추가루 -> 고추가루)
            out += ln
    out = re.sub(r"\s*,\s*", ", ", out)
    return re.sub(r"\s+", " ", out).strip()



# ---------- 5) 한국 알레르기 표시란 다듬기 ----------
DECL_HEAD_RE = re.compile(r"(알레르기|알러지)\s*(유발)?\s*(물질|성분|식품)?\s*(표시|정보)?\s*[:：]")
# 한국 알레르기 표시란에 나오는 낱말. 제품 서버(최종본)의 파서가 표시란으로 알아보는 낱말과 같게 둔다
# (src/final/parser/zones.py 의 KR_ALLERGEN_WORDS). OCR은 1차·최종본이 같이 쓰므로 어느 파서에도 기대지 않게 따로 둔다.
KR_DECL_WORDS = frozenset({
    "알류", "난류", "가금류", "계란", "달걀", "우유", "메밀", "땅콩", "대두", "콩", "밀", "고등어", "게",
    "새우", "돼지고기", "복숭아", "토마토", "아황산류", "아황산", "아황산염", "호두", "닭고기", "쇠고기",
    "소고기", "오징어", "조개류", "조개", "굴", "전복", "홍합", "잣", "참깨", "들깨", "아몬드", "캐슈너트",
    "메추리알", "오리알",
})


def _kr_words(token: str):
    """'쇠고기돼지고기' -> ['쇠고기', '돼지고기'] 처럼 한국 표시 항목 이름으로만 나뉘면 그 목록, 아니면 None."""
    s = re.sub(r"[\s*※·]", "", token)
    best = {0: []}
    for i in range(len(s)):
        if i not in best:
            continue
        for j in range(len(s), i, -1):
            if s[i:j] in KR_DECL_WORDS and j not in best:
                best[j] = best[i] + [s[i:j]]
    return best.get(len(s)) if s else None


def _split_top_commas(text: str) -> list:
    parts, buf, depth = [], [], 0
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}" and depth:
            depth -= 1
        if ch in ",，、" and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts]


def fix_declaration(text: str) -> str:
    """끝의 '… 함유' 표시란에서 CLOVA가 빠뜨린 쉼표를 채운다 (OCR 보정).

    '쇠고기돼지고기, 닭고기, 토마토 오징어, 조개류(굴) 함유' -> '쇠고기, 돼지고기, 닭고기, 토마토, 오징어, 조개류(굴) 함유'
    오른쪽부터 한국 표시 항목 이름으로만 이루어진 덩어리만 고치고, 원재료가 나오면 멈춘다.
    """
    m = ALLERGEN_TAIL_RE.search(text)
    if not m:
        return text
    head, tail = text[: m.start()], text[m.start():]
    parts = _split_top_commas(head)
    fixed = []
    while parts:
        last = parts[-1]
        name, bracket = (last.split("(", 1) + [""])[:2]
        words = _kr_words(name)
        if words:
            fixed.insert(0, ", ".join(words) + (f"({bracket}" if bracket else ""))
            parts.pop()
            continue
        # '건미역 밀': 마지막 낱말만 표시 항목이면 그 낱말만 고치고 멈춘다
        sp = name.rstrip().rfind(" ")
        if sp > 0 and not bracket and _kr_words(name[sp + 1:]):
            parts[-1] = name[:sp] + " " + ", ".join(_kr_words(name[sp + 1:]))
        break
    if not fixed:
        return text
    return ", ".join([p for p in parts if p] + fixed) + " " + tail.lstrip()


def separate_declaration(segs: list, picked: list) -> str:
    """원재료명 칸 밖에 따로 있는 표시란('우유함유' 칸, '알레르기 유발물질: 밀, 대두')을 '밀, 대두 함유' 꼴로."""
    used = {id(s) for s in picked}
    found = []
    for s in sorted(segs, key=lambda s: (s["y0"], s["x0"])):
        t = s["text"].strip()
        if id(s) in used or FACILITY_RE.search(t):
            continue
        h = DECL_HEAD_RE.search(t)
        body = t[h.end():] if h else (t[: ALLERGEN_TAIL_RE.search(t).start()] if ALLERGEN_TAIL_RE.search(t) else None)
        if body is None:
            continue
        items = []
        for p in re.split(r"[,，、·/\s]+", re.sub(r"\([^)]*\)", "", body)):
            w = _kr_words(p) if p else []
            if w is None:
                items = []
                break
            items += w
        if items:
            found += [w for w in items if w not in found]
    return ", ".join(found) + " 함유" if found else ""


# ---------- 6) 다시 찍기 안내 ----------
RETAKE_NOT_FOUND = "원재료명 칸을 찾지 못함. 원재료명이 잘 보이게 다시 찍어 주세요."
RETAKE_CUT = "원재료명이 사진 가장자리에서 잘렸을 수 있음. 라벨 전체가 들어오게 다시 찍어 주세요."
RETAKE_BLUR = "글자가 흐릿하게 읽힘. 밝은 곳에서 초점을 맞춰 다시 찍어 주세요."


def retake_warnings(raw: dict, sec: dict) -> list:
    """원재료명 칸을 못 찾음 / 칸의 글자가 사진 가장자리에 닿음(잘림) / 칸의 글자 신뢰도가 아주 낮음."""
    if not sec["body"]:
        return [RETAKE_NOT_FOUND]
    out = [] if sec["found"] else [RETAKE_NOT_FOUND]
    info = raw["images"][0].get("convertedImageInfo") or {}
    W, H = info.get("width"), info.get("height")
    fields = [f for s in sec["picked"] for f in s.get("fields", [])]
    if W and H:
        for f in fields:
            xs = [v.get("x", 0) for v in f["boundingPoly"]["vertices"]]
            ys = [v.get("y", 0) for v in f["boundingPoly"]["vertices"]]
            # 한 글자 조각('l', '즈')은 옆 칸 글자가 걸친 것일 때가 많아 두 글자 이상만 본다
            if len(f["inferText"]) >= 2 and (min(xs) <= 2 or max(xs) >= W - 3 or max(ys) >= H - 3):
                out.append(RETAKE_CUT)
                break
    conf = [f["inferConfidence"] for f in fields if f.get("inferConfidence") is not None]
    if conf and sum(conf) / len(conf) < 0.7:
        out.append(RETAKE_BLUR)
    return out


def extract_label(raw: dict) -> dict:
    """CLOVA 응답(dict) -> 원재료명 칸과 그 주변 정보.

    text        원재료명 (끝에 붙은 '○○ 함유'까지, 빠진 쉼표 보정)
    declaration 원재료명 칸 밖에 따로 있는 표시란 ('우유 함유'). text에 이미 표시란이 있으면 빈 문자열
    facility    같은 시설 문장
    warnings    다시 찍기 안내
    """
    fields = raw["images"][0].get("fields", [])
    segs = segments(fields)
    sec = extract_section(segs)
    text = fix_declaration(join_lines(sec["body"], sec.get("spaced")))
    declaration = "" if ALLERGEN_TAIL_RE.search(text) else separate_declaration(segs, sec["picked"])
    return {
        "text": text,
        "declaration": declaration,
        "facility": " ".join(sec["facility"]),
        "warnings": retake_warnings(raw, sec),
        "lines": [s["text"] for s in sorted(segs, key=lambda s: (s["y0"], s["x0"]))],
    }


_FMT = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "application/pdf": "pdf", "image/tiff": "tiff"}


class ClovaOcr:
    """CLOVA로 사진을 읽어 원재료명(+ 따로 있는 표시란)과 다시 찍기 안내를 돌려준다.

    같은 사진을 다시 올리면 서버가 켜져 있는 동안은 CLOVA를 다시 부르지 않는다 (무료 월 100건 아끼기).
    """
    name = "clova"
    CACHE_SIZE = 64

    def __init__(self, url: str, secret: str):
        from collections import OrderedDict

        self.url, self.secret = url, secret
        self._cache: "OrderedDict[str, dict]" = OrderedDict()
        self.calls = 0  # 실제 CLOVA 호출 횟수 (확인용)

    def _raw(self, image: bytes, content_type: str) -> dict:
        import hashlib

        key = hashlib.sha256(image).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        raw = call_clova(image, _FMT.get(content_type, "jpg"), self.url, self.secret)
        self.calls += 1
        self._cache[key] = raw
        if len(self._cache) > self.CACHE_SIZE:
            self._cache.popitem(last=False)
        return raw

    @classmethod
    def from_env(cls) -> "ClovaOcr":
        import os

        url, secret = os.getenv("CLOVA_URL"), os.getenv("CLOVA_SECRET")
        if not url or not secret:
            raise RuntimeError("CLOVA_URL, CLOVA_SECRET 환경변수가 필요합니다 (.env)")
        return cls(url, secret)

    def read_text(self, image: bytes, content_type: str):
        from src.common.schema import OcrResult

        raw = self._raw(image, content_type)
        fields = raw["images"][0].get("fields", [])
        conf = [f.get("inferConfidence") for f in fields if f.get("inferConfidence") is not None]
        info = extract_label(raw)
        # 표시란이 원재료명 칸 밖에 따로 있으면 끝에 붙여서 넘긴다 (1차 파서·최종본 파서 모두 '… 함유'를 표시란으로 읽음)
        text = f"{info['text']} {info['declaration']}".strip() if info["declaration"] else info["text"]
        # 같은 시설 문장은 text에 붙이지 않고 facility 칸으로 따로 넘긴다 (1차 파서가 원재료로 읽지 않게)
        return OcrResult(text=text, engine=self.name, confidence=(sum(conf) / len(conf)) if conf else None,
                         warnings=info["warnings"], facility=info["facility"])
