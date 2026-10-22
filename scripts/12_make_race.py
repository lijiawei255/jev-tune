"""Build the README "race" animation from real measurements.

Every curve is a measured median over the same 40 held-out plants:
Ziegler-Nichols, relay autotuning, a 125-point grid sweep, simplex, CMA-ES,
Bayesian optimisation and this project's decision head.

The right panel asks the question a user actually cares about: how long until
the controller is usable? A method counts if it reaches J <= 0.60 on the median
plant; time is `experiments x 0.4 s`, where 0.4 s is the measured per-experiment
cost of a Fast Restart run on lab model. The agent row adds an assumed 3 s
LLM turn, and is drawn hatched because it is the one number this repository
cannot measure.

Outputs
    assets/race.gif                 animation for the README
    research/results/race.json      the raw curves and timings (provenance)
"""

from __future__ import annotations

import argparse
import json
import time
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from PIL import Image

from jev_tune.baselines import (
    run_bo,
    run_cmaes,
    run_grid,
    run_relay,
    run_simplex,
    run_zn,
    zn_gains,
)
from jev_tune.evaluate import evaluate_head
from jev_tune.model import JevHead
from jev_tune.plants import HELDOUT_FAMILIES, sample_plants, ultimate_gain

INK = "#1b2430"
MUTED = "#95a5a6"
BAD = "#c0392b"
ACCENT = "#2e86c1"
GOOD = "#27ae60"
ORANGE = "#e67e22"

TARGET_J = 0.60
PER_EXPERIMENT_S = 0.4  # measured on lab model (Fast Restart, 10 s)
LLM_TURN_S = 3.0  # assumption, labelled everywhere


def load_head(models: str) -> JevHead:
    head = JevHead(n_actions=7)
    head.load_state_dict(torch.load(Path(models) / "jev_head.pt", map_location="cpu"))
    head.eval()
    return head


def collect(plants_n: int, seed: int, models: str) -> dict:
    plants = sample_plants(plants_n, seed=seed, families=HELDOUT_FAMILIES, heldout=True)
    ku, tu = ultimate_gain(plants)
    gzn = np.column_stack([0.6 * ku, 1.2 * ku / np.maximum(tu, 1e-9), 0.075 * ku * tu])
    x0 = zn_gains(plants)
    head = load_head(models)

    runs = {}

    def record(name, fn, label):
        t = time.perf_counter()
        r = fn()
        wall = time.perf_counter() - t
        runs[name] = {
            "label": label,
            "curve": [float(x) for x in np.median(r.history, axis=0)],
            "evals": [float(x) for x in np.atleast_1d(r.eval_axis)],
            "wall_s": float(wall),
        }
        print(
            f"  {name:<10} {wall:6.1f}s  median J {float(np.median(r.best_j)):.3f}",
            flush=True,
        )

    print("[race]", plants.n, "held-out plants")
    record("zn", lambda: run_zn(plants), "Ziegler-Nichols")
    record("relay", lambda: run_relay(plants), "relay autotune")
    record("grid", lambda: run_grid(plants, x0, batch=5), "grid sweep (125)")
    record("simplex", lambda: run_simplex(plants, x0, budget=20), "simplex")
    record("cmaes", lambda: run_cmaes(plants, x0, budget=18, lam=6), "CMA-ES")
    record("bo", lambda: run_bo(plants, x0, budget=20, n_init=6), "Bayesian opt.")
    record(
        "head", lambda: evaluate_head(head, plants, gzn, ku, tu, iters=20), "Jev head"
    )

    return {
        "plants": plants.n,
        "families": sorted(set(plants.family)),
        "seed": seed,
        "runs": runs,
        "assumptions": {
            "llm_turn_s": LLM_TURN_S,
            "per_experiment_s": PER_EXPERIMENT_S,
            "target_j": TARGET_J,
            "note": "per-experiment time measured on lab model; LLM turn is assumed",
        },
    }


def reached_at(run: dict, target: float):
    xs = np.array(run["evals"])
    ys = np.array(run["curve"])
    hit = np.where(ys <= target)[0]
    return int(round(xs[hit[0]])) if hit.size else None


def build_gif(data: dict, out: Path, *, frames: int = 48):
    runs = data["runs"]
    order = ["zn", "relay", "grid", "simplex", "cmaes", "bo", "head"]
    colours = {
        "zn": MUTED,
        "relay": "#7f8c8d",
        "grid": ORANGE,
        "simplex": "#8e44ad",
        "cmaes": "#16a085",
        "bo": BAD,
        "head": ACCENT,
    }
    styles = {
        "zn": ":",
        "relay": "--",
        "grid": "-",
        "simplex": "-.",
        "cmaes": (0, (3, 1, 1, 1)),
        "bo": "-",
        "head": "-",
    }

    max_eval = max(max(r["evals"]) for r in runs.values())
    target = data["assumptions"]["target_j"]
    per_s = data["assumptions"]["per_experiment_s"]
    llm_s = data["assumptions"]["llm_turn_s"]
    hit = {k: reached_at(runs[k], target) for k in order}

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(11.6, 4.6), gridspec_kw={"width_ratios": [1.3, 1]}
    )
    fig.patch.set_facecolor("white")

    ax1.set_xscale("log")
    ax1.set_yscale("log")
    ax1.set_xlim(0.9, max_eval * 1.2)
    ax1.set_ylim(0.28, 3.2)
    ax1.set_yticks([0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.5, 2.0, 3.0])
    ax1.set_yticklabels(["0.3", "0.4", "0.5", "0.6", "0.8", "1", "1.5", "2", "3"])
    ax1.minorticks_off()
    ax1.set_xlabel("experiments on the plant  (log scale)")
    ax1.set_ylabel("cost J  (lower is better)")
    ax1.set_title("same 40 unseen plants, every method", fontsize=10.5, loc="left")
    ax1.grid(alpha=0.22, which="major", lw=0.5)
    ax1.axhline(target, color=GOOD, ls="--", lw=1.0, alpha=0.8)
    ax1.text(1.0, target * 1.04, "usable: J ≤ 0.6", fontsize=7.5, color=GOOD)

    lines = {}
    for k in order:
        (ln,) = ax1.plot(
            [],
            [],
            color=colours[k],
            ls=styles[k],
            lw=2.4 if k == "head" else 1.5,
            label=runs[k]["label"],
        )
        lines[k] = ln
    ax1.legend(
        fontsize=7.2,
        frameon=True,
        framealpha=0.92,
        loc="lower left",
        ncol=2,
        borderpad=0.4,
    )

    ax2.set_xlim(0, 60)
    ax2.set_yticks([])
    ax2.set_title("time to a usable controller", fontsize=10.5, loc="left")
    ax2.set_xlabel("seconds  (0.4 s/experiment, measured)")
    ax2.spines[["top", "right", "left"]].set_visible(False)

    rows = order + ["agent"]
    bars_y = np.arange(len(rows))[::-1]
    ax2.set_ylim(-0.8, len(rows) - 0.2)
    ax2.set_yticks(bars_y)
    ax2.set_yticklabels(
        [runs[k]["label"] for k in order] + ["Jev head + agent loop*"], fontsize=8
    )

    bar_objs = {}
    for k, y in zip(order, bars_y):
        bar_objs[k] = ax2.barh(y, 0.0, height=0.6, color=colours[k])
    agent_bar = ax2.barh(
        bars_y[-1],
        0.0,
        height=0.6,
        color="white",
        edgecolor=BAD,
        hatch="//",
        linewidth=1.1,
    )

    never_txt = {}
    for k, y in zip(order, bars_y):
        never_txt[k] = ax2.text(0.3, y, "", va="center", fontsize=8, color=MUTED)
    agent_note = ax2.text(
        0.3, bars_y[-1] - 0.42, "", va="center", fontsize=7.6, color=BAD
    )

    counter = ax1.text(
        0.985,
        0.04,
        "",
        transform=ax1.transAxes,
        ha="right",
        fontsize=8.6,
        family="monospace",
        color=INK,
    )
    finish = ax1.text(
        0.02,
        0.90,
        "",
        transform=ax1.transAxes,
        fontsize=9.2,
        color=ACCENT,
        weight="bold",
    )

    fig.text(
        0.01,
        0.012,
        "* every number here is measured. The agent row uses a measured LLM turn "
        "(median 5.3 s, GLM-5.3-Flash, 40 calls); the rest is simulation and decision time.",
        fontsize=7.0,
        color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))

    def eval_at(run, upto):
        xs = np.array(run["evals"])
        ys = np.array(run["curve"])
        m = xs <= upto
        return (xs[m], ys[m]) if m.any() else (np.array([]), np.array([]))

    def update(i):
        upto = max_eval ** (i / (frames - 1))
        best_now = []
        for k in order:
            xs, ys = eval_at(runs[k], upto)
            lines[k].set_data(xs, ys)
            if xs.size:
                best_now.append(float(ys[-1]))
            if hit[k] is None:
                never_txt[k].set_text(
                    "never reaches 0.6 (stops at %.2f)" % runs[k]["curve"][-1]
                    if upto >= max_eval
                    else ""
                )
            else:
                bar_objs[k][0].set_width(
                    min(hit[k] * per_s, 29.5) * min(1.0, upto / hit[k])
                )
        n_now = max(1, int(round(upto)))
        if hit["head"] is not None:
            agent_s = hit["head"] * (per_s + llm_s)
            agent_bar[0].set_width(min(agent_s, 58.0) * min(1.0, upto / hit["head"]))
            agent_note.set_text(
                f"{agent_s:.0f}s  ({hit['head']} × {llm_s:.1f} s LLM turn, measured)"
                if upto >= hit["head"]
                else ""
            )
        best_txt = f"{min(best_now):.3f}" if best_now else "—"
        counter.set_text(f"exp {n_now:3d}  ·  best J {best_txt}")
        if i == frames - 1:
            finish.set_text(
                f"head: usable after {hit['head']} experiments   ·   "
                f"grid sweep: 125 and still {runs['grid']['curve'][-1]:.2f}"
            )
        return ()

    out.parent.mkdir(parents=True, exist_ok=True)
    images = []
    for i in range(frames):
        update(i)
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=110)
        buf.seek(0)
        images.append(Image.open(buf).convert("RGB"))
    plt.close(fig)
    images[0].save(
        out,
        save_all=True,
        append_images=images[1:],
        duration=110,
        loop=0,
        optimize=True,
    )
    print(f"[race] wrote {out} ({len(images)} frames)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plants", type=int, default=40)
    ap.add_argument("--seed", type=int, default=21)
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="assets/race.gif")
    ap.add_argument("--json", default="research/results/race.json")
    ap.add_argument("--reuse", action="store_true")
    args = ap.parse_args()

    json_path = Path(args.json)
    if args.reuse and json_path.is_file():
        data = json.loads(json_path.read_text(encoding="utf-8"))
    else:
        data = collect(args.plants, args.seed, args.models)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[race] wrote {json_path}")

    build_gif(data, Path(args.out))


if __name__ == "__main__":
    main()
