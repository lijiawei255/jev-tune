"""Response metrics -> scalar cost.

**Testbed-specific (PID).** The weights below encode what "a good step response"
means for a servo loop. A different domain defines a different cost; the decision
shell does not care which one it is given, as long as the expert and the loop use
the same.

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


OBJECTIVES = ("step", "tracking", "disturbance")


def cost_from_metrics(
    m: np.ndarray,
    *,
    horizon: float = DEFAULT_HORIZON,
    ref: float = 1.0,
    y_curve: np.ndarray | None = None,
    objective: str = "step",
) -> np.ndarray:
    """m: (N, 10) metrics from plant.simulate -> (N,) cost.

    ``objective`` selects which terms matter:

    ``step``          overshoot + rise + settling + error + ITAE (the default,
                      and what the shipped head was trained on)
    ``tracking``      integral error and mean lag dominate; overshoot is
                      meaningless against a moving reference, so it is dropped
    ``disturbance``   recovery after the disturbance: settling and ITAE dominate,
                      with a light penalty on the excursion
    """
    if objective not in OBJECTIVES:
        raise ValueError(f"objective must be one of {OBJECTIVES}")
    m = np.atleast_2d(m)
    os_ = np.clip(m[:, 0], 0.0, 2.0)  # overshoot fraction
    ts_ = np.clip(m[:, 1], 0.0, 1.0)  # rise time / horizon
    settle_ = np.clip(m[:, 2] / horizon, 0.0, 1.0)
    ess_ = np.clip(np.abs(m[:, 3]), 0.0, 2.0)
    itae = np.clip(m[:, 5] / (max(ref, 1e-9) * horizon**2), 0.0, 3.0)
    sat_ = np.clip(m[:, 7], 0.0, 1.0)
    over_ = np.clip(m[:, 8], 0.0, 3.0)

    if objective == "tracking":
        lag = np.clip(np.abs(m[:, 9]) / max(ref, 1e-9), 0.0, 2.0)
        iae_n = np.clip(m[:, 4] / (max(ref, 1e-9) * horizon), 0.0, 3.0)
        j = 2.0 * iae_n + 1.5 * lag + 0.3 * settle_ + 0.5 * sat_
    elif objective == "disturbance":
        # the settling column already tracks the last time the response left the
        # band, which for a disturbance step is the recovery time
        j = 1.5 * settle_ + 2.0 * itae + 0.8 * os_ + 0.5 * sat_
    else:
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
