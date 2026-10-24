"""Peripheral calibration from frozen-model logits, without weight access.

Each calibration row must identify a different sampling unit. Disjoint IDs
prevent directly reused records; they do not establish exchangeability or
independence of the underlying observations. Calibration and its measured fit
time exclude acquiring labels, model inference and target-device execution.
"""
from __future__ import annotations

import re
import time

import numpy as np

from .primitives import calibrate_temperature, fit_split_conformal, softmax


def _inputs(logits, labels, name):
    values = np.asarray(logits, dtype=np.float64)
    targets = np.asarray(labels)
    if (values.ndim != 3 or any(size < 1 for size in values.shape)
            or not np.isfinite(values).all()):
        raise ValueError(f"{name} logits must have nonempty finite shape (N,A,K)")
    if (targets.shape != values.shape[:-1]
            or not np.issubdtype(targets.dtype, np.integer)
            or (targets < 0).any() or (targets >= values.shape[-1]).any()):
        raise ValueError(f"{name} labels must be integer indices with shape (N,A)")
    return values, targets.astype(np.int64, copy=False)


def _identities(values, n, name):
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} IDs must be one string or integer per row")
    try:
        identities = list(values)
    except TypeError as exc:
        raise ValueError(f"{name} IDs must be one string or integer per row") from exc
    if len(identities) != n:
        raise ValueError(f"{name} IDs must match the number of rows")
    tokens = []
    for identity in identities:
        if isinstance(identity, (bool, np.bool_)):
            raise ValueError(f"{name} IDs must be nonempty strings or integers")
        if isinstance(identity, (str, np.str_)) and identity.strip():
            tokens.append(("str", str(identity)))
        elif isinstance(identity, (int, np.integer)):
            tokens.append(("int", int(identity)))
        else:
            raise ValueError(f"{name} IDs must be nonempty strings or integers")
    unique = set(tokens)
    if len(unique) != n:
        raise ValueError(f"{name} IDs must be unique within the split")
    return unique


def fit_frozen_calibration(
    temperature_logits,
    temperature_labels,
    conformal_logits,
    conformal_labels,
    *,
    temperature_ids,
    conformal_ids,
    model_sha256,
    alpha=.10,
):
    """Fit per-axis temperature, then split CP, from two disjoint splits.

    Shapes are ``(N,A,K)`` / ``(N,A)`` and ``(M,A,K)`` / ``(M,A)``.
    The caller must freeze the model before collecting these logits, provide
    independent sampling units, and establish calibration/test exchangeability.
    No model, weights, weight optimizer or gradient is accessed by this function.
    The supplied SHA-256 records caller-provided model identity; it does not
    independently verify the checkpoint or its relationship to these logits.

    Returned coverage scope is per-axis marginal teacher-label inclusion on
    exchangeable new states. It excludes joint-axis, adaptive-trajectory,
    accepted-action, safety and performance guarantees. CP is monitor-only.
    """
    tx, ty = _inputs(temperature_logits, temperature_labels, "temperature")
    cx, cy = _inputs(conformal_logits, conformal_labels, "conformal")
    if tx.shape[1:] != cx.shape[1:]:
        raise ValueError("temperature and conformal logits must share axis and option counts")
    if not np.isscalar(alpha) or not np.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be finite and strictly between 0 and 1")
    if not isinstance(model_sha256, str) or re.fullmatch(r"[0-9a-fA-F]{64}", model_sha256) is None:
        raise ValueError("model_sha256 must be a 64-character hexadecimal SHA-256")
    temperature_units = _identities(temperature_ids, len(tx), "temperature")
    conformal_units = _identities(conformal_ids, len(cx), "conformal")
    if temperature_units & conformal_units:
        raise ValueError("temperature and conformal IDs must be disjoint")

    start = time.perf_counter()
    temperatures = np.array([
        calibrate_temperature(tx[:, axis, :], ty[:, axis])
        for axis in range(tx.shape[1])
    ])
    after_temperature = time.perf_counter()
    probabilities = softmax(cx, temperature=temperatures[None, :, None])
    fitted = fit_split_conformal(probabilities, cy, alpha=float(alpha))
    after_conformal = time.perf_counter()
    return {
        "temperatures": temperatures.tolist(),
        "qhat_per_axis": fitted.qhat_per_axis.tolist(),
        "alpha": float(alpha),
        "n_temperature": len(tx),
        "n_calibration": len(cx),
        "quantile_rank": fitted.quantile_rank,
        "mode": "monitor",
        "model_sha256": model_sha256.lower(),
        "fit_ms": {
            "temperature": (after_temperature - start) * 1000.,
            "conformal": (after_conformal - after_temperature) * 1000.,
            "total": (after_conformal - start) * 1000.,
        },
        "scope": (
            "Per-axis marginal teacher-label inclusion on exchangeable new states; "
            "requires a model frozen before fitting and independent temperature/CP sampling. "
            "Unique disjoint IDs do not establish independence or exchangeability, and the "
            "supplied model hash does not verify checkpoint provenance. No joint-axis, "
            "adaptive-trajectory, accepted-action, safety or performance guarantee. "
            "Fit time excludes label acquisition, model inference and target-device execution."
        ),
    }


__all__ = ["fit_frozen_calibration"]
