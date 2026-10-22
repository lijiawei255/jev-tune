"""Is the Ziegler-Nichols start systematically on one side of the optimum?

Plan A (generate expert data from starts on both sides) is only legitimate if the
current training distribution is provably one-sided *for reasons of the task*,
not because a particular model scored badly.  This measures that directly, on the
training families, without looking at any evaluation model.

For every plant: scale the ZN start by m in [0.4 .. 2.2] and record which m gives
the lowest cost.  m < 1 means "the adjustment is downwards", m > 1 means upwards.
"""

from __future__ import annotations

import numpy as np

from jev_tune.metrics import cost_from_metrics
from jev_tune.plants import sample_plants, simulate, ultimate_gain

FAMILIES = [
    "fopdt",
    "sopdt",
    "third_rhp",
    "integrating",
    "pmsl_speed",
    "position_loop",
    "two_mass",
]
FAMILIES[4] = "pmsm_speed"

MULTS = np.array([0.4, 0.55, 0.7, 0.85, 1.0, 1.2, 1.45, 1.75, 2.2])

rows = []
for fam in FAMILIES:
    plants = sample_plants(14, seed=7, families=[fam])  # training side, seed 7
    ku, tu = ultimate_gain(plants)
    gzn = np.column_stack([0.6 * ku, 1.2 * ku / np.maximum(tu, 1e-9), 0.075 * ku * tu])
    best_m = np.full(plants.n, np.nan)
    j_zn = np.full(plants.n, np.nan)
    j_best = np.full(plants.n, np.nan)
    for i in range(plants.n):
        best = np.inf
        for m in MULTS:
            g = (gzn[i] * m)[None, :]
            res = simulate(plants.take([i]), g)
            j = float(
                np.ravel(cost_from_metrics(res["metrics"], y_curve=res["y_curve"]))[0]
            )
            if m == 1.0:
                j_zn[i] = j
            if j < best:
                best = j
                best_m[i] = m
        j_best[i] = best
    rows.append((fam, best_m, j_zn, j_best))

print(
    f"{'family':<15} {'median best m':>13} {'share m<1':>9} {'share m>1':>9} "
    f"{'J at ZN':>8} {'J best':>7}"
)
all_m = []
for fam, best_m, j_zn, j_best in rows:
    all_m.append(best_m)
    print(
        f"{fam:<15} {np.median(best_m):>13.2f} "
        f"{np.mean(best_m < 1):>9.0%} {np.mean(best_m > 1):>9.0%} "
        f"{np.median(j_zn):>8.3f} {np.median(j_best):>7.3f}"
    )

m = np.concatenate(all_m)
print(
    f"\noverall: {len(m)} plants, median best m = {np.median(m):.2f}, "
    f"{np.mean(m < 1):.0%} below ZN, {np.mean(m > 1):.0%} above ZN, "
    f"{np.mean(m == 1):.0%} at ZN"
)
