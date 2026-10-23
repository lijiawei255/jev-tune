"""Jev primitives.

**Domain-agnostic decision shell.** These three types are the only output surface
of the project: a decision is a Choice, a Score, or a Noul. Nothing downstream
consumes raw logits or a regressed number, which keeps every backend (numeric
head, a text encoder, a hosted Jev) interchangeable.

They are batched: `probs` / `dist` / `p_true` are `(K,)` for one state and
`(N,K)` for the loop, and the methods return a scalar or an `(N,)` array
accordingly. `evaluate.evaluate_head` consumes these objects directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def softmax(z: np.ndarray, axis: int = -1, temperature: float = 1.0) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64)
    if temperature != 1.0:
        z = z / max(temperature, 1e-6)
    z = z - z.max(axis=axis, keepdims=True)
    e = np.exp(z, out=z)
    e /= e.sum(axis=axis, keepdims=True)
    return e


@dataclass
class Option:
    label: str
    delta: float = 0.0  # numeric payload carried by the option


@dataclass
class Choice:
    """Pick exactly one of K options; carries a probability per option.

    ``probs`` is ``(K,)`` for one state or ``(N, K)`` for a batch; every method
    below returns a scalar for the first form and an ``(N,)`` array for the
    second, so the same object is the runtime contract for a single decision and
    for the vectorised loop.
    """

    question: str
    options: list[Option]
    probs: np.ndarray | None = None

    def _deltas(self) -> np.ndarray:
        return np.asarray([o.delta for o in self.options], dtype=float)

    @property
    def argmax(self):
        if self.probs is None:
            raise ValueError("Choice has no probabilities yet")
        p = np.asarray(self.probs, dtype=float)
        return int(np.argmax(p)) if p.ndim == 1 else np.argmax(p, axis=-1)

    def expected_delta(self):
        if self.probs is None:
            raise ValueError("Choice has no probabilities yet")
        p = np.asarray(self.probs, dtype=float)
        return np.dot(p, self._deltas())

    def variance(self):
        if self.probs is None:
            raise ValueError("Choice has no probabilities yet")
        p = np.asarray(self.probs, dtype=float)
        d = self._deltas()
        mu = np.dot(p, d)
        return np.sum(p * (d - np.expand_dims(mu, -1)) ** 2, axis=-1)

    def entropy(self):
        p = np.clip(np.asarray(self.probs, dtype=float), 1e-12, 1.0)
        return -np.sum(p * np.log(p), axis=-1)

    def confidence(self):
        """Concentration of the answer: max probability (Jev's `confidence`)."""
        if self.probs is None:
            raise ValueError("Choice has no probabilities yet")
        return np.max(np.asarray(self.probs, dtype=float), axis=-1)

    def labels(self) -> list[str]:
        return [o.label for o in self.options]


@dataclass
class Score:
    """Ordered rubric judgement (0..K-1) with a distribution.

    ``dist`` is ``(K,)`` or ``(N, K)``; the methods follow the same scalar /
    batched convention as :class:`Choice`.
    """

    question: str
    levels: list[str]
    dist: np.ndarray | None = None

    def expected(self):
        if self.dist is None:
            raise ValueError("Score has no distribution yet")
        d = np.asarray(self.dist, dtype=float)
        return np.dot(d, np.arange(d.shape[-1], dtype=float))

    @property
    def argmax(self):
        if self.dist is None:
            raise ValueError("Score has no distribution yet")
        d = np.asarray(self.dist, dtype=float)
        return int(np.argmax(d)) if d.ndim == 1 else np.argmax(d, axis=-1)

    def confidence(self):
        if self.dist is None:
            raise ValueError("Score has no distribution yet")
        return np.max(np.asarray(self.dist, dtype=float), axis=-1)


@dataclass
class Noul:
    """Calibrated P(statement is true) -- the safety primitive."""

    statement: str
    p_true: float | np.ndarray | None = None

    @property
    def true(self):
        if self.p_true is None:
            raise ValueError("Noul has no probability yet")
        p = np.asarray(self.p_true, dtype=float)
        return bool(p >= 0.5) if p.ndim == 0 else p >= 0.5


@dataclass
class Answer:
    """One decision bundle: everything the loop needs, nothing it does not."""

    choice: list[Choice] = field(default_factory=list)
    score: Score | None = None
    noul: Noul | None = None


def calibrate_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """Fit a single temperature by minimising NLL (1-D golden section)."""
    logits = np.asarray(logits, dtype=np.float64)
    y = np.asarray(y, dtype=np.int64)

    def nll(t: float) -> float:
        p = softmax(logits, axis=1, temperature=t)
        return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1.0))))

    lo, hi = 0.05, 20.0
    for _ in range(60):
        m1 = lo + 0.382 * (hi - lo)
        m2 = lo + 0.618 * (hi - lo)
        if nll(m1) < nll(m2):
            hi = m2
        else:
            lo = m1
    return float(np.clip(0.5 * (lo + hi), 0.05, 20.0))


__all__ = [
    "softmax",
    "Option",
    "Choice",
    "Score",
    "Noul",
    "Answer",
    "calibrate_temperature",
]
