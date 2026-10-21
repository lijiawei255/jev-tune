"""How low can the cost go? Expert with a large budget + cost decomposition."""

import time

import numpy as np

from jev_tune.baselines import run_cmaes, run_zn, zn_gains
from jev_tune.metrics import cost_from_metrics
from jev_tune.plants import sample_plants, simulate
from jev_tune.expert import generate

p = sample_plants(100, seed=11)

t = time.perf_counter()
zn = run_zn(p)
print(f"ZN     J median={np.median(zn.best_j):.3f}  ({time.perf_counter() - t:.1f}s)")

t = time.perf_counter()
data, best_g, best_j, gzn = generate(p, gens=40, lam=8, seed=5, keep_act=False)
print(
    f"expert J median={np.median(best_j):.3f} p90={np.percentile(best_j, 90):.3f} "
    f"({time.perf_counter() - t:.1f}s)"
)

t = time.perf_counter()
cma = run_cmaes(p, zn_gains(p), budget=160, lam=8)
print(f"CMA    J median={np.median(cma.best_j):.3f}  ({time.perf_counter() - t:.1f}s)")

res = simulate(p, best_g)
m = res["metrics"]
j = cost_from_metrics(m, y_curve=res["y_curve"])
print("\ncost decomposition at expert optimum (medians):")
print(
    f"  overshoot {np.median(np.clip(m[:, 0], 0, 2)):.3f}  "
    f"rise/h {np.median(np.clip(m[:, 1] / 10, 0, 1)):.3f}  "
    f"settle/h {np.median(np.clip(m[:, 2] / 10, 0, 1)):.3f}"
)
print(
    f"  |ess| {np.median(np.abs(m[:, 3])):.4f}  "
    f"itae/norm {np.median(m[:, 5] / 100):.4f}  "
    f"sat {np.median(m[:, 7]):.3f}  over {np.median(m[:, 8]):.3f}"
)
print(f"  total J median={np.median(j):.3f} min={j.min():.3f}")

for fam in sorted(set(p.family)):
    idx = [i for i, f in enumerate(p.family) if f == fam]
    print(
        f"  {fam:12s} J median={np.median(j[idx]):6.3f}  zn={np.median(zn.best_j[idx]):6.3f}"
    )
