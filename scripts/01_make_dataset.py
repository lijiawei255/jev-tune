"""Step 1: generate the expert-rollout dataset (CPU only, batched)."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from jev_tune.expert import generate
from jev_tune.plants import sample_plants


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plants", type=int, default=2000)
    ap.add_argument("--gens", type=int, default=24)
    ap.add_argument("--lam", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="data/expert_train.npz")
    args = ap.parse_args()

    t0 = time.perf_counter()
    plants = sample_plants(args.plants, seed=args.seed)
    print(
        f"[data] {plants.n} plants, families={sorted(set(plants.family))} "
        f"({time.perf_counter() - t0:.1f}s)"
    )

    data, best_g, best_j, gzn = generate(
        plants, gens=args.gens, lam=args.lam, seed=args.seed
    )
    dt = time.perf_counter() - t0

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.out,
        feats=data.feats,
        curves=data.curves,
        choice=data.choice,
        score=data.score,
        noul=data.noul,
        cost=data.cost,
        act_state=data.act_state,
        act_delta=data.act_delta,
        act_cost=data.act_cost,
        act_best=data.act_best,
        best_gains=best_g,
        best_cost=best_j,
        gzn=gzn,
        ku=np.asarray(getattr(data, "ku", np.zeros(plants.n))),
        tu=np.asarray(getattr(data, "tu", np.zeros(plants.n))),
    )

    sims = plants.n * args.gens * (1 + args.lam)
    print(
        f"[data] {len(data.feats):,} states, {len(data.act_state):,} lookahead samples"
    )
    print(
        f"[data] expert best cost: median {np.median(best_j):.3f} p90 {np.percentile(best_j, 90):.3f}"
    )
    print(
        f"[data] {sims:,} simulations in {dt:.1f}s ({sims / max(dt, 1e-9):,.0f} sims/s)"
    )
    print(f"[data] wrote {args.out}")


if __name__ == "__main__":
    main()
