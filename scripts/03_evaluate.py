"""Head vs classical baselines on held-out plants, at one common budget.

Reference: a strong CMA-ES run (240 simulations per plant) defines the target
cost (1.05x).  *Every competitor below gets the same ``--budget`` experiments
per plant*, including the ones a method needs to estimate its own priors:

    zn                 1   analytic Ku/Tu (oracle: free frequency response)
    relay_zn           2   relay experiment for Ku/Tu + one verification run
    shrunk_zn          1   Z-N x fixed factors, chosen on the TRAIN families
    identify+pidtune   2   open-loop step fit + pidtune, one verification run
    simplex           20
    vocab_hill        20   greedy climb over the same vocabulary the head emits
    cmaes             20   same budget, small population (7 generations)
    bo                20
    jev_head          20   analytic Ku/Tu in its features (oracle)
    jev_head_relay    20   relay-estimated Ku/Tu, relay counted as experiment 1

The head's training cost is paid once off-line and is not in its per-plant
budget; see the caveat printed at the end and in ``docs/BENCHMARK.md``.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

import numpy as np

from jev_tune.baselines import (
    choose_zn_shrink,
    run_bo,
    run_cmaes,
    run_shrunk_zn,
    run_simplex,
    run_swept_zn,
    run_vocab_hill,
    run_zn,
    zn_gains,
)
from jev_tune.evaluate import evaluate_head
from jev_tune.identified import run_identify_pidtune
from jev_tune.matlab_baseline import matlab_available
from jev_tune.model import JevHead
from jev_tune.plants import (
    HELDOUT_FAMILIES,
    TRAIN_FAMILIES,
    estimate_ultimate_gain,
    sample_plants,
    ultimate_gain,
)


def load_head(models_dir: str):
    """The shipped head, through the one typed-decision entry point.

    Returns a backend (not a bare ``JevHead``) so the fitted temperatures from
    `calibration.json` are applied inside the loop, exactly as in the CLI and
    the MCP server.
    """
    from jev_tune.decision import load_backend

    return load_backend(models_dir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plants", type=int, default=120)
    ap.add_argument("--heldout", action="store_true", default=True)
    ap.add_argument(
        "--family",
        default="",
        help="evaluate one family by name (e.g. thermal_deadtime, the frozen "
        "test family); default: the held-out family",
    )
    ap.add_argument(
        "--budget",
        type=int,
        default=20,
        help="experiments per plant, identical for every method",
    )
    ap.add_argument("--ref-budget", type=int, default=240)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="research/results")
    ap.add_argument("--table", default="")
    args = ap.parse_args()

    Path(args.out).mkdir(parents=True, exist_ok=True)
    if args.family:
        fams = (args.family,)
        tag = args.family
    else:
        fams = HELDOUT_FAMILIES if args.heldout else TRAIN_FAMILIES
        tag = "heldout" if args.heldout else "train"
    table_path = args.table or (
        "research/results/benchmark_table.md"
        if not args.family
        else f"research/results/benchmark_table_{tag}.md"
    )
    plants = sample_plants(
        args.plants,
        seed=args.seed,
        families=fams,
        heldout=args.heldout and not args.family,
    )
    print(
        f"[eval] {plants.n} plants: {sorted(set(plants.family))} ({tag}),"
        f" budget {args.budget} experiments/plant"
    )

    ku, tu = ultimate_gain(plants)
    gzn = np.column_stack([0.6 * ku, 1.2 * ku / tu, 0.075 * ku * tu])
    x0 = zn_gains(plants)

    results = []

    t = time.perf_counter()
    print("[eval] strong reference (CMA-ES 240)...")
    ref = run_cmaes(plants, x0, budget=args.ref_budget, lam=8, seed=11)
    j_ref = ref.best_j.copy()
    target = 1.05 * np.maximum(j_ref, 0.02)
    print(
        f"  reference J median={np.median(j_ref):.3f} ({time.perf_counter() - t:.0f}s)"
    )

    # a one-shot prior, fitted on the training zoo, is still a fair competitor:
    # its selection cost is reported, and it costs 1 experiment at deployment.
    train = sample_plants(120, seed=args.seed, families=TRAIN_FAMILIES)
    factors, train_j, n_sel = choose_zn_shrink(train)
    print(
        f"[eval] shrunk Z-N factors {factors} (train median {train_j:.3f}, "
        f"{n_sel} sims/train plant)"
    )

    for name, fn in (
        ("zn", lambda: run_zn(plants)),
        ("swept_zn", lambda: run_swept_zn(plants)),
        ("shrunk_zn", lambda: run_shrunk_zn(plants, factors)),
        ("identify+pidtune", lambda: run_identify_pidtune(plants)),
        ("simplex", lambda: run_simplex(plants, x0, budget=args.budget)),
        ("vocab_hill", lambda: run_vocab_hill(plants, x0, budget=args.budget)),
        ("cmaes", lambda: run_cmaes(plants, x0, budget=args.budget, lam=4)),
        ("bo", lambda: run_bo(plants, x0, budget=args.budget, n_init=6)),
    ):
        t = time.perf_counter()
        r = fn()
        r.wall_s = time.perf_counter() - t
        results.append(r)
        print(
            f"  {name:16s} {r.wall_s:6.1f}s  J median={np.median(r.best_j):.3f}"
            f"  ({r.eval_axis[-1]:.0f} sims)"
        )

    head = load_head(args.models)

    t = time.perf_counter()
    hr = evaluate_head(
        head,
        plants,
        gzn,
        ku,
        tu,
        budget=args.budget,
        value=None,
        use_value_filter=False,
        seed=args.seed,
    )
    results.append(hr)
    print(
        f"  {'jev_head':16s} {hr.wall_s:6.1f}s  J median={np.median(hr.best_j):.3f}"
        f"  ({hr.sims_per_plant:.0f} sims)"
    )

    # same head, but Ku/Tu come from the 7-run Kp sweep a real installation
    # must do; those seven experiments are charged to its budget
    ku_s, tu_s, sweep_sims = estimate_ultimate_gain(plants)
    ok = np.isfinite(ku_s) & np.isfinite(tu_s) & (ku_s > 0) & (tu_s > 0)
    ku_s = np.where(ok, ku_s, ku)
    tu_s = np.where(ok, tu_s, tu)
    gzn_s = np.column_stack([0.6 * ku_s, 1.2 * ku_s / tu_s, 0.075 * ku_s * tu_s])
    if args.budget - sweep_sims < 2:
        print(
            f"[eval] budget {args.budget} is too small to pay for the "
            f"{sweep_sims}-run Ku/Tu sweep and still tune; jev_head_swept skipped"
        )
        hr_s = None
    else:
        t = time.perf_counter()
        hr_s = evaluate_head(
            head,
            plants,
            gzn_s,
            ku_s,
            tu_s,
            budget=args.budget - sweep_sims,
            value=None,
            use_value_filter=False,
            seed=args.seed,
            sims_already_spent=sweep_sims,
        )
        hr_s.name = "jev_head_swept"
        hr_s.wall_s = time.perf_counter() - t
        results.append(hr_s)
        print(
            f"  {'jev_head_swept':16s} {hr_s.wall_s:6.1f}s  "
            f"J median={np.median(hr_s.best_j):.3f}  ({hr_s.sims_per_plant:.0f} sims)"
        )
    if hr_s is not None:
        hr_s.name = "jev_head_swept"
    print(
        f"[eval] Kp sweep recovered Ku on {int(ok.sum())}/{plants.n} plants "
        f"({sweep_sims} sims/plant)"
    )

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
                "budget": int(r.eval_axis[-1]),
                "wall_s": float(getattr(r, "wall_s", 0.0)),
            }
        )

    rows.sort(key=lambda x: (-x["success_rate"], x["sims_to_target_median"]))
    print(f"\n=== held-out comparison (target = 1.05 x CMA-ES-{args.ref_budget}) ===")
    hdr = (
        f"{'method':<18}{'final med':>10}{'p90':>8}{'x ref':>8}{'success':>9}"
        f"{'sims med':>10}{'sims p90':>10}{'budget':>8}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['method']:<18}{r['final_cost_median']:>10.3f}{r['final_cost_p90']:>8.3f}"
            f"{r['ratio_to_ref']:>8.2f}{r['success_rate']:>9.1%}"
            f"{r['sims_to_target_median']:>10.1f}{r['sims_to_target_p90']:>10.1f}"
            f"{r['budget']:>8d}"
        )

    out = Path(args.out) / f"eval_{tag}_{args.plants}.json"
    payload = {
        "n_plants": plants.n,
        "families": sorted(set(plants.family)),
        "evaluation": tag,
        "heldout": bool(args.heldout and not args.family),
        "budget_per_plant": args.budget,
        "ref_budget": args.ref_budget,
        "reference_j_median": float(np.median(j_ref)),
        "shrunk_zn": {
            "factors": list(factors),
            "selection_sims_per_train_plant": n_sel,
            "train_median": float(train_j),
        },
        "sweep_recovered": int(ok.sum()),
        "sweep_sims_per_plant": int(sweep_sims),
        "matlab_available": bool(matlab_available()),
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
    Path(table_path).write_text(_markdown(payload, args), encoding="utf-8")
    print(f"\n[eval] wrote {out} and {table_path}")


def _markdown(payload: dict, args) -> str:
    rows = payload["rows"]
    lines = [
        "# Benchmark: head vs baselines at one common budget",
        "",
        f"Generated by `python scripts/03_evaluate.py --plants {payload['n_plants']} "
        f"--budget {payload['budget_per_plant']}` on {date.today().isoformat()}.",
        "Every method spends the same number of closed-loop simulations per plant.",
        "",
        f"* plants: {payload['n_plants']}, families {payload['families']}, "
        f"heldout={payload['heldout']}",
        f"* target: 1.05 x CMA-ES-{payload['ref_budget']} reference "
        f"(median J {payload['reference_j_median']:.3f})",
        f"* shrunk Z-N factors: {payload['shrunk_zn']['factors']}, chosen on the "
        f"training families with {payload['shrunk_zn']['selection_sims_per_train_plant']} "
        "simulations/plant",
        "",
        "| method | final J (median) | final J (p90) | x reference | success | "
        "sims to target (median) | budget |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        lines.append(
            f"| `{r['method']}` | {r['final_cost_median']:.3f} | "
            f"{r['final_cost_p90']:.3f} | {r['ratio_to_ref']:.2f} | "
            f"{100 * r['success_rate']:.0f}% | {r['sims_to_target_median']:.1f} | "
            f"{r['budget']} |"
        )
    lines += [
        "",
        "The head's training cost is paid once, off-line, and is not in its "
        "per-plant budget. `jev_head` gets analytic Ku/Tu (an oracle a real "
        "installation does not have); `jev_head_swept` pays the 7-run Kp sweep "
        "the Simulink bridge does and is charged 7 of its 20 experiments.",
        "",
        "`relay_zn` is kept in `baselines.py` but not reported: on the held-out "
        "family the relay did not sustain a limit cycle, so the row would have "
        "been a constant gain set rather than a relay tuner. `swept_zn` replaces "
        "it and is charged 8 experiments (7-point sweep + one verification run).",
        "",
    ]
    recovered = payload.get("sweep_recovered")
    if recovered is not None and recovered < payload["n_plants"]:
        lines += [
            f"**The Kp sweep only recovered Ku on {recovered} of "
            f"{payload['n_plants']} plants.** `jev_head_swept` falls back to the "
            "analytic Ku/Tu for the rest, so on those plants it is the oracle "
            "head minus seven experiments; `swept_zn` falls back to Ku = 1, which "
            "is why its row is far worse than plain Z-N. Read both rows with "
            "that in mind.",
            "",
        ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
