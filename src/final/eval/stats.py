"""채점에 쓰는 통계 (표준 라이브러리만): 비율, Cohen's κ, 맥니마 정확 이항 검정, 제품 단위 부트스트랩."""
from __future__ import annotations

import math
import random

SEED = 20261113          # 부트스트랩 난수 시드 (고정)
N_BOOT = 2000            # 부트스트랩 횟수


def ratio(num, den):
    """{"num", "den", "value"}. 분모가 0이면 value는 None(정의되지 않음)."""
    return {"num": num, "den": den, "value": num / den if den else None}


def cohen_kappa(matrix, labels):
    """matrix[정답][시스템] 개수 -> κ = (관측 일치 - 우연 일치) / (1 - 우연 일치).

    정수로 계산해 반올림 오차를 피한다. 우연 일치가 1이면(두 쪽 모두 한 범주뿐) None.
    """
    total = sum(matrix[g][p] for g in labels for p in labels)
    agree = sum(matrix[c][c] for c in labels)
    chance = sum(sum(matrix[c][p] for p in labels) * sum(matrix[g][c] for g in labels) for c in labels)
    if total == 0 or total * total == chance:
        return None
    return (agree * total - chance) / (total * total - chance)


def binom_two_sided(b, c):
    """맥니마 정확 검정. b, c = 한쪽만 맞은 수. H0에서 b ~ Bin(b + c, 1/2).

    양측 p = min(1, 2 * P(X <= min(b, c))). 큰 수에서도 넘치지 않게 정수로 더한 뒤 나눈다.
    """
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1))
    return min(1.0, 2 * tail / 2 ** n)


def percentile_95(values):
    """정렬한 값에서 2.5%·97.5% 자리를 고른다. 자리 = 내림(0.025n), 올림(0.975n) - 1."""
    if not values:
        return None
    v = sorted(values)
    n = len(v)
    lo = n * 25 // 1000
    hi = -((-n * 975) // 1000) - 1
    return [v[lo], v[hi]]


def bootstrap(rows, n_boot=N_BOOT, seed=SEED):
    """rows: 제품마다 {지표: (분자, 분모)}. 제품을 복원 추출해 지표마다 95% 구간을 낸다.

    돌려주는 값: {지표: {"ci": [아래,위] 또는 None, "ci_valid": 분모가 0이 아니었던 표본 수}}.
    분모가 0인 표본은 그 지표에서만 뺀다. n_boot가 0이면 {}.
    """
    if not rows or n_boot <= 0:
        return {}
    rng = random.Random(seed)
    keys = list(rows[0])
    samples = {k: [] for k in keys}
    for _ in range(n_boot):
        pick = rng.choices(rows, k=len(rows))
        for k in keys:
            den = sum(r[k][1] for r in pick)
            if den:
                samples[k].append(sum(r[k][0] for r in pick) / den)
    return {k: {"ci": percentile_95(v), "ci_valid": len(v)} for k, v in samples.items()}
