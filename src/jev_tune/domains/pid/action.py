"""PID action adapter: log-spaced multiplier vocabulary and gain updates."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...core.policy import _probabilities, _shrink, decide
from ...core.primitives import Answer

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

    def __post_init__(self):
        m = np.asarray(self.multipliers, dtype=float)
        if m.ndim != 1 or not len(m) or not np.isfinite(m).all() or (m <= 0).any():
            raise ValueError("multipliers must be a nonempty positive finite vector")
        if not np.isfinite(self.max_step) or self.max_step <= 0:
            raise ValueError("max_step must be finite and positive")

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
    p = _probabilities(probs)
    if not np.isfinite(shrinkage) or shrinkage < 0:
        raise ValueError("shrinkage must be finite and nonnegative")
    if p.shape[-1] != len(d):
        raise ValueError(f"expected {len(d)} options, got {p.shape[-1]}")

    if not use_expectation:
        step = d[np.argmax(p, axis=-1)]
    else:
        step = _shrink(p, d, shrinkage, space.var_ref)

    step = np.clip(step, -space.max_step, space.max_step)
    return step



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
    gains, dlog = np.asarray(gains, dtype=float), np.asarray(dlog, dtype=float)
    if not np.isfinite(gains).all() or not np.isfinite(dlog).all():
        raise ValueError("gains and steps must be finite")
    if not np.isfinite([lo, hi]).all() or not 0 < lo <= hi:
        raise ValueError("need finite bounds 0 < lo <= hi")
    if (gains <= 0).any():
        raise ValueError("PID gains must be positive")
    # Clip in log space to prevent overflow before the final bounds check.
    g = 10.0 ** np.clip(np.log10(gains) + dlog, np.log10(lo), np.log10(hi))
    g = np.where((dlog == 0) & (gains >= lo) & (gains <= hi), gains, g)
    return np.clip(g, lo, hi)


__all__ = ["ActionSpace", "DEFAULT_MULTIPLIERS", "LEGACY_MULTIPLIERS", "decode_choice",
           "decode_answer", "expected_quality", "interval_refine", "apply_step"]
