"""Training: imitation of the expert's step + calibrated safety/lookahead heads."""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from .expert import ExpertData
from .model import JevHead, ValueNet


def _to_t(x, dtype=torch.float32):
    return torch.as_tensor(np.asarray(x), dtype=dtype)


def train_head(
    data: ExpertData,
    *,
    epochs: int = 40,
    batch: int = 512,
    lr: float = 2e-3,
    seed: int = 0,
    verbose: bool = True,
    model: JevHead | None = None,
) -> JevHead:
    """Train (or fine-tune, when `model` is given) the decision head."""
    torch.manual_seed(seed)
    feats, curves = _to_t(data.feats), _to_t(data.curves)
    choice, score, noul = (
        _to_t(data.choice, torch.long),
        _to_t(data.score, torch.long),
        _to_t(data.noul),
    )
    ds = TensorDataset(feats, curves, choice, score, noul)
    dl = DataLoader(ds, batch_size=batch, shuffle=True, drop_last=True)

    n_actions = int(max(5, data.choice.max() + 1))
    if model is None:
        model = JevHead(n_feats=feats.shape[1], n_curve=curves.shape[-1], n_actions=n_actions)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    ce = nn.CrossEntropyLoss()
    bce = nn.BCEWithLogitsLoss()

    for ep in range(epochs):
        model.train()
        tot, n = 0.0, 0
        for f, c, ch, sc, no in dl:
            out = model(f, c)
            loss = sum(ce(out["choice"][:, i], ch[:, i]) for i in range(3)) / 3
            loss = loss + 0.5 * ce(out["score"], sc) + 0.5 * bce(out["noul"], no)
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item() * len(f)
            n += len(f)
        sched.step()
        if verbose and (ep % 10 == 0 or ep == epochs - 1):
            print(f"  epoch {ep:3d}  loss {tot / max(n, 1):.4f}")
    model.eval()
    return model


def train_value(
    data: ExpertData,
    *,
    epochs: int = 30,
    batch: int = 4096,
    lr: float = 2e-3,
    seed: int = 0,
    verbose: bool = True,
) -> ValueNet:
    if len(data.act_state) == 0:
        raise ValueError("no lookahead samples in dataset (keep_act=False?)")
    torch.manual_seed(seed + 1)
    idx = data.act_state
    feats = _to_t(data.feats[idx])
    delta = _to_t(data.act_delta)
    y = _to_t(np.log1p(np.minimum(data.act_cost, 20.0)))

    ds = TensorDataset(feats, delta, y)
    dl = DataLoader(ds, batch_size=batch, shuffle=True, drop_last=True)

    net = ValueNet(n_feats=feats.shape[1])
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
    lossf = nn.MSELoss()
    for ep in range(epochs):
        net.train()
        tot, n = 0.0, 0
        for f, d, t in dl:
            pred = net(f, d)
            loss = lossf(pred, t)
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item() * len(f)
            n += len(f)
        if verbose and (ep % 10 == 0 or ep == epochs - 1):
            print(f"  value epoch {ep:3d}  mse {tot / max(n, 1):.4f}")
    net.eval()
    return net


def save(model: nn.Module, path: str):
    torch.save(model.state_dict(), path)


__all__ = ["train_head", "train_value", "save"]
