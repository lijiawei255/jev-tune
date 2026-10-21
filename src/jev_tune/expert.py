"""Expert rollout generation.

A batched CMA-ES plays the role of the expert tuner.  For every plant it walks
a gain trajectory and, at each step, records:

* the state (metrics + traces)
* the six candidate steps it evaluated and the cost each produced
  (this is the one-step lookahead training data for the value head)
* the best candidate (imitation label for the Choice heads)
* whether the best candidate kept the loop healthy (Noul label)
* the current cost bucket (Score label)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .baselines import _DiagCMA, LOG_HI, LOG_LO
from .decode import ActionSpace
from .metrics import DIVERGED_J, cost_from_metrics
from .plants import PlantSet, simulate, ultimate_gain
from .state import build_state

FAMILY_TO_ID = {
    "fopdt": 0,
    "sopdt": 1,
    "third_rhp": 2,
    "integrating": 3,
    "pmsm_speed": 4,
    "two_mass": 5,
}


@dataclass
class ExpertData:
    feats: np.ndarray  # (M,20)
    curves: np.ndarray  # (M,2,64)
    choice: np.ndarray  # (M,3) class per axis
    score: np.ndarray  # (M,) 0..4
    noul: np.ndarray  # (M,)
    cost: np.ndarray  # (M,)
    # one-step lookahead: (M, A, 20+2*64) is too big; store state index + action
    act_state: np.ndarray  # (K,) index into feats
    act_delta: np.ndarray  # (K,3) actual log10 step taken
    act_cost: np.ndarray  # (K,) cost after that step
    act_best: np.ndarray  # (K,) 1 if this action ended up being the expert's pick


def _eval_with_traces(plants: PlantSet, gains: np.ndarray):
    res = simulate(plants, gains)
    j = cost_from_metrics(res["metrics"], y_curve=res["y_curve"])
    return res, j


def generate(
    plants: PlantSet,
    *,
    gens: int = 40,
    lam: int = 8,
    seed: int = 0,
    init_scale: float = 0.0,
    sigma0: float = 0.12,
    space: ActionSpace | None = None,
    keep_act: bool = True,
):
    rng = np.random.default_rng(seed)
    space = space or ActionSpace()
    n = plants.n
    idx = np.arange(n)

    ku, tu = ultimate_gain(plants)
    gzn = np.column_stack([0.6 * ku, 1.2 * ku / tu, 0.075 * ku * tu])
    g0 = gzn * (10 ** rng.normal(0, init_scale, size=(n, 3)))
    g0 = np.clip(g0, 10**LOG_LO, 10**LOG_HI)

    opt = _DiagCMA(n, np.log10(g0), sigma=sigma0)

    out = {
        "feats": [],
        "curves": [],
        "choice": [],
        "score": [],
        "noul": [],
        "cost": [],
        "act_state": [] if keep_act else None,
        "act_delta": [] if keep_act else None,
        "act_cost": [] if keep_act else None,
        "act_best": [] if keep_act else None,
        "gains": [],
        "ku": ku,
        "tu": tu,
        "gzn": gzn,
    }

    prev_action = np.zeros((n, 3))
    prev_cost = np.zeros(n)
    best_cost = np.full(n, np.inf)
    best_gains = g0.copy()

    for t in range(gens):
        mean_log = np.clip(opt.mean, LOG_LO, LOG_HI)
        mean_g = 10**mean_log

        # --- state at the current mean
        res, j_now = _eval_with_traces(plants, mean_g)
        feats, curves = build_state(
            res["metrics"],
            res["y_curve"],
            res["u_curve"],
            mean_g,
            gzn,
            ku,
            tu,
            prev_action=prev_action,
            prev_cost=prev_cost,
            cost=j_now,
            iteration=np.full(n, t, dtype=float),
        )

        # --- candidate steps around the mean
        cand = opt.ask(lam, rng)  # (lam,n,3)
        cand_g = 10 ** np.clip(cand, LOG_LO, LOG_HI)
        flat = plants.take(np.tile(idx, lam))
        res_c, j_c = _eval_with_traces(flat, cand_g.reshape(-1, 3))
        j_c = j_c.reshape(lam, n)

        best_k = np.argmin(j_c, axis=0)
        best_delta = cand[best_k, idx, :] - mean_log
        best_j = j_c[best_k, idx]

        # --- labels
        deltas = space.deltas
        cls = np.argmin(np.abs(best_delta[:, :, None] - deltas[None, None, :]), axis=2)

        # score: current cost bucket (0 worst .. 4 best)
        edges = np.array([0.8, 1.5, 3.0, 6.0])
        score = np.digitize(np.minimum(j_now, 20.0), edges)

        # noul: "the chosen step keeps the loop healthy"
        unstable = (
            (best_j >= 0.5 * DIVERGED_J)
            | (np.abs(res_c["metrics"][:, 3]).reshape(lam, n)[best_k, idx] > 0.6)
            | (res_c["metrics"][:, 7].reshape(lam, n)[best_k, idx] > 0.85)
            | (~np.isfinite(best_j))
        )
        noul = (~unstable).astype(np.float32)

        out["feats"].append(feats)
        out["curves"].append(curves)
        out["choice"].append(cls.astype(np.int64))
        out["score"].append(score.astype(np.int64))
        out["noul"].append(noul)
        out["cost"].append(j_now.astype(np.float32))
        out["gains"].append(mean_g.astype(np.float32))

        if keep_act:
            for k in range(lam):
                out["act_state"].append(np.arange(t * n, (t + 1) * n))
                out["act_delta"].append(cand_g[k] / mean_g)  # ratio, logged below
                out["act_cost"].append(j_c[k])
                out["act_best"].append((best_k == k).astype(np.int8))

        # --- advance
        opt.tell(cand, j_c)
        prev_action = best_delta
        prev_cost = j_now
        upd = best_j < best_cost
        best_cost = np.where(upd, best_j, best_cost)
        best_gains = np.where(upd[:, None], cand_g[best_k, idx], best_gains)

    data = ExpertData(
        feats=np.concatenate(out["feats"]),
        curves=np.concatenate(out["curves"]),
        choice=np.concatenate(out["choice"]),
        score=np.concatenate(out["score"]),
        noul=np.concatenate(out["noul"]),
        cost=np.concatenate(out["cost"]),
        act_state=np.concatenate(out["act_state"])
        if keep_act
        else np.zeros(0, np.int64),
        act_delta=np.log10(np.concatenate(out["act_delta"]))
        if keep_act
        else np.zeros((0, 3)),
        act_cost=np.concatenate(out["act_cost"]) if keep_act else np.zeros(0),
        act_best=np.concatenate(out["act_best"]) if keep_act else np.zeros(0, np.int8),
    )
    data.ku = ku
    data.tu = tu
    return data, best_gains, best_cost, gzn


__all__ = ["ExpertData", "generate", "FAMILY_TO_ID"]
