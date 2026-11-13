"""정답지 표본을 뽑는다: HACCP 2026 자료에서 개발 60개 / 시험 140개 (정답지 가이드 8장 1번).

    python tools/sample_gold.py --old-csv <2020년 haccp.csv>        # 결과는 data/raw/gold/

뽑는 규칙은 아래 RULES에 적고 sample_manifest.json에도 그대로 남긴다. 시드가 같으면 결과도 같다.
시험 세트 내용은 찍지 않는다. 표준 출력에는 건수만 나온다. 결과 폴더(data/raw/)는 git에 올라가지 않는다.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))            # python tools/sample_gold.py 로 돌려도 src를 찾게 한다

from src.final.parser import parse_label  # noqa: E402

TYPES = ("snack", "sauce_seasoning", "instant", "frozen", "beverage_dairy", "other")
MIN_INGREDIENTS = 3
REASONS = ("품목보고번호 없음·중복", "원재료 없음", "파서 실패", "원재료 3개 미만", "표시란 확인 불가", "식품 아님",
           "제조사 확인 불가")
NOTE_FIELDS = (("제품명", "prdlstNm"), ("식품유형", "prdkind"), ("제조사", "manufacture"), ("표시란 원문", "allergy"))

# 식품유형 -> product_type. 위에서부터 처음 맞는 줄을 쓴다(띄어쓰기는 지우고 본다). 어디에도 없으면 other.
TYPE_KEYWORDS = (
    ("frozen", ("냉동", "만두")),
    ("beverage_dairy", ("음료", "주스", "커피", "두유", "침출차", "액상차", "고형차", "홍차", "다류", "탄산수",
                        "가공유", "발효유", "치즈", "탁주", "소주", "리큐르")),
    ("instant", ("즉석", "즉섭", "편의식", "간편", "면", "국수", "수제비", "파스타")),
    ("sauce_seasoning", ("소스", "드레싱", "마요네즈", "케첩", "조미식품", "복합조미", "고추장", "된장", "간장", "춘장",
                         "청국장", "혼합장", "장류", "카레", "커리", "고춧가루", "향신료", "식초", "소금", "천일염", "젓",
                         "육수", "기름", "유지", "식용유", "쇼트닝", "마가린", "향미유", "올리브유", "카놀라유", "해바라기유",
                         "대두유", "현미유", "옥배유", "채종유", "유채유", "야자유", "설탕", "물엿", "올리고당", "과당", "포도당")),
    ("snack", ("과자", "캔디", "켄디", "사탕", "젤리", "양갱", "초콜릿", "초콜렛", "코코아", "껌", "빵", "떡", "케이크", "케익",
               "카스텔라", "비스킷", "쿠키", "크래커", "한과", "강정", "스낵", "빙과", "아이스크림", "아이스밀크", "샤베트",
               "디저트", "땅콩", "견과", "시리얼")),
)

# 제조사 묶기: 'F1)' 머리말, 법인 표기, 주소(시·도 이름부터), 전화번호, 공장 이름을 떼고 글자만 남긴다.
PROVINCES = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남",
             "전북", "전남", "경북", "경남", "제주", "충청북", "충청남", "전라북", "전라남", "경상북", "경상남")
ADDR_RE = re.compile(r"^(?:%s)(?:특별시|광역시|특별자치시|특별자치도|도|시)?$" % "|".join(PROVINCES))
PHONE_RE = re.compile(r"(?:tel|전화)|\d{2,4}\s*[)\-]\s*\d{3,4}", re.I)
LEGAL_RE = re.compile(r"\(주\)|㈜|\(유\)|\(합\)|\(재\)|\(사\)|주식회사|유한회사|유한책임회사|합자회사"
                      r"|농업회사법인|영농조합법인|어업회사법인|협동조합법인")
HEAD_RE = re.compile(r"^\s*(?:\(?\s*F\s*\d\s*\)?\s*[.:\-)]?|제조원|제조사|제조업소|제조)\s*[:：]?\s*", re.I)
FACTORY_RE = re.compile(r"(?:[가-힣]{2}|제?\d+)공장$")
UNKNOWN_MAKER = "(알수없음)"          # 제조사 칸이 '알수없음'이거나 주소뿐인 것. 표본에서 뺀다

RULES = (
    "거르기(차례대로): 품목보고번호 없음·중복, 원재료 없음, 파서 실패, 맨 위 원재료 3개 미만, 표시란 확인 불가, "
    "식품 아님, 제조사 확인 불가. 2020년 자료와 겹쳐도 남긴다",
    "층: 식품유형 낱말 표(TYPE_KEYWORDS)로 product_type 여섯 가지. 200개에서 층마다 20개 이상, 나머지는 후보 비중대로",
    "개발 층별 개수는 전체 층별 개수를 60에 비례해 나눈다(최대 나머지 방식). 시험은 그 나머지",
    "시험 = 새 제품(in_2020 거짓) 30개(못 채우면 있는 만큼) + 그 밖(in_2020 참)에서 층별 나머지",
    "새 제품을 낸 제조사는 모두 시험 쪽. 개발은 in_2020 참인 제품에서만, 시험 쪽 제조사를 빼고 뽑는다",
    "제조사 열쇠(maker_key: F1·법인·주소·전화·공장 이름을 뗌) 단위로 나눈다. 같은 열쇠가 양쪽에 없고, 한 열쇠에서 최대 3개",
    "heldout_ids_*.txt: 그 세트에 든 제조사가 만든 모든 제품의 품목보고번호(2026 JSONL + 2020 CSV, "
    "2020 행의 제조사로 못 이으면 같은 번호의 2026 제조사)",
    "gold_ids.txt: 1~60번째 줄은 개발, 그 뒤 140줄은 시험(B_dev_001…, B_test_001… 순서)",
)

# 뽑는 크기와 시드. 시험 세트는 total - dev개다
Settings = collections.namedtuple("Settings", "seed total dev new_in_test min_per_type max_per_maker",
                                  defaults=(20261113, 200, 60, 30, 20, 3))
# 후보 하나: 품목보고번호, product_type, 제조사 열쇠, 2020년 자료에 있는가, 파서가 읽은 표시란 항목, 원본 레코드
Candidate = collections.namedtuple("Candidate", "no ptype maker in_2020 declared item")
# 뽑은 결과: 개발, 시험, 층별 전체 개수, 새 제품을 낸 제조사(모두 시험 쪽)
Sample = collections.namedtuple("Sample", "dev test alloc new_makers")


def field(item: dict, key: str) -> str:
    value = item.get(key) or ""
    if not isinstance(value, str):
        raise ValueError(f"품목보고번호 {item.get('prdlstReportNo')}의 {key} 칸이 글자가 아니다")
    return value


def maker_key(text: str) -> str:
    """제조사 칸 -> 묶는 열쇠. 예: '매일유업㈜상하공장 전라북도 고창군 ...' -> '매일유업'"""
    s = HEAD_RE.sub("", (text or "").strip())
    s = re.split(r"[,/]|\(?F\d", s)[0]                  # 공장·업체가 여럿이면 첫째만
    m = PHONE_RE.search(s)
    if m:
        s = s[:m.start()]
    words = [w for w in re.split(r"[\s\-:：]+", LEGAL_RE.sub(" ", s)) if w]
    for i, w in enumerate(words):
        if ADDR_RE.match(w):
            words = words[:i]
            break
    words = [w for i, w in enumerate(words) if i == 0 or not w.endswith("공장")]
    name = re.sub(r"[^0-9A-Za-z가-힣]", "", "".join(words)).lower()
    cut = FACTORY_RE.sub("", name)                       # '동원fb정읍공장' -> '동원fb'
    name = cut if len(cut) >= 2 else name
    return name if name and name != "알수없음" else UNKNOWN_MAKER


def product_type(kind: str) -> str:
    k = re.sub(r"\s+", "", kind or "")
    for ptype, words in TYPE_KEYWORDS:
        if any(w in k for w in words):
            return ptype
    return "other"


def read_items(path: Path) -> List[dict]:
    """HACCP JSONL을 읽는다. 줄마다 객체여야 하고 품목보고번호가 글자여야 한다."""
    items = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path.name} {n}번째 줄이 JSON이 아니다 ({e.msg})") from e
            if not isinstance(item, dict) or not isinstance(item.get("prdlstReportNo"), str):
                raise ValueError(f"{path.name} {n}번째 줄에 글자로 된 prdlstReportNo가 없다")
            items.append(item)
    return items


def read_old(path: Path) -> Dict[str, set]:
    """2020년 CSV -> {품목보고번호: 제조사 열쇠 모음}. 내려받은 파일이라 자료로만 읽는다."""
    out = collections.defaultdict(set)
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = {c.strip().lower(): c for c in reader.fieldnames or []}
        if "prdlstreportno" not in cols:
            raise ValueError(f"{path.name}에 prdlstreportno 칸이 없다")
        maker_col = cols.get("manufacture")
        for row in reader:
            no = (row.get(cols["prdlstreportno"]) or "").strip()
            if no:
                out[no].add(maker_key(row.get(maker_col) or "") if maker_col else UNKNOWN_MAKER)
    return dict(out)


def check(item: dict):
    """(거를 이유 또는 None, 파서 결과). 이유는 REASONS 순서대로 처음 걸린 것 하나다."""
    raw = field(item, "rawmtrl")
    if not raw.strip():
        return "원재료 없음", None
    try:
        parsed = parse_label(ingredients=raw, declaration=field(item, "allergy"))
    except (TypeError, ValueError):
        return "파서 실패", None
    top = [m for m in parsed.mentions() if m[1] == 0]    # 맨 위 원재료. 면·스프 머리말은 풀어서 센다
    if not top:
        return "파서 실패", None
    if len(top) < MIN_INGREDIENTS:
        return "원재료 3개 미만", None
    if parsed.declaration_text is None:
        return "표시란 확인 불가", None
    if field(item, "productGb") != "식품":
        return "식품 아님", None
    if maker_key(field(item, "manufacture")) == UNKNOWN_MAKER:
        return "제조사 확인 불가", None                  # 제조사 단위로 나눌 수 없다
    return None, parsed


def build_pool(items: List[dict], old: Dict[str, set]) -> Tuple[List[Candidate], Dict[str, int]]:
    """거르기를 차례로 적용해 후보를 만든다. 단계별로 빠진 수를 함께 돌려준다."""
    counts = collections.Counter()
    seen = set()
    pool = []
    for item in items:
        no = item["prdlstReportNo"].strip()
        if not no or no in seen:
            counts["품목보고번호 없음·중복"] += 1
            continue
        seen.add(no)
        reason, parsed = check(item)
        if reason:
            counts[reason] += 1
            continue
        pool.append(Candidate(no, product_type(field(item, "prdkind")), maker_key(field(item, "manufacture")),
                              no in old, tuple(parsed.declared), item))
    return pool, {r: counts[r] for r in REASONS}


def largest_remainder(weights: Dict[str, int], total: int) -> Dict[str, int]:
    """total을 weights 비율대로 정수로 나눈다(최대 나머지 방식). 나머지가 같으면 이름 순."""
    whole = sum(weights.values())
    if whole <= 0:
        raise ValueError("나눌 비율이 없다")
    exact = {k: total * w / whole for k, w in weights.items()}
    out = {k: int(v) for k, v in exact.items()}
    for k in sorted(exact, key=lambda k: (out[k] - exact[k], k))[:total - sum(out.values())]:
        out[k] += 1
    return out


def allocate(sizes: Dict[str, int], s: Settings) -> Dict[str, int]:
    """층별 개수: 층마다 min_per_type 이상, 나머지는 후보 비중대로."""
    if any(sizes.get(t, 0) < s.min_per_type for t in TYPES) or s.min_per_type * len(TYPES) > s.total:
        raise ValueError(f"층마다 {s.min_per_type}개를 채울 후보가 없다: {dict(sizes)}")
    fixed: Dict[str, int] = {}
    while True:
        free = {t: sizes[t] for t in TYPES if t not in fixed}
        share = largest_remainder(free, s.total - s.min_per_type * len(fixed))
        low = [t for t in free if share[t] < s.min_per_type]
        if not low:
            return {t: fixed.get(t, share.get(t, 0)) for t in TYPES}
        fixed.update({t: s.min_per_type for t in low})


def by_type(cands) -> Dict[str, int]:
    counts = collections.Counter(c.ptype for c in cands)
    return {t: counts[t] for t in TYPES}


def pick(cands, need: Dict[str, int], used: collections.Counter, rng: random.Random, s: Settings,
         limit: Optional[int] = None, what: str = "") -> List[Candidate]:
    """후보를 섞어 앞에서부터 고른다. 층마다 need까지, 제조사마다 max_per_maker까지(used에 누적).
    what을 주면 need를 다 채우지 못할 때 멈춘다."""
    order = sorted(cands, key=lambda c: c.no)
    rng.shuffle(order)
    left = dict(need)
    chosen = []
    for c in order:
        if limit is not None and len(chosen) >= limit:
            break
        if left.get(c.ptype, 0) > 0 and used[c.maker] < s.max_per_maker:
            chosen.append(c)
            used[c.maker] += 1
            left[c.ptype] -= 1
    short = {t: n for t, n in left.items() if n > 0}
    if what and short:
        raise ValueError(f"{what}의 층별 개수가 모자란다: {short} (제조사 상한 때문일 수 있다)")
    return chosen


def draw(pool: List[Candidate], s: Settings) -> Sample:
    """시험(새 제품 먼저, 그다음 그 밖) -> 개발 순서로 뽑는다. 같은 시드면 같은 결과다."""
    rng = random.Random(s.seed)
    alloc = allocate(by_type(pool), s)
    dev_need = largest_remainder(alloc, s.dev)
    test_need = {t: alloc[t] - dev_need[t] for t in TYPES}
    used = collections.Counter()
    new = [c for c in pool if not c.in_2020]
    new_makers = frozenset(c.maker for c in new)
    test_new = pick(new, test_need, used, rng, s, limit=s.new_in_test)
    rest_need = {t: test_need[t] - n for t, n in by_type(test_new).items()}
    old = [c for c in pool if c.in_2020]
    test_rest = pick(old, rest_need, used, rng, s, what="시험 세트")
    test_makers = new_makers | {c.maker for c in test_rest}
    dev = pick([c for c in old if c.maker not in test_makers], dev_need, used, rng, s, what="개발 세트")
    test = sorted(test_new + test_rest, key=lambda c: c.no)
    dev = sorted(dev, key=lambda c: c.no)
    rng.shuffle(test)                                     # 새 제품이 앞에 몰리지 않게 섞는다
    rng.shuffle(dev)
    return Sample(tuple(dev), tuple(test), alloc, new_makers)


def blank_record(c: Candidate, rid: str) -> dict:
    """스키마 레코드 꼴. annotations만 비어 있다. notes 네 줄은 라벨링 도구가 읽는 제품 정보다."""
    item = c.item
    images = [u.strip() for u in (field(item, "imgurl1"), field(item, "imgurl2")) if u.strip()]
    notes = "\n".join(f"{label}: {' '.join(field(item, key).split())}" for label, key in NOTE_FIELDS)
    return {"id": rid, "annotator": "", "product_type": c.ptype, "package_material": "other",
            "report_number": c.no, "image_files": images, "ingredients_text": field(item, "rawmtrl"),
            "kr_declared_allergens": list(c.declared), "annotations": [], "notes": notes}


def heldout(makers: frozenset, now_keys: Dict[str, str], old: Dict[str, set]) -> Tuple[List[str], int]:
    """그 제조사들이 만든 모든 제품의 품목보고번호와, 2026 제조사를 빌려 이은 2020 번호 수."""
    makers = makers - {UNKNOWN_MAKER}                     # 제조사 미상 묶음은 넣지 않는다
    out = {no for no, key in now_keys.items() if key in makers}
    borrowed = 0
    for no, keys in old.items():
        if keys & makers:
            out.add(no)
        elif now_keys.get(no) in makers:                  # 2020 행의 제조사로 못 이으면 같은 번호의 2026 제조사
            out.add(no)
            borrowed += 1
    return sorted(out), borrowed


def ids_text(nos) -> str:
    return "".join(f"{n}\n" for n in nos)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jsonl(records) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def make_files(sample: Sample, now_keys: Dict[str, str], old: Dict[str, set]) -> Tuple[Dict[str, str], dict]:
    """결과 파일 글자들과 목록 정보(manifest용)."""
    dev_ids = [f"B_dev_{i:03d}" for i in range(1, len(sample.dev) + 1)]
    test_ids = [f"B_test_{i:03d}" for i in range(1, len(sample.test) + 1)]
    dev_nos, test_nos = [c.no for c in sample.dev], [c.no for c in sample.test]
    held_test, borrowed_test = heldout(frozenset(c.maker for c in sample.test), now_keys, old)
    held_dev, borrowed_dev = heldout(frozenset(c.maker for c in sample.dev), now_keys, old)
    files = {
        "dev_blank.jsonl": jsonl(blank_record(c, i) for c, i in zip(sample.dev, dev_ids)),
        "test_blank.jsonl": jsonl(blank_record(c, i) for c, i in zip(sample.test, test_ids)),
        "gold_ids.txt": ids_text(dev_nos + test_nos),
        "heldout_ids_test.txt": ids_text(held_test),
        "heldout_ids_dev.txt": ids_text(held_dev),
    }
    lists = {
        "dev_ids_sha256": sha(ids_text(dev_nos).encode("utf-8")),
        "test_ids_sha256": sha(ids_text(test_nos).encode("utf-8")),
        "heldout_test": {"count": len(held_test), "borrowed_2020": borrowed_test},
        "heldout_dev": {"count": len(held_dev), "borrowed_2020": borrowed_dev},
        "in_2020": {i: c.in_2020 for i, c in zip(dev_ids + test_ids, sample.dev + sample.test)},
    }
    return files, lists


def side(cands) -> dict:
    new = [c for c in cands if not c.in_2020]
    return {"records": len(cands), "makers": len({c.maker for c in cands}), "by_type": by_type(cands),
            "new": len(new), "new_by_type": by_type(new)}


def overlap_counts(items: List[dict], old: Dict[str, set], pool, now_keys: Dict[str, str]) -> dict:
    """2020년 자료와 같은 품목보고번호인 수, 어느 쪽에서도 제조사를 알 수 없는 2020 번호 수."""
    nos = [(it["prdlstReportNo"].strip(), field(it, "productGb") == "식품") for it in items]
    unknown = {UNKNOWN_MAKER}
    return {
        "all_records": sum(1 for no, _ in nos if no in old),
        "food_records": sum(1 for no, food in nos if food and no in old),
        "food_not_in_2020": sum(1 for no, food in nos if food and no not in old),
        "pool_in_2020": sum(1 for c in pool if c.in_2020),
        "pool_new": sum(1 for c in pool if not c.in_2020),
        "unlinked_2020_numbers": sum(1 for no, keys in old.items()
                                     if keys == unknown and now_keys.get(no, UNKNOWN_MAKER) == UNKNOWN_MAKER),
    }


def write_all(out: Path, files: Dict[str, str], force: bool) -> None:
    """이미 있는 결과와 내용이 다르면 --force 없이는 멈춘다(라벨을 달기 시작한 뒤 표본이 바뀌는 것을 막는다)."""
    changed = [n for n, text in files.items()
               if (out / n).exists() and (out / n).read_text(encoding="utf-8") != text]
    if changed and not force:
        raise SystemExit(f"{out}에 내용이 다른 {', '.join(changed)}이(가) 이미 있다. 덮어쓰려면 --force")
    out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="정답지 표본 뽑기 (개발 60 / 시험 140)")
    ap.add_argument("--items", default=str(ROOT / "data" / "raw" / "haccp_20261112" / "items.jsonl"))
    ap.add_argument("--old-csv", required=True, help="2020년 HACCP CSV (prdlstreportno, manufacture 칸)")
    ap.add_argument("--out", default=str(ROOT / "data" / "raw" / "gold"))
    ap.add_argument("--seed", type=int, default=Settings().seed)
    ap.add_argument("--force", action="store_true", help="이미 있는 표본과 달라도 덮어쓴다")
    args = ap.parse_args(argv)
    s = Settings(seed=args.seed)
    items_path, old_path, out = Path(args.items), Path(args.old_csv), Path(args.out)
    items, old = read_items(items_path), read_old(old_path)
    pool, filtered = build_pool(items, old)
    sample = draw(pool, s)
    now_keys = {it["prdlstReportNo"].strip(): maker_key(field(it, "manufacture")) for it in items}
    now_keys.pop("", None)
    files, lists = make_files(sample, now_keys, old)
    write_all(out, files, args.force)
    seoul = datetime.timezone(datetime.timedelta(hours=9))
    manifest = {
        "tool": "tools/sample_gold.py", "created": datetime.datetime.now(seoul).isoformat(timespec="seconds"),
        "seed": s.seed, "settings": s._asdict(), "rules": list(RULES),
        "inputs": {"items": {"file": items_path.name, "sha256": sha(items_path.read_bytes()), "records": len(items)},
                   "old_csv": {"file": old_path.name, "sha256": sha(old_path.read_bytes()), "numbers": len(old)}},
        "filtered": filtered, "in_2020_overlap": overlap_counts(items, old, pool, now_keys),
        "pool": {**side(pool), "new_makers": len(sample.new_makers)}, "allocation": sample.alloc,
        "dev": side(sample.dev), "test": side(sample.test), "lists": lists,
        "files": {name: sha((out / name).read_bytes()) for name in files},
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=1) + "\n"
    (out / "sample_manifest.json").write_text(text, encoding="utf-8")
    counts = {k: manifest[k] for k in ("filtered", "in_2020_overlap", "pool", "allocation", "dev", "test")}
    counts["heldout"] = {"test": lists["heldout_test"]["count"], "dev": lists["heldout_dev"]["count"]}
    print(json.dumps(counts, ensure_ascii=False))       # 건수만 찍는다. 제품 내용은 찍지 않는다
    print("결과:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
