"""Domain-agnostic decision policy: shrink, a-priori abstention, split-CP sets.

Every domain supplies typed ``Choice`` answers; this module turns them into a
bounded step plus explicit hold/escalate evidence. It knows nothing about PID.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .primitives import Answer


class NumericSpace(Protocol):
    """Optional schema for ordered numeric payloads (e.g. the PID ActionSpace)."""

    k: int
    deltas: np.ndarray
    max_step: float


def _shrink(
    p: np.ndarray, d: np.ndarray, shrinkage: float, var_ref: float
) -> np.ndarray:
    mu = p @ d
    var = p @ (d * d) - mu * mu
    gate = 1.0 / (1.0 + shrinkage * np.maximum(var, 0.0) / var_ref)
    return mu * gate


def _probabilities(value: np.ndarray) -> np.ndarray:
    p = np.asarray(value, dtype=float)
    if p.ndim < 1 or p.shape[-1] == 0 or not np.isfinite(p).all():
        raise ValueError("probabilities must be nonempty and finite")
    if (p < 0).any() or (p > 1).any() or not np.allclose(p.sum(axis=-1), 1, atol=1e-6):
        raise ValueError("probabilities must lie in [0, 1] and sum to one")
    return p


@dataclass(frozen=True)
class AbstainPolicy:
    """Explicit, *a-priori* abstention from the calibrated probabilities.

    This is the part that was missing in 0.3: the loop had a variance shrink
    (a soft trust region) and a post-hoc rollback (after a bad gain set had
    already been applied), but no way to say "I am not confident enough to touch
    the plant at all".

    Three zones, per gain axis, on the calibrated `p_max`:

        p_max >= tau_act              -> execute (expectation + variance shrink)
        tau_esc <= p_max < tau_act    -> hold, no escalation flag
        p_max < tau_esc               -> hold and flag "would escalate"

    plus one global override: ``noul < tau_noul`` holds every axis.  Held means
    ``delta = 0``: the gains stay exactly where they were, which is the last
    parameter set the plant actually ran.

    Thresholds are policy, not physics.  ``scripts/20_abstention.py`` sweeps
    them and reports coverage against final cost and harmful-step rate, so the
    choice is measured rather than asserted.
    """

    tau_act: float = 0.35
    tau_esc: float = 0.25
    tau_noul: float = 0.0

    def __post_init__(self):
        if not 0.0 <= self.tau_esc <= self.tau_act <= 1.0:
            raise ValueError("need 0 <= tau_esc <= tau_act <= 1")
        if not 0.0 <= self.tau_noul <= 1.0:
            raise ValueError("tau_noul must be in [0, 1]")


REASON_ACT = 0
REASON_LOW_CONFIDENCE = 1
REASON_ESCALATE = 2
REASON_NOUL = 3
REASON_CP_EMPTY = 4
REASON_CP_LARGE = 5
REASON_CP_DIRECTION = 6


@dataclass(frozen=True)
class ConformalPolicy:
    """Split-CP label sets plus an empty/large/mixed-direction veto.

    The generic shell defaults to ``hard_hold``: the veto acts before actuation.
    ``monitor`` keeps the numeric proposal and only records would_hold; the PID
    checkpoint loader selects it explicitly (see ``from_calibration``) because it
    gives the lower final cost there. Neither mode is a safety bound.
    """

    q_hat: tuple[float, ...]
    alpha: float = 0.10
    k_max: int = 3
    mode: str = "hard_hold"

    def __post_init__(self):
        q = np.asarray(self.q_hat, dtype=float)
        if q.ndim != 1 or not q.size or not np.isfinite(q).all() or ((q < 0) | (q > 1)).any():
            raise ValueError("q_hat must contain finite per-axis quantiles in [0, 1]")
        if not 0 < self.alpha < 1 or not isinstance(self.k_max, int) or self.k_max < 1:
            raise ValueError("need 0 < alpha < 1 and a positive integer k_max")
        if self.mode not in ("monitor", "hard_hold"):
            raise ValueError("conformal mode must be 'monitor' or 'hard_hold'")

    @classmethod
    def from_calibration(cls, blob):
        c = blob.get("split_conformal")
        return None if c is None else cls(tuple(c["qhat_per_axis"]), float(c["alpha"]),
                                         int(c["k_max"]), c.get("mode", "monitor"))

DEFAULT_ABSTAIN = AbstainPolicy()
"""Legacy pmax heuristic, used by backends without conformal metadata.

The selection draw and independent validation draws are reported separately in
``research/results/abstention.json``. Coverage distinguishes axes, proposals
and actual nonzero actions. Pass
`abstain=None` to `evaluate_head` to disable it (that is the A4 row of the
ablation). A checkpoint carrying split CP instead monitors label sets by
default; hard holds are opt-in, and the legacy pmax heuristic is disabled
unless explicitly combined.
"""


@dataclass
class Decision:
    """One executed (or held) step, with the evidence behind it."""

    step: np.ndarray  # (N,3) log10 steps actually sent to apply_step
    proposed: np.ndarray  # (N,3) what the decoder wanted before abstention
    held: np.ndarray  # (N,3) bool: this axis was held
    escalate: np.ndarray  # (N,3) bool: held *and* below tau_esc
    confidence: np.ndarray  # (N,3) calibrated p_max per axis
    noul: np.ndarray  # (N,)  P(healthy)
    reason: np.ndarray  # (N,3) int: 0 act, 1 low confidence, 2 escalate, 3 noul
    set_size: np.ndarray | None = None
    conformal_set: tuple[np.ndarray, ...] | None = None
    conformal_applied: bool = False
    conformal_would_hold: np.ndarray | None = None
    conformal_reason: np.ndarray | None = None
    conformal_mode: str = "off"

    @property
    def any_held(self) -> np.ndarray:
        return self.held.any(axis=-1)


def apply_conformal(decision, probabilities, deltas, policy):
    """Report complete LAC sets and a separate optional hard-hold decision.

    Keep the original temperature-scaled distribution and proposal intact.
    Monitor mode never changes step/held/escalate/reason. Noul has priority in
    the executed hard-hold reason, while the independent CP reason is retained.
    """
    if policy is not None and len(policy.q_hat) != len(probabilities):
        raise ValueError("conformal quantiles must match the number of axes")
    masks, sizes, would_hold, reasons = [], [], [], []
    for axis, (p, d) in enumerate(zip(probabilities, deltas)):
        mask = np.zeros_like(p, dtype=bool) if policy is None else (1.0 - p) <= policy.q_hat[axis]
        size = mask.sum(axis=-1)
        masks.append(mask)
        sizes.append(size)
        if policy is None:
            would_hold.append(np.zeros_like(size, dtype=bool))
            reasons.append(np.zeros_like(size, dtype=int))
            continue
        mixed = (mask & (d < 0)).any(axis=-1) & (mask & (d > 0)).any(axis=-1)
        empty, large = size == 0, size > policy.k_max
        veto = empty | large | mixed
        reason = np.where(empty, REASON_CP_EMPTY, np.where(large, REASON_CP_LARGE, REASON_CP_DIRECTION))
        would_hold.append(veto)
        reasons.append(np.where(veto, reason, REASON_ACT))
        if policy.mode == "hard_hold":
            decision.held[..., axis] |= veto
            decision.escalate[..., axis] |= veto
            decision.reason[..., axis] = np.where(veto & (decision.reason[..., axis] != REASON_NOUL), reason, decision.reason[..., axis])
    decision.set_size = np.stack(sizes, axis=-1)
    decision.conformal_set = tuple(masks)
    decision.conformal_applied = policy is not None
    decision.conformal_would_hold = np.stack(would_hold, axis=-1)
    decision.conformal_reason = np.stack(reasons, axis=-1)
    decision.conformal_mode = "off" if policy is None else policy.mode
    decision.step = np.where(decision.held, 0.0, decision.step)
    return decision


def apply_abstention(
    proposed: np.ndarray,
    confidence: np.ndarray,
    noul: np.ndarray,
    abstain: AbstainPolicy | None,
) -> Decision:
    """Turn a proposed step into an executed one, holding when unsure.

    Kept separate from `decide()` so the (disabled by default) value-filter path
    in `evaluate.py` goes through exactly the same policy.
    """
    proposed = np.asarray(proposed, dtype=float)
    confidence = np.asarray(confidence, dtype=float)
    noul = np.asarray(noul, dtype=float)
    if proposed.shape != confidence.shape or proposed.ndim < 1:
        raise ValueError("step and confidence must have matching (..., axes) shapes")
    if not np.isfinite(proposed).all() or not np.isfinite(confidence).all() or not np.isfinite(noul).all():
        raise ValueError("step, confidence and noul must be finite")
    if ((confidence < 0) | (confidence > 1)).any() or ((noul < 0) | (noul > 1)).any():
        raise ValueError("confidence and noul must lie in [0, 1]")
    if noul.shape != proposed.shape[:-1]:
        raise ValueError("noul must have one probability per state")

    if abstain is None:
        return Decision(
            step=proposed,
            proposed=proposed,
            held=np.zeros_like(proposed, dtype=bool),
            escalate=np.zeros_like(proposed, dtype=bool),
            confidence=confidence,
            noul=noul,
            reason=np.full(proposed.shape, REASON_ACT, dtype=int),
        )

    unsafe = noul < abstain.tau_noul
    unsafe = np.expand_dims(unsafe, -1)
    low = confidence < abstain.tau_act
    esc = confidence < abstain.tau_esc
    held = low | unsafe
    step = np.where(held, 0.0, proposed)

    reason = np.full(proposed.shape, REASON_ACT, dtype=int)
    reason = np.where(low, REASON_LOW_CONFIDENCE, reason)
    reason = np.where(esc, REASON_ESCALATE, reason)
    reason = np.where(unsafe, REASON_NOUL, reason)

    return Decision(
        step=step,
        proposed=proposed,
        held=held,
        escalate=esc & held,
        confidence=confidence,
        noul=noul,
        reason=reason,
    )


def decide(
    answer: Answer,
    space: NumericSpace | None = None,
    *,
    shrinkage: float = 1.0,
    use_expectation: bool = True,
    abstain: AbstainPolicy | None = None,
    max_step: float | None = None,
    conformal: ConformalPolicy | None = None,
) -> Decision:
    """Decode numeric payloads; an explicit PID space validates their schema.

    Without ``space``, each Choice's ordered numeric Option.delta values are
    authoritative. The caller owns units and actuation (e.g. additive updates).
    ``max_step`` bounds each axis in those units, defaulting to 0.32.
    """
    cap = max_step if max_step is not None else (space.max_step if space else 0.32)
    if not np.isfinite(cap) or cap <= 0 or not np.isfinite(shrinkage) or shrinkage < 0:
        raise ValueError("max_step must be positive and shrinkage nonnegative; both finite")
    if not answer.choice:
        raise ValueError("at least one numeric Choice is required")
    steps, distributions, payloads = [], [], []
    for ch in answer.choice:
        d = np.asarray([o.delta for o in ch.options], dtype=float)
        if not len(d) or not np.isfinite(d).all() or (np.diff(d) < 0).any():
            raise ValueError("numeric Option payloads must be finite and ordered")
        if space is not None and (len(d) != space.k or not np.allclose(d, space.deltas, atol=1e-12, rtol=0)):
            raise ValueError(f"choice '{ch.question}' payloads disagree with ActionSpace")
        p = _probabilities(ch.probs)
        if p.shape[-1] != len(d):
            raise ValueError("probability count must match numeric options")
        distributions.append(p)
        payloads.append(d)
        step = (_shrink(p, d, shrinkage, max(float(np.var(d)), 1e-6))
                if use_expectation else d[np.argmax(p, axis=-1)])
        steps.append(step)
    proposed = np.clip(np.stack(steps, axis=-1), -cap, cap)
    confidence = np.stack([p.max(axis=-1) for p in distributions], axis=-1)
    if answer.score is not None:
        _probabilities(answer.score.dist)
    p_true = getattr(answer.noul, "p_true", None)
    noul = (
        np.ones(proposed.shape[:-1])
        if p_true is None
        else np.asarray(p_true, dtype=float)
    )
    return apply_conformal(apply_abstention(proposed, confidence, noul, abstain), distributions, payloads, conformal)


__all__ = [
    "AbstainPolicy",
    "ConformalPolicy",
    "DEFAULT_ABSTAIN",
    "Decision",
    "NumericSpace",
    "REASON_ACT",
    "REASON_CP_DIRECTION",
    "REASON_CP_EMPTY",
    "REASON_CP_LARGE",
    "REASON_ESCALATE",
    "REASON_LOW_CONFIDENCE",
    "REASON_NOUL",
    "apply_abstention",
    "apply_conformal",
    "decide",
]
