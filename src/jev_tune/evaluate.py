"""Closed-loop evaluation of a decision head against the classical baselines.

**Layering.** This is the PID reference loop. In addition to its feature builder
and objective, it assumes three positive gains, multiplicative updates, this
simulator, and a particular rollback rule. The typed probability/abstention
functions are reusable components; this loop is not a domain-neutral runtime.
`docs/TRANSFER.md` identifies the remaining adapter work for another domain.

Accounting rules (they are the point of this file, so they are stated once):

* one experiment == one closed-loop simulation of one plant at one gain set;
* ``budget`` is the number of experiments a method may spend, **including**
  the initial response and the final measurement.  ``evaluate_head`` spends
  at most ``budget`` per plant (early stopping can spend fewer);
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
    ConformalPolicy,
    apply_abstention,
    apply_conformal,
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
    actual_simulations: np.ndarray | None = None
    measurement_counts: np.ndarray | None = None
    trajectory: dict | None = None

    @property
    def sims_per_plant(self) -> float:
        if self.actual_simulations is not None:
            return float(np.mean(self.actual_simulations))
        return float(self.eval_axis[-1]) if self.eval_axis.size else 0.0

    def sims_to_target(self, target: np.ndarray) -> np.ndarray:
        hit = self.history <= np.asarray(target)[:, None]
        idx = np.argmax(hit, axis=1)
        spent = (
            self.eval_axis[idx]
            if self.measurement_counts is None
            else self.measurement_counts[np.arange(len(idx)), idx]
        )
        return np.where(hit.any(axis=1), spent, np.inf)

    def decision_report(self) -> dict:
        """Coverage, harm and calibration of the decisions that were executed.

        * coverage      -- fraction of measured policy decisions with at least
                           one axis permitted to execute; axis_coverage reports
                           the separate per-axis quantity. A confident zero-step
                           option counts as permitted, but not as an action.
        * harmful_rate  -- executed decisions after which the next measurement
                           was >2 % worse than the one before
        * ece           -- |mean axis concentration - P(improved)| over permitted
                           decisions, 10 equal-width bins. This is a diagnostic;
                           mean axis p_max is not a joint success probability.
                           The ECE
                           in `STEP1_RESULTS.md` measures agreement with the
                           expert's label and is a different quantity.
        """
        if not self.decisions:
            return {}
        d = self.decisions
        valid = np.asarray(d.get("valid", np.ones_like(d["held"], dtype=bool)))
        event = np.asarray(d.get("event", np.full(valid.shape, "proposal")))
        policy = valid & (event != "rollback")
        conf = np.asarray(d["confidence"], dtype=float)[policy]
        held = np.asarray(d["held"], dtype=bool)[policy]
        improved = np.asarray(d["improved"], dtype=bool)[policy]
        harmful = np.asarray(d["harmful"], dtype=bool)[policy]
        executed = ~held
        out = {
            "n_decisions": int(conf.size),
            "n_transitions": int(valid.sum()),
            "n_rollbacks": int((valid & (event == "rollback")).sum()),
            "coverage": float(executed.mean()) if conf.size else 0.0,
            "abstain_rate": float(held.mean()) if conf.size else 0.0,
            "n_executed": int(executed.sum()),
        }
        if "axis_held" in d:
            axis_held = np.asarray(d["axis_held"], dtype=bool)[policy]
            out["axis_coverage"] = float((~axis_held).mean()) if axis_held.size else 0.0
            out["partial_hold_rate"] = (
                float((axis_held.any(axis=-1) & ~axis_held.all(axis=-1)).mean())
                if axis_held.size else 0.0
            )
        if "step_norm" in d:
            moved = np.asarray(d["step_norm"])[policy] > 0.0
            out["action_rate"] = float(moved.mean()) if moved.size else 0.0
            out["n_actions"] = int(moved.sum())
        if "conformal_applied" in d:
            cp = policy & np.asarray(d["conformal_applied"], dtype=bool)
            sizes = np.asarray(d["set_size"])[cp]
            out["conformal_applied"] = bool(cp.any())
            out["average_set_size"] = float(sizes.mean()) if sizes.size else None
            out["conformal_hold_axis_rate"] = (
                float(np.asarray(d["cp_veto"], dtype=bool)[cp].mean()) if sizes.size else None
            )
        if executed.any():
            out["improvement_rate"] = float(improved[executed].mean())
            out["harmful_rate"] = float(harmful[executed].mean())
            c, y = conf[executed], improved[executed].astype(float)
            edges = np.linspace(0.0, 1.0, 11)
            ece = 0.0
            for i in range(10):
                m = (c >= edges[i]) & (
                    (c < edges[i + 1]) if i < 9 else (c <= edges[i + 1])
                )
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
    answer_record: dict | None = None,
    conformal: ConformalPolicy | None = None,
) -> tuple[Decision, np.ndarray]:
    answer = backend.answer(feats, curves)
    if answer_record is not None:
        answer_record["choice_probs"] = np.stack(
            [np.asarray(ch.probs, dtype=float) for ch in answer.choice], axis=1
        )
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
        conformal=conformal,
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
        with torch.inference_mode():
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
        with torch.inference_mode():
            scores = value(f_rep, flat_d).numpy().reshape(N, 3)
        pick = np.argmin(scores, axis=1)
        step = cands[np.arange(N), pick]
        step = np.clip(step, -space.max_step, space.max_step)
        decision = apply_abstention(step, confidence, noul, abstain)
        decision = apply_conformal(decision, [np.asarray(ch.probs) for ch in answer.choice],
                                   [np.asarray([o.delta for o in ch.options]) for ch in answer.choice], conformal)

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
    hold_mask_provider=None,
    conformal: ConformalPolicy | str | None = "backend",
    **sim_kwargs,
) -> HeadResult:
    """Tune ``plants`` with at most ``budget`` experiments each (default 21).

    ``iters`` is the legacy spelling: ``iters=20`` means 21 experiments, because
    the loop measures the start, proposes 20 times, then measures the last
    proposal.  Pass ``budget`` when the experiment count is the thing being
    compared.

    ``sims_already_spent`` accounts for experiments the caller spent before the
    loop (e.g. a relay test for Ku/Tu).  They are added to ``eval_axis`` so
    ``sims_to_target`` compares total experiments, not post-prior ones.

    ``early_stop`` is **off by default**. A stopped plant is excluded from later
    simulations. ``actual_simulations`` and ``measurement_counts`` record the
    real per-plant cost including ``sims_already_spent``. History keeps the fixed
    budget axis for plotting and carries the final value forward after stopping;
    the corresponding trajectory slots are marked unmeasured. The MATLAB
    bridge uses a different stopping rule (five iterations without improvement).

    ``conformal="backend"`` loads the checkpoint's split-CP policy by default.
    Empty, broad or directionally mixed sets veto axes; this does not guarantee
    safety on adaptive trajectories. ``conformal=None`` disables this policy.
    With CP, the implicit DEFAULT_ABSTAIN pmax heuristic is disabled.

    ``abstain`` is the legacy a-priori hold (`decode.AbstainPolicy`): a step is
    executed only when the calibrated `p_max` clears `tau_act`.  It is **on** by
    for legacy backends without CP; pass
    `abstain=None` to disable it.  ``record`` keeps the per-decision trace
    (confidence, axis hold masks, costs before/after, and parameters). A trace
    slot is valid only after its resulting parameters have been measured.
    Rollbacks are separate events, never attributed to the network proposal.

    ``hold_mask_provider(decision, iteration, plant_indices)`` is an optional
    experimental control: return a boolean mask shaped like ``decision.step``
    to hold additional axes without changing probabilities or decoded proposals.
    This supports random-hold controls with identical proposed actions.
    """
    import time

    space = space or ActionSpace()
    backend = as_backend(model, space=space)
    if isinstance(conformal, str):
        if conformal != "backend":
            raise ValueError("conformal must be 'backend', None, or a ConformalPolicy")
        conformal = getattr(backend, "conformal", None)
    # A checkpoint carrying CP uses set-based abstention by default. Explicit
    # caller-supplied heuristic policies can still be combined for experiments.
    if conformal is not None and abstain is DEFAULT_ABSTAIN:
        abstain = None
    normalization = {key: sim_kwargs[key] for key in ("horizon", "ref") if key in sim_kwargs}
    if budget is None:
        budget = (20 if iters is None else int(iters)) + 1
    budget = int(budget)
    if budget < 2:
        raise ValueError("budget must be at least 2 (initial response + one step)")
    rng = np.random.default_rng(seed + 99)
    n = plants.n
    t0 = time.perf_counter()
    t_dec = 0.0
    n_proposed = 0

    gains = np.clip(gzn * (10 ** rng.normal(0, init_scale, size=(n, 3))), 1e-4, 1e3)
    gains_start = gains.copy()
    prev_action = np.zeros((n, 3))
    prev_cost = np.zeros(n)
    best_cost = np.full(n, np.inf)
    best_gains = gains.copy()
    done = np.zeros(n, dtype=bool)
    rollbacks = np.zeros(n, dtype=int)
    actual = np.zeros(n, dtype=int)
    hist = np.full((n, budget), np.inf)
    counts = np.zeros((n, budget), dtype=int)
    shape = (n, budget - 1)
    trace = None
    trajectory = None
    if record:
        trace = {
            "confidence": np.full(shape, np.nan),
            "confidence_axis": np.full((*shape, 3), np.nan),
            "choice_probs": np.full((*shape, 3, space.k), np.nan),
            "held": np.ones(shape, dtype=bool),
            "axis_held": np.ones((*shape, 3), dtype=bool),
            "external_hold": np.zeros((*shape, 3), dtype=bool),
            "conformal_applied": np.zeros(shape, dtype=bool),
            "set_size": np.zeros((*shape, 3), dtype=int),
            "conformal_set": np.zeros((*shape, 3, space.k), dtype=bool),
            "cp_veto": np.zeros((*shape, 3), dtype=bool),
            "reason": np.full(shape, -1, dtype=int),
            "step_norm": np.zeros(shape),
            "step": np.zeros((*shape, 3)),
            "applied_step": np.zeros((*shape, 3)),
            "proposed": np.full((*shape, 3), np.nan),
            "cost_before": np.full(shape, np.nan),
            "after": np.full(shape, np.nan),
            "gains_before": np.full((*shape, 3), np.nan),
            "gains_after": np.full((*shape, 3), np.nan),
            "valid": np.zeros(shape, dtype=bool),
            "event": np.full(shape, "unmeasured", dtype="<U12"),
        }
        trajectory = {
            "gains": np.full((n, budget, 3), np.nan),
            "cost": np.full((n, budget), np.nan),
            "measured": np.zeros((n, budget), dtype=bool),
        }

    for k in range(budget):
        active = np.flatnonzero(~done)
        if not active.size:
            hist[:, k:] = best_cost[:, None]
            counts[:, k:] = actual[:, None]
            break
        active_plants = plants if active.size == n else plants.take(active)
        res = simulate(active_plants, gains[active], **sim_kwargs)
        j = cost_from_metrics(
            res["metrics"], y_curve=res["y_curve"], objective=objective, **normalization
        )
        actual[active] += 1
        better = j < best_cost[active]
        improved_idx = active[better]
        best_cost[improved_idx] = j[better]
        best_gains[improved_idx] = gains[improved_idx]
        hist[:, k] = best_cost
        counts[:, k] = actual
        if trace is not None:
            trajectory["gains"][active, k] = gains[active]
            trajectory["cost"][active, k] = j
            trajectory["measured"][active, k] = True
            if k:
                trace["after"][active, k - 1] = j
                trace["valid"][active, k - 1] = True
        if k == budget - 1:
            break

        # A rollback is an independent transition. It must not suppress normal
        # proposals for another plant in the same vectorised simulation batch.
        blowing = np.zeros(active.size, dtype=bool)
        if safety_gate:
            blowing = (j > np.maximum(3.0 * best_cost[active] + 1.0, 8.0)) & (
                rollbacks[active] < max_rollbacks
            )
        if blowing.any():
            rollback_idx = active[blowing]
            old = gains[rollback_idx].copy()
            gains[rollback_idx] = np.maximum(best_gains[rollback_idx] * 0.6, 1e-4)
            rollbacks[rollback_idx] += 1
            prev_action[rollback_idx] = 0.0
            prev_cost[rollback_idx] = j[blowing]
            if trace is not None:
                trace["event"][rollback_idx, k] = "rollback"
                trace["cost_before"][rollback_idx, k] = j[blowing]
                trace["gains_before"][rollback_idx, k] = old
                trace["gains_after"][rollback_idx, k] = gains[rollback_idx]
                rollback_step = np.log10(gains[rollback_idx] / old)
                trace["step"][rollback_idx, k] = rollback_step
                trace["applied_step"][rollback_idx, k] = rollback_step
                trace["step_norm"][rollback_idx, k] = np.abs(rollback_step).max(axis=-1)

        normal = ~blowing
        idx = active[normal]
        if not idx.size:
            continue
        feats, curves = build_state(
            res["metrics"][normal], res["y_curve"][normal], res["u_curve"][normal],
            gains[idx], gzn[idx], ku[idx], tu[idx],
            prev_action=prev_action[idx], prev_cost=prev_cost[idx], cost=j[normal],
            iteration=np.full(idx.size, k, dtype=float),
            **normalization,
        )
        answer_record = {} if record else None
        t_dec -= time.perf_counter()
        decision, score_p = _propose(
            backend, value, feats, curves, space,
            use_expectation=use_expectation, shrinkage=shrinkage,
            use_value_filter=use_value_filter, abstain=abstain,
            answer_record=answer_record,
            conformal=conformal,
        )
        t_dec += time.perf_counter()
        n_proposed += idx.size
        converged = np.zeros(idx.size, dtype=bool)
        if early_stop:
            converged = (np.argmax(score_p, axis=1) == stop_band) & (decision.noul > 0.9)
            done[idx[converged]] = True

        extra_hold = np.zeros_like(decision.held, dtype=bool)
        if hold_mask_provider is not None:
            extra_hold = np.asarray(hold_mask_provider(decision, k, idx), dtype=bool)
            if extra_hold.shape != decision.step.shape:
                raise ValueError("hold_mask_provider must return one boolean per proposed axis")
        held = decision.held | extra_hold
        step = np.where(held, 0.0, decision.step)
        moving = ~converged
        target = idx[moving]
        old = gains[target].copy()
        gains[target] = apply_step(old, step[moving])
        applied_step = np.log10(gains[target] / old)
        prev_action[target] = step[moving]
        prev_cost[target] = j[normal][moving]
        if trace is not None:
            trace["confidence"][target, k] = decision.confidence[moving].mean(axis=-1)
            trace["confidence_axis"][target, k] = decision.confidence[moving]
            trace["choice_probs"][target, k] = answer_record["choice_probs"][moving]
            trace["axis_held"][target, k] = held[moving]
            trace["external_hold"][target, k] = extra_hold[moving]
            trace["conformal_applied"][target, k] = decision.conformal_applied
            trace["set_size"][target, k] = decision.set_size[moving]
            trace["conformal_set"][target, k] = np.stack(decision.conformal_set, axis=1)[moving]
            trace["cp_veto"][target, k] = np.isin(decision.reason[moving], [4, 5, 6])
            trace["held"][target, k] = held[moving].all(axis=-1)
            trace["reason"][target, k] = decision.reason[moving].max(axis=-1)
            trace["step"][target, k] = step[moving]
            trace["applied_step"][target, k] = applied_step
            trace["proposed"][target, k] = decision.proposed[moving]
            trace["step_norm"][target, k] = np.abs(applied_step).max(axis=-1)
            trace["cost_before"][target, k] = j[normal][moving]
            trace["gains_before"][target, k] = old
            trace["gains_after"][target, k] = gains[target]
            trace["event"][target, k] = np.where(held[moving].all(axis=-1), "hold", "proposal")

    if trace is not None:
        trace["improved"] = trace["valid"] & (trace["after"] < trace["cost_before"])
        trace["harmful"] = trace["valid"] & (trace["after"] > trace["cost_before"] * 1.02)

    return HeadResult(
        name="jev_head",
        gains=best_gains,
        best_j=best_cost,
        history=hist,
        eval_axis=np.arange(1, budget + 1, dtype=float) + sims_already_spent,
        stop_iter=actual + sims_already_spent,
        rollbacks=rollbacks,
        wall_s=time.perf_counter() - t0,
        budget=budget + sims_already_spent,
        gains_start=gains_start,
        decisions_ms=1e3 * t_dec / max(n_proposed, 1),
        decisions=trace,
        actual_simulations=actual + sims_already_spent,
        measurement_counts=counts + sims_already_spent,
        trajectory=trajectory,
    )


__all__ = ["HeadResult", "evaluate_head"]
