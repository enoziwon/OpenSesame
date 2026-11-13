"""지표 dict -> 사람이 읽는 마크다운 보고서 (표 위주).

제품 id와 원재료 글자는 넣지 않는다. 놓침·헛경고 목록은 JSON에만 있다(시험 세트 보호).
"""
from __future__ import annotations

from .load import ALLERGENS, CATEGORIES

DEFINITIONS = (
    "판정 단위: 제품 × 미국 9개 알레르기. 정답 annotations·응답 allergens에 없는 알레르기는 absent. "
    "범주는 confirmed / inferable / undecidable / absent 넷.",
    "정확도: 네 범주가 정답과 같은 단위의 비율. Cohen's κ: 같은 네 범주에서 (관측 일치 − 우연 일치) / (1 − 우연 일치).",
    "범주별 정밀도·재현율: 시스템이 그 범주라고 한 단위 중 정답도 그 범주인 비율 / "
    "정답이 그 범주인 단위 중 시스템도 그 범주인 비율. 분모가 0이면 –.",
    "놓침률: 정답이 confirmed·inferable인 단위 중 시스템이 absent인 비율(시스템 undecidable은 놓침이 아니다). "
    "'정답 C만'은 분모를 정답 confirmed로 한정한다.",
    "가중 재현율(누락 가중 재현율): 1 − (2 × 놓친 confirmed + 1 × 놓친 inferable) / "
    "(2 × 정답 confirmed + 1 × 정답 inferable). 놓침의 뜻은 놓침률과 같다.",
    "헛경고율(판정 단위): 정답이 absent인 단위 중 시스템이 confirmed·inferable인 비율(시스템 undecidable은 세지 않는다).",
    "헛경고율(제품): 정답 absent 단위가 하나라도 있는 제품 중, 그런 단위에 헛경고가 하나라도 있는 제품의 비율.",
    "경고 재현율·정밀도: '경고' = absent가 아님(undecidable 포함, 정답도 같다). "
    "정답이 경고인 단위 중 시스템도 경고한 비율 / 시스템이 경고한 단위 중 정답도 경고인 비율.",
    "판정 불가 적절성: 시스템 undecidable의 정밀도·재현율(범주별 표의 undecidable과 같다)과 "
    "전체 단위 중 undecidable 비율(시스템·정답).",
    "근거 일치: 판정이 맞은 단위(absent 제외) 중 evidence_ingredient가 정답과 같은 비율. "
    "함량(3%)·공백을 떼고 첫 괄호부터 버린 뒤 비교하고, 정답이 '부모(자식, …)' 꼴이면 부모나 바로 아래 자식과 같아도 일치"
    "(손자는 아님). \"표시란: X\"는 글자 그대로 비교. 빈 정답 근거와 other_evidence는 일치로 보지 않는다.",
    "부분집합: 정답 칸 hidden_or_derived = true / declared_in_kr = false인 단위(정답 absent는 칸이 없어 빠진다). "
    "칸이 없는 정답은 빼고 따로 센다. 놓침률의 분모는 그중 confirmed·inferable.",
    "알레르기별: 같은 지표를 알레르기 하나의 단위(제품 수만큼)로 잰다.",
    "시스템 비교: 같은 단위에서 한쪽만 맞은 수 b, c로 맥니마 정확 이항 검정. "
    "양측 p = min(1, 2·P(X ≤ min(b, c))), X ~ Bin(b + c, 1/2). "
    "'판정 일치'는 네 범주 일치(전체 단위), '놓치지 않음'은 정답 confirmed·inferable 단위에서 absent가 아님.",
    "처리 시간: 응답 파일의 ms(실행 도구가 제품 하나를 판정하는 데 잰 시간)의 제품당 평균.",
)

SUMMARY_RATIOS = (
    ("놓침률 (정답 C·I → absent)", "miss"),
    ("놓침률 (정답 C만)", "miss_confirmed"),
    ("가중 재현율 (C 2 : I 1)", "weighted_recall"),
    ("헛경고율 (판정 단위)", "false_alarm_unit"),
    ("헛경고율 (제품)", "false_alarm_product"),
    ("정확도 (네 범주)", "accuracy"),
)
SUBSETS = (
    ("hidden_or_derived", "hidden_or_derived = true"),
    ("not_declared_in_kr", "declared_in_kr = false (한국 표시란에 없음)"),
)


def pct(r, ci=True):
    """비율 칸: '25.0% (2/8) [0.0–50.0]'. 분모가 0이면 '– (0/0)'."""
    v = r.get("value")
    text = ("–" if v is None else f"{v * 100:.1f}%") + f" ({r['num']}/{r['den']})"
    if ci and r.get("ci"):
        lo, hi = r["ci"]
        text += f" [{lo * 100:.1f}–{hi * 100:.1f}]"
    return text


def _num(x, digits=3):
    return "–" if x is None else f"{x:.{digits}f}"


def _ms(t):
    if t["mean"] is None:
        return "–"
    note = f" (ms 있는 제품 {t['n']}/{t['products']})" if t["n"] < t["products"] else ""
    return f"{t['mean']:.2f} ms{note}"


def _p(p):
    return "< 0.0001" if p < 0.0001 else f"{p:.4f}"


def _cell(x):
    return str(x).replace("|", "\\|").replace("\n", " ")


def table(header, rows):
    lines = ["| " + " | ".join(_cell(h) for h in header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines + [""]


def _header(h, systems):
    preds = ", ".join(f"`{s['file']}` ({s['name']})" for s in systems)
    rows = [
        ("정답 파일", f"`{h['gold']}`"),
        ("정답 SHA-256", f"`{h['gold_sha256']}`"),
        ("응답 파일", preds),
        ("제품 수", h["products"]),
        ("판정 단위 수", f"{h['units']} (제품 × 알레르기 9)"),
        ("부트스트랩", f"제품 단위 {h['boot']}회, 시드 {h['seed']}" if h["boot"] else "하지 않음 (--boot 0)"),
        ("실행 시각", h["run_at"]),
    ]
    return table(("항목", "값"), rows)


def _summary(systems):
    rows = [[label] + [pct(s[key]) for s in systems] for label, key in SUMMARY_RATIOS]
    rows.append(["Cohen's κ (네 범주)"] + [_num(s["kappa"]) for s in systems])
    rows.append(["경고 재현율"] + [pct(s["alert_recall"]) for s in systems])
    rows.append(["경고 정밀도"] + [pct(s["alert_precision"]) for s in systems])
    rows.append(["판정 불가 정밀도"] + [pct(s["undecidable"]["precision"]) for s in systems])
    rows.append(["판정 불가 재현율"] + [pct(s["undecidable"]["recall"]) for s in systems])
    rows.append(["근거 일치"] + [pct(s["evidence"]["match"]) for s in systems])
    rows.append(["제품당 평균 처리 시간"] + [_ms(s["time_ms"]) for s in systems])
    rows.append(["warnings가 있는 응답"] + [f"{s['warned_products']}/{s['products']}" for s in systems])
    rows.append(["분류기 (응답 meta)"] + [", ".join(s["classifiers"]) or "–" for s in systems])
    intro = ["## 1. 한눈에 보기", "", "괄호는 (분자/분모), 대괄호는 제품 단위 부트스트랩 95% 구간(%)이다.", ""]
    return intro + table(["지표"] + [s["name"] for s in systems], rows)


def _definitions(h):
    lines = ["## 2. 지표 정의", ""] + [f"- {d}" for d in DEFINITIONS]
    lines.append(f"- 95% 구간: 제품을 복원 추출하는 부트스트랩 {h['boot']}회(시드 {h['seed']})의 2.5·97.5 백분위. "
                 "분모가 0인 표본은 그 지표에서 뺀다.")
    return lines + [""]


def _confusion(m):
    rows = [(g,) + tuple(m[g][p] for p in CATEGORIES) + (sum(m[g].values()),) for g in CATEGORIES]
    cols = tuple(sum(m[g][p] for g in CATEGORIES) for p in CATEGORIES)
    rows.append(("합",) + cols + (sum(cols),))
    return table(("정답 \\ 시스템",) + CATEGORIES + ("합",), rows)


def _per_class(pc):
    return table(("범주", "정밀도", "재현율"),
                 [(c, pct(pc[c]["precision"]), pct(pc[c]["recall"])) for c in CATEGORIES])


def _undecidable(u):
    return table(("시스템 판정 불가 비율", "정답 판정 불가 비율", "정밀도", "재현율"),
                 [(pct(u["pred_rate"]), pct(u["gold_rate"]), pct(u["precision"]), pct(u["recall"]))])


def _subsets(sub):
    rows = [(label, sub[k]["n"], pct(sub[k]["accuracy"]), pct(sub[k]["miss"]), pct(sub[k]["alert_recall"]),
             sub[k]["missing_field"]) for k, label in SUBSETS]
    return table(("부분집합 (정답 칸)", "단위 수", "정확도", "놓침률", "경고 재현율", "칸 없는 정답"), rows)


def _per_allergen(pa):
    rows = []
    for a in ALLERGENS:
        x = pa[a]
        dist = "/".join(str(x["gold"][c]) for c in CATEGORIES)
        rows.append((a, dist, pct(x["accuracy"]), pct(x["miss"]), pct(x["false_alarm_unit"]),
                     pct(x["alert_recall"]), pct(x["alert_precision"])))
    header = ("알레르기", "정답 C/I/U/absent", "정확도", "놓침률", "헛경고율", "경고 재현율", "경고 정밀도")
    return table(header, rows)


def _detail(s, no):
    lines = [f"### 3.{no} {s['name']}", "", "#### 혼동 행렬 (행: 정답, 열: 시스템)", ""] + _confusion(s["confusion"])
    lines += ["#### 범주별 정밀도·재현율", ""] + _per_class(s["per_class"])
    lines += ["#### 판정 불가 적절성", ""] + _undecidable(s["undecidable"])
    lines += ["#### 근거 일치", "", f"{pct(s['evidence']['match'])}. 빈 정답 근거 {s['evidence']['gold_empty']}개.", ""]
    lines += ["#### 부분집합", ""] + _subsets(s["subsets"])
    lines += ["#### 알레르기별", ""] + _per_allergen(s["per_allergen"])
    return lines


def _comparisons(comps, systems):
    rows = []
    for c in comps:
        for key, label in (("correct", "판정 일치 (전체 단위)"), ("caught", "놓치지 않음 (정답 C·I 단위)")):
            t = c[key]
            rows.append((f"{c['a']} vs {c['b']}", label, t["both"], t["a_only"], t["b_only"], t["neither"], _p(t["p"])))
    lines = ["## 4. 시스템 비교", "", "A만·B만은 한쪽만 맞은 단위 수(맥니마 표), p는 정확 이항 검정(양측)이다.", ""]
    lines += table(("A vs B", "기준", "둘 다", "A만", "B만", "둘 다 아님", "p"), rows)
    return lines + table(("시스템", "제품당 평균 처리 시간"), [(s["name"], _ms(s["time_ms"])) for s in systems])


def render(result, header):
    """score_all의 결과와 머리 정보(정답 파일·해시·제품 수·실행 시각 …) -> 마크다운 글자."""
    systems = result["systems"]
    lines = ["# OpenSesame 채점 보고서", ""] + _header(header, systems) + _summary(systems) + _definitions(header)
    lines += ["## 3. 시스템별 상세", ""]
    for i, s in enumerate(systems, 1):
        lines += _detail(s, i)
    if result["comparisons"]:
        lines += _comparisons(result["comparisons"], systems)
    return "\n".join(lines).rstrip() + "\n"
