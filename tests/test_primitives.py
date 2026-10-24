"""Jev primitives and the decoding layer."""

import numpy as np
import pytest

from jev_tune.domains.pid.action import ActionSpace, apply_step, decode_choice, interval_refine
from jev_tune.core.primitives import Choice, Noul, Option, Score, softmax


def test_softmax_normalised():
    p = softmax(np.array([[1.0, 2.0, 3.0]]))
    assert p.sum() == pytest.approx(1.0)
    assert np.argmax(p) == 2


def test_choice_expectation_and_variance():
    c = Choice(
        question="q",
        options=[Option("a", -0.1), Option("b", 0.0), Option("c", 0.1)],
        probs=np.array([0.0, 1.0, 0.0]),
    )
    assert c.expected_delta() == pytest.approx(0.0)
    assert c.variance() == pytest.approx(0.0)

    c.probs = np.array([0.5, 0.0, 0.5])
    assert c.expected_delta() == pytest.approx(0.0)
    assert c.variance() == pytest.approx(0.01)


def test_vocabulary_is_symmetric_and_ordered():
    d = ActionSpace().deltas
    assert len(d) == ActionSpace().k
    assert np.all(np.diff(d) > 0), "options must be ordered"
    assert abs(d[0] + d[-1]) < 1e-9, "vocabulary must be symmetric in log space"
    assert d[len(d) // 2] == pytest.approx(0.0), "one option must be 'hold'"


def test_decode_clips_to_trust_region():
    space = ActionSpace()
    probs = np.zeros((1, 3, space.k))
    probs[:, :, 0] = 1.0  # always the biggest step down
    step = decode_choice(probs, space)
    assert step.shape == (1, 3)
    assert np.all(np.abs(step) <= space.max_step + 1e-12)


def test_variance_shrinks_step():
    space = ActionSpace()
    confident = np.zeros((1, 3, space.k))
    confident[:, :, -1] = 1.0
    uncertain = np.tile(np.full(space.k, 1.0 / space.k), (1, 3, 1))
    s_conf = decode_choice(confident, space)[0]
    s_unc = decode_choice(uncertain, space)[0]
    assert np.all(np.abs(s_unc) <= np.abs(s_conf) + 1e-12)


def test_interval_refine_halves_width():
    c, w = interval_refine(0.0, 0.15, np.array([0.0, 1.0, 0.0]), k=3)
    assert w == pytest.approx(0.05)
    assert abs(c) <= 0.15


def test_apply_step_respects_bounds():
    g = apply_step(
        np.array([1.0, 1.0, 1.0]), np.array([5.0, -5.0, 0.0]), lo=0.1, hi=10.0
    )
    assert g[0] == pytest.approx(10.0)
    assert g[1] == pytest.approx(0.1)
    assert g[2] == pytest.approx(1.0)


def test_score_and_noul_contract():
    s = Score(
        question="how good", levels=list("abcde"), dist=np.array([0, 0, 0, 1.0, 0])
    )
    assert s.expected() == pytest.approx(3.0)
    assert Noul(statement="stable", p_true=0.9).true
    assert not Noul(statement="stable", p_true=0.1).true
