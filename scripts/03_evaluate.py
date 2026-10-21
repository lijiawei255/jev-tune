"""Head vs classical baselines on held-out plants.

Reference: a strong CMA-ES run (240 simulations per plant).  Target: reach
1.05x that cost.  The headline number is how many simulations each method
needs to get there.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from jev_tune.baselines import (
    run_bo,
    run_cmaes,
    run_relay,
    run_simplex,
    run_zn,
    zn_gains,
)
from jev_tune.evaluate import evaluate_head
from jev_tune.identified import run_identify_pidtune
from jev_tune.matlab_baseline import matlab_available, run_pidtune
from jev_tune.model import JevHead, ValueNet
from jev_tune.plants import (
    HELDOUT_FAMILIES,
    TRAIN_FAMILIES,
    sample_plants,
    ultimate_gain,
)


def load_models(models_dir: str):
    import torch

    import json

    meta = json.loads((Path(models_dir) / "meta.json").read_text(encoding="utf-8"))
    head = JevHead(n_actions=meta.get("n_actions", 5))
    head.load_state_dict(torch.load(f"{models_dir}/jev_head.pt", map_location="cpu"))
    head.eval()
    value = ValueNet()
    value.load_state_dict(torch.load(f"{models_dir}/value_net.pt", map_location="cpu"))
    value.eval()
    return head, value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plants", type=int, default=120)
    ap.add_argument("--heldout", action="store_true", default=True)
    ap.add_argument("--iters", type=int, default=24)
    ap.add_argument("--ref-budget", type=int, default=240)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="research/results")
    args = ap.parse_args()

    Path(args.out).mkdir(parents=True, exist_ok=True)
    fams = HELDOUT_FAMILIES if args.heldout else TRAIN_FAMILIES
    plants = sample_plants(
        args.plants, seed=args.seed, families=fams, heldout=args.heldout
    )
    print(
        f"[eval] {plants.n} plants: {sorted(set(plants.family))} (heldout={args.heldout})"
    )

    ku, tu = ultimate_gain(plants)
    gzn = np.column_stack([0.6 * ku, 1.2 * ku / tu, 0.075 * ku * tu])
    x0 = zn_gains(plants)

    results = []

    t = time.perf_counter()
    print("[eval] strong reference (CMA-ES)...")
    ref = run_cmaes(plants, x0, budget=args.ref_budget, lam=8, seed=11)
    j_ref = ref.best_j.copy()
    target = 1.05 * np.maximum(j_ref, 0.02)
    print(
        f"  reference J median={np.median(j_ref):.3f} ({time.perf_counter() - t:.0f}s)"
    )

    for name, fn in (
        ("zn", lambda: run_zn(plants)),
        ("relay_zn", lambda: run_relay(plants)),
        ("simplex", lambda: run_simplex(plants, x0, budget=20)),
        ("cmaes", lambda: run_cmaes(plants, x0, budget=18, lam=6)),
        ("bo", lambda: run_bo(plants, x0, budget=20, n_init=6)),
        ("identify+pidtune", lambda: run_identify_pidtune(plants)),
    ):
        t = time.perf_counter()
        r = fn()
        r.wall_s = time.perf_counter() - t
        results.append(r)
        print(f"  {name:12s} {r.wall_s:6.1f}s  J median={np.median(r.best_j):.3f}")

    head, value = load_models(args.models)
    t = time.perf_counter()
    hr = evaluate_head(
        head, plants, gzn, ku, tu, iters=args.iters, value=value, seed=args.seed
    )
    results.append(hr)
    print(f"  {'jev_head':12s} {hr.wall_s:6.1f}s  J median={np.median(hr.best_j):.3f}")

    rows = []
    for r in results:
        sims = r.sims_to_target(target)
        finite = sims[np.isfinite(sims)]
        rows.append(
            {
                "method": r.name,
                "final_cost_median": float(np.median(r.best_j)),
                "final_cost_p90": float(np.percentile(r.best_j, 90)),
                "ratio_to_ref": float(np.median(r.best_j / np.maximum(j_ref, 1e-6))),
                "success_rate": float(np.mean(r.best_j <= target)),
                "sims_to_target_median": float(np.median(finite))
                if len(finite)
                else float("inf"),
                "sims_to_target_p90": float(np.percentile(finite, 90))
                if len(finite)
                else float("inf"),
                "wall_s": float(getattr(r, "wall_s", 0.0)),
            }
        )

    rows.sort(key=lambda x: (-x["success_rate"], x["sims_to_target_median"]))
    print("\n=== held-out comparison (target = 1.05 x CMA-240 reference) ===")
    hdr = f"{'method':<12}{'final med':>10}{'p90':>8}{'x ref':>8}{'success':>9}{'sims med':>10}{'sims p90':>10}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['method']:<12}{r['final_cost_median']:>10.3f}{r['final_cost_p90']:>8.3f}"
            f"{r['ratio_to_ref']:>8.2f}{r['success_rate']:>9.1%}"
            f"{r['sims_to_target_median']:>10.1f}{r['sims_to_target_p90']:>10.1f}"
        )

    out = (
        Path(args.out)
        / f"eval_{'heldout' if args.heldout else 'train'}_{args.plants}.json"
    )
    payload = {
        "n_plants": plants.n,
        "families": sorted(set(plants.family)),
        "heldout": bool(args.heldout),
        "ref_budget": args.ref_budget,
        "reference_j_median": float(np.median(j_ref)),
        "rows": rows,
    }

    fam_arr = np.array(plants.family)
    payload["per_family"] = {}
    for fam in sorted(set(plants.family)):
        m = fam_arr == fam
        payload["per_family"][fam] = {
            r.name: {
                "ratio_to_ref": float(
                    np.median(r.best_j[m] / np.maximum(j_ref[m], 1e-6))
                ),
                "success_rate": float(np.mean(r.best_j[m] <= target[m])),
            }
            for r in results
        }

    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n[eval] wrote {out}")


if __name__ == "__main__":
    main()
