"""README figure: agent-in-the-loop vs a warm decision head.

Measured on lab model, 20 experiments (timings from the tuner itself):

    decision (MATLAB forward pass) ... 0.002 s
    simulation ....................... ~0.4 s   (0.09 s in a very warm session)
    MATLAB cold start ................ ~50 s
    model setup + Kp sweep ........... ~28 s + ~40 s (cached afterwards)
    one-shot CLI job ................. ~122 s
    warm worker (fresh batch) ........ 8.8 s
    long-lived MATLAB session ........ 2.7 s
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


def main(out: Path):
    fig = plt.figure(figsize=(10.8, 4.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.22, 1])

    # ---------------------------------------------------------------- lane view
    ax = fig.add_subplot(gs[0, 0])
    ax.set_title(
        "One tuning run: where the wall clock goes", fontsize=11, loc="left", color=INK
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 2.6)
    ax.axis("off")

    def lane(y, blocks, label, colour, per_line):
        ax.text(0.0, y + 0.46, label, fontsize=9.2, color=colour, fontweight="bold")
        x = 0.02
        width = 0.9 / len(blocks)
        for kind in blocks:
            fc, ec, txt = {
                "llm": ("#f5b7b1", BAD, "LLM"),
                "sim": ("#aed6f1", ACCENT, "sim"),
                "boot": ("#f9e79f", "#b7950b", "boot"),
                "comp": ("#d5dbdb", "#7f8c8d", "setup"),
            }[kind]
            ax.add_patch(
                mpatches.FancyBboxPatch(
                    (x, y),
                    width * 0.8,
                    0.34,
                    boxstyle="round,pad=0.006",
                    fc=fc,
                    ec=ec,
                    lw=1,
                )
            )
            ax.text(
                x + width * 0.4,
                y + 0.17,
                txt,
                ha="center",
                va="center",
                fontsize=7.2,
                color=ec,
            )
            x += width
        ax.text(x + 0.005, y + 0.17, "…", fontsize=12, color=colour)
        ax.text(0.02, y - 0.16, per_line, fontsize=8.2, color=MUTED)

    lane(
        1.55,
        ["llm", "sim"] * 4,
        "agent in the loop  —  every step waits for a language model",
        BAD,
        "per experiment: LLM turn (1–10 s) + simulation",
    )
    lane(
        0.45,
        ["boot", "comp"] + ["sim"] * 6,
        "warm worker  —  startup, setup and Kp sweep paid once",
        ACCENT,
        "per experiment: ~0.4 s simulation + 0.002 s decision",
    )

    # ---------------------------------------------------------------- bar view
    axb = fig.add_subplot(gs[0, 1])
    labels = [
        "agent\nin the loop\n(LLM 3 s)",
        "one CLI\nprocess\nper job",
        "warm\nworker",
        "long-lived\nMATLAB\nsession",
    ]
    values = [60.0, 122.0, 8.8, 2.7]
    colours = [BAD, "#e59866", ACCENT, "#1f618d"]
    x = np.arange(len(values))
    axb.bar(x, values, width=0.62, color=colours)
    for i, v in enumerate(values):
        axb.text(i, v + 3, f"{v:.1f} s", ha="center", fontsize=9, color=INK)
    axb.annotate(
        "",
        xy=(0.92, 55),
        xytext=(0.92, 4),
        arrowprops=dict(arrowstyle="<->", color=BAD, lw=1.1),
    )
    axb.text(0.99, 28, "7×", fontsize=10, color=BAD, fontweight="bold")
    axb.annotate(
        "",
        xy=(2.92, 58),
        xytext=(2.92, 4),
        arrowprops=dict(arrowstyle="<->", color=ACCENT, lw=1.1),
    )
    axb.text(2.99, 28, "22×", fontsize=10, color=ACCENT, fontweight="bold")
    axb.set_xticks(x)
    axb.set_xticklabels(labels, fontsize=8)
    axb.set_ylabel("wall clock, 20 experiments (s)")
    axb.set_ylim(0, 140)
    axb.set_title("same task, four ways", fontsize=11, loc="left", color=INK)
    axb.spines["top"].set_visible(False)
    axb.spines["right"].set_visible(False)

    fig.text(
        0.01,
        0.015,
        "measured on lab model: decision 0.002 s, simulation ~0.4 s, MATLAB cold start ~50 s, "
        "setup ~28 s + Kp sweep ~40 s (cached after the first job) · LLM latency 3 s is an "
        "assumption, not measured",
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
