"""jev-tune: Jev-inspired calibrated decision & safety shell.

``jev_tune.core`` is the domain-agnostic shell (numpy only): typed
``Choice`` / ``Score`` / ``Noul`` answers, temperature + split-conformal
calibration, a-priori Hold and the deterministic ``SafetyGate``.
``jev_tune.domains.pid`` is the complete PID testbed; ``jev_tune.domains.light``
holds small pure-Python instances. Names below are resolved lazily so importing
the core never loads the PID simulator.
"""
from importlib import import_module

_LAZY = {
    "PlantSet": "domains.pid.plants", "sample_plants": "domains.pid.plants",
    "simulate": "domains.pid.plants", "gains_to_params": "domains.pid.plants",
    "METRIC_NAMES": "domains.pid.plants",
    "cost_from_metrics": "domains.pid.metrics", "is_failed": "domains.pid.metrics",
    "build_state": "domains.pid.state", "FEATURE_NAMES": "domains.pid.state",
    "N_FEATURES": "domains.pid.state",
    "Choice": "core.primitives", "Score": "core.primitives", "Noul": "core.primitives",
    "Answer": "core.primitives", "softmax": "core.primitives",
    "ActionSpace": "domains.pid.action", "decode_choice": "domains.pid.action",
    "apply_step": "domains.pid.action",
}
__all__ = sorted(_LAZY)


def __getattr__(name):
    if name not in _LAZY:
        raise AttributeError(f"module 'jev_tune' has no attribute {name!r}")
    return getattr(import_module(f".{_LAZY[name]}", __name__), name)
