"""The typed decision layer: contract, slot registry, backend parity."""

import json
from pathlib import Path

import numpy as np
import pytest

from jev_tune.domains.pid.decision import (
    AXES,
    NumericBackend,
    OnnxBackend,
    Question,
    UnknownQuestion,
    as_backend,
    tuner_questions,
)
from jev_tune.domains.pid.action import ActionSpace, decode_answer

MODELS = Path(__file__).resolve().parents[1] / "models"
torch = pytest.importorskip("torch")


@pytest.fixture(scope="module")
def backend():
    return NumericBackend.from_checkpoint(MODELS)


def _state(n=2):
    rng = np.random.default_rng(0)
    return (
        rng.standard_normal((n, 20)).astype(np.float32),
        rng.standard_normal((n, 2, 64)).astype(np.float32),
    )


def test_question_registry_has_five_fixed_slots():
    qs = tuner_questions()
    assert [q.id for q in qs] == ["step:Kp", "step:Ki", "step:Kd", "quality", "healthy"]
    assert [q.kind for q in qs] == ["choice", "choice", "choice", "score", "noul"]


def test_answer_carries_the_three_primitives(backend):
    f, c = _state()
    a = backend.answer(f, c)
    assert len(a.choice) == len(AXES)
    for ch in a.choice:
        assert ch.probs.shape == (2, ActionSpace().k)
        assert np.allclose(ch.probs.sum(axis=-1), 1.0)
    assert a.score.dist.shape == (2, 5)
    assert a.noul.p_true.shape == (2,)
    assert np.all((a.noul.p_true >= 0) & (a.noul.p_true <= 1))


def test_decode_reads_the_typed_answer(backend):
    f, c = _state()
    step = decode_answer(backend.answer(f, c))
    assert step.shape == (2, 3)
    assert np.all(np.abs(step) <= ActionSpace().max_step + 1e-9)


def test_unknown_question_is_an_error_not_a_guess(backend):
    f, c = _state()
    with pytest.raises(UnknownQuestion) as exc:
        backend.answer(f, c, questions=[Question("torque:Kp", "choice", "?")])
    assert "torque:Kp" in str(exc.value)


def test_partial_question_set_is_answered(backend):
    f, c = _state()
    qs = [q for q in tuner_questions() if q.kind == "choice"]
    a = backend.answer(f, c, questions=qs)
    assert len(a.choice) == 3
    assert a.score is None and a.noul.p_true is None


def test_temperature_is_applied_and_switchable(backend):
    f, c = _state()
    smooth = NumericBackend(
        backend.model, temperature=[20.0, 20.0, 20.0], calibrate=True
    )
    raw = NumericBackend(backend.model, temperature=[20.0, 20.0, 20.0], calibrate=False)
    p_cal = smooth.answer(f, c).choice[0].probs
    p_raw = raw.answer(f, c).choice[0].probs
    assert not np.allclose(p_cal, p_raw), "T=20 must change the distribution"
    # a temperature above 1 flattens the distribution: the max probability drops
    assert p_cal.max(axis=-1).mean() < p_raw.max(axis=-1).mean()


def test_temperature_comes_from_the_checkpoint(backend):
    cal = json.loads((MODELS / "calibration.json").read_text(encoding="utf-8-sig"))
    assert np.allclose(backend.temperature, cal["choice_temperature"])


def test_as_backend_wraps_a_bare_head(backend):
    wrapped = as_backend(backend.model)
    assert isinstance(wrapped, NumericBackend)
    f, c = _state(1)
    assert wrapped.answer(f, c).choice[0].probs.shape == (1, ActionSpace().k)


def test_bare_head_keeps_its_calibration_through_as_backend(backend):
    """Regression: wrapping a checked-out head used to drop its temperatures."""
    wrapped = as_backend(backend.model)
    assert wrapped.calibrate is True
    assert np.allclose(wrapped.temperature, backend.temperature)


def test_load_backend_can_disable_calibration():
    from jev_tune.domains.pid.decision import load_backend

    off = load_backend(MODELS, calibrate=False)
    assert off.calibrate is False
    on = load_backend(MODELS)
    assert on.calibrate is True


def test_a_step_needs_all_three_axes(backend):
    """Asking only for `quality` cannot produce a gain step; it must raise."""
    f, c = _state(1)
    only_score = [q for q in tuner_questions() if q.kind == "score"]
    with pytest.raises(UnknownQuestion):
        backend.answer(f, c, questions=only_score)


def test_onnx_and_torch_agree():
    if not (MODELS / "jev_head.onnx").is_file():
        pytest.skip("no exported ONNX graph")
    pytest.importorskip("onnxruntime")
    from jev_tune.domains.pid.decision import load_backend

    f, c = _state(16)
    torch_b = load_backend(MODELS)
    onnx_b = load_backend(MODELS, kind="onnx")
    assert np.allclose(torch_b.temperature, onnx_b.temperature), "same calibration"
    a_t = torch_b.answer(f, c)
    a_o = onnx_b.answer(f, c)
    agree = 0
    total = 0
    for i in range(3):
        # near-one-hot distributions amplify float32 export noise; allow a few
        # argmax flips on near-ties, but not a behavioural difference
        agree += int((a_t.choice[i].argmax == a_o.choice[i].argmax).sum())
        total += len(a_t.choice[i].argmax)
        assert np.allclose(a_t.choice[i].probs, a_o.choice[i].probs, atol=2e-3)
    assert agree / total >= 0.95, f"argmax agreement {agree}/{total}"
    assert np.allclose(decode_answer(a_t), decode_answer(a_o), atol=2e-2)
    assert np.allclose(a_t.noul.p_true, a_o.noul.p_true, atol=1e-3)
