"""Validate the simulation against theory: P-control at Ku should oscillate at Tu."""

import numpy as np

from jev_tune.metrics import cost_from_metrics
from jev_tune.plants import TRAIN_FAMILIES, sample_plants, simulate, ultimate_gain

p = sample_plants(30, seed=3)
ku, tu = ultimate_gain(p)
print("Ku:", np.round(ku[:6], 3), " Tu:", np.round(tu[:6], 4))
print("delay:", np.round(p.delay_s[:6], 4), "families:", p.family[:6])

# open loop step with u = 1: final value should equal the DC gain
g = np.column_stack([np.zeros(p.n), np.zeros(p.n), np.zeros(p.n)])
res = simulate(p, g, horizon=30.0)
print("\nopen-loop u=0 -> y end:", np.round(res["y_curve"][:6, -1], 4))

# proportional control at Ku: y should oscillate with period ~Tu
g = np.column_stack([ku, np.zeros(p.n), np.zeros(p.n)])
res = simulate(p, g, horizon=10.0, n_curve=512)
for i in range(6):
    y = res["y_curve"][i]
    zc = np.sum(np.diff(np.signbit(y - 1.0)) != 0)
    print(
        f"plant {i} ({p.family[i]:12s}) Ku={ku[i]:8.3f} Tu={tu[i]:7.4f} "
        f"y_max={y.max():7.3f} y_end={y[-1]:7.3f} zero_cross={zc}"
    )

# a deliberately slow-but-sane PI on one plant for metric sanity
i = 0
print("\nmetric trace for plant 0 with a few gain sets:")
for kp, ki, kd in [(1, 0, 0), (2, 5, 0), (5, 10, 0.1), (0.5, 1, 0)]:
    gg = np.tile([kp, ki, kd], (p.n, 1))
    r = simulate(p, gg)
    j = cost_from_metrics(r["metrics"], y_curve=r["y_curve"])
    m = r["metrics"][i]
    print(
        f"  Kp={kp:<4} Ki={ki:<5} Kd={kd:<5} | plant0 J={j[i]:6.3f} "
        f"OS={m[0]:5.2f} rise={m[1]:5.2f} settle={m[2]:5.2f} ess={m[3]:6.3f} "
        f"sat={m[7]:5.2f} | medianJ={np.median(j):6.3f}"
    )
