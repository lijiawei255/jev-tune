"""README figure: agent-in-the-loop vs agent-as-supervisor.

Numbers come from this repo's measurements, not from a vendor datasheet:
  * Simulink Fast Restart run, motor-valve benchmark model, 10 s horizon : 111 ms
  * Jev head decision (ONNX, 1 thread)                   : 0.19 ms
  * LLM turn latency                                     : 1 / 3 / 10 s (assumption, labelled)
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
SIM_S = 0.111
HEAD_S = 0.002
ITERS = 20


def main(out: Path):
    fig = plt.figure(figsize=(10.5, 4.4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.35, 1])

    # ---------------------------------------------------------------- lane view
    ax = fig.add_subplot(gs[0, 0])
    ax.set_title("One tuning run, 20 experiments", fontsize=11, loc="left", color=INK)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 2.6)
    ax.axis("off")

    def lane(y, blocks, label, colour):
        ax.text(0.0, y + 0.46, label, fontsize=9.5, color=colour, fontweight="bold")
        x = 0.02
        width = 0.92 / len(blocks)
        for kind in blocks:
            if kind == "llm":
                ax.add_patch(
                    mpatches.FancyBboxPatch(
                        (x, y),
                        width * 0.82,
                        0.34,
                        boxstyle="round,pad=0.006",
                        fc="#f5b7b1",
                        ec=BAD,
                        lw=1,
                    )
                )
                ax.text(
                    x + width * 0.41,
                    y + 0.17,
                    "LLM",
                    ha="center",
                    va="center",
                    fontsize=7.5,
                    color=BAD,
                )
            else:
                ax.add_patch(
                    mpatches.FancyBboxPatch(
                        (x, y),
                        width * 0.82,
                        0.34,
                        boxstyle="round,pad=0.006",
                        fc="#aed6f1",
                        ec=ACCENT,
                        lw=1,
                    )
                )
                ax.text(
                    x + width * 0.41,
                    y + 0.17,
                    "sim",
                    ha="center",
                    va="center",
                    fontsize=7.5,
                    color=ACCENT,
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
        1.35,
        "per experiment: LLM turn (1–10 s) + simulation (0.111 s)",
        fontsize=8.5,
        color=MUTED,
    )

    lane(
        0.45,
        ["sim"] * 8,
        "agent as supervisor  —  one tool call, the head decides inside",
        ACCENT,
    )
    ax.text(
        0.02,
        0.25,
        "per experiment: simulation (0.111 s) + decision (0.002 s)",
        fontsize=8.5,
        color=MUTED,
    )
    ax.annotate(
        "",
        xy=(0.63, 1.05),
        xytext=(0.02, 1.05),
        arrowprops=dict(arrowstyle="->", color=INK, lw=1.2),
    )
    ax.text(
        0.33,
        1.12,
        "one MCP tool call replaces 20 round trips",
        ha="center",
        fontsize=8.5,
        color=INK,
    )

    # ---------------------------------------------------------------- bar view
    axb = fig.add_subplot(gs[0, 1])
    llms = [1.0, 3.0, 10.0]
    agent = [ITERS * (l + SIM_S) for l in llms]
    ours = [ITERS * (SIM_S + HEAD_S)] * len(llms)
    x = np.arange(len(llms))
    axb.bar(x - 0.19, agent, width=0.36, color=BAD, label="agent in the loop")
    axb.bar(x + 0.19, ours, width=0.36, color=ACCENT, label="jev-tune")
    for i, (a, o) in enumerate(zip(agent, ours)):
        axb.text(i - 0.19, a * 1.06, f"{a:.0f}s", ha="center", fontsize=8, color=BAD)
        axb.text(i + 0.19, o * 1.06, f"{o:.1f}s", ha="center", fontsize=8, color=ACCENT)
        axb.text(
            i,
            max(a, o) * 1.22,
            f"{a / o:.0f}×",
            ha="center",
            fontsize=9,
            color=INK,
            fontweight="bold",
        )
    axb.set_xticks(x)
    axb.set_xticklabels([f"LLM {l:.0f} s" for l in llms], fontsize=9)
    axb.set_ylabel("wall clock for 20 experiments (s)")
    axb.set_ylim(0, max(agent) * 1.45)
    axb.set_title("what the LLM latency costs", fontsize=11, loc="left", color=INK)
    axb.legend(fontsize=8, frameon=False, loc="upper left")
    axb.spines["top"].set_visible(False)
    axb.spines["right"].set_visible(False)

    fig.text(
        0.01,
        0.015,
        "simulation 0.111 s = measured Fast Restart run on the motor-valve benchmark model (10 s horizon) · "
        "decision 0.19 ms = measured ONNX · LLM latency is an assumption, not measured",
        fontsize=7.2,
        color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)
    print(f"[figure] wrote {out}")


if __name__ == "__main__":
    main(Path("assets/agent_vs_head.png"))
