"""Does the shipped head handle a moving reference? (no -- it was trained on steps)

This is the honest demonstration behind the "objective must match" caveat:

    step-trained head   applied to a disturbance -> cost stays high
    disturbance-trained applied to a disturbance -> cost drops

Both are measured on the same plant family with the same 20-experiment budget.
The tracking specialist is produced by the same specialist flow, only with the
disturbance profile and the disturbance cost.
"""

from __future__ import annotations

import argparse
import copy
import json
import time
from pathlib import Path

import numpy as np
import torch

from jev_tune.evaluate import evaluate_head
from jev_tune.expert import generate
from jev_tune.model import JevHead
from jev_tune.plants import PlantSet, sample_plants, simulate, ultimate_gain
from jev_tune.train import train_head

SIM = dict(profile="step", disturb_amp=0.4, disturb_time=5.0)
OBJECTIVE = "disturbance"


def load_head(models: str) -> JevHead:
    from jev_tune.decision import load_backend

    return load_backend(models).model


def ramp_cost(plants, gains, *, horizon=10.0, ref=1.0):
    from jev_tune.metrics import cost_from_metrics

    res = simulate(plants, gains, **SIM)
    return cost_from_metrics(
        res["metrics"],
        horizon=horizon,
        ref=ref,
        y_curve=res["y_curve"],
        objective="tracking",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plants", type=int, default=60)
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="research/results/tracking.json")
    args = ap.parse_args()

    t0 = time.perf_counter()
    train_p = sample_plants(args.plants, seed=args.seed)
    held_p = sample_plants(24, seed=args.seed + 100)

    # expert rollouts on the *tracking* task
    data, _, _, _ = generate(
        train_p,
        steps=args.steps,
        seed=args.seed,
        verbose=False,
        objective=OBJECTIVE,
        **SIM,
    )
    print(
        f"[track] {len(data.feats)} states ({time.perf_counter() - t0:.0f}s)",
        flush=True,
    )

    base = load_head(args.models)
    zero_shot = copy.deepcopy(base)
    spec = train_head(
        data, epochs=args.epochs, lr=args.lr, seed=args.seed, model=base, verbose=False
    )
    Path("models/specialized").mkdir(parents=True, exist_ok=True)
    torch.save(spec.state_dict(), "models/specialized/tracking.pt")

    ku, tu = ultimate_gain(held_p)
    gzn = np.column_stack([0.6 * ku, 1.2 * ku / np.maximum(tu, 1e-9), 0.075 * ku * tu])

    results = {}
    for name, model in (("zero_shot", zero_shot), ("tracking_specialist", spec)):
        r = evaluate_head(
            model,
            held_p,
            gzn,
            ku,
            tu,
            iters=20,
            value=None,
            use_value_filter=False,
            seed=args.seed,
            objective=OBJECTIVE,
            **SIM,
        )
        results[name] = float(np.median(r.best_j))
        print(f"[track] {name:<20} median J {results[name]:.3f}", flush=True)

    gain = (results["zero_shot"] - results["tracking_specialist"]) / results[
        "zero_shot"
    ]
    report = {
        "task": "disturbance rejection",
        "profile": SIM,
        "plants_train": int(train_p.n),
        "plants_heldout": int(held_p.n),
        "states": int(len(data.feats)),
        "zero_shot_median": results["zero_shot"],
        "specialist_median": results["tracking_specialist"],
        "improvement": float(gain),
        "wall_s": time.perf_counter() - t0,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[track] improvement {gain:+.0%}  ({report['wall_s']:.0f}s) -> {args.out}")


if __name__ == "__main__":
    main()
