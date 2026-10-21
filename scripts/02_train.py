"""Train the decision head on the merged dataset and report label statistics."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import torch

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
    n = len(data.feats)
    print(f"[train] {n:,} states, {len(data.act_state):,} lookahead rows", flush=True)

    # label balance: are all five steps actually represented?
    for axis, name in enumerate(("Kp", "Ki", "Kd")):
        counts = np.bincount(data.choice[:, axis], minlength=5)
        print(
            f"[train] {name} step label distribution: {np.round(counts / counts.sum(), 3)}",
            flush=True,
        )
    print(f"[train] noul positive rate: {data.noul.mean():.3f}", flush=True)
    print(
        f"[train] score distribution: {np.bincount(data.score, minlength=5)}",
        flush=True,
    )

    idx = np.random.default_rng(0).permutation(n)
    split = int(0.9 * n)
    tr, va = idx[:split], idx[split:]

    tr_data = ExpertData(
        feats=data.feats[tr],
        curves=data.curves[tr],
        choice=data.choice[tr],
        score=data.score[tr],
        noul=data.noul[tr],
        cost=data.cost[tr],
        act_state=data.act_state,
        act_delta=data.act_delta,
        act_cost=data.act_cost,
        act_best=data.act_best,
    )
    model = train_head(tr_data, epochs=args.epochs, seed=args.seed)
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    save(model, f"{args.out_dir}/jev_head.pt")
    print(f"[train] head saved ({time.perf_counter() - t0:.0f}s)", flush=True)

    value = train_value(data, epochs=args.value_epochs, seed=args.seed)
    save(value, f"{args.out_dir}/value_net.pt")
    print(f"[train] value net saved ({time.perf_counter() - t0:.0f}s)", flush=True)

    model.eval()
    with torch.no_grad():
        f_all = torch.as_tensor(data.feats[va], dtype=torch.float32)
        c_all = torch.as_tensor(data.curves[va], dtype=torch.float32)
        out = model(f_all, c_all)
        acc = (out["choice"].argmax(-1).numpy() == data.choice[va]).mean(axis=0)
        score_acc = (out["score"].argmax(-1).numpy() == data.score[va]).mean()
        noul_acc = (
            (torch.sigmoid(out["noul"]).numpy() > 0.5) == (data.noul[va] > 0.5)
        ).mean()
    print(
        f"[train] val choice acc per axis: {np.round(acc, 3)}  "
        f"score {score_acc:.3f}  noul {noul_acc:.3f}",
        flush=True,
    )

    # ---- temperature calibration on the held-out split (ECE before/after)
    import json

    from jev_tune.primitives import calibrate_temperature, softmax

    temps, ece_before, ece_after = [], [], []
    logits = out["choice"].numpy()
    y_all = data.choice[va]

    def _ece(p, y, bins=10):
        conf, pred = p.max(1), p.argmax(1)
        correct = (pred == y).astype(float)
        edges = np.linspace(0, 1, bins + 1)
        e = 0.0
        for i in range(bins):
            m = (conf > edges[i]) & (conf <= edges[i + 1])
            if m.sum() > 0:
                e += m.mean() * abs(correct[m].mean() - conf[m].mean())
        return e

    for axis in range(3):
        y = y_all[:, axis]
        t = calibrate_temperature(logits[:, axis], y)
        temps.append(t)
        ece_before.append(_ece(softmax(logits[:, axis]), y))
        ece_after.append(_ece(softmax(logits[:, axis], temperature=t), y))

    calib = {
        "choice_temperature": [float(x) for x in temps],
        "ece_before": [float(x) for x in ece_before],
        "ece_after": [float(x) for x in ece_after],
        "val_choice_acc": [float(x) for x in acc],
        "val_score_acc": float(score_acc),
        "val_noul_acc": float(noul_acc),
    }
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    (Path(args.out_dir) / "meta.json").write_text(
        json.dumps({"n_actions": int(max(5, data.choice.max() + 1)),
                    "n_feats": int(data.feats.shape[1]),
                    "n_curve": int(data.curves.shape[-1])}, indent=2), encoding="utf-8")
    (Path(args.out_dir) / "calibration.json").write_text(
        json.dumps(calib, indent=2), encoding="utf-8"
    )
    print(
        f"[train] temperature {np.round(temps, 2)}  ECE {np.round(ece_before, 3)} -> "
        f"{np.round(ece_after, 3)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
