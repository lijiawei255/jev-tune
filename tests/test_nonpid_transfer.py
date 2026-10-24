"""Non-PID transfer must preserve measurement, observation and budget contracts."""
from __future__ import annotations

import importlib.util
import copy
from pathlib import Path

import numpy as np
import pytest
from scipy.ndimage import median_filter
from scipy.signal import butter, sosfiltfilt


ROOT = Path(__file__).resolve().parents[1]
TASK_PATH = ROOT / "examples" / "denoise_transfer" / "task.py"
spec = importlib.util.spec_from_file_location("nonpid_transfer_task_tests", TASK_PATH)
task_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(task_module)
DenoiseTask = task_module.DenoiseTask
study_spec = importlib.util.spec_from_file_location(
    "nonpid_transfer_runner_tests", ROOT / "scripts" / "45_nonpid_transfer.py")
study = importlib.util.module_from_spec(study_spec)
study_spec.loader.exec_module(study)
audit_spec = importlib.util.spec_from_file_location(
    "nonpid_transfer_audit_tests", ROOT / "scripts" / "46_verify_nonpid_transfer.py")
audit_module = importlib.util.module_from_spec(audit_spec)
audit_spec.loader.exec_module(audit_module)


def reference_filter(noisy, theta):
    """Independently invoke the specified SciPy pipeline, including endpoints."""
    center = median_filter(noisy, size=9, mode="reflect")
    mad = median_filter(np.abs(noisy - center), size=9, mode="reflect")
    bound = (1.0 + 5.0 * theta[0]) * np.maximum(1.4826 * mad, .02)
    clipped = np.minimum(np.maximum(noisy, center - bound), center + bound)
    cutoff = .02 * (.35 / .02) ** theta[1]
    return sosfiltfilt(butter(2, 2.0 * cutoff, output="sos"), clipped)


def lag_one(values):
    if np.std(values[:-1]) == 0 or np.std(values[1:]) == 0:
        return 0.0
    return float(np.corrcoef(values[:-1], values[1:])[0, 1])


@pytest.mark.parametrize("theta", [[0., 0.], [1., 1.], [.2, .7]])
def test_denoising_uses_real_scipy_filter_and_raw_reference_mse(theta):
    task = DenoiseTask(940101, 3)
    expected = reference_filter(task._noisy, theta)
    np.testing.assert_array_equal(task._filter_output(theta), expected)
    measurement = task.evaluate(theta)
    assert set(measurement) == {"cost", "features"}
    mse = np.mean(np.square(expected - task._clean))
    assert measurement["cost"] == mse
    residual = task._noisy - expected
    features = [*theta, np.log1p(mse), 0.]
    for signal in (task._noisy, expected):
        features.extend([np.mean(signal), np.std(signal),
                         np.std(np.diff(signal)), lag_one(signal)])
    features.extend([np.mean(residual), np.std(residual),
                     np.quantile(np.abs(residual), .9), lag_one(residual)])
    np.testing.assert_allclose(measurement["features"], features, rtol=1e-14, atol=1e-14)
    assert np.isfinite(measurement["features"]).all()


def test_same_seed_index_resets_exactly_and_split_seeds_are_distinct():
    first, reset = DenoiseTask(940101, 3), DenoiseTask(940101, 3)
    for name in ("_clean", "_noisy"):
        np.testing.assert_array_equal(getattr(first, name), getattr(reset, name))
        assert not np.array_equal(getattr(first, name), getattr(DenoiseTask(940102, 3), name))
        assert not np.array_equal(getattr(first, name), getattr(DenoiseTask(940101, 4), name))
    before = first.evaluate([.5, .5])
    first.evaluate([0., 1.])
    assert first.evaluate([.5, .5]) == before == reset.evaluate([.5, .5])
    assert first.splitseed == 940101 and first.index == 3


def test_task_signals_and_identity_cannot_be_mutated_or_reenabled():
    task = DenoiseTask(940101, 3)
    for name in ("_clean", "_noisy"):
        signal = getattr(task, name)
        with pytest.raises(ValueError):
            signal[0] = 123.
        with pytest.raises(ValueError):
            signal.setflags(write=True)
        with pytest.raises(AttributeError):
            setattr(task, name, np.zeros_like(signal))
    with pytest.raises(AttributeError):
        task.index = 4
    measurement = task.evaluate([.5, .5])
    expected = measurement["features"].copy()
    measurement["features"][:] = [123.] * len(expected)
    assert task.evaluate([.5, .5])["features"] == expected


@pytest.mark.parametrize("theta", [
    [np.nan, .5], [.5, np.inf], [-np.inf, .5],
    [-1e-9, .5], [.5, 1. + 1e-9],
    [.5], [.5, .5, .5], [[.5, .5]], None,
])
def test_invalid_parameter_shape_nonfinite_and_out_of_bounds_are_rejected(theta):
    with pytest.raises(ValueError):
        DenoiseTask(940101, 0).evaluate(theta)


@pytest.mark.parametrize("value", [-1, 1.5, np.nan, True])
def test_seed_and_index_require_nonnegative_integer_identity(value):
    with pytest.raises(ValueError, match="nonnegative integer"):
        DenoiseTask(value, 0)
    with pytest.raises(ValueError, match="nonnegative integer"):
        DenoiseTask(940101, value)


def test_hidden_reference_changes_only_the_explicit_measured_cost_feature():
    """Intervene on reference truth, keeping observed waveform and action fixed.

    Cost feedback is intentionally visible. The remaining channels must be
    functions of the observed waveform/output, never a direct clean/latent path.
    This intervention checks that boundary instead of inferring it from shape.
    """
    task = DenoiseTask(940101, 2)
    altered = object.__new__(DenoiseTask)
    for slot in DenoiseTask.__slots__:
        object.__setattr__(altered, slot, getattr(task, slot))
    object.__setattr__(altered, "_clean", task._clean + 7.)
    first, second = task.evaluate([.3, .8]), altered.evaluate([.3, .8])
    np.testing.assert_array_equal(task._filter_output([.3, .8]),
                                  altered._filter_output([.3, .8]))
    assert first["cost"] != second["cost"]
    assert first["features"][2] == np.log1p(first["cost"])
    assert second["features"][2] == np.log1p(second["cost"])
    visible_except_cost = [index for index in range(16) if index != 2]
    np.testing.assert_array_equal(np.asarray(first["features"])[visible_except_cost],
                                  np.asarray(second["features"])[visible_except_cost])


def test_constant_observation_has_finite_zero_correlation_features():
    task = DenoiseTask(940101, 2)
    object.__setattr__(task, "_noisy", np.ones(task_module.L))
    measurement = task.evaluate([.5, .5])
    assert np.isfinite(measurement["features"]).all()
    assert measurement["features"][7] == 0.


class QuadraticTask:
    """Count physical evaluations without depending on the study's ledger."""

    def __init__(self, seed=123, index=0):
        self.calls = []

    def evaluate(self, theta):
        self.calls.append(np.array(theta, copy=True))
        cost = float(np.dot(theta, theta))
        return {"cost": cost, "features": [*theta, np.log1p(cost), 0., *([0.] * 12)]}


def test_ledger_caches_only_same_object_measurements_and_refuses_excess_before_call():
    task = QuadraticTask()
    ledger = study.Ledger(task, budget=1)
    assert ledger.observe([.5, .5]) == 0
    assert ledger.observe(np.array([.5, .5])) == 0
    assert ledger.requests[-1]["cached"] is True
    assert len(task.calls) == len(ledger.measurements) == 1
    with pytest.raises(study.StopBudget, match="budget"):
        ledger.observe([.6, .5])
    assert len(task.calls) == len(ledger.measurements) == 1
    assert len(ledger.requests) == 2
    # Neither a new operating arm nor an independent object inherits the cache.
    other = study.Ledger(task, budget=1)
    other.observe([.5, .5])
    assert len(task.calls) == 2 and not other.requests[0]["cached"]


def test_proposal_cap_counts_cached_requests_without_fabricating_evaluations():
    task = QuadraticTask()
    ledger = study.Ledger(task, budget=5, proposal_cap=2)
    ledger.observe([.5, .5])
    ledger.observe([.5, .5])
    with pytest.raises(study.StopBudget, match="proposal_cap"):
        ledger.observe([.4, .5])
    assert len(ledger.requests) == 2
    assert len(ledger.measurements) == len(task.calls) == 1


def test_failed_objective_attempt_is_charged_and_cannot_be_retried_beyond_budget():
    class FailingTask:
        calls = 0

        def evaluate(self, theta):
            self.calls += 1
            raise RuntimeError("physical evaluator failure")

    task = FailingTask()
    ledger = study.Ledger(task, budget=1)
    with pytest.raises(RuntimeError, match="physical evaluator failure"):
        ledger.observe([.5, .5])
    assert len(ledger.measurements) == task.calls == 1
    assert "RuntimeError" in ledger.measurements[0]["error"]
    with pytest.raises(study.StopBudget, match="budget"):
        ledger.observe([.5, .5])
    assert task.calls == 1


@pytest.mark.parametrize("theta", [[np.nan, .5], [.5], [-.01, .5], [.5, 1.01]])
def test_ledger_rejects_invalid_request_before_measurement(theta):
    task = QuadraticTask()
    ledger = study.Ledger(task, budget=5)
    with pytest.raises(ValueError):
        ledger.observe(theta)
    assert not task.calls and not ledger.measurements and not ledger.requests


def test_teacher_uses_joint_grid_when_each_axis_alone_is_unhelpful(monkeypatch):
    class CoupledTask(QuadraticTask):
        def evaluate(self, theta):
            self.calls.append(np.array(theta, copy=True))
            cost = float(np.sum((theta - .7) ** 2) + 10. * (theta[0] - theta[1]) ** 2)
            return {"cost": cost, "features": [*theta, np.log1p(cost), 0., *([0.] * 12)]}

    monkeypatch.setattr(study, "DenoiseTask", CoupledTask)
    result = study.teacher_object(123, 0, stages=2)
    assert result["states"][0]["labels"] == [4, 4]
    winner = result["states"][0]["selected"]
    np.testing.assert_allclose(result["measurements"][winner]["theta"], [.7, .7])
    assert result["measurements"][winner]["cost"] < result["measurements"][0]["cost"]
    # Next-stage optimum is the measured hold; no fabricated extra observation.
    assert result["states"][1]["measurement"] == winner
    assert result["states"][1]["selected"] == winner
    assert result["states"][1]["labels"] == [2, 2]
    for state in result["states"]:
        assert len(state["candidate_measurements"]) == 25
        assert all(0 <= index < len(result["measurements"])
                   for index in state["candidate_measurements"])
    assert result["requests"][13]["cached"]  # Joint zero action references start.


def test_teacher_constant_ties_hold_and_clipped_duplicates_are_charged_once(monkeypatch):
    class ConstantTask(QuadraticTask):
        def evaluate(self, theta):
            row = super().evaluate(theta)
            row["cost"] = 1.
            return row

    monkeypatch.setattr(study, "DenoiseTask", ConstantTask)
    monkeypatch.setattr(study, "START", np.zeros(2))
    result = study.teacher_object(123, 0, stages=3)
    # Clipping maps 25 nominal actions to the Cartesian product {0,.05,.2}^2.
    assert len(result["measurements"]) == 9
    assert len(result["requests"]) == 1 + 3 * 25
    assert all(state["labels"] == [2, 2] and state["selected"] == 0
               for state in result["states"])
    assert sum(not request["cached"] for request in result["requests"]) == 9
    for request in result["requests"]:
        assert request["theta"] == result["measurements"][request["measurement"]]["theta"]


def test_tiny_training_changes_weights_and_repeats_the_same_seed_exactly():
    rng = np.random.default_rng(123)
    x = rng.normal(size=(16, 16)).astype(np.float64)
    y = np.column_stack([x[:, 0] > 0, x[:, 1] > 0]).astype(np.int64)
    settings = {"learning_rate": .001, "epochs": 2, "batch_size": 8}
    study.torch.manual_seed(123)
    initial = {name: tensor.detach().numpy().copy()
               for name, tensor in study.TransferHead().state_dict().items()}
    artifact, fit = study.train_model(x, y, 123, settings)
    repeated, repeated_fit = study.train_model(x, y, 123, settings)
    assert artifact == repeated
    assert fit["epoch_losses"] == repeated_fit["epoch_losses"]
    assert fit["optimizer_steps"] == 4 and fit["epochs"] == 2 and fit["examples"] == 16
    assert any(not np.array_equal(initial[name], value)
               for name, value in artifact["state_dict"].items())
    np.testing.assert_array_equal(artifact["normalization_mean"], x.mean(axis=0))
    np.testing.assert_array_equal(artifact["normalization_scale"], x.std(axis=0))
    logits = study.infer_logits(study.load_model(artifact), artifact, x[0])
    assert logits.shape == (2, 5) and np.isfinite(logits).all()


def test_collector_preserves_prior_objects_and_current_failed_attempt(monkeypatch):
    class BrokenTask(QuadraticTask):
        def __init__(self, seed, index):
            super().__init__()
            self.index = index
        def evaluate(self, theta):
            if self.index == 1:
                raise RuntimeError("physical evaluator failed")
            return super().evaluate(theta)
    monkeypatch.setattr(study, "DenoiseTask", BrokenTask)
    target = []
    with pytest.raises(RuntimeError, match="physical evaluator failed"):
        study.collect({"seed": 123, "n": 3, "teacher_stages": 1}, target)
    assert len(target) == 2 and target[0]["task"] == 0 and target[1]["task"] == 1
    assert len(target[0]["measurements"]) == 25
    assert len(target[1]["measurements"]) == 1
    assert "physical evaluator failed" in target[1]["measurements"][0]["error"]


def test_checkpoint_failure_after_initial_measurement_keeps_its_charge(monkeypatch):
    monkeypatch.setattr(study, "DenoiseTask", QuadraticTask)
    def broken_load(_):
        raise RuntimeError("checkpoint rejected")
    monkeypatch.setattr(study, "load_model", broken_load)
    with pytest.raises(RuntimeError, match="checkpoint rejected") as caught:
        study.rollout(123, 0, "typed_seed_101", 8, artifact={})
    assert len(caught.value.nonpid_ledger["measurements"]) == 1
    assert caught.value.nonpid_ledger["requests"][0]["cached"] is False


def test_teacher_postprocessing_failure_keeps_all_prior_measurements(monkeypatch):
    monkeypatch.setattr(study, "DenoiseTask", QuadraticTask)
    def broken_observation(*_):
        raise RuntimeError("observation postprocessing failed")
    monkeypatch.setattr(study, "observation", broken_observation)
    with pytest.raises(RuntimeError, match="observation postprocessing failed") as caught:
        study.teacher_object(123, 0, 1)
    assert len(caught.value.nonpid_ledger["measurements"]) == 25
    assert len(caught.value.nonpid_ledger["requests"]) == 26


def constant_artifact(option_index):
    """Real TransferHead weights with a known distribution, no fake predictor."""
    model = study.TransferHead()
    with study.torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
        model.net[-1].bias.reshape(2, 5)[:, option_index] = 4.
    return {"seed": 123, "normalization_mean": [0.] * 16,
            "normalization_scale": [1.] * 16,
            "state_dict": {name: value.detach().numpy().tolist()
                           for name, value in model.state_dict().items()}}


def test_real_model_probabilities_drive_actions_and_cp_monitor_preserves_them(monkeypatch):
    monkeypatch.setattr(study, "DenoiseTask", QuadraticTask)
    observed_shapes = []
    original_load = study.load_model

    def record_load(artifact):
        model = original_load(artifact)
        model.register_forward_pre_hook(lambda _, arguments: observed_shapes.append(tuple(arguments[0].shape)))
        return model

    monkeypatch.setattr(study, "load_model", record_load)
    positive = constant_artifact(4)
    full = {"temperatures": [1., 1.], "qhat_per_axis": [1., 1.]}
    empty = {"temperatures": [1., 1.], "qhat_per_axis": [0., 0.]}
    monitor_full = study.rollout(123, 0, "typed_seed_123", 3, artifact=positive, calibration=full)
    monitor_empty = study.rollout(123, 0, "typed_seed_123", 3, artifact=positive, calibration=empty)
    assert monitor_full["measurements"] == monitor_empty["measurements"]
    assert monitor_full["returned"] == monitor_empty["returned"] == 0
    assert len(monitor_full["measurements"]) == 3
    for whole, none in zip(monitor_full["decisions"], monitor_empty["decisions"]):
        assert whole["probabilities"] == none["probabilities"]
        assert whole["step"] == none["step"]
        assert np.asarray(whole["sets"]).all() and not np.asarray(none["sets"]).any()
        assert np.all(np.asarray(whole["next_theta"]) >
                      np.asarray(monitor_full["measurements"][whole["current"]]["theta"]))
    reverse = study.rollout(123, 0, "typed_seed_123", 3,
                            artifact=constant_artifact(0), calibration=full)
    assert reverse["measurements"][1]["theta"] != monitor_full["measurements"][1]["theta"]
    assert reverse["returned"] == 2
    assert observed_shapes and all(shape == (1, 16) for shape in observed_shapes)


@pytest.mark.parametrize("method", ["coordinate_search", "space_filling", "simplex"])
@pytest.mark.parametrize("budget", [1, 2, 8])
def test_each_baseline_respects_fresh_evaluation_budget_and_returns_measured_best(monkeypatch, method, budget):
    tasks = []

    def task_factory(seed, index):
        task = QuadraticTask()
        tasks.append(task)
        return task

    monkeypatch.setattr(study, "DenoiseTask", task_factory)
    result = study.rollout(123, 0, method, budget)
    measured = result["measurements"]
    assert len(tasks) == 1
    assert 1 <= len(measured) == len(tasks[0].calls) <= budget
    assert len(result["requests"]) <= 4 * budget
    assert measured[result["returned"]]["cost"] == min(row["cost"] for row in measured)
    assert measured[result["returned"]]["cost"] <= measured[0]["cost"]
    for actual, row in zip(tasks[0].calls, measured):
        np.testing.assert_array_equal(actual, row["theta"])


@pytest.fixture
def independent_teacher_record():
    record = study.teacher_object(940101, 0, stages=1)
    clean, noisy = audit_module.signals(940101, 0)
    return record, clean, noisy


def test_independent_audit_replays_recorded_candidates_and_joint_teacher(independent_teacher_record):
    record, clean, noisy = independent_teacher_record
    audit = audit_module.AuditCompute()
    audit_module.verify_ledger(record, clean, noisy, audit, budget=25)
    audit_module.verify_teacher(record, stages=1)
    assert audit.evaluations == len(record["measurements"]) == 25


@pytest.mark.parametrize("mutation", ["cost", "cached", "budget", "joint_label"])
def test_independent_audit_rejects_false_cost_cache_budget_and_one_changed_axis(independent_teacher_record, mutation):
    original, clean, noisy = independent_teacher_record
    record = copy.deepcopy(original)
    if mutation == "joint_label":
        record["states"][0]["labels"][1] = (record["states"][0]["labels"][1] + 1) % 5
        with pytest.raises(ValueError, match="label"):
            audit_module.verify_teacher(record, stages=1)
        return
    if mutation == "cost":
        record["measurements"][0]["cost"] += 1.
    elif mutation == "cached":
        record["requests"][0]["cached"] = True
    audit = audit_module.AuditCompute()
    with pytest.raises(ValueError):
        audit_module.verify_ledger(record, clean, noisy, audit,
                                   budget=24 if mutation == "budget" else 25)
    assert audit.evaluations <= len(original["measurements"])
    if mutation in {"cached", "budget"}:
        assert audit.evaluations == 0


def test_acceptance_requires_every_seed_and_every_primary_baseline():
    settings = {"operating": {"primary_budget": 20}, "training": {"seeds": [101, 202, 303]}}
    rows = [{"method": name, "budget": 20, "mean_final_MSE": 1., "p90_final_MSE": 2.}
            for name in ("coordinate_search", "space_filling", "simplex")]
    rows += [{"method": f"typed_seed_{seed}", "budget": 20,
              "mean_final_MSE": .8, "p90_final_MSE": 1.8} for seed in (101, 202, 303)]
    assert audit_module.assess_acceptance(rows, settings)["stable_empirical_policy_benefit"]
    rows[-1]["mean_final_MSE"] = .99
    result = audit_module.assess_acceptance(rows, settings)
    assert result["status"] == "negative_stop"
    assert not result["stable_empirical_policy_benefit"] and not result["further_policy_deepening"]
    assert any(not comparison["mean_at_least_five_percent_better"] and comparison["seed"] == 303
               for comparison in result["comparisons"])


@pytest.mark.parametrize("n", [1, 2, 8])
def test_independent_conformal_checker_keeps_finite_sample_upper_endpoint(n):
    probabilities = np.tile([.8, .1, .05, .03, .02], (n, 2, 1))
    qhat = audit_module.independent_conformal(probabilities, np.zeros((n, 2), dtype=int))
    np.testing.assert_array_equal(qhat, np.ones(2))


def test_replay_example_rejects_missing_artifacts_before_constructing_any_task(tmp_path, monkeypatch):
    example_spec = importlib.util.spec_from_file_location(
        "nonpid_example_tests", ROOT / "examples" / "denoise_transfer" / "run.py")
    example = importlib.util.module_from_spec(example_spec)
    example_spec.loader.exec_module(example)
    monkeypatch.setattr(example, "_runner", lambda: study)

    def forbidden(*args, **kwargs):
        pytest.fail("missing artifact check must precede every objective construction")

    monkeypatch.setattr(study, "DenoiseTask", forbidden)
    with pytest.raises(FileNotFoundError, match="completed study report"):
        example.replay(tmp_path)
