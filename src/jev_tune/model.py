"""The decision head: a small numeric encoder with Jev-primitive heads.

One forward pass produces everything: three Choice distributions (the
multiplicative step for Kp, Ki, Kd), one Score distribution (how good is the
current response), and one Noul logit (will the step keep the loop healthy).

A second, tiny head scores a *given* action -- that is the one-step lookahead
used to filter the model's own proposals before spending a simulation.
"""

from __future__ import annotations

import torch
import torch.nn as nn


class Encoder(nn.Module):
    def __init__(self, n_feats: int = 20, n_curve: int = 64, hidden: int = 128):
        super().__init__()
        self.curve = nn.Sequential(
            nn.Conv1d(2, 16, 5, stride=2, padding=2),
            nn.ReLU(),
            nn.Conv1d(16, 32, 5, stride=2, padding=2),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.mlp = nn.Sequential(
            nn.Linear(n_feats, 64),
            nn.ReLU(),
            nn.Linear(64, 64),
            nn.ReLU(),
        )
        self.trunk = nn.Sequential(
            nn.Linear(32 + 64, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.hidden = hidden

    def forward(self, feats: torch.Tensor, curves: torch.Tensor) -> torch.Tensor:
        c = self.curve(curves).squeeze(-1)
        f = self.mlp(feats)
        return self.trunk(torch.cat([c, f], dim=-1))


class JevHead(nn.Module):
    def __init__(self, n_feats=20, n_curve=64, n_actions=5, hidden=128):
        super().__init__()
        self.enc = Encoder(n_feats, n_curve, hidden)
        self.choice = nn.ModuleList([nn.Linear(hidden, n_actions) for _ in range(3)])
        self.score = nn.Linear(hidden, 5)
        self.noul = nn.Linear(hidden, 1)
        self.value = nn.Sequential(
            nn.Linear(hidden + 3, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

    def forward(self, feats, curves):
        h = self.enc(feats, curves)
        choice = torch.stack([head(h) for head in self.choice], dim=1)  # (B,3,K)
        return {
            "choice": choice,
            "score": self.score(h),
            "noul": self.noul(h).squeeze(-1),
            "h": h,
        }

    def action_value(self, h: torch.Tensor, delta: torch.Tensor) -> torch.Tensor:
        """delta: (..., 3) log10 steps -> predicted cost (...,)."""
        if h.dim() == delta.dim() - 1:
            h = h.unsqueeze(-2)
        return self.value(torch.cat([h, delta], dim=-1)).squeeze(-1)


class ValueNet(nn.Module):
    """One-step lookahead: (state features, proposed step) -> predicted cost."""

    def __init__(self, n_feats: int = 20, hidden: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_feats + 3, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, feats: torch.Tensor, delta: torch.Tensor) -> torch.Tensor:
        return self.net(torch.cat([feats, delta], dim=-1)).squeeze(-1)


class TorchBackend:
    """Runtime wrapper exposing only the Jev primitives."""

    def __init__(
        self, weights_path: str, n_feats=20, n_curve=64, hidden=128, device="cpu"
    ):
        self.model = JevHead(n_feats, n_curve, 5, hidden)
        self.model.load_state_dict(torch.load(weights_path, map_location="cpu"))
        self.model.eval()
        self.device = device

    @torch.no_grad()
    def probs(self, feats, curves):
        import numpy as np
        from .primitives import softmax

        f = torch.as_tensor(np.asarray(feats), dtype=torch.float32)
        c = torch.as_tensor(np.asarray(curves), dtype=torch.float32)
        out = self.model(f, c)
        self._h = out["h"]
        return {
            "choice": softmax(out["choice"].numpy(), axis=-1),
            "score": softmax(out["score"].numpy(), axis=-1),
            "noul": torch.sigmoid(out["noul"]).numpy(),
        }

    @torch.no_grad()
    def action_cost(self, deltas):
        import numpy as np

        d = torch.as_tensor(np.asarray(deltas), dtype=torch.float32)
        h = self._h
        if d.dim() == 2:
            d = d.unsqueeze(1)
        return self.model.action_value(h, d).numpy()


__all__ = ["Encoder", "JevHead", "TorchBackend"]
