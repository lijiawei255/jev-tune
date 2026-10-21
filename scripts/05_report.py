"""Turn an evaluation JSON into the report table and a performance profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="research/results/eval_heldout_120.json")
    ap.add_argument("--out", default="research/results")
    args = ap.parse_args()

    payload = json.loads(Path(args.json).read_text(encoding="utf-8"))
    rows = payload["rows"]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(
        f"# Benchmark: {payload['n_plants']} plants, families={payload['families']}, "
        f"heldout={payload['heldout']}\n"
    )
    lines.append(
        f"Reference: CMA-ES {payload['ref_budget']} sims/plant, "
        f"median J = {payload['reference_j_median']:.3f}\n"
    )
    lines.append(
        "| method | final J (median) | final J (p90) | x reference | success | sims to target (median) | sims (p90) |"
    )
    lines.append("| :--- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in rows:
        lines.append(
            f"| `{r['method']}` | {r['final_cost_median']:.3f} | {r['final_cost_p90']:.3f} | "
            f"{r['ratio_to_ref']:.2f} | {r['success_rate']:.0%} | "
            f"{r['sims_to_target_median']:.1f} | {r['sims_to_target_p90']:.1f} |"
        )
    table = "\n".join(lines)
    (out / "benchmark_table.md").write_text(table, encoding="utf-8")
    print(table)

    # bar chart: final cost vs reference
    names = [r["method"] for r in rows]
    ratios = [r["ratio_to_ref"] for r in rows]
    fig, ax = plt.subplots(figsize=(7, 3.2))
    colors = ["#c0392b" if n != "jev_head" else "#2e86c1" for n in names]
    ax.bar(names, ratios, color=colors)
    ax.axhline(1.0, color="k", ls="--", lw=1)
    ax.set_ylabel("final cost / reference")
    ax.set_title("Held-out performance (lower is better)")
    plt.xticks(rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(out / "benchmark_ratio.png", dpi=160)
    print(f"\n[wrote] {out / 'benchmark_table.md'} and benchmark_ratio.png")


if __name__ == "__main__":
    main()
