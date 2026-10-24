"""Original-record auditing must reject mathematical and trajectory mutations."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


verify = load_module(ROOT / "scripts/52_verify_recorded_transfer.py", "recorded_transfer_tests")
runner = load_module(ROOT / "scripts/45_nonpid_transfer.py", "recorded_transfer_runner_tests")
tracer = load_module(ROOT / "scripts/51_diagnose_calibration_runtime.py", "recorded_transfer_actual_trace_tests")


def actual_traces(logits, labels):
    from jev_tune.primitives import calibrate_temperature
    traces = []
    for axis in range(2):
        temperature, trace = tracer.golden_trace(logits[:, axis, :], labels[:, axis])
        assert temperature == calibrate_temperature(logits[:, axis, :], labels[:, axis])
        traces.append(trace)
    return traces


def artifact():
    state = {}
    for layer, incoming, outgoing in ((0, 16, 32), (2, 32, 32), (4, 32, 10)):
        state[f"net.{layer}.weight"] = np.zeros((outgoing, incoming)).tolist()
        state[f"net.{layer}.bias"] = np.zeros(outgoing).tolist()
    state["net.4.bias"] = [-.3, -.2, 0., .3, .8, .5, .1, 0., -.2, -.7]
    return {"seed": 123, "normalization_mean": np.zeros(16).tolist(),
            "normalization_scale": np.ones(16).tolist(), "state_dict": state,
            "architecture": [16, 32, 32, 10], "dtype": "float64", "inference_shape": [1, 16]}


class SyntheticTask:
    def __init__(self, seed, index):
        assert seed == 940101 and index == 7

    def evaluate(self, theta):
        cost = float((theta[0] - .8) ** 2 + (theta[1] - .2) ** 2)
        return {"cost": cost,
                "features": [*theta, float(np.log1p(cost)), 0., *np.linspace(-.2, .3, 12).tolist()]}


@pytest.fixture
def synthetic_rollouts(monkeypatch):
    monkeypatch.setattr(runner, "DenoiseTask", SyntheticTask)
    model = artifact()
    calibration = {"temperatures": [1.1, 1.3], "qhat_per_axis": [.85, .85]}
    def make(method="typed_seed_123", budget=4):
        return runner.rollout(940101, 7, method, budget,
                              artifact=model if method.startswith("typed_") else None,
                              calibration=calibration if method.startswith("typed_") else None)
    return make, model, calibration


def test_choice_decode_matches_scalar_moments_and_keeps_full_monitor_sets():
    p = np.asarray([[.1, .1, .1, .2, .5], [.4, .2, .1, .1, .2]])
    result = verify.decode_recorded(p, [.95, .95])
    vocabulary = [-.2, -.05, 0., .05, .2]
    reference = []
    reference_variance = sum(d*d for d in vocabulary) / 5
    for row in p:
        mean = sum(float(w) * d for w, d in zip(row, vocabulary))
        variance = sum(float(w) * d*d for w, d in zip(row, vocabulary)) - mean*mean
        reference.append(mean / (1 + variance / reference_variance))
    np.testing.assert_allclose(result["step"], reference, rtol=1e-15, atol=0.)
    assert result["sets"].all() and result["conformal_would_hold"].all()
    assert not result["held"].any() and not result["escalate"].any()
    assert (result["step"] != 0).all() and result["noul"] == 1.
    verify.verify_typed_shell(p, [.95, .95], result)


@pytest.mark.parametrize("probabilities,qhat", [
    ([[.2] * 5] * 2, [1., np.nan]),
    ([[.2] * 5] * 2, [1.1, .5]),
    ([[.3] * 5] * 2, [.5, .5]),
    ([[np.nan] * 5] * 2, [.5, .5]),
    ([[-.1, .2, .2, .2, .5]] * 2, [.5, .5]),
    ([[.25] * 4] * 2, [.5, .5]),
])
def test_invalid_mathematical_evidence_fails_closed(probabilities, qhat):
    with pytest.raises(ValueError):
        verify.decode_recorded(probabilities, qhat)


def test_real_synthetic_model_certifies_recorded_probability_action_chain(synthetic_rollouts):
    make, model, calibration = synthetic_rollouts
    record = make()
    api = verify.numeric_api()
    assert verify.verify_operating(record, model, calibration, api) == 3
    assert record["returned"] != 0


@pytest.mark.parametrize("mutation", ["probabilities", "features", "current", "step", "next_theta",
                                     "sets", "measurement", "returned", "stop", "cache"])
def test_observation_and_action_mutations_rejected_without_hashes(synthetic_rollouts, mutation):
    make, model, calibration = synthetic_rollouts
    record = make()
    if mutation == "probabilities":
        record["decisions"][0]["probabilities"][0][0] += .01
        record["decisions"][0]["probabilities"][0][1] -= .01
    elif mutation == "features":
        record["decisions"][1]["features"][3] += .1
    elif mutation == "current":
        record["decisions"][1]["current"] = 0
    elif mutation == "step":
        record["decisions"][0]["step"][0] += .01
    elif mutation == "next_theta":
        record["decisions"][0]["next_theta"][0] += .01
    elif mutation == "sets":
        record["decisions"][0]["sets"][0][0] = not record["decisions"][0]["sets"][0][0]
    elif mutation == "measurement":
        record["decisions"][0]["measurement"] = 0
    elif mutation == "returned":
        record["returned"] = 0
    elif mutation == "stop":
        record["stop"] = "no_action"
    else:
        record["requests"][1]["cached"] = True
    with pytest.raises(ValueError):
        verify.verify_operating(record, model, calibration, verify.numeric_api())


@pytest.mark.parametrize("method", ["coordinate_search", "space_filling", "simplex"])
def test_baseline_proposals_and_budget_reconstructed_without_objectives(synthetic_rollouts, method):
    make, _, _ = synthetic_rollouts
    record = make(method, budget=8)
    verify.verify_baseline(record)
    # Keep the measurement and request mutually consistent: only an independent
    # reconstruction of the prescribed proposal notices this change.
    bad = copy.deepcopy(record)
    index = bad["requests"][1]["measurement"]
    bad["measurements"][index]["theta"][0] += .001
    for request in bad["requests"]:
        if request["measurement"] == index:
            request["theta"][0] += .001
    with pytest.raises(ValueError, match="proposal coordinate"):
        verify.verify_baseline(bad)


def test_typed_audit_cannot_finish_before_all_paid_requests_are_consumed(synthetic_rollouts):
    make, model, calibration = synthetic_rollouts
    record = make()
    record["decisions"].pop()
    with pytest.raises(ValueError):
        verify.verify_operating(record, model, calibration, verify.numeric_api())


def test_exact_repeated_theta_is_cached_and_stops_without_an_extra_measurement(synthetic_rollouts):
    make, model, calibration = synthetic_rollouts
    model["state_dict"]["net.4.bias"] = [0.] * 10
    record = make()
    assert record["stop"] == "no_action" and len(record["measurements"]) == 1
    assert record["requests"][-1]["cached"] is True
    assert verify.verify_operating(record, model, calibration, verify.numeric_api()) == 1


def test_full_budget_still_allows_same_ledger_cache_but_cap_preempts_it():
    row = {"theta": [.5, .5], "cost": 1.}
    record = {"budget": 1, "returned": 0, "measurements": [row],
              "requests": [{"theta": [.5, .5], "measurement": 0, "cached": cached}
                           for cached in (False, True, True, True)]}
    ledger = verify.RecordedLedger(record)
    assert ledger.observe([.5, .5]) == 0
    with pytest.raises(StopIteration, match="budget"):
        ledger.observe([.6, .5])
    for _ in range(3):
        assert ledger.observe([.5, .5]) == 0
    with pytest.raises(StopIteration, match="proposal_cap"):
        ledger.observe([.5, .5])
    ledger.finish()


def test_failed_audit_persists_every_attempted_filter_charge(tmp_path, monkeypatch):
    def failure(root, output, audit, **kwargs):
        audit.evaluations += 13
        raise ValueError("deliberate evidence mismatch")
    monkeypatch.setattr(verify, "_verify", failure)
    with pytest.raises(ValueError, match="additional_verification_objective_evaluations=13"):
        verify.check(tmp_path, receipt_root=tmp_path / "receipts")
    receipts = list((tmp_path / "receipts").glob("*.json"))
    assert len(receipts) == 1
    record = json.loads(receipts[0].read_text())
    assert record["status"] == "failed"
    assert record["additional_verification_objective_evaluations"] == 13
    assert "NOT strict" in record["verification_scope"]


def test_successful_audit_does_not_overwrite_an_earlier_receipt(tmp_path, monkeypatch):
    def success(root, output, audit, **kwargs):
        audit.evaluations += 7
        return {"ok": True, "strict_cpu_replay_proven": False,
                "additional_verification_objective_evaluations": audit.evaluations}
    monkeypatch.setattr(verify, "_verify", success)
    first = verify.check(tmp_path, receipt_root=tmp_path / "receipts")
    second = verify.check(tmp_path, receipt_root=tmp_path / "receipts")
    assert first["receipt_path"] != second["receipt_path"]
    assert len(list((tmp_path / "receipts").glob("*.json"))) == 2
    assert not second["strict_cpu_replay_proven"]


def test_archive_binding_checks_each_array_bits_and_split_evidence(tmp_path, monkeypatch):
    import hashlib
    root = tmp_path
    destination = root / verify.ARRAYS
    destination.parent.mkdir(parents=True)
    primary = root / "research/results/nonpid_transfer"
    primary.mkdir(parents=True)
    (primary / "report.json").write_text("{}\n")
    (root / "scripts").mkdir()
    producer = root / "scripts/53_archive_original_calibration.py"
    producer.write_text("# synthetic unit producer\n")
    arrays = {split: (np.zeros((1, 16)), np.zeros((1, 2), dtype=np.int64))
              for split in ("temperature", "conformal", "test")}
    saved = {f"seed_{seed}_{split}_{kind}": values[index]
             for seed in (101, 202, 303) for split, values in arrays.items()
             for index, kind in enumerate(("features", "labels"))}
    np.savez_compressed(destination, **saved)
    archive_hash = verify.audit46.digest(destination)
    monkeypatch.setattr(verify, "ARRAY_SHA256", archive_hash)
    report = {"raw_sha256": "a" * 64, "artifacts": {}}
    manifest = {"schema_version": 1, "archive": verify.ARRAYS, "archive_sha256": archive_hash,
                "additional_objective_evaluations": 0, "gradient_steps": 0,
                "original_48_passed_before_capture": True, "original_logits_bits_unchanged": True,
                "source_script_sha256": verify.audit46.digest(producer, text=True),
                "input_hashes": {"research/results/nonpid_transfer/report.json": verify.audit46.digest(primary / "report.json", text=True),
                                 "research/results/nonpid_transfer/raw.json.gz": report["raw_sha256"]},
                "arrays": {name: {"shape": list(value.shape), "dtype": str(value.dtype),
                                  "sha256": hashlib.sha256(value.tobytes()).hexdigest()}
                           for name, value in saved.items()}}
    manifest_path = root / verify.ARRAY_MANIFEST
    manifest_path.write_text(json.dumps(manifest))
    archive, _ = verify._archive(root, arrays, report)
    archive.close()
    # A coherent ZIP-level hash update cannot conceal a changed array from the
    # per-array original-bit manifest.
    saved["seed_101_temperature_features"] = np.ones((1, 16))
    np.savez_compressed(destination, **saved)
    archive_hash = verify.audit46.digest(destination)
    monkeypatch.setattr(verify, "ARRAY_SHA256", archive_hash)
    manifest["archive_sha256"] = archive_hash
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="array bits"):
        verify._archive(root, arrays, report)


def supplemental_row():
    n = 16
    samples = [{"temperature": 1., "conformal": 2., "total": 3.} for _ in range(31)]
    benchmark = load_module(ROOT / "scripts/48_recalibration_benchmark.py", "recorded_supplement_test_formula")
    calibration = {"temperatures": [1., 1.], "qhat_per_axis": [.8, .8], "alpha": .1,
                   "n_temperature": n, "n_calibration": n, "quantile_rank": 16,
                   "mode": "monitor", "model_sha256": "c" * 64, "scope": "synthetic unit scope"}
    p = np.full((256, 2, 5), .2)
    y = np.zeros((256, 2), dtype=np.int64)
    row = {"model_seed": 123, "n_per_split": n, "total_label_states": 2 * n,
           "calibration": calibration, "warmup_fits": 1, "recorded_repetitions": 31,
           "timing_samples_ms": samples, "timing_statistics_ms": benchmark.timing_statistics(samples),
           "test_diagnostics": verify.audit46.conformal_diagnostics(p, y, [.8, .8])}
    logits = {split: np.zeros((count, 2, 5)) for split, count in (("temperature", n), ("conformal", n), ("test", 256))}
    labels = {split: np.zeros(values.shape[:-1], dtype=np.int64) for split, values in logits.items()}
    calibration["temperatures"] = [tracer.calibrate_temperature(logits["temperature"][:, axis, :], labels["temperature"][:, axis]) for axis in range(2)]
    return row, logits, labels, p[:n], p


def test_supplemental_certificate_keeps_observed_clock_samples_and_exact_sets():
    row, logits, labels, cp, test = supplemental_row()
    preserved = copy.deepcopy(row["timing_samples_ms"])
    result = verify.verify_recalibration_row(row, logits, labels, cp, test, verify.numeric_api(),
                                            model_sha256="c" * 64, scope="synthetic unit scope",
                                            golden_traces=actual_traces(logits["temperature"], labels["temperature"]))
    assert result["cp_certificate"]["rank"] == 16
    assert np.asarray(result["cp_certificate"]["sets"]).all()
    assert row["timing_samples_ms"] == preserved


@pytest.mark.parametrize("mutation", ["temperature", "qhat", "coverage", "timing", "statistics", "schedule", "identity"])
def test_supplemental_fit_math_rank_diagnostics_clocks_and_identity_mutations_rejected(mutation):
    row, logits, labels, cp, test = supplemental_row()
    if mutation == "temperature":
        row["calibration"]["temperatures"][0] = -1.
    elif mutation == "qhat":
        row["calibration"]["qhat_per_axis"][0] = np.nextafter(.8, 1.)
    elif mutation == "coverage":
        row["test_diagnostics"]["coverage_per_axis"][0] = .99
    elif mutation == "timing":
        row["timing_samples_ms"][0]["total"] = -1.
    elif mutation == "statistics":
        row["timing_statistics_ms"]["total_fit_ms"]["p99"] += .1
    elif mutation == "schedule":
        row["recorded_repetitions"] = 30
    else:
        row["calibration"]["model_sha256"] = "d" * 64
    with pytest.raises(ValueError):
        verify.verify_recalibration_row(row, logits, labels, cp, test, verify.numeric_api(),
                                        model_sha256="c" * 64, scope="synthetic unit scope",
                                        golden_traces=actual_traces(logits["temperature"], labels["temperature"]))


def test_supplemental_failure_receipt_keeps_zero_filter_accounting(tmp_path, monkeypatch):
    def failure(root, **kwargs):
        raise ValueError("deliberate supplemental mismatch")
    monkeypatch.setattr(verify, "_verify_recalibration", failure)
    with pytest.raises(ValueError, match="additional_objective_evaluations=0"):
        verify.check_recalibration(tmp_path, receipt_root=tmp_path / "receipts")
    record = json.loads(next((tmp_path / "receipts").glob("*.json")).read_text())
    assert record["additional_objective_evaluations"] == record["gradient_steps"] == 0
    assert record["status"] == "failed"


def test_spawn_workers_match_real_serial_math_and_never_execute_a_filter(synthetic_rollouts, monkeypatch):
    import os
    make, model, calibration = synthetic_rollouts
    records = [make(budget=4), make(budget=5)]
    expected = sum(verify.verify_operating(record, model, calibration, verify.numeric_api()) for record in records)

    def forbidden(*args, **kwargs):
        raise AssertionError("parallel numerical audit called a parent filter")
    monkeypatch.setattr(verify.audit46, "filter_output", forbidden)
    monkeypatch.setattr(verify.audit46, "verify_ledger", forbidden)
    count, report = verify.verify_operating_parallel([(r, model, calibration) for r in records], max_workers=2)
    assert count == expected == 7
    assert report["workers"] == 2 and report["failed_records"] == 0
    assert report["expected_records"] == report["completed_records"] == 2
    assert report["expected_decisions"] == report["verified_complete_record_decisions"] == 7
    assert [row["budget"] for row in report["records"]] == [4, 5]
    assert all(row["worker_pid"] != os.getpid() for row in report["records"])
    assert all(row["source_hashes"] == report["source_hashes"] for row in report["records"])
    assert all(row["additional_objective_evaluations"] == row["gradient_steps"] == 0
               for row in report["records"])


def test_spawn_failure_preserves_roster_error_and_other_completed_record(synthetic_rollouts):
    make, model, calibration = synthetic_rollouts
    first, second = make(budget=4), make(budget=5)
    first["decisions"][0]["step"][0] += .01
    with pytest.raises(ValueError, match="numeric operating records failed") as raised:
        verify.verify_operating_parallel([(first, model, calibration), (second, model, calibration)], max_workers=2)
    report = raised.value.operating_parallel_audit
    assert report["failed_records"] == 1 and report["completed_records"] == 2
    assert [row["status"] for row in report["records"]] == ["failed", "passed"]
    assert report["records"][0]["error_type"] == "ValueError"
    assert "expectation/variance decode" in report["records"][0]["error"]
    assert report["records"][1]["decisions"] == report["verified_complete_record_decisions"] == 4
    assert report["additional_objective_evaluations"] == report["gradient_steps"] == 0


def test_parallel_failure_receipt_keeps_parent_filter_cost_and_all_worker_outcomes(tmp_path, monkeypatch):
    outcomes = {"failed_records": 1, "records": [{"status": "failed"}, {"status": "passed"}],
                "additional_objective_evaluations": 0}
    def failure(root, output, audit, **kwargs):
        audit.evaluations = 13
        error = ValueError("deliberate numerical-worker failure")
        error.operating_parallel_audit = outcomes
        raise error
    monkeypatch.setattr(verify, "_verify", failure)
    with pytest.raises(ValueError, match="additional_verification_objective_evaluations=13"):
        verify.check(tmp_path, receipt_root=tmp_path / "receipts")
    record = json.loads(next((tmp_path / "receipts").glob("*.json")).read_text())
    assert record["additional_verification_objective_evaluations"] == 13
    assert record["operating_parallel_audit"] == outcomes


def test_full_budget_cannot_hide_a_required_cached_boundary_action(synthetic_rollouts):
    make, model, calibration = synthetic_rollouts
    # Both axes propose +.2 until clipping at one.  The next boundary proposal
    # must hit the existing last measurement, even after four fresh calls.
    model["state_dict"]["net.4.bias"] = [0., 0., 0., 0., 100.] * 2
    record = make(budget=4)
    assert record["stop"] == "no_action"
    assert len(record["measurements"]) == record["budget"] == 4
    assert record["requests"][-1]["cached"] is True
    assert record["decisions"][-1]["next_theta"] == [1., 1.]
    api = verify.numeric_api()
    assert verify.verify_operating(record, model, calibration, api) == 4
    forged = copy.deepcopy(record)
    forged["decisions"].pop()
    forged["requests"].pop()
    forged["stop"] = "budget"
    # The forged ledger, returned-best, actual feedback and budget are mutually
    # consistent.  Only examining the *next* proposal exposes the omitted cache
    # action and the false budget-exhaustion claim.
    assert len(forged["requests"]) == len(forged["decisions"]) + 1 == 4
    assert len(forged["measurements"]) == forged["budget"]
    with pytest.raises(ValueError):
        verify.verify_operating(forged, model, calibration, api)


def test_independent_filter_rejects_cost_and_feedback_forged_together():
    clean, noisy = verify.audit46.signals(940101, 8)
    points = ([.5, .5], [.7, .5])
    measurements = [{"theta": list(theta), **verify.audit46.observation(
        theta, verify.audit46.filter_output(theta, noisy), clean, noisy)} for theta in points]
    record = {"measurements": measurements,
              "requests": [{"theta": list(points[0]), "measurement": 0, "cached": False},
                           {"theta": list(points[1]), "measurement": 1, "cached": False},
                           {"theta": list(points[1]), "measurement": 1, "cached": True}]}
    correct_audit = verify.audit46.AuditCompute()
    verify.audit46.verify_ledger(record, clean, noisy, correct_audit, budget=2)
    assert correct_audit.evaluations == 2
    forged = copy.deepcopy(record)
    for row in forged["measurements"]:
        row["cost"] += .5
        row["features"][2] = float(np.log1p(row["cost"]))
    first, second = forged["measurements"]
    feedback = float(np.log1p(second["cost"]) - np.log1p(first["cost"]))
    forged["decisions"] = [{"current": 0, "features": list(first["features"])},
                           {"current": 1, "features": list(second["features"])}]
    forged["decisions"][1]["features"][3] = feedback
    assert all(row["features"][2] == float(np.log1p(row["cost"])) for row in forged["measurements"])
    assert forged["decisions"][1]["features"][3] == feedback
    failed_audit = verify.audit46.AuditCompute()
    with pytest.raises(ValueError, match="independent reference MSE"):
        verify.audit46.verify_ledger(forged, clean, noisy, failed_audit, budget=2)
    assert failed_audit.evaluations == 1
