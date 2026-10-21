"""Response metrics -> scalar cost.

The cost is the training target for the expert search and the scoring rule for
every baseline, so it has to be scale-free across the plant zoo.
"""

from __future__ import annotations

import numpy as np

from .plants import METRIC_NAMES, DEFAULT_HORIZON

# weights chosen so that a "textbook good" PID lands near J ~= 1.0
W_OS = 1.0
W_TS = 1.0
W_ESS = 4.0
W_ITAE = 1.0
W_SAT = 1.0
W_OVER = 0.5

DIVERGED_J = 50.0


def cost_from_metrics(
    m: np.ndarray,
    *,
    horizon: float = DEFAULT_HORIZON,
    ref: float = 1.0,
    y_curve: np.ndarray | None = None,
) -> np.ndarray:
    """m: (N, 9) metrics from plant.simulate -> (N,) cost."""
    m = np.atleast_2d(m)
    os_ = np.clip(m[:, 0], 0.0, 2.0)  # overshoot fraction
    ts_ = np.clip(m[:, 1], 0.0, 1.0)  # rise time / horizon
    settle_ = np.clip(m[:, 2] / horizon, 0.0, 1.0)
    ess_ = np.clip(np.abs(m[:, 3]), 0.0, 2.0)
    itae = np.clip(m[:, 5] / (max(ref, 1e-9) * horizon**2), 0.0, 3.0)
    sat_ = np.clip(m[:, 7], 0.0, 1.0)
    over_ = np.clip(m[:, 8], 0.0, 3.0)

    j = (
        W_OS * os_
        + W_TS * (0.5 * ts_ + settle_)
        + W_ESS * ess_
        + W_ITAE * itae
        + W_SAT * sat_
        + W_OVER * over_
    )

    if y_curve is not None:
        diverged = np.max(np.abs(y_curve), axis=1) > 12 * max(abs(ref), 1e-9)
        j = np.where(diverged, DIVERGED_J, j)
    return j


def is_failed(m: np.ndarray, y_curve: np.ndarray | None = None, ref: float = 1.0):
    m = np.atleast_2d(m)
    bad = (~np.isfinite(m[:, 3])) | (np.abs(m[:, 3]) > 0.5)
    if y_curve is not None:
        bad |= np.max(np.abs(y_curve), axis=1) > 12 * max(abs(ref), 1e-9)
    return bad


__all__ = ["cost_from_metrics", "is_failed", "METRIC_NAMES", "DIVERGED_J"]
