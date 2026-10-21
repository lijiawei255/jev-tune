"""Merge dataset chunks produced by 01_make_dataset.py (parallel CPU runs)."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

SCALAR = ("feats", "curves", "choice", "score", "noul", "cost")
PER_CHUNK = (
    "act_delta",
    "act_cost",
    "act_best",
    "best_gains",
    "best_cost",
    "gzn",
    "ku",
    "tu",
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--chunks",
        nargs="+",
        default=[
            "data/g_0.npz",
            "data/g_1.npz",
            "data/g_2.npz",
            "data/g_3.npz",
        ],
    )
    ap.add_argument("--out", default="data/expert_train.npz")
    args = ap.parse_args()

    arrays = {}
    state_offset = 0
    act_states = []
    for path in args.chunks:
        if not Path(path).is_file():
            print(f"[merge] missing {path}, skipped")
            continue
        z = np.load(path)
        n_states = len(z["feats"])
        for key in SCALAR:
            arrays.setdefault(key, []).append(z[key])
        act_states.append(z["act_state"] + state_offset)
        for key in PER_CHUNK:
            if key in z:
                arrays.setdefault(key, []).append(z[key])
        state_offset += n_states
        print(f"[merge] {path}: {n_states:,} states")

    merged = {k: np.concatenate(v) for k, v in arrays.items()}
    merged["act_state"] = np.concatenate(act_states)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, **merged)
    print(f"[merge] {len(merged['feats']):,} states -> {args.out}")


if __name__ == "__main__":
    main()
