"""Independently audit the frozen non-PID transfer and generate its report.

The audit rebuilds budget, measured-best, teacher, calibration and acceptance
quantities from saved measurements. It never trains a checkpoint or chooses
new settings from test outcomes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import itertools
import re
import subprocess
from math import ceil
from pathlib import Path
import time
import uuid

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "research/protocols/nonpid_transfer_v0100.json"
PROTOCOL_SHA256 = "cdaa0d5028f8c5789a2aa6b25a1a9b9569c807d16ba8c188372d6ad25448a2c5"
RESULT = "research/results/nonpid_transfer/report.json"
RAW = "research/results/nonpid_transfer/raw.json.gz"
DOC = "docs/NONPID_TRANSFER.md"
PREREGISTRATION_COMMIT = "b4b8858"
ACCOUNTING_CLARIFICATION_COMMIT = "9cd159f"
TEXT_SUFFIXES = {".py", ".json", ".md", ".txt", ".toml", ".yml"}
REUSED_SOURCES = {
    "src/jev_tune/primitives.py": "935beb006be0f2a6c7202ba09c8848db476f2d50630933276aa6b9ad4b781975",
    "src/jev_tune/decode.py": "de7db4fc097ef85f032b6e8de2e43b537f69c5cccb15f7a6714d632a2d58db0d",
}


def digest(path, *, text=False):
    data = Path(path).read_bytes()
    if text:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _close(observed, expected, context, *, atol=1e-12, rtol=1e-10):
    left, right = np.asarray(observed), np.asarray(expected)
    _require(left.shape == right.shape, f"{context}: shape differs")
    _require(np.isfinite(left).all() and np.isfinite(right).all(),
             f"{context}: nonfinite evidence")
    _require(np.allclose(left, right, atol=atol, rtol=rtol),
             f"{context}: recorded/reconstructed values differ")


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _treeclose(observed, expected, context):
    if isinstance(expected, dict):
        _require(isinstance(observed, dict) and set(observed) == set(expected),
                 f"{context}: keys differ")
        for key in expected:
            _treeclose(observed[key], expected[key], f"{context}.{key}")
    elif isinstance(expected, (list, tuple)):
        _require(isinstance(observed, (list, tuple)) and len(observed) == len(expected),
                 f"{context}: list length differs")
        for i, (left, right) in enumerate(zip(observed, expected)):
            _treeclose(left, right, f"{context}[{i}]")
    elif isinstance(expected, (float, np.floating)):
        _close(observed, expected, context)
    else:
        _require(type(observed) == type(expected) and observed == expected,
                 f"{context}: scalar differs")


def _source_manifest(root, recorded, required):
    _require(set(recorded) == set(required), "incomplete source manifest")
    for name in required:
        _require(digest(root / name, text=Path(name).suffix in TEXT_SUFFIXES)
                 == recorded[name], f"source content changed: {name}")


def _lag1(values):
    left = values[:-1] - np.mean(values[:-1])
    right = values[1:] - np.mean(values[1:])
    denominator = np.sqrt(np.dot(left, left) * np.dot(right, right))
    return 0.0 if denominator == 0 else float(np.dot(left, right) / denominator)


def _signal_stats(values):
    return [float(np.mean(values)), float(np.std(values)),
            float(np.std(np.diff(values))), _lag1(values)]


def signals(seed, index):
    """Reconstruct the preregistered generator independently of task.py."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, index]))
    amplitude = rng.uniform(.5, 1.5)
    f1, f2 = rng.uniform(.005, .03), rng.uniform(.03, .09)
    phase1, phase2 = rng.uniform(0, 2*np.pi), rng.uniform(0, 2*np.pi)
    drift, step = rng.uniform(-.3, .3), rng.uniform(-.5, .5)
    step_index = rng.integers(48, 144)
    sigma = rng.uniform(.05, .4)
    impulse_probability, impulse_amplitude = rng.uniform(.005, .04), rng.uniform(1, 4)
    gaussian = rng.normal(0, sigma, 192)
    mask, signs = rng.random(192) < impulse_probability, rng.choice([-1, 1], 192)
    t = np.arange(192, dtype=float)
    clean = (amplitude*(np.sin(2*np.pi*f1*t+phase1)
                        + .35*np.sin(2*np.pi*f2*t+phase2))
             + drift*(t/191) + step*(t >= step_index))
    return clean, clean + gaussian + mask*signs*impulse_amplitude


def observation(theta, output, clean, noisy):
    """Recompute MSE and observations from retained filter output, without filtering."""
    theta, output = np.asarray(theta, dtype=float), np.asarray(output, dtype=float)
    _require(theta.shape == (2,) and np.isfinite(theta).all()
             and ((theta >= 0) & (theta <= 1)).all(), "invalid normalized action")
    _require(output.shape == (192,) and np.isfinite(output).all(),
             "invalid retained filter output")
    cost = float(np.mean((output-clean)**2))
    residual = noisy-output
    features = [*theta.tolist(), float(np.log1p(cost)), 0.0]
    features += _signal_stats(noisy) + _signal_stats(output)
    features += [float(np.mean(residual)), float(np.std(residual)),
                 float(np.percentile(np.abs(residual), 90)), _lag1(residual)]
    return {"cost": cost, "features": features}


def filter_output(theta, noisy):
    """Independent implementation of the frozen objective, charged as audit work."""
    from scipy.ndimage import median_filter
    from scipy.signal import butter, sosfiltfilt

    theta = np.asarray(theta, dtype=float)
    median = median_filter(noisy, size=9, mode="reflect")
    scale = np.maximum(1.4826*median_filter(np.abs(noisy-median), size=9,
                                          mode="reflect"), .02)
    clipped = np.clip(noisy, median-(1+5*theta[0])*scale,
                      median+(1+5*theta[0])*scale)
    cutoff = .02*(.35/.02)**theta[1]
    return sosfiltfilt(butter(2, Wn=2*cutoff, output="sos"), clipped)


class AuditCompute:
    """Count every independent objective execution, including failed audits."""

    def __init__(self):
        self.evaluations = 0

    def replay(self, theta, clean, noisy):
        _require(self.evaluations < 83840, "audit exceeds frozen replay cap")
        self.evaluations += 1
        return observation(theta, filter_output(theta, noisy), clean, noisy)


def _receipt(root, raw_sha256, audit, start, status, error=None):
    record = {"schema_version": 1, "study_id": "nonpid_denoise_transfer_v0100",
              "started_utc": start, "finished_utc": datetime.now(timezone.utc).isoformat(),
              "status": status, "error": error, "raw_sha256": raw_sha256,
              "additional_verification_objective_evaluations": audit.evaluations,
              "scope": "Exact recorded-candidate deterministic replay; not new independent data"}
    receipt = root / ".local-audit/nonpid_transfer_verification" / (uuid.uuid4().hex+".json")
    try:
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
        record["receipt_path"] = str(receipt)
    except OSError as exc:
        record["receipt_write_error"] = f"{type(exc).__name__}: {exc}"
    return record


def independent_conformal(probabilities, labels, alpha=.10):
    """LAC order statistic and descriptive diagnostics; no fitting on tests."""
    p, y = np.asarray(probabilities, dtype=float), np.asarray(labels, dtype=int)
    _require(p.ndim == 3 and p.shape[1:] == (2, 5) and y.shape == p.shape[:2],
             "invalid conformal evidence shape")
    _require(np.isfinite(p).all() and (p >= 0).all()
             and np.allclose(p.sum(axis=-1), 1), "invalid probabilities")
    _require(((y >= 0) & (y < 5)).all(), "invalid teacher labels")
    rank = ceil((len(p)+1)*(1-alpha))
    scores = 1-np.take_along_axis(p, y[..., None], axis=-1)[..., 0]
    qhat = np.ones(2) if rank > len(p) else np.sort(scores, axis=0)[rank-1]
    return qhat


def conformal_diagnostics(probabilities, labels, qhat):
    p, y, q = (np.asarray(probabilities, dtype=float), np.asarray(labels, dtype=int),
               np.asarray(qhat, dtype=float))
    masks = (1-p) <= q[None, :, None]
    sizes = masks.sum(axis=-1)
    included = np.take_along_axis(masks, y[..., None], axis=-1)[..., 0]
    return {"n_states": len(p), "coverage_per_axis": included.mean(axis=0).tolist(),
            "mean_set_size_per_axis": sizes.mean(axis=0).tolist(),
            "empty_set_rate_per_axis": (sizes == 0).mean(axis=0).tolist(),
            "set_size_histogram_per_axis": np.stack([
                (sizes == k).sum(axis=0) for k in range(6)], axis=-1).tolist()}


def assess_acceptance(rows, protocol):
    """Apply only the frozen primary-budget empirical rule, separately per seed."""
    primary = protocol["operating"]["primary_budget"]
    indexed = {(row["method"], row["budget"]): row for row in rows}
    baselines = ["coordinate_search", "space_filling", "simplex"]
    comparisons = []
    for seed in protocol["training"]["seeds"]:
        learned = indexed[(f"typed_seed_{seed}", primary)]
        for name in baselines:
            baseline = indexed[(name, primary)]
            mean_pass = learned["mean_final_MSE"] <= .95*baseline["mean_final_MSE"]
            p90_pass = learned["p90_final_MSE"] <= baseline["p90_final_MSE"]
            comparisons.append({"seed": seed, "baseline": name,
                                "mean_at_least_five_percent_better": bool(mean_pass),
                                "p90_noninferior": bool(p90_pass)})
    passed = all(row["mean_at_least_five_percent_better"] and row["p90_noninferior"]
                 for row in comparisons)
    return {"framework_transfer": True, "stable_empirical_policy_benefit": passed,
            "status": "validated_simulation_only" if passed else "negative_stop",
            "comparisons": comparisons, "complex_risk_research": "paused",
            "generic_pid_deployment_changed": False,
            "further_policy_deepening": "requires_new_prospective_protocol" if passed else False}


def verify_ledger(record, clean, noisy, audit, *, budget=None):
    """Validate independent fresh observations and exact same-ledger caching."""
    measurements, requests = record["measurements"], record["requests"]
    _require(measurements and requests, "empty measured ledger")
    _require(budget is None or len(measurements) <= budget, "objective budget exceeded")
    _require(budget is None or len(requests) <= 4*budget, "proposal cap exceeded")
    _close(measurements[0]["theta"], [.5, .5], "shared initial point", atol=0, rtol=0)
    cache, next_index = {}, 0
    for request in requests:
        key = tuple(request["theta"])
        index = request["measurement"]
        _require(type(index) is int and 0 <= index < len(measurements), "bad measurement reference")
        _require(tuple(measurements[index]["theta"]) == key, "request measurement coordinate differs")
        if key in cache:
            _require(request["cached"] is True and index == cache[key], "cache reference differs")
        else:
            _require(request["cached"] is False and index == next_index, "fresh order differs")
            cache[key], next_index = index, next_index+1
    _require(next_index == len(measurements), "uncharged or unreachable measurement")
    _require(len(cache) == len(measurements), "duplicate recorded as fresh objective")
    for row in measurements:
        _require("error" not in row, "objective execution failed; successful transfer cannot be claimed")
        replayed = audit.replay(row["theta"], clean, noisy)
        _close(row["cost"], replayed["cost"], "independent reference MSE")
        _close(row["features"], replayed["features"], "independent 16-feature observation")


def verify_teacher(record, stages):
    rows, requests = record["measurements"], record["requests"]
    _require(len(record["states"]) == stages, "teacher trajectory stage count differs")
    _require(len(requests) == 1+25*stages, "joint teacher request roster differs")
    pairs = list(itertools.product(range(5), repeat=2))
    deltas = np.asarray([-.2, -.05, 0., .05, .2])
    current, previous = 0, None
    for stage, state in enumerate(record["states"]):
        _require(state["measurement"] == current, "teacher reached-state chain differs")
        features = list(rows[current]["features"])
        features[3] = 0. if previous is None else float(np.log1p(rows[current]["cost"])-np.log1p(previous))
        _close(state["features"], features, "teacher previous measured-cost feedback")
        _require(len(state["candidate_measurements"]) == 25, "joint teacher grid incomplete")
        for j, pair in enumerate(pairs):
            point = np.clip(np.asarray(rows[current]["theta"])+deltas[list(pair)], 0, 1)
            candidate = state["candidate_measurements"][j]
            _require(requests[1+25*stage+j]["measurement"] == candidate,
                     "teacher grid and request references differ")
            _close(rows[candidate]["theta"], point, "joint teacher candidate", atol=0, rtol=0)
        winner = min(range(25), key=lambda j: (
            rows[state["candidate_measurements"][j]]["cost"],
            float(np.sum(deltas[list(pairs[j])]**2)), pairs[j]))
        _require(state["labels"] == list(pairs[winner]), "joint teacher label or tie-break differs")
        _require(state["selected"] == state["candidate_measurements"][winner],
                 "teacher selected action differs")
        previous, current = rows[current]["cost"], state["selected"]


def statistics(raw, p):
    """Rebuild reported costs and accounting independently of runner.summarize."""
    rows = []
    for budget in p["operating"]["budgets"]:
        for method in p["operating"]["methods"]:
            runs = [r for r in raw["operating"] if r["budget"] == budget and r["method"] == method]
            values = np.asarray([r["measurements"][r["returned"]]["cost"] for r in runs])
            counts = np.asarray([len(r["measurements"]) for r in runs])
            rows.append({"budget": budget, "method": method, "n": len(runs),
                         "mean_final_MSE": float(np.mean(values)),
                         "median_final_MSE": float(np.median(values)),
                         "p90_final_MSE": float(np.quantile(values, .9)),
                         "mean_calls": float(np.mean(counts)), "min_calls": int(min(counts)),
                         "max_calls": int(max(counts)), "total_calls": int(sum(counts)),
                         "trial_increases": sum(sum(m["cost"] > r["measurements"][0]["cost"]
                                                     for m in r["measurements"][1:]) for r in runs),
                         "returned_worse_than_start": sum(float(value) > r["measurements"][0]["cost"]
                                                          for value, r in zip(values, runs))})
    phases = {name: sum(len(record["measurements"]) for record in raw["teacher"][name])
              for name in p["splits"]}
    phases["operating"] = sum(len(record["measurements"]) for record in raw["operating"])
    accounting = {"actual_objective_evaluations": sum(phases.values()),
                  "maximum_objective_evaluations": p["accounting"]["maximum_objective_evaluations"],
                  "by_phase": phases,
                  "standalone_offline_per_model": sum(phases[name] for name in ("train", "temperature", "conformal"))}
    return rows, accounting, assess_acceptance(rows, p)


def amortization(rows, accounting):
    """Report calls by task count without implying equal outcome quality."""
    primary = {row["method"]: row for row in rows if row["budget"] == 20}
    result = []
    offline = accounting["standalone_offline_per_model"]
    for seed in (101, 202, 303):
        method = f"typed_seed_{seed}"
        head = primary[method]
        for baseline in ("coordinate_search", "space_filling", "simplex"):
            other = primary[baseline]
            saving = other["mean_calls"]-head["mean_calls"]
            result.append({"seed": seed, "baseline": baseline,
                           "standalone_offline_objectives": offline,
                           "learned_mean_operating_calls": head["mean_calls"],
                           "baseline_mean_operating_calls": other["mean_calls"],
                           "call_only_break_even_tasks": None if saving <= 0 else int(np.ceil(offline/saving)),
                           "task_counts": [{"tasks": n, "learned_total_calls": offline+n*head["mean_calls"],
                                            "baseline_total_calls": n*other["mean_calls"]}
                                           for n in (1, 10, 100, 1000)]})
    return result


def _independent_logits(artifact, features):
    """Independent forward equations; canonical runner mapping checked separately."""
    value = ((np.asarray(features)-artifact["normalization_mean"])
             / artifact["normalization_scale"])
    state = artifact["state_dict"]
    for index in (0, 2, 4):
        value = value @ np.asarray(state[f"net.{index}.weight"]).T + state[f"net.{index}.bias"]
        if index != 4:
            value = np.tanh(value)
    return value.reshape(2, 5)


def _probabilities(logits, temperature):
    scaled = (logits-np.max(logits, axis=-1, keepdims=True))/np.asarray(temperature)[:, None]
    exp = np.exp(scaled)
    return exp/exp.sum(axis=-1, keepdims=True)


def _operating_decisions(record, artifact, calibration):
    current, previous = 0, None
    deltas = np.asarray([-.2, -.05, 0., .05, .2])
    for decision in record["decisions"]:
        _require(decision["current"] == current, "operating current-state chain differs")
        row = record["measurements"][current]
        features = list(row["features"])
        features[3] = 0. if previous is None else float(np.log1p(row["cost"])-np.log1p(previous))
        _close(decision["features"], features, "operating actual feedback")
        probabilities = _probabilities(_independent_logits(artifact, features), calibration["temperatures"])
        _close(decision["probabilities"], probabilities, "independent trained MLP probabilities")
        # Use recorded probabilities for equality-sensitive CP set boundaries;
        # canonical PyTorch reconstruction below also verifies them.
        p = np.asarray(decision["probabilities"])
        mask = (1-p) <= np.asarray(calibration["qhat_per_axis"])[:, None]
        _require(np.array_equal(decision["sets"], mask), "complete CP monitor sets differ")
        mu = p @ deltas
        variance = np.maximum(p @ (deltas*deltas)-mu*mu, 0)
        step = np.clip(mu/(1+variance/np.var(deltas)), -.2, .2)
        _close(decision["step"], step, "independent expectation/variance decode")
        theta = np.clip(np.asarray(row["theta"])+step, 0, 1)
        _close(decision["next_theta"], theta, "bounded additive actuation")
        _close(record["measurements"][decision["measurement"]]["theta"], decision["next_theta"],
               "operating action measurement", atol=0, rtol=0)
        previous, current = row["cost"], decision["measurement"]


def _verify(root, output, audit, *, check_document):
    root, output = Path(root).resolve(), Path(output).resolve()
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    p, report = load(root/PROTOCOL), load(output/"report.json")
    _require(digest(root/PROTOCOL, text=True) == PROTOCOL_SHA256, "frozen protocol changed")
    runner = _module(root/"scripts/45_nonpid_transfer.py", "_nonpid_frozen_runner_audit")
    _source_manifest(root, report["source_hashes"], runner.SOURCES)
    revision = report.get("git_revision", "")
    _require(isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision), "invalid recorded Git revision")
    present = subprocess.run(["git", "cat-file", "-e", revision + "^{commit}"], cwd=root, capture_output=True)
    if present.returncode:
        fetched = subprocess.run(["git", "fetch", "--no-tags", "--depth=1", "origin", revision], cwd=root, capture_output=True)
        _require(fetched.returncode == 0, "recorded source commit unavailable; fetch that revision to verify provenance")
    for name, expected in report["source_hashes"].items():
        committed = subprocess.check_output(["git", "show", revision + ":" + name], cwd=root)
        if Path(name).suffix in TEXT_SUFFIXES:
            committed = committed.replace(b"\r\n", b"\n")
        _require(hashlib.sha256(committed).hexdigest() == expected, "recorded commit differs from execution manifest: " + name)
    _source_manifest(root, REUSED_SOURCES, REUSED_SOURCES)
    _require(report["schema_version"] == 1 and report["study_id"] == p["study_id"], "report identity differs")
    _require(report["protocol"] == PROTOCOL, "report protocol path differs")
    _require(digest(output/"raw.json.gz") == report["raw_sha256"], "raw bytes changed")
    names = {f"{kind}_{seed}.json" for kind in ("model", "calibration") for seed in p["training"]["seeds"]}
    _require(set(report["artifacts"]) == names, "trained/calibrated artifact roster differs")
    for name in names:
        _require(digest(output/name, text=True) == report["artifacts"][name], f"artifact changed: {name}")
    with gzip.open(output/"raw.json.gz", "rt", encoding="utf-8") as stream:
        raw = json.load(stream)
    _require(raw["schema_version"] == 1 and set(raw["teacher"]) == set(p["splits"]), "raw split roster differs")
    split_ids = [split["seed"] for split in p["splits"].values()]
    _require(len(set(split_ids)) == 4, "split identities overlap")
    arrays = {}
    for name, split in p["splits"].items():
        objects = raw["teacher"][name]
        _require([obj["task"] for obj in objects] == list(range(split["n"])), f"incomplete split: {name}")
        for record in objects:
            clean, noisy = signals(split["seed"], record["task"])
            verify_ledger(record, clean, noisy, audit)
            verify_teacher(record, split["teacher_stages"])
        arrays[name] = (np.asarray([s["features"] for obj in objects for s in obj["states"]]),
                        np.asarray([s["labels"] for obj in objects for s in obj["states"]], dtype=np.int64))
    x = arrays["train"][0]
    mean, scale = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-8)
    artifacts, calibrations, cp_diagnostics = {}, {}, []
    from jev_tune.primitives import calibrate_temperature
    for seed in p["training"]["seeds"]:
        artifact, calibration = load(output/f"model_{seed}.json"), load(output/f"calibration_{seed}.json")
        _require(artifact["seed"] == calibration["seed"] == seed, "model/calibration seed differs")
        _require(artifact["architecture"] == [16, 32, 32, 10] and artifact["dtype"] == "float64"
                 and artifact["inference_shape"] == [1, 16], "checkpoint architecture/mapping differs")
        _close(artifact["normalization_mean"], mean, "train-only normalization mean")
        _close(artifact["normalization_scale"], scale, "train-only normalization scale")
        model = runner.load_model(artifact)
        logits = {}
        for name in ("temperature", "conformal", "test"):
            logits[name] = np.stack([runner.infer_logits(model, artifact, features) for features in arrays[name][0]])
            independent = np.stack([_independent_logits(artifact, features) for features in arrays[name][0]])
            _close(logits[name], independent, "canonical single-object trained inference")
        temperatures = [calibrate_temperature(logits["temperature"][:, a], arrays["temperature"][1][:, a])
                        for a in range(2)]
        _close(calibration["temperatures"], temperatures, "independent temperature split fit")
        probs = {name: np.stack([_probabilities(value, temperatures) for value in logits[name]])
                 for name in ("conformal", "test")}
        # Runner's canonical probability calculation is authoritative at score ties.
        canonical_cp = np.stack([runner.predict(model, artifact, features, calibration)
                                 for features in arrays["conformal"][0]])
        _close(probs["conformal"], canonical_cp, "calibrated canonical probabilities")
        qhat = independent_conformal(canonical_cp, arrays["conformal"][1])
        _close(calibration["qhat_per_axis"], qhat, "finite-sample split CP rank", atol=0, rtol=0)
        _require(calibration["alpha"] == .1 and calibration["n_calibration"] == 256
                 and calibration["quantile_rank"] == 232 and calibration["mode"] == "monitor",
                 "CP boundary/mode differs")
        canonical_test = np.stack([runner.predict(model, artifact, features, calibration)
                                   for features in arrays["test"][0]])
        diagnostics = conformal_diagnostics(canonical_test, arrays["test"][1], qhat)
        cp_diagnostics.append({"seed": seed, "n": diagnostics["n_states"],
                               "coverage_per_axis": diagnostics["coverage_per_axis"],
                               "mean_set_size_per_axis": diagnostics["mean_set_size_per_axis"]})
        artifacts[seed], calibrations[seed] = artifact, calibration
    _treeclose(report["cp_diagnostics"], cp_diagnostics, "independent initial-state CP diagnostics")
    expected_runs = [(budget, method, index) for budget in p["operating"]["budgets"]
                     for method in p["operating"]["methods"] for index in range(p["splits"]["test"]["n"])]
    _require([(r["budget"], r["method"], r["task"]) for r in raw["operating"]] == expected_runs,
             "operating roster/order differs")
    original_task = runner.DenoiseTask
    try:
        for record in raw["operating"]:
            clean, noisy = signals(p["splits"]["test"]["seed"], record["task"])
            verify_ledger(record, clean, noisy, audit, budget=record["budget"])
            rows = record["measurements"]
            best = min(range(len(rows)), key=lambda i: rows[i]["cost"])
            _require(type(record["returned"]) is int and record["returned"] == best, "returned point is not measured best")
            _require(rows[best]["cost"] <= rows[0]["cost"], "return regresses from measured start")
            seed = int(record["method"].rsplit("_", 1)[1]) if record["method"].startswith("typed_seed_") else None
            if seed is not None:
                _operating_decisions(record, artifacts[seed], calibrations[seed])
            else:
                _require(record["decisions"] == [], "baseline records hidden learned decisions")
            measured = {tuple(row["theta"]): {"cost": row["cost"], "features": row["features"]} for row in rows}
            class RecordedTask:
                def __init__(self, split_seed, index):
                    _require(split_seed == p["splits"]["test"]["seed"] and index == record["task"],
                             "replay task identity differs")
                def evaluate(self, theta):
                    _require(tuple(theta) in measured, "method replay requests an unrecorded objective")
                    return measured[tuple(theta)]
            runner.DenoiseTask = RecordedTask
            replay = runner.rollout(p["splits"]["test"]["seed"], record["task"], record["method"], record["budget"],
                                    artifact=artifacts.get(seed), calibration=calibrations.get(seed))
            _treeclose(record, replay, "canonical recorded-only operating replay")
    finally:
        runner.DenoiseTask = original_task
    rows, accounting, acceptance = statistics(raw, p)
    _treeclose(report["rows"], rows, "independent operating statistics")
    _treeclose(report["acceptance"], acceptance, "frozen independent acceptance")
    observed_accounting = {k: v for k, v in report["accounting"].items() if k != "optimizer_fit"}
    _treeclose(observed_accounting, accounting, "independent objective accounting")
    _require(accounting["actual_objective_evaluations"] <= 83840, "prospective acquisition cap exceeded")
    phase_caps = {"train": 24832, "temperature": 3200, "conformal": 6400, "test": 6400, "operating": 43008}
    _require(all(accounting["by_phase"][name] <= maximum for name, maximum in phase_caps.items()), "phase cap exceeded")
    fits = report["accounting"]["optimizer_fit"]
    _require([fit["seed"] for fit in fits] == p["training"]["seeds"], "optimizer seed roster differs")
    for fit in fits:
        _require(fit["examples"] == 1024 and fit["epochs"] == 100 and fit["optimizer_steps"] == 800,
                 "final fixed-epoch training schedule differs")
        _require(len(fit["epoch_losses"]) == 100 and np.isfinite(fit["epoch_losses"]).all(), "training loss trace incomplete")
        _close(fit["first_epoch_loss"], fit["epoch_losses"][0], "first epoch loss")
        _close(fit["last_epoch_loss"], fit["epoch_losses"][-1], "last epoch loss")
        _require(fit["cpu_seconds"] >= 0 and fit["wall_seconds"] >= 0, "invalid measured fit time")
    if "amortization" in report:
        _treeclose(report["amortization"], amortization(rows, accounting), "cost-versus-task-count")
    if check_document:
        _require((root/DOC).read_text(encoding="utf-8") == render(report), "generated bilingual report differs")
    _require(audit.evaluations == accounting["actual_objective_evaluations"], "audit replay count differs from recorded candidates")
    return {"ok": True, "framework_transfer": True, "acceptance": acceptance,
            "raw_sha256": report["raw_sha256"], "accounting": report["accounting"],
            "additional_verification_objective_evaluations": audit.evaluations,
            "verification_scope": "Independent generator/filter/MSE/features/teacher/rank/statistics and canonical recorded-only rollout replay"}


def check(root=ROOT, output=None, *, check_document=True):
    root = Path(root).resolve()
    output = Path(output).resolve() if output else root/"research/results/nonpid_transfer"
    audit, started = AuditCompute(), datetime.now(timezone.utc).isoformat()
    raw_hash = digest(output/"raw.json.gz") if (output/"raw.json.gz").exists() else None
    try:
        result = _verify(root, output, audit, check_document=check_document)
    except Exception as exc:
        receipt = _receipt(root, raw_hash, audit, started, "failed", f"{type(exc).__name__}: {exc}")
        raise ValueError(f"{exc}; additional_verification_objective_evaluations={audit.evaluations}; "
                         f"receipt={receipt.get('receipt_path', receipt.get('receipt_write_error'))}") from exc
    result["receipt"] = _receipt(root, raw_hash, audit, started, "passed")
    return result


def _number(value, digits=8):
    return f"{value:.{digits}f}"


def render(report):
    """Generate all numeric prose and tables from the saved acquisition report."""
    summary = report.get("summary", report)
    rows, accounting = summary["rows"], summary["accounting"]
    acceptance = summary["acceptance"]
    table = ["| budget | method | mean / median / p90 MSE | actual calls mean (min–max) |",
             "| ---: | :--- | ---: | ---: |"]
    for row in sorted(rows, key=lambda row: (row["budget"], row["method"])):
        table.append(f"| {row['budget']} | `{row['method']}` | "
                     f"{_number(row['mean_final_MSE'])} / {_number(row['median_final_MSE'])} / "
                     f"{_number(row['p90_final_MSE'])} | {row['mean_calls']:.6f} "
                     f"({row['min_calls']}–{row['max_calls']}) |")
    comparison = ["| seed | baseline, primary budget 20 | mean rule | p90 rule |",
                  "| ---: | :--- | :--- | :--- |"]
    for row in acceptance["comparisons"]:
        comparison.append(f"| {row['seed']} | `{row['baseline']}` | "
                          f"{'PASS' if row['mean_at_least_five_percent_better'] else 'FAIL'} | "
                          f"{'PASS' if row['p90_noninferior'] else 'FAIL'} |")
    table_text = "\n".join(table)+"\n\n"+"\n".join(comparison)
    phase_rows = ["| phase | actual fresh objective evaluations |",
                  "| :--- | ---: |"]
    for phase, count in accounting["by_phase"].items():
        phase_rows.append(f"| `{phase}` | {count} |")
    phase_text = "\n".join(phase_rows)
    fit_rows = ["| model seed | SGD steps | CPU seconds | wall seconds |",
                "| ---: | ---: | ---: | ---: |"]
    for row in accounting["optimizer_fit"]:
        fit_rows.append(f"| {row['seed']} | {row['optimizer_steps']} | {row['cpu_seconds']:.6f} | "
                        f"{row['wall_seconds']:.6f} |")
    fit_text = "\n".join(fit_rows)
    coverage_rows = ["| seed | initial-state coverage, axes 0 / 1 | mean complete-set size, axes 0 / 1 |",
                     "| ---: | ---: | ---: |"]
    for row in summary["cp_diagnostics"]:
        stats = row.get("test", row)
        coverage_rows.append(f"| {row['seed']} | "
                             f"{stats['coverage_per_axis'][0]:.6f} / {stats['coverage_per_axis'][1]:.6f} | "
                             f"{stats['mean_set_size_per_axis'][0]:.6f} / "
                             f"{stats['mean_set_size_per_axis'][1]:.6f} |")
    coverage_text = "\n".join(coverage_rows)
    status_en = ("All three seeds passed the registered descriptive rule within this synthetic task. "
                 "This does not authorize other populations or automatic deployment."
                 if acceptance["stable_empirical_policy_benefit"] else
                 "The learned policy failed the frozen stable-benefit rule. The outcome is `negative_stop`: "
                 "preserve all trained artifacts and evidence and stop policy/risk deepening on this test.")
    status_zh = ("三个种子全部通过本合成任务内预先注册的描述性规则；不授权其他总体或自动部署。"
                 if acceptance["stable_empirical_policy_benefit"] else
                 "学习策略未通过冻结的稳定收益规则，结论为`negative_stop`：保留全部训练产物与证据，停止利用本测试继续深化策略或风险头。")
    amortization_rows = summary.get("amortization", amortization(rows, accounting))
    amortization_table = ["| seed | baseline | call-only break-even tasks | learned / baseline calls after 100 tasks |",
                          "| ---: | :--- | ---: | ---: |"]
    for row in amortization_rows:
        hundred = next(value for value in row["task_counts"] if value["tasks"] == 100)
        point = row["call_only_break_even_tasks"]
        amortization_table.append(f"| {row['seed']} | `{row['baseline']}` | {'null' if point is None else point} | "
                                  f"{hundred['learned_total_calls']:.6f} / {hundred['baseline_total_calls']:.6f} |")
    amortization_text = "\n".join(amortization_table)
    return f"""# Trained non-PID transfer / 非PID训练迁移

[English](#english) · [简体中文](#简体中文)

## English

Framework transfer is **PASS** after the independent evidence checker passes. Policy-value acceptance is **{acceptance['status']}**. {status_en}

The protocol was frozen in `{PREREGISTRATION_COMMIT}`, with verification accounting clarified in `{ACCOUNTING_CLARIFICATION_COMMIT}` before acquisition. One prospective run trains the three fixed seeds on shared teacher data and tests every frozen arm on the same 256 new signals. Seeds are correlated model replicates, not 768 independent test objects. No architecture, checkpoint, threshold, task variant or acceptance criterion is selected from test results. Budget 8 is secondary; budget 20 alone determines policy-value acceptance. Every model must have mean MSE at most 0.95 times each baseline and p90 no greater than each baseline; this is an empirical stability rule, not a confidence guarantee or a significance test.

The task is synthetic, offline reference denoising calibration: adjust a local winsorization multiplier and a low-pass cutoff through two bounded additive coordinates. Each 192-sample noisy/reference pair is immutable and resettable. A full filter execution measures reference MSE. The clean signal and latent generator parameters are excluded from policy input, but reference MSE is supplied by the evaluator; this is not blind denoising or validation on external data. Filtering deliberately uses future samples. The initial normalized coordinates are `[0.5, 0.5]`; every operating arm includes that initial measurement in its budget, returns its best actually measured point, and receives no uncharged final optimization.

{table_text}

Temperature scaling and split CP use distinct independent signal splits after weight fitting. Each fitted checkpoint is applied in the canonical `(1,16)` float64 CPU mapping on every calibration and operating inference. CP retains complete sets in monitor mode and never changes an action. Its 90% marginal teacher-label inclusion boundary is per axis on independent initial-state signals under this fixed generator and inference mapping. It does not cover both axes jointly, reached states, accepted-action risk, closed-loop safety or performance. Empirical test coverage is descriptive and never changes a threshold. Noul reports finite observation validity; it is not a trained harmful-action probability.

{coverage_text}

Acquisition executed **{accounting['actual_objective_evaluations']}** fresh objectives against the frozen maximum **{accounting['maximum_objective_evaluations']}**. Exact coordinate duplicates reuse only their own ledger; no cache is shared across splits, objects, arms or budgets. Shared teacher acquisition is physically charged once, and its complete training + temperature + CP cost is charged to every deployable model's standalone cost: **{accounting['standalone_offline_per_model']}** objective evaluations. Offline test teacher labels are separate from operating calls and never fit a model. Model optimizer time is recorded separately from objective calls.

{phase_text}

{fit_text}

Cost versus task count is descriptive and uses actual operating calls. The break-even entry remains null when the learned method does not reduce operating calls. It does not assert equal quality merely because calls match or decrease.

{amortization_text}

Reusable components are unchanged `Choice`/`Option`/`Answer`/`Noul`, softmax, temperature fitting, split CP and `decide` for ordered numeric payloads. The domain owns observations, teacher labels, this two-axis MLP, reference objective, additive actuation, ledger, baselines and acceptance. PID weights, three-axis features, multiplicative gain updates, PID rollback and complex joint-risk heads are not transferred. Score remains an optional unused primitive. Existing Python/C/MATLAB PID deployment is unchanged.

Sources: [frozen protocol](../{PROTOCOL}), [summary](../{RESULT}), [raw measured records](../{RAW}). `python scripts/45_nonpid_transfer.py --run` refuses existing outputs; use `--output-root <new-directory>` for a separate replay. `python scripts/46_verify_nonpid_transfer.py --check` independently reconstructs recorded objectives, labels, calibration, decisions, budgets and acceptance. Each audit reports and persists its additional deterministic filter executions separately; these are verification compute, not new independent data or prospective acquisition. Historical failed risk studies remain available unchanged.

## 简体中文

独立证据检查通过后，框架迁移验收为**PASS**；策略价值验收为**{acceptance['status']}**。{status_zh}

协议在`{PREREGISTRATION_COMMIT}`冻结，并在采集前由`{ACCOUNTING_CLARIFICATION_COMMIT}`明确复核计账。一次前瞻执行使用共享teacher数据训练三个固定种子，在同一批256个新信号上测试全部冻结方法。三个种子是相关模型重复，不是768个独立测试对象。没有用测试结果挑选架构、checkpoint、阈值、任务变体或验收条件。8次预算属于次要诊断，只有20次预算决定策略价值验收。每个种子的平均MSE都必须不高于每条基线的0.95倍，p90也不得高于每条基线；这属于经验稳定性规则，不是置信保证或显著性检验。

任务是合成的离线参考去噪标定，通过两个有界加法坐标调整局部截断倍数及低通截止频率。每个192点带噪/参考信号对固定且可重置，一次完整滤波执行计算参考MSE。策略输入没有干净波形及隐含生成参数，但评估器提供参考MSE，因此不能称盲去噪或外部数据验证；非因果滤波有意使用未来样本。所有方法都从归一化坐标`[0.5, 0.5]`起步，初测计入运行预算，只返回实际测过的最优点，没有免费末次优化。

{table_text}

权重训练后，温度缩放与Split CP分别使用两个独立信号划分。所有校准和运行推理均使用固定checkpoint的`(1,16)` float64 CPU映射。CP在monitor模式保留完整集合，不改变动作。90%边际teacher标签包含边界仅针对固定生成器及推理映射下、独立初态信号的单轴标签；不保证联合双轴、到达状态、已接受动作风险、闭环安全或性能。测试经验覆盖率仅描述结果，不能用来修改阈值。Noul只表示观测是否有限，不是训练得到的有害动作概率。

{coverage_text}

前瞻采集共真实执行**{accounting['actual_objective_evaluations']}**次目标函数，冻结上限为**{accounting['maximum_objective_evaluations']}**次。完全相同的坐标只在自己的账本内复用，不跨划分、对象、方法或预算共享缓存。共享teacher采集物理上只计一次，同时每个可部署模型均独立承担完整训练、温度和CP采集成本：**{accounting['standalone_offline_per_model']}**次目标函数。测试teacher标签单独计账，不用于拟合模型，不混入在线运行次数。优化器时间与目标调用次数分开报告。

{phase_text}

{fit_text}

随任务次数的成本比较采用实际运行次数，仅作描述。当学习方法没有减少运行调用时，收支平衡项保持null。调用相同或更少也不表示质量相同。

{amortization_text}

复用边界为未改动的`Choice`/`Option`/`Answer`/`Noul`、softmax、温度拟合、Split CP，以及处理有序数值载荷的`decide`。新领域负责观测、teacher标签、双轴MLP、参考目标函数、加法执行器、账本、基线及验收。PID权重、三轴特征、乘法增益更新、PID回退与复杂联合风险头均未迁移；Score作为可选原语，本例未使用。既有Python/C/MATLAB PID部署不变。

来源：[冻结协议](../{PROTOCOL})、[汇总](../{RESULT})、[原始实测记录](../{RAW})。`python scripts/45_nonpid_transfer.py --run`拒绝覆盖已有输出；使用`--output-root <new-directory>`单独复现。`python scripts/46_verify_nonpid_transfer.py --check`独立重建已记录目标、标签、校准、决策、预算和验收。每次复核单独报告并保存额外确定性滤波执行次数，属于复核算力，不是新增独立样本或前瞻采集。历史失败风险研究保持原样可用。
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true")
    action.add_argument("--render-only", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    output = args.output_root or args.root/"research/results/nonpid_transfer"
    if args.render_only:
        document = args.root/DOC
        document.parent.mkdir(parents=True, exist_ok=True)
        document.write_text(render(load(output/"report.json")), encoding="utf-8")
        print(json.dumps({"ok": True, "document": str(document),
                          "additional_verification_objective_evaluations": 0}))
        return
    try:
        result = check(root=args.root, output=output)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
