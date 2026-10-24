"""Exercise diagnostic numerics against frozen production calibration logic."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from jev_tune.primitives import calibrate_temperature, fit_split_conformal, softmax

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runtime_diagnostic_test", ROOT / "scripts/51_diagnose_calibration_runtime.py")
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


@pytest.mark.parametrize("seed", [7, 23, 311])
def test_golden_trace_exactly_matches_frozen_search_and_every_branch(seed):
    rng = np.random.default_rng(seed)
    logits = rng.normal(size=(37, 5))
    labels = rng.integers(0, 5, size=37)
    actual, trace = diag.golden_trace(logits, labels)
    assert actual == calibrate_temperature(logits, labels)
    assert len(trace) == 60
    lo, hi = .05, 20.
    for iteration, row in enumerate(trace):
        assert row["iteration"] == iteration and row["lo"] == lo and row["hi"] == hi
        assert lo < row["m1"] < row["m2"] < hi
        left = diag.nll(logits, labels, row["m1"])
        right = diag.nll(logits, labels, row["m2"])
        assert row["nll_m1"] == left and row["nll_m2"] == right
        if left < right:
            assert row["branch"] == "hi=m2"
            hi = row["m2"]
        else:
            assert row["branch"] == "lo=m1"
            lo = row["m1"]
    assert actual == .5 * (lo + hi)


def test_flat_logits_record_real_ties_without_changing_search():
    logits = np.zeros((19, 4))
    labels = np.arange(19) % 4
    temperature, trace = diag.golden_trace(logits, labels)
    assert temperature == calibrate_temperature(logits, labels)
    assert all(row["branch"] == "lo=m1" for row in trace)
    assert all(row["nll_ulp_distance"] == 0 and row["nll_m1_minus_m2"] == 0 for row in trace)
    assert diag.ulps(1., np.nextafter(1., np.inf)) == 1


def example():
    rng = np.random.default_rng(915)
    return rng.normal(size=(41, 2, 4)), rng.integers(0, 4, size=(41, 2)), rng.normal(size=(53, 2, 4)), rng.integers(0, 4, size=(53, 2))


def test_same_temperature_preserves_rank_threshold_and_complete_sets():
    logits, labels, test_logits, test_labels = example()
    temperature = [0.7, 1.3]
    probabilities = softmax(logits, temperature=np.array(temperature)[None, :, None])
    fitted = fit_split_conformal(probabilities, labels, alpha=.1)
    archive = {}
    result = diag.cp_comparison(archive, "same", logits, labels, list(range(41)), test_logits, test_labels,
                                temperature, temperature, fitted.qhat_per_axis.tolist())
    assert result["refit_qhat_minus_recorded_t_qhat"] == [0., 0.]
    assert result["saved_qhat_minus_current_recorded_t_qhat"] == [0., 0.]
    assert result["recorded_t_order_statistic"] == result["refit_t_order_statistic"]
    for axis, record in enumerate(result["recorded_t_order_statistic"]):
        assert record["rank"] == fitted.quantile_rank
        assert record["qhat"] == fitted.qhat_per_axis[axis]
    np.testing.assert_array_equal(archive["same_probabilities_recorded_t"], archive["same_probabilities_refit_t"])
    np.testing.assert_array_equal(archive["same_sort_recorded_t"], archive["same_sort_refit_t"])
    for field in ("cp_set_difference", "test_set_difference", "saved_vs_refit_test_sets"):
        assert result[field]["differing_options_per_axis"] == [0, 0]
        assert result[field]["differing_state_axes_per_axis"] == [0, 0]
    expected_sets = (1 - probabilities) <= fitted.qhat_per_axis[None, :, None]
    np.testing.assert_array_equal(result["cp_set_difference"]["recorded_temperature_mean_set_size"], expected_sets.sum(axis=-1).mean(axis=0))


def test_changed_temperatures_expose_threshold_and_membership_changes_readonly():
    logits, labels, test_logits, test_labels = example()
    inputs = [logits, labels, test_logits, test_labels]
    before = [value.copy() for value in inputs]
    result = diag.cp_comparison({}, "changed", logits, labels, list(range(41)), test_logits, test_labels,
                                [.1, .2], [3., 4.])
    assert any(value != 0 for value in result["refit_qhat_minus_recorded_t_qhat"])
    assert sum(result["test_set_difference"]["differing_options_per_axis"]) > 0
    for actual, original in zip(inputs, before): np.testing.assert_array_equal(actual, original)


def test_tiny_calibration_population_reports_explicit_rank_overflow():
    scores = np.array([[.2, .4], [.3, .1]])
    qhat, order, records = diag.sorted_scores(scores, ["a", "b"])
    np.testing.assert_array_equal(qhat, [1., 1.])
    assert order.shape == scores.shape
    assert all(row["rank"] == 3 and row["kth_index"] is None and row["kth_identity"] is None for row in records)


def test_existing_output_is_rejected_before_diagnosis_or_model_access(tmp_path):
    sentinel = tmp_path / "existing-model.json"
    sentinel.write_bytes(b'{"weight":1.25}\n')
    before = diag.sha(sentinel)
    with pytest.raises(FileExistsError, match="Refuse to overwrite"):
        diag.diagnose(tmp_path, label="must-not-run")
    assert diag.sha(sentinel) == before
    assert list(tmp_path.iterdir()) == [sentinel]
