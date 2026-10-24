"""Adversarial numeric boundaries and a non-PID, additive two-axis port."""
import numpy as np
import pytest

from jev_tune.core.policy import AbstainPolicy, apply_abstention, decide
from jev_tune.domains.pid.action import ActionSpace, apply_step
from jev_tune.domains.pid.decision import NumericBackend
from jev_tune.core.primitives import Answer, Choice, Noul, Option, softmax


def test_non_pid_payloads_drive_additive_two_axis_actions():
    answer = Answer(choice=[
        Choice("heater offset", [Option("down", -.1), Option("up", .1)], np.array([0., 1.])),
        Choice("fan offset", [Option("down", -.2), Option("up", .2)], np.array([1., 0.])),
    ], noul=Noul("valid", .9))
    result = decide(answer, max_step=.15, abstain=AbstainPolicy())
    np.testing.assert_allclose(np.array([.5, .5]) + result.step, [.6, .35])
    assert result.held.shape == (2,)
    assert not result.held.any()


def test_explicit_pid_schema_rejects_changed_payload():
    s = ActionSpace()
    ch = Choice("gain", [Option(str(i), .1) for i in range(s.k)], np.eye(s.k)[-1])
    with pytest.raises(ValueError, match="payloads disagree"):
        decide(Answer(choice=[ch]), s)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_invalid_steps_confidence_and_noul_raise(bad):
    for field in range(3):
        values = [np.zeros((1, 3)), np.ones((1, 3)), np.ones(1)]
        values[field].flat[0] = bad
        with pytest.raises(ValueError, match="finite"):
            apply_abstention(*values, AbstainPolicy())
    with pytest.raises(ValueError, match="finite"):
        apply_step(np.ones(3), np.array([bad, 0, 0]))


@pytest.mark.parametrize("probs", [[np.nan, 0], [-.1, 1.1], [.2, .2]])
def test_invalid_probability_distribution_is_rejected(probs):
    with pytest.raises(ValueError, match="probabilities"):
        decide(Answer(choice=[Choice("q", [Option("a", 0), Option("b", .1)], probs)]))


@pytest.mark.parametrize("temperature", [0, -1, np.nan, np.inf])
def test_invalid_temperature_is_rejected(temperature):
    with pytest.raises(ValueError, match="temperature"):
        softmax(np.ones(2), temperature=temperature)
    with pytest.raises(ValueError, match="temperature"):
        NumericBackend(None, temperature=[temperature] * 3)


def test_confident_zero_is_action_not_abstention():
    ch = Choice("offset", [Option("zero", 0)], np.array([1.]))
    d = decide(Answer(choice=[ch]))
    assert d.step[0] == 0
    assert not d.held[0]


def test_hold_preserves_parameter_bits_and_extreme_temperature_is_finite():
    gains = np.array([.02, .35, 7.7])
    np.testing.assert_array_equal(apply_step(gains, np.zeros(3)), gains)
    np.testing.assert_array_equal(softmax(np.array([1., 2.]), temperature=1e-320), [0., 1.])
    backend = NumericBackend(None, temperature=[1e-320] * 3)
    p = backend._choice_probs(np.tile(np.array([1., 2.]), (1, 3, 1)))
    assert np.isfinite(p).all()
    np.testing.assert_array_equal(p.sum(axis=-1), np.ones((1, 3)))
