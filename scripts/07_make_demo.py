"""Build the README demo assets from a real Simulink tuning run.

Inputs  : research/sim_tune/demo_traces.mat  (written by matlab/save_demo_traces.m)
Outputs : assets/tuning.gif, assets/before_after.png, assets/convergence.png

The GIF is the real thing -- every frame is one closed-loop experiment on the
motor-valve benchmark DC-motor model, with the gains and the cost the tuner saw at that step.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter
from scipy.io import loadmat

INK = "#1b2430"
ACCENT = "#2e86c1"
BAD = "#c0392b"
GOOD = "#27ae60"
MUTED = "#95a5a6"


def _unpack_history(R):
    hist = R["hist"]
    frames = []
    for h in hist.ravel():
        h = h.ravel()[0] if h.size == 1 else h
        try:
            rec = h[0, 0] if hasattr(h, "shape") and h.dtype.names is None else h
        except Exception:
            rec = h
        frames.append(rec)
    return frames


def load(path: str):
    z = loadmat(path, squeeze_me=True, struct_as_record=False)
    return z["S"], z["R"]


def make_gif(S, R, out: Path, interval_ms: int = 550):
    hist = R.hist
    n = len(hist)
    ref = float(R.ref)
    horizon = float(R.stopTime)

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(9.6, 3.7), gridspec_kw={"width_ratios": [2.05, 1]}
    )
    fig.patch.set_facecolor("white")

    t0 = np.asarray(hist[0].t, dtype=float)
    y0 = np.asarray(hist[0].y, dtype=float)
    ax1.plot(t0, y0, color=MUTED, lw=1.2, alpha=0.55, label="start (Z-N)")
    (line,) = ax1.plot([], [], color=ACCENT, lw=2.0, label="this experiment")
    ax1.axhline(ref, color=INK, ls="--", lw=1.0)
    ax1.set_xlim(0, horizon)
    ymax = max(1.35 * ref, float(np.max(y0)) * 1.05)
    ax1.set_ylim(-0.05 * ref, min(ymax, 2.2 * ref))
    ax1.set_xlabel("time (s)")
    ax1.set_ylabel("position (rad)")
    ax1.set_title(
        "Simulink motor-valve benchmark DC motor — one step per experiment", fontsize=10, loc="left"
    )
    ax1.legend(loc="lower right", fontsize=8, frameon=False)
    txt = ax1.text(
        0.015,
        0.97,
        "",
        transform=ax1.transAxes,
        va="top",
        fontsize=8.5,
        family="monospace",
        color=INK,
    )

    Js = [float(h.J) for h in hist]
    ax2.plot(range(n), Js, color=ACCENT, lw=1.2, alpha=0.35)
    (dot,) = ax2.plot([], [], "o", color=ACCENT, ms=6)
    (best_line,) = ax2.plot([], [], color=GOOD, lw=1.6)
    ax2.axhline(float(S[2].J), color=INK, ls=":", lw=1.0)
    ax2.text(
        n - 0.5,
        float(S[2].J),
        "human hand-tuned",
        ha="right",
        va="bottom",
        fontsize=7.5,
        color=INK,
    )
    ax2.set_xlim(-0.4, n - 0.6)
    ax2.set_ylim(0, max(Js) * 1.12)
    ax2.set_xlabel("experiment #")
    ax2.set_ylabel("cost J  (lower is better)")
    ax2.set_title("convergence", fontsize=10, loc="left")
    for s in ("top", "right"):
        ax1.spines[s].set_visible(False)
        ax2.spines[s].set_visible(False)

    def update(i):
        h = hist[i]
        line.set_data(np.asarray(h.t, dtype=float), np.asarray(h.y, dtype=float))
        g = np.asarray(h.gains, dtype=float)
        step = np.asarray(h.step, dtype=float)
        arrow = (
            ""
            if not step.any()
            else f"   step {step[0]:+.2f} {step[1]:+.2f} {step[2]:+.2f}"
        )
        txt.set_text(
            f"experiment {i + 1:2d}/{n}\n"
            f"Kp={g[0]:7.2f}  Ki={g[1]:7.1f}  Kd={g[2]:6.2f}\n"
            f"J = {float(h.J):.3f}{arrow}"
        )
        dot.set_data([i], [Js[i]])
        upto = Js[: i + 1]
        best_line.set_data(np.arange(i + 1), np.minimum.accumulate(upto))
        return line, dot, best_line, txt

    anim = FuncAnimation(fig, update, frames=n, interval=interval_ms, blit=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    anim.save(out, writer=PillowWriter(fps=max(1, int(1000 / interval_ms))))
    plt.close(fig)
    print(f"[demo] wrote {out}")


def make_before_after(S, out: Path, n_exp: int = 0):
    fig, (ax, axb) = plt.subplots(
        1, 2, figsize=(9.6, 3.6), gridspec_kw={"width_ratios": [2.3, 1]}
    )
    styles = {
        "zn": ("start — Ziegler-Nichols", MUTED, 1.4),
        "head": (f"after {n_exp or 8} experiments — Jev head", ACCENT, 2.2),
        "human": ("human hand-tuned (reference)", INK, 1.4),
    }
    for rec in S:
        name = str(rec.name)
        label, colour, lw = styles.get(name, (name, BAD, 1.2))
        ls = "--" if name == "human" else "-"
        ax.plot(
            np.asarray(rec.t),
            np.asarray(rec.y),
            color=colour,
            lw=lw,
            ls=ls,
            label=label,
        )
    ax.axhline(float(S[0].y[-1] * 0 + 0.5236), color=INK, ls=":", lw=0.9, alpha=0.6)
    ax.set_xlim(0, 6)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("position (rad)")
    ax.set_title("Same plant, three gain sets", fontsize=10, loc="left")
    ax.legend(loc="lower right", fontsize=8, frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    names = [str(r.name) for r in S]
    vals = [float(r.J) for r in S]
    cols = {"zn": MUTED, "head": ACCENT, "human": INK}
    axb.barh(names, vals, color=[cols.get(n, BAD) for n in names], height=0.55)
    for i, v in enumerate(vals):
        axb.text(v + 0.02, i, f"{v:.2f}", va="center", fontsize=8.5)
    axb.set_xlim(0, max(vals) * 1.28)
    axb.set_xlabel("cost J")
    axb.set_title(f"cost after {n_exp or 8} experiments", fontsize=10, loc="left")
    for s in ("top", "right"):
        axb.spines[s].set_visible(False)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170)
    plt.close(fig)
    print(f"[demo] wrote {out}")


def make_convergence(R, out: Path):
    hist = R.hist
    Js = [float(h.J) for h in hist]
    best = np.minimum.accumulate(Js)
    fig, ax = plt.subplots(figsize=(5.2, 2.7))
    ax.plot(Js, "o-", color=ACCENT, ms=4, lw=1.2, label="cost at each experiment")
    ax.plot(best, color=GOOD, lw=1.8, label="best so far")
    ax.set_xlabel("experiment")
    ax.set_ylabel("cost J")
    ax.legend(fontsize=8, frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170)
    plt.close(fig)
    print(f"[demo] wrote {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mat", default="research/sim_tune/demo_traces.mat")
    ap.add_argument("--out", default="assets")
    args = ap.parse_args()
    S, R = load(args.mat)
    out = Path(args.out)
    make_gif(S, R, out / "tuning.gif")
    n_exp = int(np.argmin([float(h.J) for h in R.hist])) + 1
    make_before_after(S, out / "before_after.png", n_exp)
    make_convergence(R, out / "convergence.png")


if __name__ == "__main__":
    main()
