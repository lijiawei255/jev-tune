"""Closed-loop evaluation of a decision head against the classical baselines.

**Layering.** The loop, the budget accounting, the abstention policy and the
deterministic gate are domain-agnostic. The two PID-specific calls are
`state.build_state` (features) and `metrics.cost_from_metrics` (objective);
`docs/TRANSFER.md` lists them as the parts a port replaces.

Accounting rules (they are the point of this file, so they are stated once):

* one experiment == one closed-loop simulation of one plant at one gain set;
* ``budget`` is the number of experiments a method may spend, **including**
  the initial response and the final measurement.  ``evaluate_head`` spends
  exactly ``budget`` per plant;
* the reported ``best_j`` is the cost of the returned ``gains`` -- the final
  measurement competes for "best" like every other one.  Anything else lets the
  head report a cost it never achieved (see CHANGELOG, 0.4.0);
* the "never worse than the start" promise is *by construction*: the returned
  point is the best measured point, and the start is measured first.  It is not
  evidence that the policy is safe; the safety gate and its measured effect are
  reported separately.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .decision import DecisionBackend, as_backend
from .decode import (
    DEFAULT_ABSTAIN,
    AbstainPolicy,
    ActionSpace,
    Decision,
    apply_abstention,
    decide,
    apply_step,
)
from .metrics import cost_from_metrics
from .plants import PlantSet, simulate
from .state import build_state


@dataclass
class HeadResult:
    name: str
    gains: np.ndarray
    best_j: np.ndarray
    history: np.ndarray
    eval_axis: np.ndarray
    stop_iter: np.ndarray
    rollbacks: np.ndarray | None = None
    wall_s: float = 0.0
    budget: int = 0
    gains_start: np.ndarray | None = None
    decisions_ms: float = 0.0
    decisions: dict | None = None

    @property
    def sims_per_plant(self) -> float:
        return float(self.eval_axis[-1]) if self.eval_axis.size else 0.0

    def sims_to_target(self, target: np.ndarray) -> np.ndarray:
        hit = self.history <= np.asarray(target)[:, None]
        idx = np.argmax(hit, axis=1)
        return np.where(hit.any(axis=1), self.eval_axis[idx], np.inf)

    def decision_report(self) -> dict:
        """Coverage, harm and calibration of the decisions that were executed.

        * coverage      -- fraction of proposed decisions that were executed
                           (not held by the abstention policy)
        * harmful_rate  -- executed decisions after which the next measurement
                           was >2 % worse than the one before
        * ece           -- |confidence - P(improved)| over executed decisions,
                           10 equal-width bins.  This is *outcome* calibration,
                           which is what an abstention threshold needs; the ECE
                           in `STEP1_RESULTS.md` measures agreement with the
                           expert's label and is a different quantity.
        """
        if not self.decisions:
            return {}
        d = self.decisions
        conf = np.asarray(d["confidence"], dtype=float).ravel()
        held = np.asarray(d["held"], dtype=bool).ravel()
        improved = np.asarray(d["improved"], dtype=bool).ravel()
        harmful = np.asarray(d["harmful"], dtype=bool).ravel()
        executed = ~held
        out = {
            "n_decisions": int(conf.size),
            "coverage": float(executed.mean()) if conf.size else 0.0,
            "abstain_rate": float(held.mean()) if conf.size else 0.0,
            "n_executed": int(executed.sum()),
        }
        if executed.any():
            out["improvement_rate"] = float(improved[executed].mean())
            out["harmful_rate"] = float(harmful[executed].mean())
            c, y = conf[executed], improved[executed].astype(float)
            edges = np.linspace(0.0, 1.0, 11)
            ece = 0.0
            for i in range(10):
                m = (c > edges[i]) & (c <= edges[i + 1])
                if m.any():
                    ece += m.mean() * abs(y[m].mean() - c[m].mean())
            out["ece"] = float(ece)
        else:
            out["improvement_rate"] = None
            out["harmful_rate"] = None
            out["ece"] = None
        return out


def _propose(
    backend: DecisionBackend,
    value,
    feats: np.ndarray,
    curves: np.ndarray,
    space: ActionSpace,
    *,
    use_expectation: bool = True,
    shrinkage: float = 1.0,
    use_value_filter: bool = False,
    abstain: AbstainPolicy | None = None,
) -> tuple[Decision, np.ndarray]:
    answer = backend.answer(feats, curves)
    confidence = np.stack(
        [np.asarray(ch.probs, dtype=float).max(axis=-1) for ch in answer.choice],
        axis=-1,
    )
    noul = np.asarray(answer.noul.p_true, dtype=float)
    decision = decide(
        answer,
        space,
        use_expectation=use_expectation,
        shrinkage=shrinkage,
        abstain=abstain,
    )

    if use_value_filter and value is not None:
        # (b) one-step lookahead.  Measured to *hurt* on held-out plants
        #     (p90 1.04 -> 2.89): the net is trained on single-axis probes but
        #     this arbitration scores combined multi-axis steps.  Off by default.
        import torch

        step_exp = decision.proposed
        f = torch.as_tensor(feats, dtype=torch.float32)
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
        cands = np.stack([step_exp, step_val, np.zeros_like(step_exp)], axis=1)
        flat_d = torch.as_tensor(cands.reshape(-1, 3), dtype=torch.float32)
        f_rep = f.repeat_interleave(3, dim=0)
        scores = value(f_rep, flat_d).numpy().reshape(N, 3)
        pick = np.argmin(scores, axis=1)
        step = cands[np.arange(N), pick]
        step = np.clip(step, -space.max_step, space.max_step)
        decision = apply_abstention(step, confidence, noul, abstain)

    return decision, np.asarray(answer.score.dist)


def evaluate_head(
    model,
    plants: PlantSet,
    gzn: np.ndarray,
    ku: np.ndarray,
    tu: np.ndarray,
    *,
    budget: int | None = None,
    iters: int | None = None,
    space: ActionSpace | None = None,
    value=None,
    init_scale: float = 0.0,
    seed: int = 0,
    use_expectation: bool = True,
    shrinkage: float = 1.0,
    use_value_filter: bool = False,
    early_stop: bool = False,
    stop_band: int = 0,
    safety_gate: bool = True,
    max_rollbacks: int = 4,
    objective: str = "step",
    sims_already_spent: int = 0,
    abstain: AbstainPolicy | None = DEFAULT_ABSTAIN,
    record: bool = True,
    **sim_kwargs,
) -> HeadResult:
    """Tune ``plants`` with ``budget`` experiments each (default 21).

    ``iters`` is the legacy spelling: ``iters=20`` means 21 experiments, because
    the loop measures the start, proposes 20 times, then measures the last
    proposal.  Pass ``budget`` when the experiment count is the thing being
    compared.

    ``sims_already_spent`` accounts for experiments the caller spent before the
    loop (e.g. a relay test for Ku/Tu).  They are added to ``eval_axis`` so
    ``sims_to_target`` compares total experiments, not post-prior ones.

    ``early_stop`` is **off by default**: stopping once the response reaches the
    cheapest cost band (J < 0.8, `noul` > 0.9) saves about 9 of 20 experiments
    and costs about 0.22 median J on the held-out family
    (`docs/ABLATION.md`).  The MATLAB bridge stops on "no improvement for 5
    iterations", which is a different rule and is not affected by this switch.

    ``abstain`` is the explicit a-priori hold (`decode.AbstainPolicy`): a step is
    executed only when the calibrated `p_max` clears `tau_act`.  It is **on** by
    default with the thresholds measured in `docs/ABSTENTION.md`; pass
    `abstain=None` to disable it.  ``record`` keeps the per-decision trace
    (confidence, whether the axis was held, whether the next measurement
    improved), which is what the calibration and coverage curves are computed
    from.
    """
    import time

    space = space or ActionSpace()
    backend = as_backend(model, space=space)
    if budget is None:
        budget = (20 if iters is None else int(iters)) + 1
    budget = int(budget)
    if budget < 2:
        raise ValueError("budget must be at least 2 (initial response + one step)")
    iters = budget - 1

    rng = np.random.default_rng(seed + 99)
    n = plants.n
    t0 = time.perf_counter()
    t_dec = 0.0

    gains = np.clip(gzn * (10 ** rng.normal(0, init_scale, size=(n, 3))), 1e-4, 1e3)
    gains_start = gains.copy()
    prev_action = np.zeros((n, 3))
    prev_cost = np.zeros(n)
    best_cost = np.full(n, np.inf)
    best_gains = gains.copy()
    done = np.zeros(n, dtype=bool)
    stop_iter = np.full(n, budget, dtype=int)
    rollbacks = np.zeros(n, dtype=int)

    hist = []
    trace = (
        {
            "confidence": [],
            "held": [],
            "reason": [],
            "step_norm": [],
            "cost_before": [],
        }
        if record
        else None
    )

    def _measure(k: int) -> np.ndarray:
        """One experiment per plant; update best-so-far (gains and cost together)."""
        nonlocal gains, best_cost, best_gains
        res = simulate(plants, gains, **sim_kwargs)
        j = cost_from_metrics(
            res["metrics"], y_curve=res["y_curve"], objective=objective
        )
        upd = (j < best_cost) & ~done
        best_cost = np.where(upd, j, best_cost)
        best_gains = np.where(upd[:, None], gains, best_gains)
        hist.append(best_cost.copy())
        return res, j

    for k in range(iters):
        res, j = _measure(k)

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
        t_dec -= time.perf_counter()
        decision, score_p = _propose(
            backend,
            value,
            feats,
            curves,
            space,
            use_expectation=use_expectation,
            shrinkage=shrinkage,
            use_value_filter=use_value_filter,
            abstain=abstain,
        )
        t_dec += time.perf_counter()
        step = decision.step
        noul = decision.noul

        if trace is not None:
            trace["confidence"].append(decision.confidence.mean(axis=-1))
            trace["held"].append(decision.held.any(axis=-1))
            trace["reason"].append(np.max(decision.reason, axis=-1))
            trace["step_norm"].append(np.abs(step).max(axis=-1))
            trace["cost_before"].append(j)

        # deterministic veto: if the loop is clearly worse than the best gain
        # set we have seen, retreat instead of trusting the head.  This mirrors
        # jev_tune_model.m so the Python benchmark and the Simulink loop behave
        # the same way when a step would blow the loop up.
        if safety_gate:
            blowing = j > np.maximum(3.0 * best_cost + 1.0, 8.0)
            blowing &= rollbacks < max_rollbacks
            blowing &= ~done
            if blowing.any():
                gains = np.where(
                    blowing[:, None], np.maximum(best_gains * 0.6, 1e-4), gains
                )
                rollbacks = rollbacks + blowing.astype(int)
                prev_action = np.where(blowing[:, None], 0.0, prev_action)
                continue

        if early_stop:
            # `score` is the current cost band (0 = cheapest).  "Converged"
            # therefore means: the response is already in the best band and the
            # head believes the next step is safe.  The predicate used to test
            # band 4 (the *worst* band), so it never fired -- see CHANGELOG.
            converged = (np.argmax(score_p, axis=1) == stop_band) & (noul > 0.9)
            stop_iter = np.where(converged & ~done, k + 1, stop_iter)
            done |= converged

        step = np.where(done[:, None], 0.0, step)
        if trace is not None:
            trace["confidence"].append(decision.confidence.mean(axis=-1))
            trace["held"].append(decision.held.any(axis=-1))
            trace["reason"].append(np.max(decision.reason, axis=-1))
            trace["step_norm"].append(np.abs(step).max(axis=-1))
            trace["cost_before"].append(j)
        gains = apply_step(gains, step)
        prev_action = step
        prev_cost = j

    # the last proposal is also an experiment; it competes for "best" and is
    # counted in the budget, so the returned gains and best_j always agree.
    res_final, j_final = _measure(iters)

    decisions = None
    if trace is not None:
        decisions = {k: np.column_stack(v) for k, v in trace.items()}
        # did the experiment after this decision end below the one before it?
        before = decisions["cost_before"]
        after = np.column_stack([decisions["cost_before"][:, 1:], j_final])
        decisions["improved"] = after < before
        decisions["harmful"] = after > before * 1.02
        decisions["after"] = after

    return HeadResult(
        name="jev_head",
        gains=best_gains,
        best_j=best_cost,
        history=np.column_stack(hist),
        eval_axis=np.arange(1, budget + 1, dtype=float) + sims_already_spent,
        stop_iter=stop_iter + sims_already_spent,
        rollbacks=rollbacks,
        wall_s=time.perf_counter() - t0,
        budget=budget + sims_already_spent,
        gains_start=gains_start,
        decisions_ms=1e3 * t_dec / max(iters * n, 1),
        decisions=decisions,
    )


__all__ = ["HeadResult", "evaluate_head"]
