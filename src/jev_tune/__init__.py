"""jev-tune: System-1 (Jev-style) decision head for control-parameter autotuning.

Runtime contract: every decision is expressed as one of three Jev primitives --
``Choice`` (pick one of K), ``Score`` (ordered rubric), ``Noul`` (calibrated
yes/no).  There is no parallel "regress the gain directly" pathway.
"""

from .domains.pid.plants import PlantSet, sample_plants, simulate, gains_to_params, METRIC_NAMES
from .domains.pid.metrics import cost_from_metrics, is_failed
from .domains.pid.state import build_state, FEATURE_NAMES, N_FEATURES
from .core.primitives import Choice, Score, Noul, Answer, softmax
from .domains.pid.action import ActionSpace, decode_choice, apply_step

__all__ = [
    "PlantSet",
    "sample_plants",
    "simulate",
    "gains_to_params",
    "compute_metrics",
    "cost_from_metrics",
    "is_failed",
    "METRIC_NAMES",
    "build_state",
    "FEATURE_NAMES",
    "N_FEATURES",
    "Choice",
    "Score",
    "Noul",
    "Answer",
    "softmax",
    "ActionSpace",
    "decode_choice",
    "apply_step",
]
