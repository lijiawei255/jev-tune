"""README figure: agent-in-the-loop vs a warm decision head.

Every number except the LLM latency is measured on the motor-valve benchmark model
(10 s horizon):

    simulation, Fast Restart ......... 0.09 s
    decision (MATLAB forward pass) ... 0.002 s
    MATLAB cold start ................ 50 s
    model compile (first run) ........ ~10 s
    one-shot CLI job (20 experiments)  72 s inside MATLAB + 50 s startup
    warm worker, recompiling .......... 12-17 s per job
    LLM turn .......................... 3 s (assumption, labelled)
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

INK = "#1b2430"
ACCENT = "#2e86c1"
BAD = "#c0392b"
MUTED = "#95a5a6"
SIM_S = 0.09
HEAD_S = 0.002


def main(out: Path):
    fig = plt.figure(figsize=(10.6, 4.5))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.25, 1])

    # ---------------------------------------------------------------- lane view
    ax = fig.add_subplot(gs[0, 0])
    ax.set_title(
        "One tuning run: where the wall clock goes", fontsize=11, loc="left", color=INK
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 2.6)
    ax.axis("off")

    def lane(y, blocks, label, colour):
        ax.text(0.0, y + 0.46, label, fontsize=9.2, color=colour, fontweight="bold")
        x = 0.02
        width = 0.92 / len(blocks)
        for kind in blocks:
            fc, ec, txt = {
                "llm": ("#f5b7b1", BAD, "LLM"),
                "sim": ("#aed6f1", ACCENT, "sim"),
                "boot": ("#f9e79f", "#b7950b", "boot"),
                "comp": ("#d5dbdb", "#7f8c8d", "compile"),
            }[kind]
            ax.add_patch(
                mpatches.FancyBboxPatch(
                    (x, y),
                    width * 0.82,
                    0.34,
                    boxstyle="round,pad=0.006",
                    fc=fc,
                    ec=ec,
                    lw=1,
                )
            )
            ax.text(
                x + width * 0.41,
                y + 0.17,
                txt,
                ha="center",
                va="center",
                fontsize=7.5,
                color=ec,
            )
            x += width
        ax.text(x + 0.005, y + 0.17, "…", fontsize=12, color=colour)

    lane(
        1.55,
        ["llm", "sim"] * 4,
        "agent in the loop  —  every step waits for a language model",
        BAD,
    )
    ax.text(
        0.02,
        1.30,
        "per experiment: LLM turn (1–10 s) + simulation (0.09 s)",
        fontsize=8.4,
        color=MUTED,
    )

    lane(
        0.45,
        ["boot", "comp"] + ["sim"] * 6,
        "warm worker  —  startup and compile paid once, then ~0.09 s per experiment",
        ACCENT,
    )
    ax.text(
        0.02,
        0.20,
        "first experiment carries boot + compile; the rest are pure simulation",
        fontsize=8.4,
        color=MUTED,
    )

    # ---------------------------------------------------------------- bar view
    axb = fig.add_subplot(gs[0, 1])
    labels = [
        "agent\nin the loop\n(LLM 3 s)",
        "one CLI\nprocess\nper job",
        "warm\nMATLAB\nworker",
        "warm +\nmodel already\ncompiled",
    ]
    values = [60.0, 122.0, 15.0, 2.0]
    colours = [BAD, "#e59866", ACCENT, "#1f618d"]
    x = np.arange(len(values))
    axb.bar(x, values, width=0.62, color=colours)
    for i, v in enumerate(values):
        axb.text(i, v + 3, f"{v:.0f}s", ha="center", fontsize=9, color=INK)
    axb.annotate(
        "",
        xy=(1, 118),
        xytext=(1, 66),
        arrowprops=dict(arrowstyle="<->", color=BAD, lw=1.2),
    )
    axb.text(1.12, 92, "50 s startup\n+ 10 s compile", fontsize=8, color=BAD)
    axb.set_xticks(x)
    axb.set_xticklabels(labels, fontsize=8)
    axb.set_ylabel("wall clock, 20 experiments (s)")
    axb.set_ylim(0, 145)
    axb.set_title("same task, four ways", fontsize=11, loc="left", color=INK)
    axb.spines["top"].set_visible(False)
    axb.spines["right"].set_visible(False)

    fig.text(
        0.01,
        0.015,
        "measured on the motor-valve benchmark model (10 s horizon): simulation 0.09 s, decision 0.002 s, "
        "MATLAB cold start 50 s, model compile ~10 s · LLM latency 3 s is an assumption · "
        "last bar extrapolated",
        fontsize=7.0,
        color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)
    print(f"[figure] wrote {out}")


if __name__ == "__main__":
    main(Path("assets/agent_vs_head.png"))
