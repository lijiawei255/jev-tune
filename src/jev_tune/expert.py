"""Expert rollout generation: a coordinate line search over the action vocabulary.

Earlier versions used a CMA-ES walk, but its annealed step size made 80 % of the
labels "hold", which is a useless thing to imitate.  The expert here evaluates
**every action in the vocabulary the decoder can actually emit** (three axes x
seven multiplicative steps = 21 single-axis probes), so the imitation target is
well posed and the one-step lookahead data is exactly the candidate set used at
inference.

Per plant and per step: 21 single-axis probes + 1 combined probe = 22
simulations.  A 20-step trajectory therefore costs 20 x 22 + 1 = 441
simulations, which is why the dataset is the expensive part of this project.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

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
    feats: np.ndarray
    curves: np.ndarray
    choice: np.ndarray
    score: np.ndarray
    noul: np.ndarray
    cost: np.ndarray
    act_state: np.ndarray
    act_delta: np.ndarray
    act_cost: np.ndarray
    act_best: np.ndarray


def _sim(plants: PlantSet, gains: np.ndarray, objective: str = "step", **sim_kwargs):
    res = simulate(plants, gains, **sim_kwargs)
    j = cost_from_metrics(res["metrics"], y_curve=res["y_curve"], objective=objective)
    return res, j


def generate(
    plants: PlantSet,
    *,
    steps: int = 20,
    seed: int = 0,
    space: ActionSpace | None = None,
    init_scale: float = 0.0,
    verbose: bool = True,
    objective: str = "step",
    **sim_kwargs,
):
    space = space or ActionSpace()
    rng = np.random.default_rng(seed)
    n = plants.n
    idx = np.arange(n)

    ku, tu = ultimate_gain(plants)
    gzn = np.column_stack([0.6 * ku, 1.2 * ku / tu, 0.075 * ku * tu])
    gains = np.clip(gzn * (10 ** rng.normal(0, init_scale, size=(n, 3))), 1e-4, 1e3)

    out = {
        k: []
        for k in (
            "feats",
            "curves",
            "choice",
            "score",
            "noul",
            "cost",
            "act_state",
            "act_delta",
            "act_cost",
            "act_best",
        )
    }

    prev_action = np.zeros((n, 3))
    prev_cost = np.zeros(n)

    res, j_now = _sim(plants, gains, objective, **sim_kwargs)

    for t in range(steps):
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
            cost=j_now,
            iteration=np.full(n, t, dtype=float),
        )

        # --- 15 single-axis probes (axis-major, so reshape is trivial)
        probe_gains = []
        probe_delta = []
        for axis in range(3):
            for k in range(space.k):
                g = gains.copy()
                g[:, axis] *= space.multipliers[k]
                probe_gains.append(g)
                d = np.zeros(3)
                d[axis] = space.deltas[k]
                probe_delta.append(d)
        probe_gains = np.concatenate(probe_gains)  # (15n, 3)
        flat = plants.take(np.tile(idx, 3 * space.k))
        _, j_probe = _sim(flat, probe_gains, objective, **sim_kwargs)
        j_probe = j_probe.reshape(3, space.k, n)  # (axis, bin, plant)

        best_bin = np.argmin(j_probe, axis=1)  # (3, n)
        combined = gains * (10 ** space.deltas[best_bin].T)  # (n,3)

        # --- combined probe: the next state, and the Noul label
        res_next, j_next = _sim(plants, combined, objective, **sim_kwargs)

        unstable = (
            (~np.isfinite(j_next))
            | (j_next >= 0.5 * DIVERGED_J)
            | (np.abs(res_next["metrics"][:, 3]) > 0.6)
            | (res_next["metrics"][:, 7] > 0.9)
        )
        cheap_enough = j_next < np.maximum(j_now * 1.5, j_now + 0.5)
        noul = (~unstable & cheap_enough).astype(np.float32)

        edges = np.array([0.8, 1.5, 3.0, 6.0])
        score = np.digitize(np.minimum(j_now, 20.0), edges)

        out["feats"].append(feats)
        out["curves"].append(curves)
        out["choice"].append(best_bin.T.astype(np.int64))
        out["score"].append(score.astype(np.int64))
        out["noul"].append(noul)
        out["cost"].append(j_now.astype(np.float32))

        state_idx = np.arange(t * n, (t + 1) * n)
        for a in range(3):
            for k in range(space.k):
                out["act_state"].append(state_idx)
                d = np.zeros((n, 3))
                d[:, a] = space.deltas[k]
                out["act_delta"].append(d)
                out["act_cost"].append(j_probe[a, k])
                out["act_best"].append((best_bin[a] == k).astype(np.int8))

        if verbose and (t % 5 == 0 or t == steps - 1):
            print(
                f"    step {t + 1}/{steps}  J median {np.median(j_now):.3f}", flush=True
            )

        # --- advance: keep the better of (current, combined)
        better = j_next < j_now
        gains = np.where(better[:, None], combined, gains)
        prev_action = np.where(better[:, None], space.deltas[best_bin].T, 0.0)
        prev_cost = j_now
        res = res_next if better.all() else res
        if not better.all():
            res, j_now = _sim(plants, gains, objective, **sim_kwargs)
        else:
            j_now = j_next

    data = ExpertData(
        feats=np.concatenate(out["feats"]),
        curves=np.concatenate(out["curves"]),
        choice=np.concatenate(out["choice"]),
        score=np.concatenate(out["score"]),
        noul=np.concatenate(out["noul"]),
        cost=np.concatenate(out["cost"]),
        act_state=np.concatenate(out["act_state"]),
        act_delta=np.concatenate(out["act_delta"]),
        act_cost=np.concatenate(out["act_cost"]),
        act_best=np.concatenate(out["act_best"]),
    )
    data.ku = ku
    data.tu = tu
    return data, gains, j_now, gzn


__all__ = ["ExpertData", "generate", "FAMILY_TO_ID"]
