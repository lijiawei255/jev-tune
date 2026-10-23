"""Robustness sweep: does the tuner ever make a plant worse than it found it?

The benchmark answers "how good is it on average". This answers the question a
practitioner actually asks before pointing it at their loop: **if I let it run,
can it blow my plant up?**

Three populations, all zero-shot:

    zoo       120 plants across the six training families (in-distribution)
    heldout    40 two-mass resonant plants (unseen family)
    outofzoo   10 scenarios x 4 jitters (dead band, unstable, inverse response…)

For each plant: cost at the Z-N start, best cost reached, how many safety-gate
rollbacks fired, and whether the final answer is worse than the start.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from jev_tune.evaluate import evaluate_head
from jev_tune.metrics import DIVERGED_J
from jev_tune.model import JevHead
from jev_tune.plants import (
    HELDOUT_FAMILIES,
    TRAIN_FAMILIES,
    sample_plants,
    ultimate_gain,
)
from jev_tune.scenarios import names as scenario_names
from jev_tune.scenarios import variants


def load_head(models: str) -> JevHead:
    from jev_tune.decision import load_backend

    return load_backend(models).model


def run_group(head, plants, label, *, gate: bool, seed: int = 0):
    ku, tu = ultimate_gain(plants)
    kuf = np.where(np.isfinite(ku) & (ku > 0), ku, 1.0)
    tuf = np.where(np.isfinite(tu) & (tu > 0), tu, 1.0)
    gzn = np.column_stack(
        [0.6 * kuf, 1.2 * kuf / np.maximum(tuf, 1e-9), 0.075 * kuf * tuf]
    )

    r = evaluate_head(
        head,
        plants,
        gzn,
        kuf,
        tuf,
        iters=20,
        value=None,
        use_value_filter=False,
        safety_gate=gate,
        seed=seed,
    )
    start = r.history[:, 0]
    final = r.best_j
    ratio = final / np.maximum(start, 1e-9)

    diverged = final >= DIVERGED_J
    improved = final < start * 0.98
    unchanged = np.abs(ratio - 1.0) <= 0.02
    worse = ratio > 1.02

    return {
        "group": label,
        "n": int(plants.n),
        "gate": gate,
        "start_median": float(np.median(start)),
        "final_median": float(np.median(final)),
        "improved_pct": float(100 * improved.mean()),
        "unchanged_pct": float(100 * unchanged.mean()),
        "worse_pct": float(100 * worse.mean()),
        "worst_ratio": float(np.max(ratio)),
        "diverged": int(diverged.sum()),
        "rollbacks_total": int(0 if r.rollbacks is None else r.rollbacks.sum()),
        "plants_rolling_back": int(
            0 if r.rollbacks is None else (r.rollbacks > 0).sum()
        ),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="research/results/robustness.json")
    args = ap.parse_args()

    head = load_head(args.models)

    zoo = sample_plants(120, seed=11, families=TRAIN_FAMILIES)
    held = sample_plants(40, seed=12, families=HELDOUT_FAMILIES, heldout=True)
    scenarios = []
    for nm in scenario_names():
        scenarios.append(variants(nm, 4, seed=3))
    from jev_tune.scenarios import _stack

    ood = _stack(scenarios)

    rows = []
    print(
        f"{'group':<12}{'n':>4}{'start J':>9}{'final J':>9}{'better':>8}{'same':>7}{'worse':>7}{'worst':>8}{'rollback':>9}{'diverged':>9}"
    )
    print("-" * 92)
    for label, plants in (("zoo", zoo), ("heldout", held), ("outofzoo", ood)):
        for gate in (True,):
            row = run_group(head, plants, label, gate=gate)
            rows.append(row)
            print(
                f"{label:<12}{row['n']:>4}{row['start_median']:>9.3f}{row['final_median']:>9.3f}"
                f"{row['improved_pct']:>7.0f}%{row['unchanged_pct']:>6.0f}%{row['worse_pct']:>6.0f}%"
                f"{row['worst_ratio']:>8.2f}{row['rollbacks_total']:>9d}{row['diverged']:>9d}"
            )

    # how much the gate buys: same populations with it disabled
    print()
    for label, plants in (("outofzoo", ood),):
        row = run_group(head, plants, label, gate=False)
        rows.append(row)
        print(
            f"{label} (no gate): worse {row['worse_pct']:.0f}%, worst ratio {row['worst_ratio']:.2f}, "
            f"diverged {row['diverged']}"
        )

    total = sum(r["n"] for r in rows if r["gate"])
    worse = sum(r["worse_pct"] * r["n"] for r in rows if r["gate"]) / 100
    print(
        f"\nsummary: {total - worse:.0f}/{total} plants end at or better than the Z-N start "
        f"({100 * (1 - worse / total):.0f}%), {sum(r['diverged'] for r in rows if r['gate'])} diverged, "
        f"{sum(r['rollbacks_total'] for r in rows if r['gate'])} rollbacks"
    )

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"rows": rows}, indent=2), encoding="utf-8")
    print(f"[robust] wrote {args.out}")


if __name__ == "__main__":
    main()
