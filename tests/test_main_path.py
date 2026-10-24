"""Every shell layer must change something observable on the real PID main path."""
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("onnxruntime")

from jev_tune.domains.pid.baselines import zn_gains
from jev_tune.domains.pid.decision import UnknownQuestion, load_backend, tuner_questions
from jev_tune.domains.pid.evaluate import evaluate_head
from jev_tune.domains.pid.plants import sample_plants, ultimate_gain

MODELS = Path(__file__).resolve().parents[1] / "models"
F, C = np.zeros((2, 20), np.float32), np.zeros((2, 2, 64), np.float32)


@pytest.fixture(scope="module")
def loop():
    head = load_backend(MODELS, kind="onnx")
    plants = sample_plants(6, seed=3, heldout=True)
    ku, tu = ultimate_gain(plants)
    return head, plants, zn_gains(plants), ku, tu


def test_temperature_layer_is_applied(loop):
    head = loop[0]
    raw = load_backend(MODELS, kind="onnx", calibrate=False)
    assert (head.temperature > 1).all()
    assert not np.allclose(head.answer(F, C).choice[0].probs, raw.answer(F, C).choice[0].probs)


def test_monitor_only_records_and_hard_hold_vetoes_before_actuation(loop):
    head, plants, gains, ku, tu = loop
    mon = evaluate_head(head, plants, gains, ku, tu, budget=8, conformal="monitor").decisions
    hard = evaluate_head(head, plants, gains, ku, tu, budget=8, conformal="hard_hold").decisions
    vm, vh = mon["decision_valid"], hard["decision_valid"]
    assert not mon["axis_held"][vm].any() and mon["conformal_would_hold"][vm].any()
    assert hard["axis_held"][vh].any()
    np.testing.assert_array_equal(hard["axis_held"][vh], hard["conformal_would_hold"][vh])
    assert (hard["step"][vh][hard["axis_held"][vh]] == 0).all()


def test_onnx_backend_rejects_an_incomplete_question_set(loop):
    with pytest.raises(UnknownQuestion):
        loop[0].answer(F, C, [tuner_questions()[0]])
