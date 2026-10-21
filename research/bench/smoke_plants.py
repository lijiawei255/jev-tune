"""Smoke test: plant zoo, simulation speed, metric sanity."""

import time

import numpy as np

from jev_tune.metrics import cost_from_metrics
from jev_tune.plants import METRIC_NAMES, sample_plants, simulate, ultimate_gain


def main():
    t = time.perf_counter()
    p = sample_plants(300, seed=1)
    print(
        f"sample_plants(300): {time.perf_counter() - t:.2f}s  state_dim={p.a.shape[1]}"
    )
    print("families:", {f: p.family.count(f) for f in sorted(set(p.family))})

    t = time.perf_counter()
    ku, tu = ultimate_gain(p)
    print(
        f"ultimate_gain: {time.perf_counter() - t:.3f}s  finite={np.isfinite(ku).mean():.2%}"
    )
    print(f"  Ku  median={np.nanmedian(ku):.3f}  Tu median={np.nanmedian(tu):.3f}")

    gzn = np.column_stack([0.6 * ku, 1.2 * ku / np.maximum(tu, 1e-9), 0.075 * ku * tu])
    for name, gains in (
        ("zn", gzn),
        ("x0.5", gzn * 0.5),
        ("x2", gzn * 2.0),
        ("kp_only", np.column_stack([np.full(p.n, 1.0), np.zeros(p.n), np.zeros(p.n)])),
    ):
        t = time.perf_counter()
        res = simulate(p, gains)
        dt = time.perf_counter() - t
        j = cost_from_metrics(res["metrics"], y_curve=res["y_curve"])
        print(
            f"{name:9s} {dt * 1000:6.1f} ms  J median={np.median(j):6.3f} "
            f"p90={np.percentile(j, 90):6.3f} finite={np.isfinite(j).mean():.2%}"
        )
        if name == "zn":
            for k, mn in enumerate(METRIC_NAMES):
                col = res["metrics"][:, k]
                print(
                    f"    {mn:14s} median={np.nanmedian(col):12.4f} "
                    f"p10={np.nanpercentile(col, 10):10.4f} p90={np.nanpercentile(col, 90):10.4f}"
                )

    # batch scaling: 300 plants x 6 candidates
    flat = p.take(np.tile(np.arange(p.n), 6))
    t = time.perf_counter()
    simulate(flat, np.tile(gzn, (6, 1)))
    print(f"batch 1800 rows: {time.perf_counter() - t:.2f}s")


if __name__ == "__main__":
    main()
