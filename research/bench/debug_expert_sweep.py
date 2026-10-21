"""Expert strength sweep: which settings get close to a strong reference?"""

import time

import numpy as np

from jev_tune.baselines import run_cmaes, run_zn, zn_gains
from jev_tune.expert import generate
from jev_tune.plants import sample_plants

p = sample_plants(80, seed=11)
zn = run_zn(p)
print(f"ZN      J median={np.median(zn.best_j):.3f}")

t = time.perf_counter()
ref = run_cmaes(p, zn_gains(p), budget=320, lam=8)
print(
    f"CMA-320 J median={np.median(ref.best_j):.3f} p90={np.percentile(ref.best_j, 90):.3f} "
    f"({time.perf_counter() - t:.0f}s)"
)

for gens, lam, sigma in ((40, 8, 0.12), (60, 8, 0.12), (60, 8, 0.20), (80, 8, 0.15)):
    t = time.perf_counter()
    data, bg, bj, gzn = generate(
        p, gens=gens, lam=lam, seed=5, sigma0=sigma, keep_act=False
    )
    ratio = np.median(bj / np.maximum(ref.best_j, 1e-6))
    print(
        f"expert gens={gens:3d} lam={lam} sigma={sigma:.2f}: "
        f"J median={np.median(bj):.3f} p90={np.percentile(bj, 90):.3f} "
        f"ratio_vs_ref={ratio:.3f} ({time.perf_counter() - t:.0f}s)"
    )
