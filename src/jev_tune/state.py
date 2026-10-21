"""State construction: numeric features + resampled traces.

The state is what the decision head sees.  Two channels:

* ``feats`` -- 20 hand-crafted, scale-free descriptors (human tuning language)
* ``curves`` -- 2 x 64 normalised samples of y(t) and u(t)

Both are cheap to compute and cost the same whether the backend is a 1M-param
numeric head or a text encoder.
"""

from __future__ import annotations

import numpy as np

from .plants import DEFAULT_HORIZON

N_CURVE = 64
N_FEATURES = 20

FEATURE_NAMES = (
    "overshoot",
    "rise/h",
    "settle/h",
    "ss_error",
    "log_iae",
    "log_itae",
    "oscillations",
    "sat_frac",
    "sat_over",
    "y_max",
    "log_Kp/Kp_zn",
    "log_Ki/Ki_zn",
    "log_Kd/Kd_zn",
    "prev_dlog_Kp",
    "prev_dlog_Ki",
    "prev_dlog_Kd",
    "prev_dJ",
    "iter_frac",
    "log_Ku/Kp",
    "Tu/h",
)


def _safe_log10(x: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    return np.log10(np.maximum(np.asarray(x, dtype=np.float64), eps))


def build_state(
    metrics: np.ndarray,
    y_curve: np.ndarray,
    u_curve: np.ndarray,
    gains: np.ndarray,
    gains_zn: np.ndarray,
    ku: np.ndarray,
    tu: np.ndarray,
    *,
    prev_action: np.ndarray | None = None,
    prev_cost: np.ndarray | None = None,
    cost: np.ndarray | None = None,
    iteration: np.ndarray | None = None,
    horizon: float = DEFAULT_HORIZON,
    ref: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (feats* (N,20) float32, curves (N,2,64) float32)."""
    m = np.atleast_2d(metrics)
    g = np.atleast_2d(gains)
    gzn = np.atleast_2d(gains_zn)
    N = g.shape[0]

    prev_action = (
        np.zeros((N, 3)) if prev_action is None else np.atleast_2d(prev_action)
    )
    prev_cost = np.zeros(N) if prev_cost is None else np.asarray(prev_cost, dtype=float)
    cost = np.zeros(N) if cost is None else np.asarray(cost, dtype=float)
    iteration = np.zeros(N) if iteration is None else np.asarray(iteration, dtype=float)

    with np.errstate(divide="ignore", invalid="ignore"):
        f = np.column_stack(
            [
                np.clip(m[:, 0], -1.0, 3.0),  # overshoot
                np.clip(m[:, 1] / horizon, 0.0, 2.0),  # rise
                np.clip(m[:, 2] / horizon, 0.0, 2.0),  # settle
                np.clip(m[:, 3], -3.0, 3.0),  # ess
                np.clip(_safe_log10(m[:, 4]), -9.0, 3.0) / 3.0,  # log IAE
                np.clip(_safe_log10(m[:, 5] / (ref * horizon**2)), -9.0, 3.0) / 3.0,
                np.clip(m[:, 6] / 5.0, 0.0, 4.0),
                np.clip(m[:, 7], 0.0, 1.0),
                np.clip(m[:, 8], 0.0, 3.0),
                np.clip(np.max(np.abs(y_curve), axis=1) / max(ref, 1e-9), 0.0, 12.0)
                / 12.0,
                np.clip(_safe_log10(g[:, 0] / np.maximum(gzn[:, 0], 1e-9)), -3, 3)
                / 3.0,
                np.clip(_safe_log10((g[:, 1] + 1e-6) / (gzn[:, 1] + 1e-6)), -3, 3)
                / 3.0,
                np.clip(_safe_log10((g[:, 2] + 1e-6) / (gzn[:, 2] + 1e-6)), -3, 3)
                / 3.0,
                np.clip(prev_action[:, 0], -0.5, 0.5) * 4,
                np.clip(prev_action[:, 1], -0.5, 0.5) * 4,
                np.clip(prev_action[:, 2], -0.5, 0.5) * 4,
                np.clip((prev_cost - cost) / 5.0, -3.0, 3.0),
                np.clip(iteration / 20.0, 0.0, 1.0),
                np.clip(_safe_log10(ku / np.maximum(g[:, 0], 1e-9)), -3, 3) / 3.0,
                np.clip(tu / horizon, 0.0, 5.0) / 5.0,
            ]
        )

    feats = np.nan_to_num(f, nan=0.0, posinf=3.0, neginf=-3.0).astype(np.float32)

    yc = np.asarray(y_curve, dtype=np.float32) / max(abs(ref), 1e-9)
    uc = np.asarray(u_curve, dtype=np.float32)
    curves = np.stack([yc, uc], axis=1).astype(np.float32)
    return feats, curves


__all__ = ["build_state", "FEATURE_NAMES", "N_FEATURES", "N_CURVE"]
