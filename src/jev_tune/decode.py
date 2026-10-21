"""Decoding: Jev Choice distributions -> a bounded, safe gain step.

Two decoders, both operating on the same primitives:

* ``decode_choice``  -- expected-value decode with variance-driven shrinking
  (gives a continuous step while staying strictly inside the Choice format)
* ``interval_refine`` -- NumericJev-style refinement in log-gain space, only
  used in the final +-10 % neighbourhood where a wrong interval is harmless
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .primitives import Choice, Option, softmax

DEFAULT_MULTIPLIERS = (0.80, 0.90, 1.00, 1.10, 1.25)


@dataclass
class ActionSpace:
    multipliers: tuple[float, ...] = DEFAULT_MULTIPLIERS
    max_step: float = 0.20  # hard cap on |dlog10 K| per iteration

    @property
    def deltas(self) -> np.ndarray:
        return np.log10(np.asarray(self.multipliers, dtype=float))

    @property
    def k(self) -> int:
        return len(self.multipliers)

    def choices(self, names=("Kp", "Ki", "Kd")) -> list[Choice]:
        return [
            Choice(
                question=f"Which multiplicative step should {n} take?",
                options=[
                    Option(label=f"x{m:g}", delta=float(np.log10(m)))
                    for m in self.multipliers
                ],
            )
            for n in names
        ]


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
        mu = p @ d
        var = p @ (d**2) - mu**2
        var_ref = max(float(np.var(d)), 1e-6)
        gate = 1.0 / (1.0 + shrinkage * np.clip(var, 0, None) / var_ref)
        step = mu * gate

    step = np.clip(step, -space.max_step, space.max_step)
    return step


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
    "decode_choice",
    "expected_quality",
    "interval_refine",
    "apply_step",
    "DEFAULT_MULTIPLIERS",
]
