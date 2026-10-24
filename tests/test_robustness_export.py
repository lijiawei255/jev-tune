"""Unmeasured stop padding is JSON null; measured nonfinite data is an error."""
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

from jev_tune.domains.pid.action import ActionSpace
from jev_tune.domains.pid.plants import make_plant
from jev_tune.core.primitives import Answer, Choice, Noul, Option, Score


@pytest.fixture
def robustness():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    spec = importlib.util.spec_from_file_location("robustness_export", root / "scripts/11_robustness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Hold:
    def answer(self, feats, curves, questions=None):
        space = ActionSpace()
        options = [Option(str(m), float(np.log10(m))) for m in space.multipliers]
        p = np.zeros((len(feats), space.k))
        p[:, 3] = 1
        score = np.zeros((len(feats), 5))
        score[:, 2] = 1
        return Answer([Choice(name, options, p) for name in ("Kp", "Ki", "Kd")],
                      Score("quality", list("abcde"), score), Noul("healthy", np.ones(len(feats))))


def test_stopped_run_exports_standard_json_with_truthful_measurement_masks(robustness, monkeypatch):
    monkeypatch.setattr(robustness, "ultimate_gain", lambda p: (np.ones(p.n), np.ones(p.n)))
    plants = make_plant([1.], [.5, 1., 0.])
    row = robustness.run_group(Hold(), plants, "stop", gate=True, budget=4)
    decoded = json.loads(json.dumps(row, allow_nan=False))
    p = decoded["per_plant"]
    assert row["actual_simulations_total"] == 1
    assert p["measured"] == [[True, False, False, False]]
    assert p["measured_cost"][0][0] == p["start_J"][0]
    assert p["measured_cost"][0][1:] == [None] * 3
    assert p["measured_gains"][0][1:] == [[None] * 3] * 3
    assert p["stop_reason"] == ["no_action"]
    assert p["decision_valid"] == [[True, False, False]]
    assert p["transition_valid"] == [[False] * 3]
    assert p["transition_events"][0][0] == "stop_no_action"


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_measured_nonfinite_values_are_never_silently_converted_to_null(robustness, bad):
    with pytest.raises(ValueError, match="measured trajectory values must be finite"):
        robustness.measured_values_json(np.array([[bad, np.nan]]), np.array([[True, False]]))
