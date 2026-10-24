"""VLA action-mask instance: a categorical action head behind the same shell.

A vision-language-action policy scores discrete action tokens. The shell
1) temperature-scales the logits, 2) forms a split-conformal label set,
3) removes tokens the domain forbids in this state (a hard mask, never learned),
4) executes only a single admissible token that is also the policy's top choice;
otherwise it holds with ``noop`` and says why. Categorical actions are never
averaged. Synthetic logits only: no robot, camera or trained VLA is involved.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...core.primitives import (calibrate_temperature, conformal_prediction_set,
                                fit_split_conformal, softmax)

ACTIONS = ("noop", "reach", "grasp", "lift", "place", "release", "retreat")
NOOP = 0


def allowed_actions(holding: bool) -> np.ndarray:
    """Domain rule: grasp only with an empty gripper, lift/place/release only while holding."""
    mask = np.ones(len(ACTIONS), dtype=bool)
    mask[[ACTIONS.index(a) for a in (("grasp",) if holding else ("lift", "place", "release"))]] = False
    return mask


@dataclass(frozen=True)
class VlaShell:
    temperature: float
    qhat: float

    @classmethod
    def fit(cls, t_logits, t_labels, cp_logits, cp_labels, alpha=0.10) -> "VlaShell":
        """Temperature and CP from two disjoint splits, as in core.calibration."""
        t = calibrate_temperature(t_logits, t_labels)
        cp = fit_split_conformal(softmax(cp_logits, axis=-1, temperature=t), cp_labels, alpha)
        return cls(t, float(cp.qhat_per_axis))

    def act(self, logits, allowed) -> tuple[int, str]:
        p = softmax(logits, temperature=self.temperature)
        admissible = conformal_prediction_set(p, self.qhat) & allowed
        top = int(np.argmax(p))
        if not allowed[top]:
            return NOOP, "forbidden_top"
        if admissible.sum() == 0:
            return NOOP, "empty_set"
        if admissible.sum() > 1:
            return NOOP, "ambiguous_set"
        return top, "act"


def synthetic(n: int, rng: np.random.Generator, signal: float = 2.5):
    """Overconfident noisy logits around an admissible teacher action."""
    holding = rng.random(n) < 0.5
    masks = np.stack([allowed_actions(h) for h in holding])
    labels = np.array([rng.choice(np.flatnonzero(m[1:]) + 1) for m in masks])
    logits = 3.0 * (signal * np.eye(len(ACTIONS))[labels] + rng.normal(0, 1.4, (n, len(ACTIONS))))
    return logits, labels, masks


def run(seed: int = 0, n: int = 600) -> dict:
    rng = np.random.default_rng(seed)
    (lt, yt, _), (lc, yc, _), (lx, yx, mx) = (synthetic(n, rng) for _ in range(3))
    shell = VlaShell.fit(lt, yt, lc, yc)
    raw = lx.argmax(axis=1)
    out = [shell.act(z, m) for z, m in zip(lx, mx)]
    act = np.array([a for a, _ in out])
    moved = act != NOOP
    cp = conformal_prediction_set(softmax(lx, axis=-1, temperature=shell.temperature), shell.qhat)
    return {
        "temperature": round(shell.temperature, 3),
        "cp_coverage": float(cp[np.arange(n), yx].mean()),
        "raw_forbidden_rate": float((~mx[np.arange(n), raw]).mean()),
        "raw_error_rate": float((raw != yx).mean()),
        "shell_forbidden_rate": float((~mx[np.arange(n), act])[moved].mean()) if moved.any() else 0.0,
        "shell_hold_rate": float((~moved).mean()),
        "shell_error_rate_when_acting": float((act[moved] != yx[moved]).mean()) if moved.any() else 0.0,
        "hold_reasons": {r: sum(1 for _, x in out if x == r) for r in
                         ("forbidden_top", "empty_set", "ambiguous_set")},
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
