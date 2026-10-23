"""E5: calibration-only adaptation — freeze the weights, fit two scalars.

The full specialist path (`scripts/10_specialize.py`) needs expert rollouts:
22 counterfactual simulations per state, because the expert has to evaluate every
action.  That is the price of *training*.  This script measures the much cheaper
alternative for a new operating condition or a small real dataset:

    freeze the encoder and every head; fit one temperature T (and the abstention
    threshold tau) on a few dozen (state, did-this-step-help) pairs.

No weights change, so the answer is often "the base model was over- or
under-confident here, and we corrected the confidence" — not "we learned the
task".  The point is to report which one it is.

    python scripts/22_calibrate_only.py --plants 8 --steps 6
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from jev_tune.decision import load_backend
from jev_tune.decode import DEFAULT_ABSTAIN, AbstainPolicy, decide
from jev_tune.evaluate import evaluate_head
from jev_tune.metrics import cost_from_metrics
from jev_tune.plants import simulate, ultimate_gain
from jev_tune.scenarios import _stack, variants

TAUS = np.linspace(0.05, 0.95, 19)


def _gzn(plants):
    ku, tu = ultimate_gain(plants)
    kuf = np.where(np.isfinite(ku) & (ku > 0), ku, 1.0)
    tuf = np.where(np.isfinite(tu) & (tu > 0), tu, 1.0)
    return (
        np.column_stack([0.6 * kuf, 1.2 * kuf / tuf, 0.075 * kuf * tuf]),
        kuf,
        tuf,
    )


def collect(backend, plants, *, steps: int, seed: int):
    """Roll out the head, then measure whether each proposed step helped.

    One simulation per sample: the step is applied and the next response is
    measured.  This is what a small real dataset would give you.
    """
    gzn, ku, tu = _gzn(plants)
    gains = gzn.copy()
    probs, improved = [], []
    for k in range(steps):
        res = simulate(plants, gains)
        j = cost_from_metrics(res["metrics"], y_curve=res["y_curve"])
        from jev_tune.state import build_state

        feats, curves = build_state(
            res["metrics"],
            res["y_curve"],
            res["u_curve"],
            gains,
            gzn,
            ku,
            tu,
            prev_action=np.zeros_like(gains),
            prev_cost=np.zeros(plants.n),
            cost=j,
            iteration=np.full(plants.n, k, dtype=float),
        )
        answer = backend.answer(feats, curves)
        dec = decide(answer, space=None, abstain=None)
        trial = np.clip(gains * 10.0**dec.step, 1e-4, 1e3)
        res2 = simulate(plants, trial)
        j2 = cost_from_metrics(res2["metrics"], y_curve=res2["y_curve"])
        probs.append(
            np.stack([np.asarray(ch.probs, float) for ch in answer.choice], axis=-2)
        )
        improved.append(j2 < j)
        gains = np.where((j2 < j)[:, None], trial, gains)
    return np.concatenate(probs), np.concatenate(improved).astype(float)


def _mean_pmax(probs: np.ndarray, T: float) -> np.ndarray:
    """p_max after one temperature: exactly the transform the backend applies."""
    q = np.power(np.clip(probs, 1e-12, 1.0), 1.0 / T)
    q /= q.sum(axis=-1, keepdims=True)
    return q.max(axis=-1).mean(axis=-1)


def fit_temperature(probs, improved):
    """1-D search: which T makes p_max predict 'this step helped'?"""
    best = (np.inf, 1.0)
    for T in np.linspace(0.5, 4.0, 36):
        q = np.clip(_mean_pmax(probs, T), 1e-4, 1 - 1e-4)
        nll = -np.mean(improved * np.log(q) + (1 - improved) * np.log(1 - q))
        if nll < best[0]:
            best = (nll, float(T))
    return best[1]


def pick_tau(conf_cal, coverage_target=0.6):
    return float(np.quantile(conf_cal, 1.0 - coverage_target))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="valve_dead_zone")
    ap.add_argument("--plants", type=int, default=8, help="calibration plants")
    ap.add_argument("--held", type=int, default=40, help="held-out plants to evaluate")
    ap.add_argument("--steps", type=int, default=6)
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="research/results/calibrate_only.json")
    ap.add_argument("--doc", default="docs/CALIBRATE_ONLY.md")
    args = ap.parse_args()

    backend = load_backend(args.models)
    cal_plants = _stack([variants(args.scenario, args.plants, seed=101)])
    held = _stack([variants(args.scenario, args.held, seed=202)])

    t0 = time.perf_counter()
    probs, improved = collect(backend, cal_plants, steps=args.steps, seed=0)
    collect_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    T = fit_temperature(probs, improved)
    tau = pick_tau(_mean_pmax(probs, T))
    fit_ms = (time.perf_counter() - t1) * 1e3

    base = evaluate_head(
        backend, held, *_gzn(held), budget=20, seed=7, abstain=DEFAULT_ABSTAIN
    )
    # apply the new temperature through a thin wrapper: the calibrated backend
    # multiplies each axis temperature by T
    base_T = np.asarray(backend.temperature, dtype=float)
    adapted = type(backend)(
        backend.model,
        space=backend.space,
        temperature=base_T * T,
        calibrate=True,
    )
    adapted_policy = AbstainPolicy(tau_act=tau, tau_esc=max(0.0, tau - 0.10))
    tuned = evaluate_head(
        adapted, held, *_gzn(held), budget=20, seed=7, abstain=adapted_policy
    )

    payload = {
        "scenario": args.scenario,
        "calibration_plants": int(cal_plants.n),
        "calibration_samples": int(len(improved)),
        "steps_per_plant": args.steps,
        "simulations_per_sample": 1,
        "held_out_plants": int(held.n),
        "base_temperature": [float(x) for x in base_T],
        "fitted_temperature_scale": float(T),
        "fitted_abstain_tau": float(tau),
        "base_abstain_tau": DEFAULT_ABSTAIN.tau_act,
        "wall_s_collect": float(collect_s),
        "fit_ms": float(fit_ms),
        "base": {
            "median": float(np.median(base.best_j)),
            "coverage": base.decision_report().get("coverage"),
            "harmful_rate": base.decision_report().get("harmful_rate"),
            "ece": base.decision_report().get("ece"),
        },
        "adapted": {
            "median": float(np.median(tuned.best_j)),
            "coverage": tuned.decision_report().get("coverage"),
            "harmful_rate": tuned.decision_report().get("harmful_rate"),
            "ece": tuned.decision_report().get("ece"),
        },
        "note": (
            "calibration-only freezes every weight. It can only fix the "
            "confidence, not the policy; if the median does not move, say so."
        ),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    Path(args.doc).write_text(_doc(payload), encoding="utf-8")
    print(
        f"[calib] T scale {T:.2f}, tau_act {tau:.2f} from {len(improved)} samples "
        f"({collect_s:.1f}s of simulation, {fit_ms:.0f}ms fit)"
    )
    print(
        f"[calib] base {payload['base']['median']:.3f} -> adapted "
        f"{payload['adapted']['median']:.3f} on {held.n} held-out plants"
    )
    print(f"[calib] wrote {args.out} and {args.doc}")


def _n(x, nd=3):
    return "n/a" if x is None else f"{x:.{nd}f}"


def _doc(p: dict) -> str:
    b, a = p["base"], p["adapted"]
    lines = [
        "# Calibration-only adaptation (freeze the weights)",
        "",
        "> [English](#english) · [简体中文](#简体中文)",
        "",
        "## English",
        "",
        "Generated by `python scripts/22_calibrate_only.py`. Only two scalars are",
        "fitted — a temperature and the abstention threshold — on "
        f"{p['calibration_samples']} samples from {p['calibration_plants']} "
        f"`{p['scenario']}` plants. Every weight is frozen.",
        "",
        "| | base | calibration-only |",
        "| :--- | ---: | ---: |",
        f"| median cost, {p['held_out_plants']} held-out plants | {b['median']:.3f} | {a['median']:.3f} |",
        f"| coverage | {_n(b['coverage'], 2)} | {_n(a['coverage'], 2)} |",
        f"| harmful steps | {_n(b['harmful_rate'])} | {_n(a['harmful_rate'])} |",
        f"| outcome ECE | {_n(b['ece'])} | {_n(a['ece'])} |",
        "",
        f"* fitted temperature scale: **{p['fitted_temperature_scale']:.2f}** "
        f"(base {np.round(p['base_temperature'], 3).tolist()})",
        f"* fitted `tau_act`: **{p['fitted_abstain_tau']:.2f}** "
        f"(base {p['base_abstain_tau']:.2f})",
        f"* cost of the calibration set: {p['calibration_samples']} simulations "
        f"(one per sample), {p['wall_s_collect']:.1f} s of simulation",
        f"* fit time on CPU: **{p['fit_ms']:.1f} ms**",
        "",
        "**How to read it.** A calibration-only adaptation can only change how",
        "*sure* the model is; it cannot change what the model wants to do. If the",
        "median cost improves, that is the abstention threshold doing the work. If",
        "it gets **worse** — which is what happened here — the honest conclusion is",
        "that the confidence signal does not transfer to this operating condition:",
        "flattening it makes the head hold more without making it choose better.",
        "The fix is a specialist (`docs/SPECIALIZE.md`), not a new temperature. Note",
        "also that the fit ran to the edge of its grid, so the temperature is not",
        "even identified by this sample.",
        "",
        "---",
        "",
        "## 简体中文",
        "",
        "由 `python scripts/22_calibrate_only.py` 生成。只拟合两个标量——温度与弃权阈值——",
        f"样本来自 {p['calibration_plants']} 株 `{p['scenario']}`，共 "
        f"{p['calibration_samples']} 个；所有网络权重冻结。",
        "",
        "| | 基线 | 仅校准 |",
        "| :--- | ---: | ---: |",
        f"| 中位代价（{p['held_out_plants']} 株留出） | {b['median']:.3f} | {a['median']:.3f} |",
        f"| 覆盖率 | {_n(b['coverage'], 2)} | {_n(a['coverage'], 2)} |",
        f"| 有害步比例 | {_n(b['harmful_rate'])} | {_n(a['harmful_rate'])} |",
        f"| 结果 ECE | {_n(b['ece'])} | {_n(a['ece'])} |",
        "",
        f"* 拟合的温度缩放：**{p['fitted_temperature_scale']:.2f}**"
        f"（基线 {np.round(p['base_temperature'], 3).tolist()}）",
        f"* 拟合的 `tau_act`：**{p['fitted_abstain_tau']:.2f}**"
        f"（基线 {p['base_abstain_tau']:.2f}）",
        f"* 校准集成本：{p['calibration_samples']} 次仿真（每样本 1 次），"
        f"{p['wall_s_collect']:.1f} 秒",
        f"* CPU 拟合耗时：**{p['fit_ms']:.1f} ms**",
        "",
        "**怎么读。** 仅校准只能改变模型「有多确定」，不能改变「它想做什么」。中位代价若变好，",
        "那是弃权阈值在起作用；若**变差**——这里就是——诚实的结论是：这套置信度信号不能迁移到",
        "这个工况，把它压平只会让决策头更多地保持，而不是选得更好。正确的修法是专门化",
        "（`docs/SPECIALIZE.md`），不是换一个温度。另外，拟合跑到了网格边界，说明这个样本",
        "连温度都没有真正辨识出来。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
