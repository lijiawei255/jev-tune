"""Baselines and the cost function: cheap, pure, and never unit-tested before.

These run on two plants, so the whole file is a couple of seconds; they exist to
pin the accounting (budget spent) and the shapes the comparison tables rely on.
"""

import numpy as np
import pytest

from jev_tune.domains.pid.baselines import (
    choose_zn_shrink,
    relay_estimate,
    run_bo,
    run_cmaes,
    run_grid,
    run_relay,
    run_shrunk_zn,
    run_simplex,
    run_swept_zn,
    run_vocab_hill,
    run_zn,
    zn_gains,
)
from jev_tune.domains.pid.metrics import cost_from_metrics, is_failed
from jev_tune.domains.pid.plants import (
    TRAIN_FAMILIES,
    estimate_ultimate_gain,
    make_plant,
    sample_plants,
    simulate,
    ultimate_gain,
)


def _plants(n=2):
    return sample_plants(n, seed=5, families=TRAIN_FAMILIES)


def test_zn_gains_and_run_zn():
    p = _plants()
    g = zn_gains(p)
    assert g.shape == (p.n, 3)
    assert np.all(g > 0)
    r = run_zn(p)
    assert r.eval_axis.tolist() == [1.0]
    assert np.all(np.isfinite(r.best_j))


def test_shrunk_zn_uses_the_factors():
    p = _plants()
    r = run_shrunk_zn(p, (0.3, 0.1, 1.0))
    expected = zn_gains(p) * np.array([0.3, 0.1, 1.0])
    assert np.allclose(r.gains, expected)
    assert r.eval_axis.tolist() == [1.0]


def test_choose_zn_shrink_over_a_one_point_grid():
    p = _plants()
    factors, median_j, sims = choose_zn_shrink(p, kp=(0.3,), ki=(0.1,), kd=(1.0,))
    assert factors == (0.3, 0.1, 1.0)
    assert sims == 1
    assert np.isfinite(median_j)


def test_hill_climb_spends_exactly_the_budget():
    p = _plants()
    r = run_vocab_hill(p, zn_gains(p), budget=7)
    assert r.eval_axis[-1] == 7.0
    assert r.history.shape[1] == 7
    assert np.all(np.diff(r.history, axis=1) <= 1e-12)


@pytest.mark.parametrize("budget", [4, 8, 20])
def test_simplex_never_overshoots(budget):
    p = _plants()
    r = run_simplex(p, zn_gains(p), budget=budget)
    assert r.eval_axis[-1] <= budget


def test_cmaes_spends_exactly_the_budget():
    p = _plants()
    r = run_cmaes(p, zn_gains(p), budget=6, lam=4)
    assert r.eval_axis[-1] == 6.0


def test_bo_spends_exactly_the_budget_even_below_n_init():
    p = _plants()
    r = run_bo(p, zn_gains(p), budget=3, n_init=6)
    assert r.eval_axis[-1] == 3.0


def test_grid_sweep_reports_its_cost():
    p = _plants()
    r = run_grid(p, zn_gains(p), kp=(0.5, 1.0), ki=(0.5, 1.0), kd=(1.0,), batch=2)
    assert r.eval_axis[-1] == 4.0
    assert np.all(np.isfinite(r.best_j))


def test_relay_and_swept_zn_have_the_documented_budgets():
    p = _plants(4)
    ku, tu = relay_estimate(p)
    assert ku.shape == (p.n,) and tu.shape == (p.n,)
    assert run_relay(p).eval_axis.tolist() == [2.0]
    assert run_swept_zn(p).eval_axis.tolist() == [8.0]


def test_ultimate_gain_analytic_vs_measured():
    p = _plants(4)
    ku, tu = ultimate_gain(p)
    assert ku.shape == (p.n,)
    ku_s, tu_s, sims = estimate_ultimate_gain(p)
    assert sims == 7
    assert ku_s.shape == (p.n,)
    # the measurement is coarse (a 7-point grid), so only its sign is asserted
    ok = np.isfinite(ku_s)
    assert np.all(ku_s[ok] > 0)


def test_cost_objectives_and_failure_flag():
    p = _plants()
    res = simulate(p, zn_gains(p))
    for objective in ("step", "tracking", "disturbance"):
        j = cost_from_metrics(
            res["metrics"], y_curve=res["y_curve"], objective=objective
        )
        assert j.shape == (p.n,)
        assert np.all(np.isfinite(j))
    with pytest.raises(ValueError):
        cost_from_metrics(res["metrics"], objective="nonsense")
    assert is_failed(res["metrics"], res["y_curve"]).shape == (p.n,)


def test_make_plant_with_nonlinearities_still_simulates():
    plant = make_plant(
        [1.0],
        [0.5, 1.0, 0.0],
        delay_s=0.05,
        u_max=1.0,
        dead_zone=0.02,
        noise_sigma=0.01,
    )
    assert plant.n == 1
    res = simulate(plant, np.array([[1.5, 0.8, 0.02]]))
    assert res["y_curve"].shape == (1, 64)
    assert np.all(np.isfinite(res["metrics"]))
