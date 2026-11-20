"""EXP-007: may contain(추정·판정 불가)이 얼마나 나오는지, 왜 드문지, '확실함' 뒤에 숨은 애매함이 있는지 잰다.

    python experiments/EXP-007/analyze.py [--facility <EXP-006 전사_조정.jsonl>]

- 정답 세트(data/raw/gold/dev.jsonl, test.jsonl, exp006_photo.jsonl): 정답 판정의 분포.
- HACCP 전체(data/raw/haccp_20261112/items.jsonl): 최종본 판정을 표시란과 함께, 표시란 없이 두 번 낸다.
  allergy 칸이 '알수없음'이거나 비었으면 표시란을 못 읽은 제품으로 둔다.
- 모르는 이름: 최종본의 이름 찾기(Resolver, 오타 맞추기 포함)로도 찾지 못한 이름(via unknown·suspect).
- LLM 보조(OPENSESAME_FINAL_FALLBACK)는 쓰지 않는다. 결과는 experiments/EXP-007/results/에 쓴다.
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from src.final.parser import parse_label  # noqa: E402
from src.final.resolve import Resolver  # noqa: E402
from src.final.verdict import judge, read_box  # noqa: E402

ALLERGENS = ("milk", "egg", "fish", "crustacean", "tree_nut", "peanut", "wheat", "soy", "sesame")
MAY = ("inferable", "undecidable")
# 한국 표시란이 다 덮지 못하는 알레르기 (가이드 4장 표). 참깨는 전혀, 나머지는 일부 종만 덮는다
NOT_FULLY_COVERED = ("sesame", "fish", "tree_nut", "crustacean")
NO_BOX_VALUES = ("", "알수없음", "없음 정보", None)
GOLD = ROOT / "data" / "raw" / "gold"
ITEMS = ROOT / "data" / "raw" / "haccp_20261112" / "items.jsonl"


def read_jsonl(path: Path) -> list:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def cell(x) -> str:
    """TSV 칸: 줄바꿈·탭을 빈칸으로 (HACCP 제품명에 줄바꿈이 섞인 것이 있다)."""
    return " ".join(str(x or "").split())


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}% ({n}/{d})" if d else "-"


# ---------- 정답 세트 ----------
def gold_stats(rows: list) -> dict:
    units = collections.Counter()
    per_allergen = collections.defaultdict(collections.Counter)
    products_may = 0
    for r in rows:
        verdicts = {a["allergen"]: a["verdict"] for a in r["annotations"]}
        products_may += any(v in MAY for v in verdicts.values())
        for allergen in ALLERGENS:
            v = verdicts.get(allergen, "absent")
            units[v] += 1
            per_allergen[allergen][v] += 1
    n = len(rows)
    return {"products": n, "products_with_may": products_may, "units": dict(units),
            "may_units": units["inferable"] + units["undecidable"],
            "per_allergen_may": {a: per_allergen[a]["inferable"] + per_allergen[a]["undecidable"] for a in ALLERGENS}}


# ---------- HACCP 전체 ----------
def judge_once(parsed, drop_box: bool):
    if drop_box:
        parsed = dataclasses.replace(parsed, declaration_text=None, declared=())
    resolver = Resolver(fuzzy=True, codes=True, fallback=None)
    j = judge(parsed, resolve=resolver.resolve)
    return j, resolver


def leaf_kinds(parsed, resolver) -> dict:
    """원재료 이름(언급)마다 모르는 이름, 속 모를 원료, 일반 향료로 나눈다."""
    out = {"unknown": [], "opaque": [], "flavor": []}
    for mention in parsed.mentions():
        name = mention[0]
        hit = resolver.resolve(name)
        if getattr(hit, "via", "") in ("unknown", "suspect"):
            out["unknown"].append(name)
        elif getattr(hit, "opaque", False):
            out["opaque"].append(name)
        elif getattr(hit, "flavor", False) and not getattr(hit, "sources", ()):
            out["flavor"].append(name)
    return out


def product_record(item: dict) -> dict:
    allergy = (item.get("allergy") or "").strip()
    declaration = None if allergy in NO_BOX_VALUES else allergy
    parsed = parse_label(ingredients=item.get("rawmtrl") or "", declaration=declaration)
    j, resolver = judge_once(parsed, drop_box=False)
    kinds = leaf_kinds(parsed, resolver)
    j0, _ = judge_once(parsed, drop_box=True)
    verdicts = {v.allergen: (v.verdict, v.basis[0] if v.basis else "") for v in j.allergens}
    no_box = {v.allergen: v.verdict for v in j0.allergens}
    return {
        "id": item.get("prdlstReportNo"), "name": item.get("prdlstNm"), "kind": item.get("prdkind") or "",
        "box_read": j.box_read, "read_any": j.read_any, "verdicts": verdicts, "no_box": no_box,
        "unknown": kinds["unknown"], "opaque": kinds["opaque"], "flavor": kinds["flavor"],
        "missing_notes": [n for n in j.notes if n.startswith("표시란 누락 의심")],
        "facility": bool(parsed.facility_text),
        "declared": sorted(read_box(parsed).words) if j.box_read else [],
    }


def haccp_stats(recs: list) -> dict:
    n = len(recs)
    out = {"products": n, "read_any": sum(r["read_any"] for r in recs), "box_read": sum(r["box_read"] for r in recs)}
    for label, sub in (("all", recs), ("box", [r for r in recs if r["box_read"]]),
                       ("no_box_label", [r for r in recs if not r["box_read"]])):
        may = [r for r in sub if any(v in MAY for v, _ in r["verdicts"].values())]
        may_wo = [r for r in sub if any(v in MAY for v in r["no_box"].values())]
        units = collections.Counter(v for r in sub for a in ALLERGENS for v in [r["verdicts"].get(a, ("absent", ""))[0]])
        per_allergen = {a: sum(r["verdicts"].get(a, ("absent", ""))[0] in MAY for r in sub) for a in ALLERGENS}
        per_basis = collections.Counter(b for r in sub for v, b in r["verdicts"].values() if v in MAY)
        per_allergen_wo = {a: sum(r["no_box"].get(a, "absent") in MAY for r in sub) for a in ALLERGENS}
        out[label] = {"products": len(sub), "products_with_may": len(may), "products_with_may_without_box": len(may_wo),
                      "units": dict(units), "per_allergen_may": per_allergen, "per_basis_may": dict(per_basis),
                      "per_allergen_may_without_box": per_allergen_wo}
    box = [r for r in recs if r["box_read"]]
    out["box_only_confirmed"] = {a: sum(r["verdicts"].get(a, ("", ""))[0] == "confirmed" and
                                        r["verdicts"].get(a, ("", ""))[1] == "KR-DECL" for r in box) for a in ALLERGENS}
    out["confirmed_with_box"] = {a: sum(r["verdicts"].get(a, ("", ""))[0] == "confirmed" for r in box) for a in ALLERGENS}
    out["missing_in_box"] = sum(bool(r["missing_notes"]) for r in box)
    with_unknown = [r for r in box if r["unknown"]]
    out["box_with_unknown"] = len(with_unknown)
    out["hidden"] = {a: sum(r["verdicts"].get(a, ("absent", ""))[0] == "absent" for r in with_unknown) for a in NOT_FULLY_COVERED}
    out["products_with_unknown_all"] = sum(bool(r["unknown"]) for r in recs)
    out["facility_in_text"] = sum(r["facility"] for r in recs)
    # 제조사가 표시란에 적은 알레르기를 원재료만 보고(표시란 없이)도 찾는가: 확인됨·추정 / 판정 불가 / 없음
    agree = {a: collections.Counter() for a in ALLERGENS}
    for r in box:
        for a in r["declared"]:
            v = r["no_box"].get(a, "absent")
            agree[a]["found" if v in ("confirmed", "inferable") else "unsure" if v == "undecidable" else "missed"] += 1
    out["box_declared_vs_ingredients"] = {a: dict(c) for a, c in agree.items()}
    occ = collections.Counter(n for r in recs for n in set(r["unknown"]))
    total = sum(occ.values())
    out["unknown_names"] = {"distinct": len(occ), "occurrences": total,
                            "top100_share": round(sum(c for _, c in occ.most_common(100)) / total, 3) if total else 0,
                            "top300_share": round(sum(c for _, c in occ.most_common(300)) / total, 3) if total else 0,
                            "seen_once": sum(1 for c in occ.values() if c == 1)}
    return out


def facility_stats(path: Path) -> dict:
    rows = read_jsonl(path)
    have = [r for r in rows if (r.get("facility_text") or "").strip()]
    words = collections.Counter()
    for r in have:
        for w in ("우유", "알류", "난류", "계란", "밀", "대두", "땅콩", "호두", "잣", "게", "새우", "고등어", "참깨"):
            if w in r["facility_text"]:
                words[w] += 1
    return {"products": len(rows), "with_facility": len(have), "allergen_words": dict(words.most_common())}


def write_outputs(gold: dict, hac: dict, recs: list, fac: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps({"gold": gold, "haccp": hac, "facility": fac},
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
    names = collections.Counter(n for r in recs for n in set(r["unknown"]))
    lines = ["이름\t제품 수"] + [f"{cell(n)}\t{c}" for n, c in names.most_common(300)]
    (out_dir / "unknown_names_top.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sample = [r for r in recs if r["box_read"] and r["unknown"] and r["verdicts"].get("sesame", ("absent", ""))[0] == "absent"]
    rows = ["품목보고번호\t제품명\t식품유형\t모르는 이름"] + [
        f"{r['id']}\t{cell(r['name'])}\t{cell(r['kind'])}\t{cell(', '.join(r['unknown']))}" for r in sample[:200]]
    (out_dir / "hidden_sesame_examples.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def draw_sample(recs: list, n: int = 100, seed: int = 20261119) -> list:
    """숨은 애매함 어림용 표본: 표시란을 읽었고 모르는 이름이 있는 제품에서 n개 (판단은 사람이 results/hidden_sample_100.tsv에 적었다)."""
    import random
    pool = [r for r in recs if r["box_read"] and r["unknown"]]
    return random.Random(seed).sample(pool, min(n, len(pool)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="EXP-007 may contain 분석")
    ap.add_argument("--facility", type=Path, help="EXP-006 전사_조정.jsonl (같은 시설 문구)")
    ap.add_argument("--out", type=Path, default=HERE / "results")
    ap.add_argument("--limit", type=int, help="HACCP 제품을 앞에서부터 이만큼만 (시험용)")
    args = ap.parse_args(argv)
    gold = {name: gold_stats(read_jsonl(GOLD / f"{name}.jsonl")) for name in ("dev", "test", "exp006_photo")}
    items = read_jsonl(ITEMS)[: args.limit] if args.limit else read_jsonl(ITEMS)
    recs = [product_record(item) for item in items]
    hac = haccp_stats(recs)
    fac = facility_stats(args.facility) if args.facility else {}
    write_outputs(gold, hac, recs, fac, args.out)
    picked = draw_sample(recs)
    (args.out / "hidden_sample_draw.tsv").write_text("\n".join(
        ["번호\t품목보고번호\t제품명\t모르는 이름"] + [f"{k}\t{r['id']}\t{cell(r['name'])}\t{cell(', '.join(dict.fromkeys(r['unknown'])))}"
                                               for k, r in enumerate(picked, 1)]) + "\n", encoding="utf-8")
    for name, g in gold.items():
        print(f"정답 {name}: may contain 제품 {pct(g['products_with_may'], g['products'])}, "
              f"판정 단위 {pct(g['may_units'], g['products'] * 9)}")
    for label in ("all", "box", "no_box_label"):
        h = hac[label]
        print(f"HACCP {label}: may contain 제품 {pct(h['products_with_may'], h['products'])}, "
              f"표시란 없이 {pct(h['products_with_may_without_box'], h['products'])}")
    print(f"숨은 애매함(표시란 읽음 + 모르는 이름 있음): {pct(hac['box_with_unknown'], hac['box_read'])}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
