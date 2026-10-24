"""Sensor noise is tied to plant identity, not current batch composition."""
from dataclasses import replace

import numpy as np

from jev_tune.domains.pid.baselines import run_cmaes
from jev_tune.domains.pid.action import ActionSpace
from jev_tune.domains.pid.evaluate import evaluate_head
from jev_tune.domains.pid.metrics import cost_from_metrics
from jev_tune.domains.pid.plants import make_plant, simulate
from jev_tune.core.primitives import Answer, Choice, Noul, Option, Score
from jev_tune.domains.pid.scenarios import _stack


def noisy():
    return make_plant([1.], [.5, 1., 0.], noise_sigma=.01)


def test_subset_reorder_and_repeated_candidates_keep_their_noise():
    p = replace(noisy().take(np.array([0, 0])), noise_seed=np.array([71, 93]))
    gains = np.tile([1.6, .8, .02], (2, 1))
    full = simulate(p, gains, horizon=.5)
    order = np.array([1, 0, 1])
    rearranged = simulate(p.take(order), gains[order], horizon=.5)
    one = simulate(p.subset([1]), gains[1:], horizon=.5)
    np.testing.assert_array_equal(rearranged["y_curve"], full["y_curve"][order])
    np.testing.assert_array_equal(one["metrics"], full["metrics"][1:])
    assert not np.array_equal(full["y_curve"][0], full["y_curve"][1])


def test_stacking_and_polynomial_padding_preserve_identity():
    first = noisy()
    padded = replace(first, num=np.pad(first.num, ((0, 0), (2, 0))),
                     den=np.pad(first.den, ((0, 0), (2, 0))), noise_seed=None)
    np.testing.assert_array_equal(first.noise_seed, padded.noise_seed)
    second = replace(first, noise_seed=np.array([17]))
    stacked = _stack([first, second])
    np.testing.assert_array_equal(stacked.noise_seed, np.r_[first.noise_seed, 17])
    gains = np.tile([1.6, .8, .02], (2, 1))
    np.testing.assert_array_equal(
        simulate(stacked, gains, horizon=.5)["y_curve"][1:],
        simulate(second, gains[1:], horizon=.5)["y_curve"],
    )


class HoldAndStopFirst:
    def __init__(self):
        self.calls = 0

    def answer(self, feats, curves, questions=None):
        space = ActionSpace()
        options = [Option(str(m), float(np.log10(m))) for m in space.multipliers]
        probs = np.zeros((len(feats), space.k))
        probs[:, 3] = 1
        bands = np.full(len(feats), 2)
        if self.calls == 0:
            bands[0] = 0
        self.calls += 1
        score = np.zeros((len(feats), 5))
        score[np.arange(len(feats)), bands] = 1
        return Answer(
            [Choice(name, options, probs) for name in ("Kp", "Ki", "Kd")],
            Score("quality", list("abcde"), score), Noul("healthy", np.ones(len(feats))),
        )


def test_actual_early_stop_does_not_change_a_continuing_plants_sensor_noise():
    p = replace(noisy().take(np.array([0, 0])), noise_seed=np.array([71, 93]))
    gains = np.tile([1.6, .8, .02], (2, 1))
    result = evaluate_head(HoldAndStopFirst(), p, gains, np.ones(2), np.ones(2),
                           budget=3, early_stop=True, stop_on_no_action=False)
    assert result.actual_simulations.tolist() == [1, 3]
    np.testing.assert_array_equal(result.trajectory["gains"][1], np.tile(gains[1], (3, 1)))
    np.testing.assert_array_equal(result.trajectory["cost"][1], np.repeat(result.trajectory["cost"][1, 0], 3))
    assert not result.decisions["improved"][1].any()
    assert not result.decisions["harmful"][1].any()


def test_noisy_cma_returned_winner_cost_is_reproducible_outside_candidate_batch():
    p = noisy()
    result = run_cmaes(p, np.array([[1.6, .8, .02]]), budget=7, lam=4)
    response = simulate(p, result.gains)
    measured = cost_from_metrics(response["metrics"], y_curve=response["y_curve"])
    np.testing.assert_allclose(result.best_j, measured, rtol=0, atol=1e-12)


def test_zero_action_stops_without_repeating_a_fixed_sensor_noise_realization():
    p = noisy()
    gains = np.array([[1.6, .8, .02]])
    result = evaluate_head(HoldAndStopFirst(), p, gains, np.ones(1), np.ones(1), budget=4)
    assert result.actual_simulations.tolist() == [1]
    assert result.stop_reason.tolist() == ["no_action"]
    assert result.decisions["decision_valid"].tolist() == [[True, False, False]]
    assert not result.decisions["valid"].any()
    response = simulate(p, result.gains)
    j = cost_from_metrics(response["metrics"], y_curve=response["y_curve"])
    np.testing.assert_array_equal(result.best_j, j)
