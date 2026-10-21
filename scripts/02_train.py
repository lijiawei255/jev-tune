"""Step 2: train the Jev decision head + the lookahead value net."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from jev_tune.expert import ExpertData
from jev_tune.train import save, train_head, train_value


def load(path: str) -> ExpertData:
    z = np.load(path)
    return ExpertData(
        feats=z["feats"],
        curves=z["curves"],
        choice=z["choice"],
        score=z["score"],
        noul=z["noul"],
        cost=z["cost"],
        act_state=z["act_state"],
        act_delta=z["act_delta"],
        act_cost=z["act_cost"],
        act_best=z["act_best"],
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/expert_train.npz")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--value-epochs", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", default="models")
    args = ap.parse_args()

    t0 = time.perf_counter()
    data = load(args.data)
    print(f"[train] {len(data.feats):,} states, {len(data.act_state):,} lookahead rows")

    model = train_head(data, epochs=args.epochs, seed=args.seed)
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    save(model, f"{args.out_dir}/jev_head.pt")
    print(f"[train] head saved ({time.perf_counter() - t0:.1f}s)")

    value = train_value(data, epochs=args.value_epochs, seed=args.seed)
    save(value, f"{args.out_dir}/value_net.pt")
    print(f"[train] value net saved ({time.perf_counter() - t0:.1f}s)")

    # quick label sanity
    import torch

    with torch.no_grad():
        f = torch.as_tensor(data.feats, dtype=torch.float32)
        c = torch.as_tensor(data.curves, dtype=torch.float32)
        out = model(f, c)
        acc = (out["choice"].argmax(-1).numpy() == data.choice).mean(axis=0)
        noul_acc = (
            (torch.sigmoid(out["noul"]).numpy() > 0.5) == (data.noul > 0.5)
        ).mean()
    print(f"[train] train accuracy per axis: {np.round(acc, 3)}  noul {noul_acc:.3f}")


if __name__ == "__main__":
    main()
