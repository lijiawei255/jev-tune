"""Closed-loop evaluation of a decision head against the classical baselines."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch

from .decode import ActionSpace, apply_step, decode_choice
from .metrics import cost_from_metrics
from .model import JevHead, ValueNet
from .plants import PlantSet, simulate
from .primitives import softmax
from .state import build_state


@dataclass
class HeadResult:
    name: str
    gains: np.ndarray
    best_j: np.ndarray
    history: np.ndarray  # (N, iters) best-so-far after each simulation
    eval_axis: np.ndarray  # iterations 1..iters
    stop_iter: np.ndarray  # iteration at which the head declared convergence
    wall_s: float = 0.0

    def sims_to_target(self, target: np.ndarray) -> np.ndarray:
        hit = self.history <= np.asarray(target)[:, None]
        idx = np.argmax(hit, axis=1)
        return np.where(hit.any(axis=1), self.eval_axis[idx], np.inf)


@torch.no_grad()
def _propose(
    model: JevHead,
    value: ValueNet | None,
    feats: np.ndarray,
    curves: np.ndarray,
    space: ActionSpace,
    *,
    use_expectation: bool = True,
    use_value_filter: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    f = torch.as_tensor(feats, dtype=torch.float32)
    c = torch.as_tensor(curves, dtype=torch.float32)
    out = model(f, c)
    choice_p = softmax(out["choice"].numpy(), axis=-1)  # (N,3,K)
    score_p = softmax(out["score"].numpy(), axis=-1)
    noul = torch.sigmoid(out["noul"]).numpy()

    step = decode_choice(choice_p, space, use_expectation=use_expectation)

    if use_value_filter and value is not None:
        # candidate set: top-2 classes per axis -> 8 combinations
        top2 = np.argsort(-choice_p, axis=-1)[:, :, :2]  # (N,3,2)
        deltas = space.deltas
        combos = np.stack(
            np.meshgrid([0, 1], [0, 1], [0, 1], indexing="ij"), axis=-1
        ).reshape(-1, 3)  # (8,3) indices into top2
        N = f.shape[0]
        cand = np.zeros((N, len(combos), 3))
        for j, combo in enumerate(combos):
            for axis in range(3):
                cand[:, j, axis] = deltas[top2[:, axis, combo[axis]]]
        # value head scoring
        flat = torch.as_tensor(cand.reshape(-1, 3), dtype=torch.float32)
        f_rep = f.repeat_interleave(len(combos), dim=0)
        pred = value(f_rep, flat).numpy().reshape(N, len(combos))
        pred = np.where(np.isfinite(pred), pred, 1e6)
        best = np.argmin(pred, axis=1)
        cand_step = cand[np.arange(N), best]
        # blend: trust the learned step when its predicted cost is not worse
        improve = pred[np.arange(N), best] < pred[:, len(combos) // 2]
        step = np.where(improve[:, None], cand_step, step)

    step = np.clip(step, -space.max_step, space.max_step)
    return step, score_p, noul


def evaluate_head(
    model: JevHead,
    plants: PlantSet,
    gzn: np.ndarray,
    ku: np.ndarray,
    tu: np.ndarray,
    *,
    iters: int = 20,
    space: ActionSpace | None = None,
    value: ValueNet | None = None,
    init_scale: float = 0.25,
    seed: int = 0,
    use_expectation: bool = True,
    use_value_filter: bool = True,
    early_stop: bool = True,
) -> HeadResult:
    import time

    space = space or ActionSpace()
    rng = np.random.default_rng(seed + 99)
    n = plants.n
    t0 = time.perf_counter()

    gains = np.clip(gzn * (10 ** rng.normal(0, init_scale, size=(n, 3))), 1e-4, 1e3)
    prev_action = np.zeros((n, 3))
    prev_cost = np.zeros(n)
    best_cost = np.full(n, np.inf)
    best_gains = gains.copy()
    done = np.zeros(n, dtype=bool)
    stop_iter = np.full(n, iters, dtype=int)

    hist = []
    for k in range(iters):
        res = simulate(plants, gains)
        j = cost_from_metrics(res["metrics"], y_curve=res["y_curve"])
        upd = (j < best_cost) & ~done
        best_cost = np.where(upd, j, best_cost)
        best_gains = np.where(upd[:, None], gains, best_gains)
        hist.append(best_cost.copy())

        feats, curves = build_state(
            res["metrics"],
            res["y_curve"],
            res["u_curve"],
            gains,
            gzn,
            ku,
            tu,
            prev_action=prev_action,
            prev_cost=prev_cost,
            cost=j,
            iteration=np.full(n, k, dtype=float),
        )
        step, score_p, noul = _propose(
            model,
            value,
            feats,
            curves,
            space,
            use_expectation=use_expectation,
            use_value_filter=use_value_filter,
        )

        if early_stop:
            converged = (np.argmax(score_p, axis=1) == 4) & (noul > 0.9)
            newly = converged & ~done
            stop_iter = np.where(newly, k, stop_iter)
            done |= converged

        step = np.where(done[:, None], 0.0, step)
        gains = apply_step(gains, step)
        prev_action = step
        prev_cost = j

    res = simulate(plants, gains)
    j = cost_from_metrics(res["metrics"], y_curve=res["y_curve"])
    best_cost = np.where(~done & (j < best_cost), j, best_cost)

    return HeadResult(
        name="jev_head",
        gains=best_gains,
        best_j=best_cost,
        history=np.column_stack(hist),
        eval_axis=np.arange(1, iters + 1, dtype=float),
        stop_iter=stop_iter,
        wall_s=time.perf_counter() - t0,
    )


__all__ = ["HeadResult", "evaluate_head"]
