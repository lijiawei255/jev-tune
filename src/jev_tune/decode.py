"""Decoding: Jev Choice distributions -> a bounded, safe gain step.

**Domain-agnostic decision shell.** This module knows about bounded options,
expectation, variance and confidence thresholds; it does not know what the
options mean. The only PID-specific thing it imports is `ActionSpace`, whose
default vocabulary happens to be multiplicative gain steps.

Three decisions, in order of increasing conservatism:

* ``decode_answer`` / ``decode_choice`` -- expected-value decode with
  variance-driven shrinking (a continuous step while staying inside the Choice
  format)
* ``decide`` -- the same, plus the explicit three-zone abstention policy
  (`AbstainPolicy`): execute, hold, or hold-and-flag-escalation
* ``interval_refine`` -- NumericJev-style refinement in log-gain space.
  Implemented and unit-tested but **not on the runtime path**; measured to add
  nothing once the expected-value decode is in place.  Kept as the documented
  fallback for a future exact-resolution stage.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .primitives import Answer, softmax

DEFAULT_MULTIPLIERS = (0.50, 0.70, 0.87, 1.00, 1.15, 1.43, 2.00)
"""Coarse-to-fine vocabulary: ~15 % steps near unity, up to 2x far away.

A 5-point uniform grid (+-10/25 %) needed ~50 iterations to walk a gain that
was 4x off.  Log-spacing the same number of options keeps the fine resolution
where it matters (near convergence) while allowing a single decisive move when
the plant is badly detuned.
"""

LEGACY_MULTIPLIERS = (0.80, 0.90, 1.00, 1.10, 1.25)


@dataclass
class ActionSpace:
    multipliers: tuple[float, ...] = DEFAULT_MULTIPLIERS
    max_step: float = 0.32  # hard cap on |dlog10 K| per iteration (~2x)

    @property
    def deltas(self) -> np.ndarray:
        return np.log10(np.asarray(self.multipliers, dtype=float))

    @property
    def k(self) -> int:
        return len(self.multipliers)

    @property
    def var_ref(self) -> float:
        """Variance of a uniform draw over the vocabulary (the shrink scale)."""
        d = self.deltas
        return max(float(np.var(d)), 1e-6)


def _shrink(
    p: np.ndarray, d: np.ndarray, shrinkage: float, var_ref: float
) -> np.ndarray:
    mu = p @ d
    var = p @ (d * d) - mu * mu
    gate = 1.0 / (1.0 + shrinkage * np.maximum(var, 0.0) / var_ref)
    return mu * gate


def decode_choice(
    probs: np.ndarray,
    space: ActionSpace | None = None,
    *,
    shrinkage: float = 1.0,
    use_expectation: bool = True,
) -> np.ndarray:
    """probs: (3, K) or (N, 3, K) -> (3,) / (N, 3) log10 gain steps.

    ``use_expectation=False`` falls back to the argmax (pure discrete action).
    Variance shrinks the step: var(v) = sum p_i (d_i - E[d])^2, and the shrink
    factor is 1 / (1 + shrinkage * var / var_ref).
    """
    space = space or ActionSpace()
    d = space.deltas
    p = np.atleast_3d(np.asarray(probs, dtype=float))
    if p.shape[-1] != len(d):
        raise ValueError(f"expected {len(d)} options, got {p.shape[-1]}")

    if not use_expectation:
        step = d[np.argmax(p, axis=-1)]
    else:
        step = _shrink(p, d, shrinkage, space.var_ref)

    step = np.clip(step, -space.max_step, space.max_step)
    return step


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

DEFAULT_ABSTAIN = AbstainPolicy()
"""The shipped policy: hold below `p_max = 0.35`.

Chosen by `scripts/20_abstention.py` on one held-out draw and validated on two
draws it was not chosen on: median cost 0.466 -> 0.440 at 60 % coverage.  Pass
`abstain=None` to `evaluate_head` to disable it (that is the A4 row of the
ablation).  The MATLAB bridge applies the same thresholds from the .mat file.
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

    @property
    def any_held(self) -> np.ndarray:
        return self.held.any(axis=-1)


def decode_answer(
    answer: Answer,
    space: ActionSpace | None = None,
    *,
    shrinkage: float = 1.0,
    use_expectation: bool = True,
) -> np.ndarray:
    """The same decode, but reading the typed `Choice` objects.

    This is what the runtime loop calls: the probabilities travel as a
    :class:`~jev_tune.primitives.Choice` (with its option labels attached), not
    as a bare logit tensor.  Numerically identical to ``decode_choice``;
    ``tests/test_primitives.py`` asserts that on random inputs.
    """
    return decide(
        answer,
        space,
        shrinkage=shrinkage,
        use_expectation=use_expectation,
        abstain=None,
    ).step


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
    if np.ndim(unsafe) > 0:
        unsafe = unsafe[:, None]
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
    space: ActionSpace | None = None,
    *,
    shrinkage: float = 1.0,
    use_expectation: bool = True,
    abstain: AbstainPolicy | None = None,
) -> Decision:
    """Decode a typed answer into a step, optionally holding when unsure."""
    space = space or ActionSpace()
    d = space.deltas
    for ch in answer.choice:
        if len(ch.options) != len(d):
            raise ValueError(
                f"choice '{ch.question}' has {len(ch.options)} options, "
                f"the action space has {len(d)}"
            )
    probs = np.stack(
        [np.asarray(ch.probs, dtype=float) for ch in answer.choice], axis=-2
    )
    if not use_expectation:
        proposed = d[np.argmax(probs, axis=-1)]
    else:
        proposed = _shrink(probs, d, shrinkage, space.var_ref)
    proposed = np.clip(proposed, -space.max_step, space.max_step)

    confidence = probs.max(axis=-1)
    p_true = getattr(answer.noul, "p_true", None)
    noul = (
        np.ones(proposed.shape[0])
        if p_true is None
        else np.asarray(p_true, dtype=float)
    )
    return apply_abstention(proposed, confidence, noul, abstain)


def expected_quality(dist: np.ndarray) -> float:
    return float(np.dot(np.asarray(dist, dtype=float), np.arange(len(dist))))


def interval_refine(
    center: float,
    width: float,
    probs: np.ndarray,
    *,
    k: int = 3,
) -> tuple[float, float]:
    """One NumericJev refinement round on a 1-D interval.

    ``probs`` are the K probabilities over the equally sized sub-intervals of
    ``[center - width, center + width]``.  Returns the new (center, width).
    """
    edges = np.linspace(center - width, center + width, k + 1)
    idx = int(np.argmax(probs))
    new_lo, new_hi = edges[idx], edges[idx + 1]
    return float(0.5 * (new_lo + new_hi)), float(0.5 * (new_hi - new_lo))


def apply_step(gains: np.ndarray, dlog: np.ndarray, lo=1e-4, hi=1e3) -> np.ndarray:
    g = np.asarray(gains, dtype=float) * (10.0 ** np.asarray(dlog, dtype=float))
    return np.clip(g, lo, hi)


__all__ = [
    "ActionSpace",
    "AbstainPolicy",
    "DEFAULT_ABSTAIN",
    "Decision",
    "REASON_ACT",
    "REASON_LOW_CONFIDENCE",
    "REASON_ESCALATE",
    "REASON_NOUL",
    "decode_choice",
    "decode_answer",
    "decide",
    "apply_abstention",
    "expected_quality",
    "interval_refine",
    "apply_step",
    "DEFAULT_MULTIPLIERS",
    "LEGACY_MULTIPLIERS",
]
