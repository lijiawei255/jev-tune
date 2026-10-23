"""Head vs classical baselines on held-out plants, at one common budget.

Reference: a strong CMA-ES run (240 simulations per plant) defines the target
cost (1.05x). Iterative competitors have the same maximum ``--budget``;
one-shot methods report their actual lower cost. Priors are explicitly charged:

    zn                 1   analytic Ku/Tu (oracle: free frequency response)
    swept_zn           8   seven Kp tests for Ku/Tu + one verification run
    shrunk_zn          1   Z-N x fixed factors, chosen on the TRAIN families
    identify+pidtune   2   open-loop step fit + pidtune, one verification run
    simplex           20
    vocab_hill        20   greedy climb over the same vocabulary the head emits
    cmaes             20   measured common start + remaining search budget
    bo                20
    jev_head          20   analytic Ku/Tu in its features (oracle)
    jev_head_swept    20   seven Kp tests counted; failed sweeps use Ku=Tu=1

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
    TEST_FAMILIES,
    TRAIN_FAMILIES,
    estimate_ultimate_gain,
    sample_plants,
    ultimate_gain,
)
from _experiment_protocol import manifest


def load_head(models_dir: str):
    """The shipped head, through the one typed-decision entry point.

    Returns a backend (not a bare ``JevHead``) so the fitted temperatures from
    `calibration.json` are applied inside the loop, exactly as in the CLI and
    the MCP server.
    """
    from jev_tune.decision import load_backend

    return load_backend(models_dir)


def sweep_prior(ku, tu):
    """Shared documented non-oracle fallback; failed estimates never use truth."""
    ok = np.isfinite(ku) & np.isfinite(tu) & (ku > 0) & (tu > 0)
    return np.where(ok, ku, 1.), np.where(ok, tu, 1.), ok


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
        help="maximum experiments per plant for iterative methods",
    )
    ap.add_argument("--ref-budget", type=int, default=240)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="research/results")
    ap.add_argument("--table", default="")
    args = ap.parse_args()
    if args.budget < 2:
        ap.error("--budget must cover an initial response and at least one proposal")
    provenance = manifest(args, files=[Path(args.models)/"jev_head.pt",
        Path(args.models)/"calibration.json"], extra={"evaluation_seed": args.seed,
        "shrunk_zn_selection_seed": args.seed, "reference_seed": 11})
    head = load_head(args.models)
    if getattr(head, "conformal", None) is None:
        raise ValueError("the default benchmark requires split CP metadata; run 02_train.py --calibrate-only first")

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
        if name == "swept_zn" and args.budget < 8:
            print("[eval] swept_zn skipped: its seven-run prior plus verification exceeds the budget")
            continue
        t = time.perf_counter()
        r = fn()
        r.wall_s = time.perf_counter() - t
        results.append(r)
        print(
            f"  {name:16s} {r.wall_s:6.1f}s  J median={np.median(r.best_j):.3f}"
            f"  ({r.eval_axis[-1]:.0f} sims)"
        )

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
    sweep_start = time.perf_counter()
    ku_s, tu_s, sweep_sims = estimate_ultimate_gain(plants)
    sweep_wall = time.perf_counter() - sweep_start
    ku_s, tu_s, ok = sweep_prior(ku_s, tu_s)
    # Same available fallback as run_swept_zn; never reveal the analytic plant
    # oracle to only one competitor after an identification failure.
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
        hr_s.wall_s = time.perf_counter() - t + sweep_wall
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
                "decision_report": r.decision_report() if hasattr(r, "decision_report") else None,
                "rollbacks": int(r.rollbacks.sum()) if hasattr(r, "rollbacks") else None,
                "decision_policy": "temperature plus split CP; no pmax heuristic"
                if r.name in {"jev_head", "jev_head_swept"} else None,
                "oracle_access": "analytic Ku/Tu in initial gains and/or features"
                if r.name in {"zn_classic", "shrunk_zn", "simplex", "vocab_hill", "cmaes", "bo", "jev_head"}
                else "none",
                "initial_point": "analytic Z-N, measured within the budget"
                if r.name in {"simplex", "vocab_hill", "cmaes", "bo", "jev_head"}
                else "method-specific, charged in experiments",
                "fallback_policy": "Ku=1, Tu=1 on sweep failure"
                if r.name in {"swept_zn", "jev_head_swept"} else None,
                "fallback_plants": int((~ok).sum())
                if r.name in {"swept_zn", "jev_head_swept"} else 0,
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
        "evaluation_role": "frozen_test" if args.family in TEST_FAMILIES else "validation",
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
        "manifest": provenance,
        "calibration_evidence": json.loads((Path(args.models)/"calibration.json").read_text(encoding="utf-8")),
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
        "> [English](#english) · [简体中文](#简体中文)",
        "",
        "## English",
        "",
        f"Generated by `python scripts/03_evaluate.py --plants {payload['n_plants']} "
        f"--budget {payload['budget_per_plant']}"
        f"{(' --family ' + args.family) if args.family else ''}` on {date.today().isoformat()}.",
        "Iterative methods share a maximum budget; one-shot methods report their actual simulations.",
        "Both head rows use temperature scaling plus split CP monitor (no CP veto), without the legacy pmax threshold. CP label-set coverage is not a guarantee of closed-loop improvement or safety.",
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
            "same Ku=Tu=1 fallback as `swept_zn` for the rest. Neither swept "
            "row receives analytic Ku/Tu on failure. These rows include "
            "identification failures rather than demonstrating a reliable identifier.",
            "",
        ]
    lines += [
        "## 简体中文", "",
        f"由上面的命令生成。对象数{payload['n_plants']}，族{payload['families']}，"
        f"角色为`{payload['evaluation_role']}`。迭代方法最多使用{payload['budget_per_plant']}次实验，"
        "包含实际评估的共同起点；一次性方法按表中实际次数计费，不能说每种方法都恰好20次。",
        "两个head行均使用温度缩放与Split CP monitor（不按集合否决），不叠加旧pmax阈值。CP标签集合覆盖不等于闭环改善或安全保证。",
        "",
        "表中的final J为最终返回增益对应的实测代价；success为达到参考目标的比例，"
        "sims to target只对达到目标的对象统计。CMA/BO/simplex/hill/head的共同ZN初值使用"
        "解析Ku/Tu，这是已知模型提供的特权信息；离线训练和缩小ZN先验选择成本单列。",
        "",
        f"两种swept方法均支付{payload['sweep_sims_per_plant']}次扫描成本；"
        f"本次扫描成功{payload['sweep_recovered']}/{payload['n_plants']}株。失败时两者均使用"
        "Ku=Tu=1，不回填解析真值。结果包含辨识失败，不能据此宣称扫描器可靠。"
        "JSON的每个方法行记录oracle信息、初值和回退策略，manifest记录参数、源代码及权重hash。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
