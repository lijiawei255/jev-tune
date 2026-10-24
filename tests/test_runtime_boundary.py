"""Archived numerical failures and continuous actions remain independently visible."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runtime_boundary_test", ROOT/"scripts/54_compare_calibration_runtimes.py")
boundary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boundary)


def test_same_complete_sets_do_not_hide_continuous_action_difference():
    spec = importlib.util.spec_from_file_location("runtime_boundary_runner", ROOT/"scripts/45_nonpid_transfer.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    left = np.array([[[.1, .1, .6, .1, .1], [.1, .1, .6, .1, .1]]])
    right = left.copy()
    right[0, 0, 0] += .001
    right[0, 0, 4] -= .001
    q = [.99, .99]
    assert np.array_equal(boundary.sets(left, q), boundary.sets(right, q))
    result = boundary.actiondiff(runner, left, q, right, q)
    assert result["step_max_abs_per_axis"][0] > 0
    assert result["step_max_abs_per_axis"][1] == 0
    assert result["different_step_states_per_axis"] == [1, 0]
    assert result["held_disagreements_per_axis"] == [0, 0]


def test_complete_sets_count_every_option_including_ties():
    p = np.array([[[.1, .2, .3, .2, .2], [.1, .2, .3, .2, .2]]])
    left = boundary.sets(p, [.8, .8])
    q = [.7, .8]
    right = boundary.sets(p, q)
    result = boundary.setdiff(left, right)
    assert result["different_options_per_axis"] == [3, 0]
    assert result["different_state_axes_per_axis"] == [1, 0]


def test_document_is_generated_from_observed_differences():
    import json
    observed = json.loads((ROOT/boundary.RESULT).read_text(encoding="utf-8"))
    assert boundary.render(observed) == (ROOT/"docs/NUMERICAL_REPRODUCIBILITY.md").read_text(encoding="utf-8")
    observed["summary"]["changed_CP_options"] = 11
    assert boundary.render(observed) != (ROOT/"docs/NUMERICAL_REPRODUCIBILITY.md").read_text(encoding="utf-8")


def test_stale_archived_comparison_fails(tmp_path, monkeypatch):
    import json
    target = tmp_path/boundary.RESULT
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"genuine": False}), encoding="utf-8")
    monkeypatch.setattr(boundary, "compare", lambda root: {"genuine": True})
    with pytest.raises(AssertionError, match="Archived runtime comparison changed"):
        boundary.check(tmp_path)
