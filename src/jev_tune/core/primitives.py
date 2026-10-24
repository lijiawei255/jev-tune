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
from math import ceil

import numpy as np


def softmax(z: np.ndarray, axis: int = -1, temperature: float = 1.0) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64)
    temperature = np.asarray(temperature, dtype=np.float64)
    if not np.isfinite(temperature).all() or (temperature <= 0).any():
        raise ValueError("temperature must be finite and positive")
    if not np.isfinite(z).all() or z.size == 0:
        raise ValueError("logits must be nonempty and finite")
    # Center before scaling. Very small positive T can legitimately saturate
    # a nonmaximum entry to -inf; exp(-inf)=0 while a maximum stays exactly 0.
    with np.errstate(over="ignore", under="ignore"):
        z = (z - z.max(axis=axis, keepdims=True)) / temperature
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


def _conformal_probabilities(probs: np.ndarray) -> np.ndarray:
    p = np.asarray(probs, dtype=np.float64)
    if (p.ndim < 1 or not p.size or p.shape[-1] < 1
            or not np.isfinite(p).all() or (p < 0).any() or (p > 1).any()
            or not np.allclose(p.sum(axis=-1), 1.0, rtol=1e-7, atol=1e-8)):
        raise ValueError("conformal probabilities must be finite normalized distributions")
    return p


def _conformal_labels(labels: np.ndarray, p: np.ndarray) -> np.ndarray:
    y = np.asarray(labels)
    if (p.ndim < 2 or y.shape != p.shape[:-1]
            or not np.issubdtype(y.dtype, np.integer)
            or (y < 0).any() or (y >= p.shape[-1]).any()):
        raise ValueError("labels must be integer option indices with shape probs.shape[:-1]")
    return y.astype(np.int64, copy=False)


def conformal_quantile(scores: np.ndarray, alpha: float = 0.10) -> np.ndarray:
    """Finite-sample LAC threshold over axis 0 (one exchangeable state per row).

    Uses rank ``ceil((n + 1) * (1 - alpha))`` without interpolation. When that
    rank is n+1, the bounded score's upper endpoint 1 is required, rather than
    the largest observed score. The latter silently loses the coverage bound.
    """
    s = np.asarray(scores, dtype=np.float64)
    if not np.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be finite and strictly between 0 and 1")
    if (s.ndim < 1 or s.shape[0] < 1 or not np.isfinite(s).all()
            or (s < 0).any() or (s > 1).any()):
        raise ValueError("nonconformity scores must be nonempty and in [0, 1]")
    rank = ceil((s.shape[0] + 1) * (1 - alpha))
    if rank > s.shape[0]:
        return np.ones(s.shape[1:], dtype=np.float64)
    return np.partition(s, rank - 1, axis=0)[rank - 1].copy()


def conformal_prediction_set(probs: np.ndarray, qhat: np.ndarray | float) -> np.ndarray:
    """LAC candidate mask, including equality: ``p >= 1 - qhat``.

    A scalar qhat applies to one axis; a vector applies to the penultimate
    probability axis. This function does not choose an action or assert safety.
    """
    p = _conformal_probabilities(probs)
    q = np.asarray(qhat, dtype=np.float64)
    if q.ndim > 1 or not q.size or not np.isfinite(q).all() or (q < 0).any() or (q > 1).any():
        raise ValueError("qhat must be a scalar or axis vector in [0, 1]")
    if q.ndim and (p.ndim < 2 or q.shape != (p.shape[-2],)):
        raise ValueError("qhat vector must match the probability axis count")
    # Score-space comparison is mathematically p >= 1-q and preserves ties
    # when q itself was formed as 1-p (a second subtraction can round up).
    return (1.0 - p) <= q[..., None]


def conformal_inclusion_threshold(qhat) -> np.ndarray:
    """float32 ``p_min`` with ``p >= p_min`` exactly equal to ``(1 - p) <= qhat``.

    Single-precision ports (c/jev_head.c) compare float32 probabilities
    without double arithmetic. For every float32 ``p`` in [0, 1] the returned
    threshold selects the same options as the float64 score-space rule above,
    including the near-one quantiles that a plain ``float32(1 - qhat)`` breaks.
    """
    q = np.atleast_1d(np.asarray(qhat, dtype=np.float64))
    if q.ndim != 1 or not np.isfinite(q).all() or (q < 0).any() or (q > 1).any():
        raise ValueError("qhat must be finite values in [0, 1]")
    down, up = np.float32(-1.0), np.float32(2.0)
    out = np.empty(q.shape, dtype=np.float32)
    for i, qi in enumerate(q):
        x = np.float32(1.0 - qi)
        if 1.0 - float(x) <= qi:
            while x > 0 and 1.0 - float(np.nextafter(x, down)) <= qi:
                x = np.nextafter(x, down)
        else:
            while 1.0 - float(x) > qi:
                x = np.nextafter(x, up)
        out[i] = max(x, np.float32(0.0))
    return out


@dataclass(frozen=True)
class SplitConformal:
    """Split conformal model for marginal teacher-label coverage per axis.

    The predictor (including temperature) must be fixed before CP fitting.
    Exchangeable calibration/test states give a marginal label inclusion bound;
    neither joint-axis coverage nor adaptive closed-loop safety follows from it.
    """

    alpha: float
    n_calibration: int
    qhat_per_axis: np.ndarray

    def __post_init__(self):
        if not np.isfinite(self.alpha) or not 0 < self.alpha < 1:
            raise ValueError("alpha must be finite and strictly between 0 and 1")
        if (not isinstance(self.n_calibration, (int, np.integer))
                or self.n_calibration < 1):
            raise ValueError("n_calibration must be a positive integer")
        q = np.asarray(self.qhat_per_axis, dtype=np.float64)
        if q.ndim > 1 or not q.size or not np.isfinite(q).all() or (q < 0).any() or (q > 1).any():
            raise ValueError("qhat_per_axis must be a scalar or axis vector in [0, 1]")
        q = q.copy()
        q.setflags(write=False)
        object.__setattr__(self, "qhat_per_axis", q)

    @property
    def quantile_rank(self) -> int:
        return ceil((self.n_calibration + 1) * (1 - self.alpha))

    def prediction_set(self, probs: np.ndarray) -> np.ndarray:
        return conformal_prediction_set(probs, self.qhat_per_axis)

    def evaluate(self, probs: np.ndarray, labels: np.ndarray) -> dict:
        """Report untouched evaluation data; never refit thresholds here."""
        p = _conformal_probabilities(probs)
        y = _conformal_labels(labels, p)
        mask = self.prediction_set(p)
        included = np.take_along_axis(mask, y[..., None], axis=-1)[..., 0]
        sizes = mask.sum(axis=-1)
        return {
            "n_states": len(p),
            "coverage_per_axis": np.mean(included, axis=0).tolist(),
            "mean_set_size_per_axis": np.mean(sizes, axis=0).tolist(),
            "empty_set_rate_per_axis": np.mean(sizes == 0, axis=0).tolist(),
            "set_size_histogram_per_axis": np.stack(
                [np.sum(sizes == k, axis=0) for k in range(p.shape[-1] + 1)], axis=-1
            ).tolist(),
        }


def fit_split_conformal(
    probs: np.ndarray, labels: np.ndarray, alpha: float = 0.10
) -> SplitConformal:
    """Fit 1-p(label) thresholds from a split unused for weights or temperature."""
    p = _conformal_probabilities(probs)
    if p.ndim not in (2, 3):
        raise ValueError("fit probabilities must have shape (N,K) or (N,A,K)")
    y = _conformal_labels(labels, p)
    scores = 1.0 - np.take_along_axis(p, y[..., None], axis=-1)[..., 0]
    return SplitConformal(alpha, len(p), conformal_quantile(scores, alpha))


__all__ = [
    "softmax",
    "Option",
    "Choice",
    "Score",
    "Noul",
    "Answer",
    "calibrate_temperature",
    "conformal_quantile",
    "conformal_prediction_set",
    "conformal_inclusion_threshold",
    "SplitConformal",
    "fit_split_conformal",
]
