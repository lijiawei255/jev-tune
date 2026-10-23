"""Out-of-distribution generalisation test.

The shipped head is applied **zero-shot** (no per-plant training) to ten control
scenarios that are not in the training zoo, each with four jittered draws
(+-20 % gain and delay).  If the head only works on the zoo it was trained on,
this table shows it immediately.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from jev_tune.baselines import run_cmaes, run_relay, run_zn, zn_gains
from jev_tune.evaluate import evaluate_head
from jev_tune.model import JevHead
from jev_tune.plants import ultimate_gain
from jev_tune.scenarios import names, variants


def load_head(models: str, n_actions: int = 7) -> JevHead:
    # one loader for every entry point: it attaches the fitted temperatures so
    # `evaluate_head` applies the same calibration as the headline benchmark
    from jev_tune.decision import load_backend

    return load_backend(models).model


def safe_gzn(ku: np.ndarray, tu: np.ndarray) -> np.ndarray:
    ku = np.asarray(ku, float)
    tu = np.asarray(tu, float)
    ok = np.isfinite(ku) & np.isfinite(tu) & (ku > 0) & (tu > 0)
    g = np.column_stack([0.6 * ku, 1.2 * ku / np.maximum(tu, 1e-9), 0.075 * ku * tu])
    g[~ok] = np.array([1.0, 0.5, 0.01])
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="models")
    ap.add_argument("--draws", type=int, default=4)
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--out", default="research/results/generalization.json")
    args = ap.parse_args()

    head = load_head(args.models)
    rows = []

    header = f"{'scenario':<20}{'jev':>8}{'zn':>8}{'relay':>8}{'cmaes':>8}{'ratio':>8}{'wins':>7}"
    print(header)
    print("-" * len(header))

    for name in names():
        p = variants(name, args.draws, seed=1)
        ku, tu = ultimate_gain(p)
        kuf = np.where(np.isfinite(ku), ku, 1.0)
        tuf = np.where(np.isfinite(tu), tu, 1.0)
        gzn = safe_gzn(kuf, tuf)

        zn = run_zn(p)
        rl = run_relay(p)
        cm = run_cmaes(p, gzn, budget=18, lam=6)
        hr = evaluate_head(
            head, p, gzn, kuf, tuf, iters=args.iters, value=None, use_value_filter=False
        )

        jev = np.median(hr.best_j)
        classical = np.array(
            [np.median(zn.best_j), np.median(rl.best_j), np.median(cm.best_j)]
        )
        best_classical = float(np.min(classical))
        ratio = float(jev / max(best_classical, 1e-9))
        wins = int(
            np.sum(
                hr.best_j <= np.minimum.reduce([zn.best_j, rl.best_j, cm.best_j]) * 1.05
            )
        )

        rows.append(
            {
                "scenario": name,
                "n": int(p.n),
                "jev_median": float(jev),
                "zn_median": float(np.median(zn.best_j)),
                "relay_median": float(np.median(rl.best_j)),
                "cmaes_median": float(np.median(cm.best_j)),
                "ratio_vs_best_classical": ratio,
                "plants_beaten": f"{wins}/{p.n}",
            }
        )
        print(
            f"{name:<20}{jev:>8.3f}{np.median(zn.best_j):>8.3f}"
            f"{np.median(rl.best_j):>8.3f}{np.median(cm.best_j):>8.3f}"
            f"{ratio:>8.2f}{wins:>4}/{p.n}"
        )

    ratios = np.array([r["ratio_vs_best_classical"] for r in rows])
    total_wins = sum(int(r["plants_beaten"].split("/")[0]) for r in rows)
    total_plants = sum(int(r["plants_beaten"].split("/")[1]) for r in rows)

    print("-" * len(header))
    print(
        f"head within 5 % of the best classical tuner on {total_wins}/{total_plants} plants "
        f"across {len(rows)} scenarios"
    )
    print(
        f"median cost ratio vs best classical: {np.median(ratios):.2f}x  "
        f"(1.00 = parity, <1 = head wins)"
    )

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(
            {
                "rows": rows,
                "plants_beaten": total_wins,
                "plants_total": total_plants,
                "median_ratio": float(np.median(ratios)),
                "draws_per_scenario": args.draws,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[gen] wrote {args.out}")


if __name__ == "__main__":
    main()
