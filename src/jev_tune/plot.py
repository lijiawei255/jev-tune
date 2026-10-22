"""Before/after plot for a tuning result.

The two traces come from the JSON that ``jev_tune_json`` writes (start and
best), downsampled in MATLAB so the file stays small.  Nothing here invents
data: if a trace is missing the plot says so instead of drawing a curve.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def save_before_after(
    result: dict, out: str | Path, *, title: str | None = None
) -> Path:
    """Draw the closed-loop response before and after, plus the cost curve."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    trace = result.get("trace") or {}
    start = trace.get("start") or {}
    best = trace.get("best") or {}
    hist = result.get("history") or []
    ref = result.get("reference")

    fig, (ax, ax2) = plt.subplots(
        2,
        1,
        figsize=(11, 7.5),
        dpi=140,
        gridspec_kw={"height_ratios": [2.1, 1.0], "hspace": 0.32},
    )
    fig.patch.set_facecolor("white")

    if start.get("y") and best.get("y"):
        ax.plot(
            start["t"],
            start["y"],
            color="#8a949c",
            lw=1.6,
            label=f"start  J={start.get('J', float('nan')):.3f}",
        )
        ax.plot(
            best["t"],
            best["y"],
            color="#1f77b4",
            lw=2.2,
            label=f"tuned  J={best.get('J', float('nan')):.3f}",
        )
        if ref:
            ax.axhline(
                float(ref), color="#444", ls="--", lw=1.0, alpha=0.7, label="reference"
            )
        # A diverging start would squash the tuned trace into a flat line, so the
        # axis follows the tuned response and the start is clipped, with a note.
        lo = min(min(best["y"]), float(ref) if ref else 0.0)
        hi = max(max(best["y"]), float(ref) if ref else 1.0)
        span = max(hi - lo, 1e-6)
        ax.set_ylim(lo - 0.35 * span, hi + 0.35 * span)
        peak = max(abs(float(v)) for v in start["y"])
        if peak > hi + 0.35 * span:
            ax.text(
                0.99,
                0.94,
                f"start reaches {peak:.0f} (clipped)",
                transform=ax.transAxes,
                ha="right",
                va="top",
                fontsize=8,
                color="#8a949c",
            )
        ax.legend(frameon=False, loc="lower right", fontsize=9)
        ax.set_ylabel("measured signal")
    else:
        ax.text(
            0.5,
            0.5,
            "no trace in the result\n(run without --json truncation)",
            ha="center",
            va="center",
            transform=ax.transAxes,
            color="#8a949c",
        )
    ax.set_xlabel("time (s)")
    ax.grid(alpha=0.25, lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    if hist:
        js = [h.get("J") for h in hist]
        ax2.plot(range(1, len(js) + 1), js, "-o", color="#1f77b4", ms=4, lw=1.6)
        ax2.set_xlabel("experiment")
        ax2.set_ylabel("cost J")
        ax2.grid(alpha=0.25, lw=0.6)
        for s in ("top", "right"):
            ax2.spines[s].set_visible(False)

    name = Path(result.get("model", "model")).name
    gains = result.get("final_gains") or []
    sub = "  ".join(f"{k}={v:.4g}" for k, v in zip(("Kp", "Ki", "Kd"), gains))
    fig.suptitle(title or f"{name}\n{sub}", fontsize=12, x=0.02, ha="left")
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out
