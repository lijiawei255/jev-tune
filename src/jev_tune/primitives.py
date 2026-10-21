"""Jev primitives.

This is the *only* output surface of the project: a decision is a Choice, a
Score, or a Noul.  Nothing downstream consumes raw logits or a regressed
number, which keeps every backend (numeric head, Laya, JevNext, ...)
interchangeable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def softmax(z: np.ndarray, axis: int = -1, temperature: float = 1.0) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64) / max(temperature, 1e-6)
    z = z - np.max(z, axis=axis, keepdims=True)
    e = np.exp(z)
    return e / np.sum(e, axis=axis, keepdims=True)


@dataclass
class Option:
    label: str
    delta: float = 0.0  # numeric payload carried by the option


@dataclass
class Choice:
    """Pick exactly one of K options; carries a probability per option."""

    question: str
    options: list[Option]
    probs: np.ndarray | None = None

    @property
    def argmax(self) -> int:
        if self.probs is None:
            raise ValueError("Choice has no probabilities yet")
        return int(np.argmax(self.probs))

    def expected_delta(self) -> float:
        if self.probs is None:
            raise ValueError("Choice has no probabilities yet")
        return float(np.dot(self.probs, [o.delta for o in self.options]))

    def variance(self) -> float:
        if self.probs is None:
            raise ValueError("Choice has no probabilities yet")
        d = np.array([o.delta for o in self.options])
        mu = float(np.dot(self.probs, d))
        return float(np.dot(self.probs, (d - mu) ** 2))

    def entropy(self) -> float:
        p = np.clip(np.asarray(self.probs, dtype=float), 1e-12, 1.0)
        return float(-(p * np.log(p)).sum())


@dataclass
class Score:
    """Ordered rubric judgement (0..K-1) with a distribution."""

    question: str
    levels: list[str]
    dist: np.ndarray | None = None

    def expected(self) -> float:
        if self.dist is None:
            raise ValueError("Score has no distribution yet")
        return float(np.dot(self.dist, np.arange(len(self.levels), dtype=float)))


@dataclass
class Noul:
    """Calibrated P(statement is true) -- the safety primitive."""

    statement: str
    p_true: float | None = None

    @property
    def true(self) -> bool:
        if self.p_true is None:
            raise ValueError("Noul has no probability yet")
        return bool(self.p_true >= 0.5)


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
