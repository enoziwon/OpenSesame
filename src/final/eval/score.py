"""채점 본체: 정답 + 시스템 응답 -> 지표 dict (그대로 JSON으로 저장할 수 있다).

    from src.final.eval import load_gold, load_pred, score_system
    m = score_system(load_gold("dev.jsonl"), load_pred("a.jsonl", gold))
    m["miss"]     # {"num": 2, "den": 8, "value": 0.25, "ci": [아래, 위], "ci_valid": 2000}

판정 단위는 제품 × 미국 9개 알레르기, 범주는 confirmed / inferable / undecidable / absent.
지표 정의는 report.DEFINITIONS에 한 줄씩 적었다. 모호한 곳은 시스템에 불리한 쪽으로 정했다.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Optional

from .evidence import evidence_matches
from .load import ABSENT, ALLERGENS, CATEGORIES
from .stats import N_BOOT, SEED, binom_two_sided, bootstrap, cohen_kappa, ratio

POSITIVE = ("confirmed", "inferable")       # 놓침을 세는 정답
WEIGHT = {"confirmed": 2, "inferable": 1}   # 누락 가중 재현율의 가중치


@dataclass(frozen=True)
class Unit:
    """판정 단위 하나 (제품 × 알레르기)."""
    pid: str
    allergen: str
    gold: str                           # confirmed / inferable / undecidable / absent
    pred: str
    gold_evidence: str = ""
    pred_evidence: str = ""
    hidden: Optional[bool] = None       # 정답 hidden_or_derived (absent거나 칸이 없으면 None)
    declared: Optional[bool] = None     # 정답 declared_in_kr

    @property
    def correct(self):
        return self.gold == self.pred

    @property
    def missed(self):
        """놓침: 정답 confirmed·inferable인데 시스템 absent."""
        return self.gold in POSITIVE and self.pred == ABSENT

    @property
    def false_alarm(self):
        """헛경고: 정답 absent인데 시스템 confirmed·inferable."""
        return self.gold == ABSENT and self.pred in POSITIVE


def build_units(gold, pred):
    """정답 파일 순서 × 알레르기 순서로 판정 단위를 만든다."""
    units = []
    for g in gold.products:
        p = pred.products[g.id]
        for a in ALLERGENS:
            gl, pl = g.labels.get(a), p.labels.get(a)
            units.append(Unit(
                pid=g.id, allergen=a,
                gold=gl.verdict if gl else ABSENT, pred=pl.verdict if pl else ABSENT,
                gold_evidence=gl.evidence if gl else "", pred_evidence=pl.evidence if pl else "",
                hidden=gl.hidden if gl else None, declared=gl.declared if gl else None,
            ))
    return tuple(units)


def _share(pool, cond):
    """pool 중 cond를 만족하는 비율."""
    return ratio(sum(1 for u in pool if cond(u)), len(pool))


def confusion(units):
    """혼동 행렬 m[정답][시스템]."""
    counts = Counter((u.gold, u.pred) for u in units)
    return {g: {p: counts[(g, p)] for p in CATEGORIES} for g in CATEGORIES}


def per_class(m):
    out = {}
    for c in CATEGORIES:
        col = sum(m[g][c] for g in CATEGORIES)
        row = sum(m[c][p] for p in CATEGORIES)
        out[c] = {"precision": ratio(m[c][c], col), "recall": ratio(m[c][c], row)}
    return out


def _product_row(us):
    """제품 하나의 {지표: (분자, 분모)}. 점 추정과 부트스트랩이 같은 수를 쓴다."""
    pos = [u for u in us if u.gold in POSITIVE]
    conf = [u for u in us if u.gold == "confirmed"]
    neg = [u for u in us if u.gold == ABSENT]
    alarms = sum(u.false_alarm for u in neg)
    return {
        "accuracy": (sum(u.correct for u in us), len(us)),
        "miss": (sum(u.missed for u in pos), len(pos)),
        "miss_confirmed": (sum(u.missed for u in conf), len(conf)),
        "weighted_recall": (sum(WEIGHT[u.gold] for u in pos if not u.missed), sum(WEIGHT[u.gold] for u in pos)),
        "false_alarm_unit": (alarms, len(neg)),
        "false_alarm_product": (int(alarms > 0), int(len(neg) > 0)),
    }


def product_rows(units):
    by_product = {}
    for u in units:
        by_product.setdefault(u.pid, []).append(u)
    return [_product_row(us) for us in by_product.values()]


def _main_ratios(rows, n_boot, seed):
    """제품 단위 합으로 주요 비율을 내고 부트스트랩 95% 구간을 붙인다."""
    boot = bootstrap(rows, n_boot, seed)
    out = {}
    for key in rows[0]:
        r = ratio(sum(row[key][0] for row in rows), sum(row[key][1] for row in rows))
        b = boot.get(key)
        out[key] = dict(r, ci=b["ci"], ci_valid=b["ci_valid"]) if b else dict(r, ci=None, ci_valid=0)
    return out


def undecidable_stats(units, m):
    """판정 불가 적절성: 시스템 undecidable의 정밀도·재현율과 전체 중 비율."""
    pred_u = sum(m[g]["undecidable"] for g in CATEGORIES)
    gold_u = sum(m["undecidable"][p] for p in CATEGORIES)
    hit = m["undecidable"]["undecidable"]
    return {"precision": ratio(hit, pred_u), "recall": ratio(hit, gold_u),
            "pred_rate": ratio(pred_u, len(units)), "gold_rate": ratio(gold_u, len(units))}


def evidence_stats(units):
    """근거 일치: 판정이 맞은 단위(absent 제외) 중 근거가 같은 비율."""
    pool = [u for u in units if u.correct and u.gold != ABSENT]
    return {"match": _share(pool, lambda u: evidence_matches(u.gold_evidence, u.pred_evidence)),
            "gold_empty": sum(1 for u in units if u.gold != ABSENT and not u.gold_evidence.strip())}


def _subset_stats(pool, missing):
    pos = [u for u in pool if u.gold in POSITIVE]
    return {"n": len(pool), "accuracy": _share(pool, lambda u: u.correct),
            "miss": _share(pos, lambda u: u.missed), "alert_recall": _share(pool, lambda u: u.pred != ABSENT),
            "missing_field": missing}


def subsets(units):
    """정답 칸 기준 부분집합. 칸이 없는 정답은 빼고 missing_field로 센다."""
    gold_pos = [u for u in units if u.gold != ABSENT]
    return {
        "hidden_or_derived": _subset_stats([u for u in gold_pos if u.hidden is True],
                                           sum(u.hidden is None for u in gold_pos)),
        "not_declared_in_kr": _subset_stats([u for u in gold_pos if u.declared is False],
                                            sum(u.declared is None for u in gold_pos)),
    }


def per_allergen(units):
    out = {}
    for a in ALLERGENS:
        us = [u for u in units if u.allergen == a]
        out[a] = {
            "gold": {c: sum(u.gold == c for u in us) for c in CATEGORIES},
            "accuracy": _share(us, lambda u: u.correct),
            "miss": _share([u for u in us if u.gold in POSITIVE], lambda u: u.missed),
            "false_alarm_unit": _share([u for u in us if u.gold == ABSENT], lambda u: u.false_alarm),
            "alert_recall": _share([u for u in us if u.gold != ABSENT], lambda u: u.pred != ABSENT),
            "alert_precision": _share([u for u in us if u.pred != ABSENT], lambda u: u.gold != ABSENT),
        }
    return out


def time_stats(gold, pred):
    ms = [pred.products[g.id].ms for g in gold.products]
    have = [x for x in ms if x is not None]
    return {"mean": sum(have) / len(have) if have else None, "n": len(have), "products": len(ms)}


def item_lists(units):
    """놓침·헛경고 목록 (제품 id와 근거 글자가 들어가므로 JSON에만 쓴다)."""
    return {
        "misses": [{"id": u.pid, "allergen": u.allergen, "gold": u.gold, "gold_evidence": u.gold_evidence}
                   for u in units if u.missed],
        "false_alarms": [{"id": u.pid, "allergen": u.allergen, "pred": u.pred, "pred_evidence": u.pred_evidence}
                         for u in units if u.false_alarm],
    }


def score_system(gold, pred, name="", n_boot=N_BOOT, seed=SEED, items=True):
    """시스템 하나의 지표 dict."""
    units = build_units(gold, pred)
    m = confusion(units)
    products = pred.products.values()
    out = {
        "name": name or pred.path, "file": pred.path,
        "classifiers": sorted({p.classifier for p in products}),
        "warned_products": sum(p.warned for p in products),
        "products": len(gold.products), "units": len(units),
        "confusion": m, "kappa": cohen_kappa(m, CATEGORIES), "per_class": per_class(m),
        **_main_ratios(product_rows(units), n_boot, seed),
        "alert_recall": _share([u for u in units if u.gold != ABSENT], lambda u: u.pred != ABSENT),
        "alert_precision": _share([u for u in units if u.pred != ABSENT], lambda u: u.gold != ABSENT),
        "undecidable": undecidable_stats(units, m),
        "evidence": evidence_stats(units),
        "subsets": subsets(units),
        "per_allergen": per_allergen(units),
        "time_ms": time_stats(gold, pred),
    }
    return dict(out, **item_lists(units)) if items else out


def mcnemar(units_a, units_b, ok, within=None):
    """같은 단위에서 두 시스템이 맞았는지(ok) 세고 정확 이항 검정 p를 낸다. within이 있으면 그 단위만."""
    counts = Counter()
    for ua, ub in zip(units_a, units_b):
        if (ua.pid, ua.allergen) != (ub.pid, ub.allergen):
            raise ValueError("두 시스템의 판정 단위 순서가 다름")
        if within is None or within(ua):
            counts[(ok(ua), ok(ub))] += 1
    a_only, b_only = counts[(True, False)], counts[(False, True)]
    return {"both": counts[(True, True)], "a_only": a_only, "b_only": b_only,
            "neither": counts[(False, False)], "p": binom_two_sided(a_only, b_only)}


def compare_systems(gold, preds, names):
    """두 시스템씩 짝지어 맥니마 표를 만든다: 판정 일치(전체 단위), 놓치지 않음(정답 C·I 단위)."""
    units = [build_units(gold, p) for p in preds]
    out = []
    for i in range(len(preds)):
        for j in range(i + 1, len(preds)):
            out.append({
                "a": names[i], "b": names[j],
                "correct": mcnemar(units[i], units[j], lambda u: u.correct),
                "caught": mcnemar(units[i], units[j], lambda u: u.pred != ABSENT, lambda u: u.gold in POSITIVE),
            })
    return out


def score_all(gold, preds, names, n_boot=N_BOOT, seed=SEED, items=True):
    """시스템마다 지표를 내고, 둘 이상이면 서로 비교한다."""
    systems = [score_system(gold, p, n, n_boot, seed, items) for p, n in zip(preds, names)]
    return {"systems": systems, "comparisons": compare_systems(gold, preds, names) if len(preds) > 1 else []}
