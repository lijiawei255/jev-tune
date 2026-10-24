"""Deterministic post-measurement safety gate, independent of every model output.

The typed head may propose and the policy may hold, but only this rule can
force recovery: after a measured cost exceeds ``max(best_factor * best + offset,
cost_floor)`` the parameters return to ``rollback_factor * best`` (domain units),
at most ``max_rollbacks`` times. It is recovery after measurement, not a
physical-safety proof. c/jev_head.c::jev_gate_rollback and
matlab/jev_tune_model.m implement the same thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SafetyGate:
    best_factor: float = 3.0
    offset: float = 1.0
    cost_floor: float = 8.0
    rollback_factor: float = 0.6
    max_rollbacks: int = 4

    def __post_init__(self):
        values = (self.best_factor, self.offset, self.cost_floor, self.rollback_factor)
        if not np.isfinite(values).all() or self.best_factor <= 0 or not 0 < self.rollback_factor <= 1:
            raise ValueError("gate factors must be finite, best_factor > 0, 0 < rollback_factor <= 1")
        if not isinstance(self.max_rollbacks, (int, np.integer)) or self.max_rollbacks < 0:
            raise ValueError("max_rollbacks must be a nonnegative integer")

    def threshold(self, best_cost):
        return np.maximum(self.best_factor * np.asarray(best_cost, dtype=float) + self.offset,
                          self.cost_floor)

    def trips(self, cost, best_cost, rollbacks) -> np.ndarray:
        """True where the measured cost must trigger a rollback."""
        return (np.asarray(cost, dtype=float) > self.threshold(best_cost)) & (
            np.asarray(rollbacks) < self.max_rollbacks)

    def recover(self, best_params) -> np.ndarray:
        return np.asarray(best_params, dtype=float) * self.rollback_factor


__all__ = ["SafetyGate"]
