"""Behavioral checks that fail if variance, clipping or gate ordering disappears."""
import numpy as np
import pytest

import jev_tune.domains.pid.evaluate as evaluator
from jev_tune.core.policy import AbstainPolicy, REASON_NOUL, decide
from jev_tune.domains.pid.action import ActionSpace, decode_choice
from jev_tune.core.primitives import Answer, Choice, Noul, Option, Score


def numeric_answer(probabilities, payloads=(-.2, 0., .2)):
    return Answer([Choice("offset", [Option(str(value), value) for value in payloads],
                          np.asarray(probabilities))])


def test_variance_reduces_steps_with_the_same_nonzero_expected_payload():
    # Both expectations are .1; variances are .01 and .03 respectively.
    low_variance = decide(numeric_answer([0., .5, .5]), max_step=.2)
    high_variance = decide(numeric_answer([.25, 0., .75]), max_step=.2)
    uniform_vocabulary_variance = .08 / 3.
    assert low_variance.step[0] == pytest.approx(.1 / (1. + .01 / uniform_vocabulary_variance), abs=1e-15)
    assert high_variance.step[0] == pytest.approx(.1 / (1. + .03 / uniform_vocabulary_variance), abs=1e-15)
    assert 0. < high_variance.step[0] < low_variance.step[0] < .1


@pytest.mark.parametrize("probabilities,expected", [([1., 0., 0.], -.07), ([0., 0., 1.], .07)])
def test_numeric_clip_is_exercised_by_payloads_larger_than_the_cap(probabilities, expected):
    result = decide(numeric_answer(probabilities, (-10., 0., 10.)), max_step=.07)
    np.testing.assert_array_equal(result.step, [expected])
    # Exercise the PID decoding entry independently with an active trust bound.
    space = ActionSpace(multipliers=(.01, 1., 100.), max_step=.07)
    np.testing.assert_array_equal(decode_choice(np.asarray(probabilities), space), expected)


def test_noul_hold_precedes_measurement_and_deterministic_rollback_follows_it(monkeypatch):
    class OnePlant:
        n = 1

        def take(self, indices):
            assert list(indices) == [0]
            return self

    class Policy:
        def __init__(self):
            self.calls = 0

        def answer(self, features, curves, questions=None):
            self.calls += 1
            space = ActionSpace()
            options = [Option(str(value), float(value)) for value in space.deltas]
            probabilities = np.zeros((len(features), space.k))
            probabilities[:, -1] = 1.
            quality = np.zeros((len(features), 5))
            quality[:, 2] = 1.
            return Answer([Choice(name, options, probabilities) for name in ("Kp", "Ki", "Kd")],
                          Score("quality", list("abcde"), quality),
                          Noul("healthy", np.zeros(len(features))))

    actual_gains = []

    def measured(plant, gains, **kwargs):
        actual_gains.append(gains.copy())
        cost = np.where(gains[:, 0] > 1.5, 100., 1.)
        return {"metrics": cost[:, None], "y_curve": np.zeros((1, 64)),
                "u_curve": np.zeros((1, 64))}

    monkeypatch.setattr(evaluator, "simulate", measured)
    monkeypatch.setattr(evaluator, "cost_from_metrics", lambda metrics, **kwargs: metrics[:, 0])
    monkeypatch.setattr(evaluator, "build_state", lambda *args, **kwargs:
                        (np.zeros((1, 20)), np.zeros((1, 2, 64))))
    policy = Policy()
    guarded = evaluator.evaluate_head(policy, OnePlant(), np.ones((1, 3)), np.ones(1), np.ones(1),
                                      budget=3, abstain=AbstainPolicy(0., 0., .5))
    assert len(actual_gains) == guarded.actual_simulations[0] == 1
    assert guarded.decisions["reason"][0, 0] == REASON_NOUL
    assert not guarded.decisions["valid"].any() and not guarded.rollbacks.any()
    np.testing.assert_array_equal(guarded.gains, np.ones((1, 3)))
    actual_gains.clear()
    policy = Policy()
    unguarded = evaluator.evaluate_head(policy, OnePlant(), np.ones((1, 3)), np.ones(1), np.ones(1),
                                        budget=3, abstain=None)
    assert len(actual_gains) == unguarded.actual_simulations[0] == 3
    np.testing.assert_array_equal(actual_gains[1], [[2., 2., 2.]])
    np.testing.assert_array_equal(actual_gains[2], [[.6, .6, .6]])
    assert unguarded.rollbacks.tolist() == [1]
    assert unguarded.decisions["event"].tolist() == [["proposal", "rollback"]]
    assert policy.calls == 1  # Measured failure triggers rollback before another proposal.
    assert unguarded.decision_report()["n_rollbacks"] == 1
