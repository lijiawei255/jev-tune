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
    history: np.ndarray
    eval_axis: np.ndarray
    stop_iter: np.ndarray
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

    # (a) Jev-format decode: expected step, shrunk by the distribution variance
    step_exp = decode_choice(choice_p, space, use_expectation=use_expectation)

    if not (use_value_filter and value is not None):
        return np.clip(step_exp, -space.max_step, space.max_step), score_p, noul

    # (b) one-step lookahead: value head is trained on single-axis probes, so
    #     score each axis independently over the same five actions
    N = f.shape[0]
    deltas = space.deltas
    pred = np.zeros((N, 3, space.k))
    for axis in range(3):
        for k in range(space.k):
            d = torch.zeros(N, 3)
            d[:, axis] = float(deltas[k])
            pred[:, axis, k] = value(f, d).numpy()
    step_val = deltas[np.argmin(pred, axis=2)]  # (N,3)

    # (c) arbitration: whichever of {model step, greedy step, hold} looks best
    cands = np.stack([step_exp, step_val, np.zeros_like(step_exp)], axis=1)  # (N,3,3)
    flat_d = torch.as_tensor(cands.reshape(-1, 3), dtype=torch.float32)
    f_rep = f.repeat_interleave(3, dim=0)
    scores = value(f_rep, flat_d).numpy().reshape(N, 3)
    pick = np.argmin(scores, axis=1)
    step = cands[np.arange(N), pick]

    return np.clip(step, -space.max_step, space.max_step), score_p, noul


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
    init_scale: float = 0.0,
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
            stop_iter = np.where(converged & ~done, k, stop_iter)
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
