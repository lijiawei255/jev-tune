"""Metric extraction and cost sanity."""

import numpy as np

from jev_tune.metrics import cost_from_metrics
from jev_tune.plants import METRIC_NAMES, sample_plants, simulate


def test_metric_columns():
    p = sample_plants(10, seed=2)
    res = simulate(p, np.tile([2.0, 1.0, 0.05], (p.n, 1)))
    assert res["metrics"].shape == (p.n, len(METRIC_NAMES))


def test_better_tuning_costs_less():
    """A relaxed gain set must beat a deliberately unstable one."""
    p = sample_plants(30, seed=3)
    good = simulate(p, np.tile([0.6, 0.4, 0.02], (p.n, 1)))
    bad = simulate(p, np.tile([40.0, 60.0, 2.0], (p.n, 1)))
    jg = cost_from_metrics(good["metrics"], y_curve=good["y_curve"])
    jb = cost_from_metrics(bad["metrics"], y_curve=bad["y_curve"])
    assert np.median(jg) < np.median(jb)


def test_cost_is_bounded_and_finite():
    p = sample_plants(30, seed=4)
    res = simulate(p, np.tile([1.0, 1.0, 0.0], (p.n, 1)))
    j = cost_from_metrics(res["metrics"], y_curve=res["y_curve"])
    assert np.isfinite(j).all()
    assert (j >= 0).all()


def test_divergence_penalised():
    """Driving with a huge gain must be flagged, not silently cheap."""
    p = sample_plants(20, seed=5)
    res = simulate(p, np.tile([500.0, 200.0, 20.0], (p.n, 1)))
    j = cost_from_metrics(res["metrics"], y_curve=res["y_curve"])
    assert np.median(j) > 3.0
