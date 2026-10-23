"""Fine-tune the decision head on one plant family ("specialise").

The shipped head is trained on a broad zoo and is applied zero-shot.  When a
project sits outside that zoo, the supported path is a specialist: describe the
plant, generate a few dozen jittered variants, let the expert play them, and
fine-tune the existing head for a few epochs.

    python scripts/10_specialize.py --scenario valve_dead_zone --name valve
    python scripts/10_specialize.py --spec plant.json --name myplant   # {"num":[...],"den":[...],"delay_s":..}

Cost: ~1-2 min of CPU.  Output: models/specialized/<name>.pt plus a JSON report
comparing zero-shot and specialised on held-out jitters.
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
from jev_tune.expert import ExpertData, generate
from jev_tune.model import JevHead
from jev_tune.plants import make_plant, ultimate_gain
from jev_tune.scenarios import SPECS
from jev_tune.train import save, train_head
from _experiment_protocol import manifest


def build_family(args):
    """Jittered draws of one plant, split into train / held-out."""
    rng = np.random.default_rng(args.seed)
    if args.scenario:
        num, den, kw = SPECS[args.scenario]
        base = (np.array(num, float), np.array(den, float), kw)
    else:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        num, den = np.array(spec["num"], float), np.array(spec["den"], float)
        kw = {
            k: spec[k]
            for k in ("delay_s", "u_max", "noise_sigma", "dead_zone")
            if k in spec
        }
        base = (num, den, kw)

    num0, den0, kw0 = base
    plants = []
    for _ in range(args.plants):
        num_v = num0 * 10 ** rng.uniform(-args.jitter, args.jitter)
        den_v = den0.copy()
        idx = 0 if den_v[-1] == 0 else len(den_v) - 1
        den_v[idx] *= 10 ** rng.uniform(-args.jitter, args.jitter)
        kw_v = dict(kw0)
        if "delay_s" in kw_v:
            kw_v["delay_s"] = float(kw_v["delay_s"]) * rng.uniform(
                1 - args.jitter, 1 + args.jitter
            )
        plants.append(make_plant(num_v, den_v, name=args.name or "special", **kw_v))

    from jev_tune.scenarios import _stack

    allp = _stack(plants)
    n_eval = max(3, args.plants // 4)
    idx = rng.permutation(allp.n)
    train = allp.take(idx[n_eval:])
    held = allp.take(idx[:n_eval])
    return train, held


def load_head(models: str) -> JevHead:
    # fine-tuning starts from the shipped head; the fitted temperatures come
    # with it and are copied to the specialist below (they are not re-fitted)
    from jev_tune.decision import load_backend

    return load_backend(models).model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", help="a name from jev_tune.scenarios")
    ap.add_argument("--spec", help="JSON with num/den/delay_s for a custom plant")
    ap.add_argument("--name", default="special")
    ap.add_argument("--plants", type=int, default=48)
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--jitter", type=float, default=0.2)
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="models/specialized")
    ap.add_argument("--report", help="Optional versioned JSON report path")
    args = ap.parse_args()

    if not (args.scenario or args.spec):
        ap.error("pass --scenario or --spec")

    t0 = time.perf_counter()
    train, held = build_family(args)
    print(f"[spec] {train.n} train / {held.n} held-out plants", flush=True)

    data, _, _, gzn = generate(train, steps=args.steps, seed=args.seed, verbose=False)
    print(
        f"[spec] {len(data.feats)} states from expert rollouts "
        f"({time.perf_counter() - t0:.0f}s)",
        flush=True,
    )

    base = load_head(args.models)
    zero_shot_model = copy.deepcopy(base)  # train_head mutates its argument
    spec = train_head(
        data, epochs=args.epochs, lr=args.lr, seed=args.seed, model=base, verbose=False
    )
    # the fine-tune does not re-fit temperatures; inherit the base head's so the
    # zero-shot and specialist rows are calibrated identically
    if hasattr(zero_shot_model, "temperature"):
        spec.temperature = zero_shot_model.temperature
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    save(spec, out_dir / f"{args.name}.pt")
    # a specialist needs the same sidecars as the shipped head, otherwise the
    # MATLAB exporter and the CLI fall back to 5 actions and fail
    (out_dir / "meta.json").write_text(
        json.dumps(
            {
                "n_actions": int(spec.choice[0].out_features),
                "n_feats": int(spec.enc.mlp[0].in_features),
                "n_curve": 64,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    ku, tu = ultimate_gain(held)
    gzn_h = np.column_stack(
        [0.6 * ku, 1.2 * ku / np.maximum(tu, 1e-9), 0.075 * ku * tu]
    )
    zero = evaluate_head(
        zero_shot_model,
        held,
        gzn_h,
        ku,
        tu,
        budget=20,
        conformal=None,
        value=None,
        use_value_filter=False,
        seed=args.seed,
    )
    tuned = evaluate_head(
        spec,
        held,
        gzn_h,
        ku,
        tu,
        budget=20,
        conformal=None,
        value=None,
        use_value_filter=False,
        seed=args.seed,
    )

    z = float(np.median(zero.best_j))
    t = float(np.median(tuned.best_j))
    better = float(np.mean(tuned.best_j < zero.best_j * 0.98))
    worse = float(np.mean(tuned.best_j > zero.best_j * 1.02))
    report = {
        "name": args.name,
        "scenario": args.scenario or "custom",
        "train_plants": train.n,
        "heldout_plants": held.n,
        "steps": args.steps,
        "states": int(len(data.feats)),
        "zero_shot_median": z,
        "specialised_median": t,
        "improvement": (z - t) / z if z else 0.0,
        "zero_shot_mean": float(np.mean(zero.best_j)),
        "specialised_mean": float(np.mean(tuned.best_j)),
        "fraction_better": better,
        "fraction_worse": worse,
        "wall_s": time.perf_counter() - t0,
        "budget_per_plant": 20,
        "conformal": "disabled for both arms; a changed specialist needs its own independent CP calibration",
        "expert_simulation_counts": data.simulation_counts,
        "manifest": manifest(args, files=[Path(args.models) / "jev_head.pt", Path(args.models) / "calibration.json"]),
    }
    (out_dir / f"{args.name}.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"[spec] zero-shot J={z:.3f}  specialised J={t:.3f}  "
        f"improvement {report['improvement']:+.0%}  ({report['wall_s']:.0f}s)"
    )
    print(f"[spec] wrote {out_dir / (args.name + '.pt')}")


if __name__ == "__main__":
    main()
