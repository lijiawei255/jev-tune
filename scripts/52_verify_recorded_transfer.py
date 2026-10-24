"""Audit original recorded transfer evidence, without claiming strict CPU replay.

This is a separate, post-incident audit.  It does not modify or replace the
frozen 46/48 checks.  Recorded probabilities are independently certified before
they are used to reconstruct the original operating chain.  No model is trained
and only previously recorded filter candidates may be evaluated.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import importlib
import itertools
import json
import multiprocessing
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ARRAYS = "research/results/calibration_runtime_sources/original_machine_arrays.npz"
ARRAY_MANIFEST = "research/results/calibration_runtime_sources/original_machine_arrays.json"
ARRAY_SHA256 = "e8245f4e57bcc387d3ee5b2636b4fbff8d0d88da79a36bfa315bf43cc85c8f21"
SMALL_ARRAYS = "research/results/calibration_runtime_sources/small_sample_arrays.npz"
SMALL_MANIFEST = "research/results/calibration_runtime_sources/small_sample_arrays.json"
SMALL_SHA256 = "24d635a6e0805a05f3724adad43b23ce0baf9ff9278dad85740ae18957fa290f"
RECEIPTS = ".local-audit/recorded_transfer_verification"
AUDIT_PROTOCOL = "research/protocols/recorded_evidence_audit_v0100.json"
ORIGINAL_DIAGNOSIS = "research/results/calibration_runtime_sources/calibration_runtime_root_default_v0100/diagnosis.json"
SCOPE = ("Post-incident original-record evidence audit: independent recorded-candidate "
         "filter/MSE/features/teacher/accounting, certified recorded probabilities, "
         "and recorded-probability operating-chain reconstruction. This is NOT "
         "strict current-CPU trajectory replay, a replacement for failed 46/48, "
         "new independent data, or a new coverage/deployment claim.")


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


audit46 = module(ROOT / "scripts/46_verify_nonpid_transfer.py", "_recorded_transfer_independent46")
require, close, treeclose = audit46._require, audit46._close, audit46._treeclose
DELTAS = np.asarray([-.2, -.05, 0., .05, .2])


def numeric_api(root=ROOT):
    return module(Path(root) / "scripts/calibration_numeric_audit.py", "_recorded_transfer_decimal_audit")


def execution_sources(root):
    """Require a committed, reviewable snapshot before a complete real audit."""
    names = ("scripts/52_verify_recorded_transfer.py", "scripts/calibration_numeric_audit.py",
             "scripts/46_verify_nonpid_transfer.py", "scripts/48_recalibration_benchmark.py",
             "scripts/53_archive_original_calibration.py", "scripts/55_archive_supplemental_arrays.py",
             "scripts/54_compare_calibration_runtimes.py", "scripts/56_summarize_recorded_evidence.py",
             "tests/test_recorded_transfer.py", "tests/test_numeric_audit.py",
             "tests/test_runtime_boundary.py", "tests/test_recorded_summary.py", AUDIT_PROTOCOL)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    hashes = {}
    for name in names:
        value = audit46.digest(root / name, text=True)
        committed = subprocess.run(["git", "show", revision + ":" + name], cwd=root, capture_output=True)
        require(committed.returncode == 0
                and hashlib.sha256(committed.stdout.replace(b"\r\n", b"\n")).hexdigest() == value,
                "commit audit implementation before executing: " + name)
        hashes[name] = value
    protocol = audit46.load(root / AUDIT_PROTOCOL)
    require(protocol["study_type"] == "post_incident_recorded_evidence_audit"
            and protocol["strict_cross_cpu_refit_passed"] is False,
            "recorded evidence protocol scope differs")
    require(set(protocol["source_hashes"]) == set(names)-{AUDIT_PROTOCOL},
            "recorded evidence protocol source manifest incomplete")
    audit46._source_manifest(root, protocol["source_hashes"], protocol["source_hashes"])
    return {"git_revision": revision, "source_hashes": hashes}


def observed_golden_traces(root, seed, n, temperatures):
    """Post-incident original-host observations, never invented search branches."""
    root = Path(root)
    diagnostic = audit46.load(root / ORIGINAL_DIAGNOSIS)
    require(diagnostic["label"] == "original_machine_default"
            and diagnostic["original_48_check"]["returncode"] == 0
            and diagnostic["additional_objective_evaluations"] == 0
            and diagnostic["training_gradient_steps"] == 0,
            "original host branch observation identity differs")
    require(diagnostic["model_hashes_before"] == diagnostic["model_hashes_after"],
            "original host model changed during observation")
    manifest = audit46.load(root / ARRAY_MANIFEST)
    require(diagnostic["input_hashes"] == manifest["input_hashes"], "original branch inputs differ")
    base = (root / ORIGINAL_DIAGNOSIS).parent / "canonical_arrays.npz"
    require(audit46.digest(base) == diagnostic["canonical_arrays_sha256"], "original branch logits archive changed")
    with np.load(base, allow_pickle=False) as old, np.load(root / ARRAYS, allow_pickle=False) as captured:
        for name in old.files:
            require(old[name].tobytes() == captured[name].tobytes(), "original branch array bits differ: " + name)
    rows = [row for row in diagnostic["rows"] if row["seed"] == seed and row["n_temperature"] == n]
    require(len(rows) == 1 and len(rows[0]["axes"]) == 2, "original branch roster differs")
    traces = []
    for axis, row in enumerate(rows[0]["axes"]):
        require(row["axis"] == axis and row["recorded_temperature"] == row["trace_temperature"]
                == row["refit_temperature"] == temperatures[axis]
                and row["trace_matches_frozen_function_exactly"] is True,
                "original observed branch return differs")
        traces.append(row["golden_iterations"])
    return traces


def decode_recorded(probabilities, qhat):
    """Independently reconstruct the frozen two-axis Choice/monitor contract."""
    p, q = np.asarray(probabilities, dtype=float), np.asarray(qhat, dtype=float)
    require(p.shape == (2, 5) and np.isfinite(p).all()
            and ((p >= 0) & (p <= 1)).all()
            and np.allclose(p.sum(axis=-1), 1, atol=1e-6), "invalid recorded Choice probabilities")
    require(q.shape == (2,) and np.isfinite(q).all()
            and ((q >= 0) & (q <= 1)).all(), "invalid recorded CP quantiles")
    mean = p @ DELTAS
    variance = np.maximum(p @ (DELTAS * DELTAS) - mean * mean, 0.)
    proposed = np.clip(mean / (1 + variance / np.var(DELTAS)), -.2, .2)
    mask = (1. - p) <= q[:, None]
    sizes = mask.sum(axis=-1)
    mixed = ((mask & (DELTAS < 0)).any(axis=-1)
             & (mask & (DELTAS > 0)).any(axis=-1))
    would_hold = (sizes == 0) | (sizes > 3) | mixed
    # abstain=None, Noul=1, CP monitor: no confidence/CP veto is executed.
    return {"step": proposed, "held": np.zeros(2, dtype=bool),
            "escalate": np.zeros(2, dtype=bool), "noul": 1.,
            "sets": mask, "set_size": sizes, "conformal_would_hold": would_hold}


def verify_typed_shell(probabilities, qhat, expected):
    """Check that the frozen Choice/Noul/decide path implements that contract."""
    from jev_tune.decode import ConformalPolicy, decide
    from jev_tune.primitives import Answer, Choice, Noul, Option
    answer = Answer(choice=[Choice(name, [Option(str(d), float(d)) for d in DELTAS], np.asarray(probabilities)[axis])
                            for axis, name in enumerate(("winsor_threshold", "lowpass_cutoff"))],
                    noul=Noul("finite observation", 1.))
    decision = decide(answer, max_step=.2, shrinkage=1., abstain=None,
                      conformal=ConformalPolicy(tuple(qhat), mode="monitor"))
    close(decision.step, expected["step"], "frozen typed Choice decode")
    require(not decision.held.any() and not decision.escalate.any()
            and (decision.reason == 0).all() and decision.noul == 1.,
            "monitor or Noul unexpectedly vetoed an operating action")
    require(decision.conformal_mode == "monitor" and decision.conformal_applied is True,
            "frozen conformal mode differs")
    require(np.array_equal(np.asarray(decision.conformal_set), expected["sets"])
            and np.array_equal(decision.set_size, expected["set_size"])
            and np.array_equal(decision.conformal_would_hold, expected["conformal_would_hold"]),
            "frozen typed monitor evidence differs")


class RecordedLedger:
    """Consume the exact original request/cache roster without an objective."""

    def __init__(self, record):
        self.record, self.position, self.fresh, self.cache = record, 0, 0, {}

    def observe(self, theta):
        theta = np.asarray(theta, dtype=float)
        require(theta.shape == (2,) and np.isfinite(theta).all()
                and ((theta >= 0) & (theta <= 1)).all(), "invalid reconstructed proposal")
        if self.position >= 4 * self.record["budget"]:
            raise StopIteration("proposal_cap")
        key = tuple(float(x) for x in theta)
        cached = key in self.cache
        if not cached and self.fresh >= self.record["budget"]:
            raise StopIteration("budget")
        require(self.position < len(self.record["requests"]), "reconstruction requests an unrecorded objective")
        request = self.record["requests"][self.position]
        require(tuple(request["theta"]) == key, "reconstructed proposal coordinate differs")
        expected = self.cache[key] if cached else self.fresh
        require(type(request["measurement"]) is int and request["measurement"] == expected
                and request["cached"] is cached, "reconstructed proposal/cache reference differs")
        require(tuple(self.record["measurements"][expected]["theta"]) == key,
                "reconstructed proposal measurement differs")
        if not cached:
            self.cache[key], self.fresh = self.fresh, self.fresh + 1
        self.position += 1
        return expected

    def best(self):
        return min(range(self.fresh), key=lambda i: self.record["measurements"][i]["cost"])

    def finish(self):
        require(self.position == len(self.record["requests"]), "unconsumed original requests")
        require(self.fresh == len(self.record["measurements"]), "unconsumed original measurements")
        require(type(self.record["returned"]) is int and self.record["returned"] == self.best(),
                "returned point is not measured best")


def verify_operating(record, artifact, calibration, api):
    """Check actual feedback, full recorded probabilities and every action link."""
    ledger = RecordedLedger(record)
    current, previous = ledger.observe([.5, .5]), None
    decisions = record["decisions"]
    require(decisions, "typed operating record has no decisions")
    for index, decision in enumerate(decisions):
        require(type(decision["current"]) is int and decision["current"] == current,
                "operating current-state chain differs")
        row = record["measurements"][current]
        features = list(row["features"])
        features[3] = (0. if previous is None else
                       float(np.log1p(row["cost"]) - np.log1p(previous)))
        close(decision["features"], features, "operating actual feedback")
        try:
            # Certify the original recorded model input after independently
            # checking its measured-state/feedback derivation above.
            certificate = api.audit_forward(artifact, decision["features"])
            api.audit_softmax(certificate["logits"], calibration["temperatures"],
                              recorded_probabilities=decision["probabilities"],
                              logit_intervals=certificate["logit_intervals"])
        except ValueError as exc:
            raise ValueError(f"{record['method']} task={record['task']} budget={record['budget']} "
                             f"decision={index}: {exc}") from exc
        decoded = decode_recorded(decision["probabilities"], calibration["qhat_per_axis"])
        verify_typed_shell(decision["probabilities"], calibration["qhat_per_axis"], decoded)
        require(np.array_equal(np.asarray(decision["sets"]), decoded["sets"]),
                "complete CP monitor sets differ")
        close(decision["step"], decoded["step"], "independent Choice expectation/variance decode")
        # Check the original binary64 addition/clip from its recorded step exactly;
        # no new-CPU MLP proposal is substituted at an equality-sensitive cache key.
        expected_theta = np.clip(np.asarray(row["theta"]) + np.asarray(decision["step"]), 0., 1.)
        close(decision["next_theta"], expected_theta, "bounded additive actuation", atol=0, rtol=0)
        measured = ledger.observe(decision["next_theta"])
        require(type(decision["measurement"]) is int and decision["measurement"] == measured,
                "operating action measurement differs")
        repeated = np.array_equal(expected_theta, row["theta"])
        require(not repeated or index == len(decisions) - 1, "operating continued after exact no-action")
        previous, current = row["cost"], measured
    if repeated:
        require(record["stop"] == "no_action", "exact no-action stop differs")
    elif record["stop"] == "budget":
        require(ledger.fresh == record["budget"], "typed budget stop before budget exhaustion")
        require(ledger.position < 4 * record["budget"], "proposal cap must precede budget rejection")
        row = record["measurements"][current]
        terminal_features = list(row["features"])
        terminal_features[3] = float(np.log1p(row["cost"]) - np.log1p(previous))
        # Full budget does not prohibit cache hits. Independently enclose the
        # next unrecorded proposal and prove it cannot equal ANY cached point.
        # An unresolved boundary rejects the evidence; it never assumes budget
        # exhaustion just because the acquisition count has reached its cap.
        api.audit_next_proposal(artifact, terminal_features, calibration["temperatures"],
                                row["theta"], list(ledger.cache), deltas=DELTAS.tolist(),
                                feedback_costs=(row["cost"], previous))
    elif record["stop"] == "proposal_cap":
        require(ledger.position == 4 * record["budget"], "typed proposal stop before exhaustion")
    else:
        raise ValueError("invalid typed operating stop")
    ledger.finish()
    return len(decisions)


def _numeric_only_worker(record, artifact, calibration, binding, roster_index):
    """Spawn-safe entry: certify one record; any objective attempt is rejected."""
    require(str(ROOT.resolve()) == binding["root"], "numeric worker repository differs")
    for name, expected in binding["source_hashes"].items():
        require(audit46.digest(ROOT / name, text=True) == expected, "numeric worker source differs: " + name)

    def forbidden_objective(*args, **kwargs):
        raise ValueError("numeric-only worker attempted a forbidden objective/filter")

    audit46.filter_output = forbidden_objective
    audit46.verify_ledger = forbidden_objective
    audit46.AuditCompute.replay = forbidden_objective
    seed = int(record["method"].rsplit("_", 1)[1])
    require(artifact["seed"] == calibration.get("seed", seed) == seed, "numeric worker model identity differs")
    count = verify_operating(record, artifact, calibration, numeric_api(ROOT))
    return {"roster_index": roster_index, "task": record["task"], "method": record["method"],
            "budget": record["budget"], "decisions": count, "status": "passed", "worker_pid": os.getpid(),
            "additional_objective_evaluations": 0, "gradient_steps": 0,
            "source_hashes": binding["source_hashes"]}


def verify_operating_parallel(jobs, *, root=ROOT, max_workers=4):
    """Collect every record in roster order; workers never own filter accounting.

    A stable namespace import is intentional: callers such as 16 load this
    script under arbitrary dynamic module names, which spawn cannot unpickle.
    Only frozen, already validated in-memory records are passed to children.
    """
    root = Path(root).resolve()
    require(root == ROOT.resolve(), "numeric worker must use this script's repository")
    require(type(max_workers) is int and 1 <= max_workers <= 4, "numeric workers must be between one and four")
    require(jobs, "no typed operating records to certify")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    stable = importlib.import_module("scripts.52_verify_recorded_transfer")
    require(Path(stable.__file__).resolve() == Path(__file__).resolve(), "spawn worker imported another script")
    names = ("scripts/52_verify_recorded_transfer.py", "scripts/calibration_numeric_audit.py",
             "scripts/46_verify_nonpid_transfer.py", "src/jev_tune/primitives.py", "src/jev_tune/decode.py")
    binding = {"root": str(root), "source_hashes": {name: audit46.digest(root / name, text=True) for name in names}}
    workers = min(max_workers, len(jobs))
    rows, failures = [], []
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = [pool.submit(stable._numeric_only_worker, record, artifact, calibration, binding, index)
                   for index, (record, artifact, calibration) in enumerate(jobs)]
        # Never discard later completed records because an earlier one failed.
        for index, (future, (record, _, _)) in enumerate(zip(futures, jobs)):
            try:
                row = future.result()
                require((row["roster_index"], row["task"], row["method"], row["budget"])
                        == (index, record["task"], record["method"], record["budget"]),
                        "numeric worker result roster differs")
                require(row["decisions"] == len(record["decisions"]), "numeric worker omitted a decision")
                require(row["additional_objective_evaluations"] == row["gradient_steps"] == 0
                        and row["source_hashes"] == binding["source_hashes"], "numeric worker scope/source differs")
            except Exception as exc:
                row = {"roster_index": index, "task": record["task"], "method": record["method"],
                       "budget": record["budget"], "status": "failed", "expected_decisions": len(record["decisions"]),
                       "error_type": type(exc).__name__, "error": str(exc),
                       "additional_objective_evaluations": 0, "gradient_steps": 0}
                failures.append(exc)
            rows.append(row)
    summary = {"executor": "ProcessPoolExecutor/spawn", "max_workers": max_workers, "workers": workers,
               "worker_pids": sorted({row["worker_pid"] for row in rows if "worker_pid" in row}),
               "expected_records": len(jobs), "completed_records": len(rows),
               "expected_decisions": sum(len(record["decisions"]) for record, _, _ in jobs),
               "verified_complete_record_decisions": sum(row.get("decisions", 0) for row in rows),
               "failed_records": len(failures), "additional_objective_evaluations": 0, "gradient_steps": 0,
               "source_hashes": binding["source_hashes"], "records": rows}
    for name, expected in binding["source_hashes"].items():
        require(audit46.digest(root / name, text=True) == expected, "numeric worker source changed during certification: " + name)
    if failures:
        exc = ValueError(f"{len(failures)} numeric operating records failed; "
                         f"first={type(failures[0]).__name__}: {failures[0]}")
        exc.operating_parallel_audit = summary
        raise exc from failures[0]
    require(summary["verified_complete_record_decisions"] == summary["expected_decisions"],
            "numeric workers omitted operating decisions")
    return summary["verified_complete_record_decisions"], summary


def verify_baseline(record):
    """Rebuild every frozen baseline proposal using only its paid observations."""
    from scipy.optimize import minimize
    from scipy.stats import qmc
    require(record["decisions"] == [], "baseline records hidden learned decisions")
    ledger = RecordedLedger(record)
    ledger.observe([.5, .5])
    stop = "optimizer_end"
    try:
        if record["method"] == "coordinate_search":
            cycle = 0
            while True:
                center = np.asarray(record["measurements"][ledger.best()]["theta"])
                scale = [.2, .1, .05, .025][min(cycle, 3)]
                for axis, sign in itertools.product(range(2), (-1, 1)):
                    point = center.copy()
                    point[axis] = np.clip(point[axis] + sign * scale, 0., 1.)
                    ledger.observe(point)
                cycle += 1
        elif record["method"] == "space_filling":
            sampler = qmc.Halton(2, scramble=False)
            sampler.fast_forward(1)
            while True:
                ledger.observe(sampler.random(1)[0])
        elif record["method"] == "simplex":
            def objective(theta):
                return record["measurements"][ledger.observe(theta)]["cost"]
            minimize(objective, np.asarray([.5, .5]), method="Nelder-Mead", bounds=[(0., 1.)] * 2,
                     options={"initial_simplex": np.asarray([[.5, .5], [.7, .5], [.5, .7]]),
                              "maxiter": 4 * record["budget"], "maxfev": 4 * record["budget"],
                              "xatol": 0., "fatol": 0.})
        else:
            raise ValueError("unknown frozen baseline")
    except StopIteration as exc:
        stop = str(exc)
    require(record["stop"] == stop, "baseline stop differs")
    ledger.finish()


def _archive(root, arrays, report):
    """Bind original-machine numeric evidence to current immutable artifacts."""
    manifest = audit46.load(root / ARRAY_MANIFEST)
    require(manifest["schema_version"] == 1 and manifest["archive"] == ARRAYS,
            "original numeric archive identity differs")
    require(manifest["archive_sha256"] == audit46.digest(root / ARRAYS) == ARRAY_SHA256,
            "original numeric archive changed")
    require(manifest["additional_objective_evaluations"] == 0 and manifest["gradient_steps"] == 0
            and manifest["original_48_passed_before_capture"] is True
            and manifest["original_logits_bits_unchanged"] is True, "numeric archive capture scope differs")
    require(manifest["source_script_sha256"] == audit46.digest(root / "scripts/53_archive_original_calibration.py", text=True),
            "numeric archive producer source differs")
    expected_inputs = {"research/results/nonpid_transfer/report.json": audit46.digest(root / "research/results/nonpid_transfer/report.json", text=True),
                       "research/results/nonpid_transfer/raw.json.gz": report["raw_sha256"],
                       **{"research/results/nonpid_transfer/" + name: value for name, value in report["artifacts"].items()}}
    require(manifest["input_hashes"] == expected_inputs, "numeric archive input binding differs")
    archive = np.load(root / ARRAYS, allow_pickle=False)
    require(set(archive.files) == set(manifest["arrays"]), "numeric archive array roster differs")
    for name, spec in manifest["arrays"].items():
        value = archive[name]
        require(spec == {"shape": list(value.shape), "dtype": str(value.dtype),
                         "sha256": hashlib.sha256(value.tobytes()).hexdigest()},
                "numeric archive array bits differ: " + name)
    for seed in (101, 202, 303):
        for split in ("temperature", "conformal", "test"):
            prefix = f"seed_{seed}_{split}"
            for name, expected in zip(("features", "labels"), arrays[split]):
                actual = archive[f"{prefix}_{name}"]
                require(actual.shape == expected.shape and np.array_equal(actual, expected),
                        "numeric archive split evidence differs: " + prefix + "_" + name)
    return archive, manifest


def verify_calibration(seed, artifact, calibration, arrays, archive, api, *, golden_traces=None):
    """Certify original logits/probabilities; keep exact recorded CP ranks/sets."""
    certificates, probabilities, intervals = [], {}, {}
    for split in ("temperature", "conformal", "test"):
        prefix = f"seed_{seed}_{split}"
        logits, p = archive[prefix + "_logits"], archive[prefix + "_probabilities"]
        require(logits.shape == p.shape == (len(arrays[split][0]), 2, 5)
                and np.isfinite(logits).all(), "original numeric archive shape/finiteness differs")
        intervals[split] = []
        for index, (features, observed_logits, observed_p) in enumerate(zip(arrays[split][0], logits, p)):
            try:
                forward = api.audit_forward(artifact, features, recorded_logits=observed_logits)
                softmax = api.audit_softmax(observed_logits, calibration["temperatures"],
                                           recorded_probabilities=observed_p,
                                           logit_intervals=forward["logit_intervals"])
            except ValueError as exc:
                raise ValueError(f"seed={seed} split={split} state={index}: {exc}") from exc
            intervals[split].append(softmax["probability_intervals"])
        probabilities[split] = p
    temperature_logits = archive[f"seed_{seed}_temperature_logits"]
    for axis in range(2):
        certificates.append(api.audit_temperature(temperature_logits[:, axis], arrays["temperature"][1][:, axis],
                                                   calibration["temperatures"][axis],
                                                   golden_trace=None if golden_traces is None else golden_traces[axis]))
    require(calibration["alpha"] == .1 and calibration["n_temperature"] == 128
            and calibration["n_calibration"] == 256 and calibration["quantile_rank"] == 232
            and calibration["mode"] == "monitor", "CP boundary/mode differs")
    qhat = audit46.independent_conformal(probabilities["conformal"], arrays["conformal"][1])
    close(calibration["qhat_per_axis"], qhat, "exact recorded finite-sample split CP rank", atol=0, rtol=0)
    cp = api.audit_cp(probabilities["conformal"], arrays["conformal"][1], qhat, alpha=.1,
                      probability_intervals=intervals["conformal"])
    diagnostics = audit46.conformal_diagnostics(probabilities["test"], arrays["test"][1], qhat)
    return {"seed": seed, "temperature_certificates": certificates, "cp_certificate": cp}, {
        "seed": seed, "n": diagnostics["n_states"], "coverage_per_axis": diagnostics["coverage_per_axis"],
        "mean_set_size_per_axis": diagnostics["mean_set_size_per_axis"]}


def _recorded_context(root, benchmark):
    """Rebuild 48's immutable input context without its current-CPU inference."""
    primary = root / benchmark["primary_study_directory"]
    require(primary.resolve().is_relative_to(root), "primary study escapes repository")
    report = audit46.load(primary / "report.json")
    runner = module(root / "scripts/45_nonpid_transfer.py", "_recorded_recalibration_manifest_runner")
    protocol = runner.protocol(root)
    require(report["study_id"] == protocol["study_id"] and report["schema_version"] == 1,
            "primary report identity differs")
    audit46._source_manifest(root, report["source_hashes"], runner.SOURCES)
    names = {f"{kind}_{seed}.json" for kind in ("model", "calibration") for seed in (101, 202, 303)}
    require(set(report["artifacts"]) == names, "six frozen primary artifacts required")
    hashes = {str((primary / name).relative_to(root).as_posix()):
              audit46.digest(primary / name, text=Path(name).suffix in audit46.TEXT_SUFFIXES)
              for name in ("report.json", "raw.json.gz", *sorted(names))}
    require(audit46.digest(primary / "raw.json.gz") == report["raw_sha256"], "primary raw evidence changed")
    for name in names:
        require(audit46.digest(primary / name, text=True) == report["artifacts"][name],
                "primary artifact changed: " + name)
    with gzip.open(primary / "raw.json.gz", "rt", encoding="utf-8") as stream:
        raw = json.load(stream)
    arrays = {}
    for name in ("temperature", "conformal", "test"):
        objects, split = raw["teacher"][name], protocol["splits"][name]
        require(len(objects) == split["n"] and [o["task"] for o in objects] == list(range(split["n"])),
                "primary split roster differs: " + name)
        require(all(o["split_seed"] == split["seed"] and len(o["states"]) == 1 for o in objects),
                "primary initial-state identities differ: " + name)
        arrays[name] = (np.asarray([o["states"][0]["features"] for o in objects]),
                        np.asarray([o["states"][0]["labels"] for o in objects], dtype=np.int64))
    models = {seed: audit46.load(primary / f"model_{seed}.json") for seed in (101, 202, 303)}
    for seed, artifact in models.items():
        require(artifact["seed"] == seed and artifact["inference_shape"] == [1, 16], "model mapping differs")
    archive, manifest = _archive(root, arrays, report)
    return {"arrays": arrays, "models": models, "input_hashes": hashes,
            "archive": archive, "archive_manifest": manifest}


def _small_archive(root, benchmark, context):
    manifest = audit46.load(root / SMALL_MANIFEST)
    require(manifest["schema_version"] == 1 and manifest["archive"] == SMALL_ARRAYS,
            "supplement numeric archive identity differs")
    require(SMALL_SHA256 is not None and manifest["archive_sha256"]
            == audit46.digest(root / SMALL_ARRAYS) == SMALL_SHA256,
            "supplement original numeric archive changed")
    require(manifest["primary_archive_sha256"] == ARRAY_SHA256,
            "supplement original-logit archive differs")
    require(manifest["benchmark_sha256"] == audit46.digest(root / "research/results/recalibration_benchmark.json", text=True),
            "supplement benchmark binding differs")
    require(manifest["input_hashes"] == context["input_hashes"], "supplement input bindings differ")
    require(manifest["additional_objective_evaluations"] == 0 and manifest["gradient_steps"] == 0,
            "supplement capture accounting differs")
    producer = (root / "scripts/55_archive_supplemental_arrays.py").resolve()
    require(producer.is_relative_to(root) and manifest["source_script_sha256"] == audit46.digest(producer, text=True),
            "supplement producer source differs")
    archive = np.load(root / SMALL_ARRAYS, allow_pickle=False)
    names = {f"seed_{seed}_n{n}_test_probabilities" for seed in (101, 202, 303) for n in (16, 32, 64)}
    require(set(archive.files) == set(manifest["arrays"]) == names, "supplement numeric array roster differs")
    for name in names:
        value = archive[name]
        require(value.shape == (256, 2, 5) and value.dtype == np.dtype("float64"),
                "supplement probability shape/dtype differs")
        require(manifest["arrays"][name] == {"shape": list(value.shape), "dtype": str(value.dtype),
                                             "sha256": hashlib.sha256(value.tobytes()).hexdigest()},
                "supplement probability bits differ: " + name)
    return archive, manifest


def verify_recalibration_row(row, logits, labels, cp_probabilities, test_probabilities, api,
                             *, model_sha256, scope, forward_intervals=None, golden_traces=None):
    """Audit a saved fit without refitting T or replacing observed clock samples."""
    benchmark = module(ROOT / "scripts/48_recalibration_benchmark.py", "_recorded_recalibration_formulas")
    n = row["n_per_split"]
    calibration = row["calibration"]
    require(set(calibration) == {"temperatures", "qhat_per_axis", "alpha", "n_temperature", "n_calibration",
                                 "quantile_rank", "mode", "model_sha256", "scope"},
            "supplement calibration fields differ")
    require(calibration["n_temperature"] == calibration["n_calibration"] == n
            and calibration["quantile_rank"] == int(np.ceil((n + 1) * .9))
            and calibration["alpha"] == .1 and calibration["mode"] == "monitor"
            and calibration["model_sha256"] == model_sha256 and calibration["scope"] == scope,
            "supplement calibration scope/identity differs")
    require(row["total_label_states"] == 2 * n, "independent label-state total differs")
    require(row["warmup_fits"] == benchmark.WARMUPS and row["recorded_repetitions"] == benchmark.REPETITIONS,
            "recorded fit schedule differs")
    stats = benchmark.timing_statistics(row["timing_samples_ms"], expected_repetitions=benchmark.REPETITIONS)
    require(row["timing_statistics_ms"] == stats, "observed timing statistics differ")
    certificates = [api.audit_temperature(logits["temperature"][:n, axis], labels["temperature"][:n, axis],
                                           calibration["temperatures"][axis],
                                           golden_trace=None if golden_traces is None else golden_traces[axis]) for axis in range(2)]
    cp_intervals = []
    for split, probabilities in (("conformal", cp_probabilities), ("test", test_probabilities)):
        count = n if split == "conformal" else 256
        require(np.asarray(probabilities).shape == (count, 2, 5), "supplement recorded probability shape differs")
        for index, observed in enumerate(probabilities):
            softmax = api.audit_softmax(logits[split][index], calibration["temperatures"],
                                        recorded_probabilities=observed,
                                        logit_intervals=None if forward_intervals is None else forward_intervals[split][index])
            if split == "conformal":
                cp_intervals.append(softmax["probability_intervals"])
    qhat = audit46.independent_conformal(cp_probabilities, labels["conformal"][:n])
    close(calibration["qhat_per_axis"], qhat, "exact supplemental recorded CP rank", atol=0, rtol=0)
    cp = api.audit_cp(cp_probabilities, labels["conformal"][:n], qhat, alpha=.1,
                      probability_intervals=cp_intervals)
    treeclose(row["test_diagnostics"], audit46.conformal_diagnostics(test_probabilities, labels["test"], qhat),
              "supplement exact recorded-test diagnostics")
    return {"model_seed": row["model_seed"], "n_per_split": n,
            "temperature_certificates": certificates, "cp_certificate": cp}


def _verify_recalibration(root, *, check_document=True):
    """Independent supplemental audit; zero filters and no strict-refit claim."""
    root = Path(root).resolve()
    execution = execution_sources(root)
    benchmark = module(root / "scripts/48_recalibration_benchmark.py", "_recorded_recalibration_metadata")
    protocol, report = benchmark.protocol(root), benchmark.read(root / benchmark.RESULT)
    require(report["schema_version"] == 1 and report["study_id"] == protocol["study_id"]
            and report["protocol"] == benchmark.PROTOCOL, "benchmark report identity differs")
    require(set(report["source_hashes"]) == set(benchmark.SOURCES), "benchmark source manifest incomplete")
    benchmark.verify_hashes(root, report["source_hashes"])
    context = _recorded_context(root, report)
    require(report["input_hashes"] == context["input_hashes"], "benchmark frozen inputs differ")
    expected = {f"{report['primary_study_directory']}/model_{seed}.json":
                benchmark.digest(root / report["primary_study_directory"] / f"model_{seed}.json")
                for seed in benchmark.SEEDS}
    require(report["model_hashes_before"] == report["model_hashes_after"] == expected,
            "frozen model before/after hashes differ")
    require(report["additional_objective_evaluations"] == report["gradient_steps"] == 0
            and report["selection_performed"] is False and report["primary_calibration_modified"] is False
            and report["test_diagnostics_independent_states"] == 256, "recalibration scope/accounting changed")
    require(np.isfinite(report["overall_wall_seconds"]) and report["overall_wall_seconds"] >= 0,
            "invalid observed overall clock")
    require([(row["model_seed"], row["n_per_split"]) for row in report["rows"]]
            == [(seed, n) for seed in benchmark.SEEDS for n in benchmark.SIZES],
            "fixed descriptive row roster differs")
    small, manifest = _small_archive(root, report, context)
    api, certificates = numeric_api(root), []
    for seed in benchmark.SEEDS:
        artifact = context["models"][seed]
        logits = {split: context["archive"][f"seed_{seed}_{split}_logits"]
                  for split in ("temperature", "conformal", "test")}
        intervals = {}
        for split in logits:
            intervals[split] = [api.audit_forward(artifact, features, recorded_logits=recorded)["logit_intervals"]
                                for features, recorded in zip(context["arrays"][split][0], logits[split])]
        labels = {split: context["arrays"][split][1] for split in logits}
        scope = audit46.load(root / report["primary_study_directory"] / f"calibration_{seed}.json")["scope"]
        for row in (r for r in report["rows"] if r["model_seed"] == seed):
            n = row["n_per_split"]
            cp = context["archive"][f"seed_{seed}_n{n}_cp{n}_probabilities_recorded_t"]
            test = small[f"seed_{seed}_n{n}_test_probabilities"]
            certificates.append(verify_recalibration_row(row, logits, labels, cp, test, api,
                                model_sha256=hashlib.sha256(audit46.canonical(artifact)).hexdigest(),
                                scope=scope, forward_intervals=intervals,
                                golden_traces=observed_golden_traces(root, seed, n, row["calibration"]["temperatures"])))
    if check_document:
        require((root / benchmark.DOC).read_text(encoding="utf-8") == benchmark.render(report),
                "generated bilingual recalibration document differs")
    audit46._source_manifest(root, execution["source_hashes"], execution["source_hashes"])
    return {"ok": True, "audit_type": "original_recorded_recalibration_evidence", "strict_cpu_replay_proven": False,
            "rows": len(certificates), "numeric_certificates": certificates,
            "numeric_certification_assumptions": api.ASSUMPTIONS,
            "original_supplement_manifest": manifest, "additional_objective_evaluations": 0,
            "gradient_steps": 0, "recorded_timings_preserved": True, "verification_scope": SCOPE,
            "audit_execution": execution}


def check_recalibration(root=ROOT, *, check_document=True, receipt_root=None):
    root = Path(root).resolve()
    directory = Path(receipt_root).resolve() if receipt_root else root / ".local-audit/recorded_recalibration_verification"
    directory.mkdir(parents=True, exist_ok=True)
    receipt = directory / (uuid.uuid4().hex + ".json")
    base = {"started_utc": datetime.now(timezone.utc).isoformat(), "verification_scope": SCOPE,
            "additional_objective_evaluations": 0, "gradient_steps": 0}
    try:
        result = _verify_recalibration(root, check_document=check_document)
    except Exception as exc:
        receipt.write_text(json.dumps({**base, "finished_utc": datetime.now(timezone.utc).isoformat(),
                                      "status": "failed", "error": f"{type(exc).__name__}: {exc}"},
                                     indent=2, allow_nan=False) + "\n", encoding="utf-8")
        raise ValueError(f"{exc}; additional_objective_evaluations=0; receipt={receipt}") from exc
    result.update({**base, "finished_utc": datetime.now(timezone.utc).isoformat(), "status": "passed"})
    receipt.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    result["receipt_path"] = str(receipt)
    return result


def _verify(root, output, audit, *, check_document=True):
    """Reconstruct all frozen 46 assertions, with explicit numeric-audit scope."""
    execution = execution_sources(root)
    p, report = audit46.load(root / audit46.PROTOCOL), audit46.load(output / "report.json")
    require(audit46.digest(root / audit46.PROTOCOL, text=True) == audit46.PROTOCOL_SHA256,
            "frozen protocol changed")
    runner = module(root / "scripts/45_nonpid_transfer.py", "_recorded_transfer_runner_manifest")
    audit46._source_manifest(root, report["source_hashes"], runner.SOURCES)
    revision = report.get("git_revision", "")
    require(isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision), "invalid recorded Git revision")
    present = subprocess.run(["git", "cat-file", "-e", revision + "^{commit}"], cwd=root, capture_output=True)
    if present.returncode:
        fetched = subprocess.run(["git", "fetch", "--no-tags", "--depth=1", "origin", revision], cwd=root, capture_output=True)
        require(fetched.returncode == 0, "recorded source commit unavailable; fetch that revision to verify provenance")
    for name, expected in report["source_hashes"].items():
        committed = subprocess.check_output(["git", "show", revision + ":" + name], cwd=root)
        if Path(name).suffix in audit46.TEXT_SUFFIXES:
            committed = committed.replace(b"\r\n", b"\n")
        require(hashlib.sha256(committed).hexdigest() == expected,
                "recorded commit differs from execution manifest: " + name)
    audit46._source_manifest(root, audit46.REUSED_SOURCES, audit46.REUSED_SOURCES)
    require(report["schema_version"] == 1 and report["study_id"] == p["study_id"], "report identity differs")
    require(report["protocol"] == audit46.PROTOCOL, "report protocol path differs")
    require(audit46.digest(output / "raw.json.gz") == report["raw_sha256"], "raw bytes changed")
    names = {f"{kind}_{seed}.json" for kind in ("model", "calibration") for seed in p["training"]["seeds"]}
    require(set(report["artifacts"]) == names, "trained/calibrated artifact roster differs")
    for name in names:
        require(audit46.digest(output / name, text=True) == report["artifacts"][name], "artifact changed: " + name)
    with gzip.open(output / "raw.json.gz", "rt", encoding="utf-8") as stream:
        raw = json.load(stream)
    require(raw["schema_version"] == 1 and set(raw["teacher"]) == set(p["splits"]), "raw split roster differs")
    require(len({split["seed"] for split in p["splits"].values()}) == 4, "split identities overlap")
    arrays = {}
    for name, split in p["splits"].items():
        objects = raw["teacher"][name]
        require([obj["task"] for obj in objects] == list(range(split["n"])), "incomplete split: " + name)
        require(all(obj["split_seed"] == split["seed"] for obj in objects), "teacher split identity differs")
        for record in objects:
            clean, noisy = audit46.signals(split["seed"], record["task"])
            audit46.verify_ledger(record, clean, noisy, audit)
            audit46.verify_teacher(record, split["teacher_stages"])
        arrays[name] = (np.asarray([s["features"] for obj in objects for s in obj["states"]]),
                        np.asarray([s["labels"] for obj in objects for s in obj["states"]], dtype=np.int64))
    archive, archive_manifest = _archive(root, arrays, report)
    x = arrays["train"][0]
    mean, scale = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-8)
    artifacts, calibrations, cp_diagnostics, numeric_certificates = {}, {}, [], []
    api = numeric_api(root)
    for seed in p["training"]["seeds"]:
        artifact = audit46.load(output / f"model_{seed}.json")
        calibration = audit46.load(output / f"calibration_{seed}.json")
        require(artifact["seed"] == calibration["seed"] == seed, "model/calibration seed differs")
        require(artifact["architecture"] == [16, 32, 32, 10] and artifact["dtype"] == "float64"
                and artifact["inference_shape"] == [1, 16], "checkpoint architecture/mapping differs")
        close(artifact["normalization_mean"], mean, "train-only normalization mean")
        close(artifact["normalization_scale"], scale, "train-only normalization scale")
        require(calibration["model_sha256"] == hashlib.sha256(audit46.canonical(artifact)).hexdigest(),
                "calibration frozen model binding differs")
        numeric, cp = verify_calibration(seed, artifact, calibration, arrays, archive, api,
            golden_traces=observed_golden_traces(root, seed, 128, calibration["temperatures"]))
        numeric_certificates.append(numeric)
        cp_diagnostics.append(cp)
        artifacts[seed], calibrations[seed] = artifact, calibration
    treeclose(report["cp_diagnostics"], cp_diagnostics, "independent original initial-state CP diagnostics")
    expected_runs = [(budget, method, index) for budget in p["operating"]["budgets"]
                     for method in p["operating"]["methods"] for index in range(p["splits"]["test"]["n"])]
    require([(r["budget"], r["method"], r["task"]) for r in raw["operating"]] == expected_runs,
            "operating roster/order differs")
    typed_jobs = []
    for record in raw["operating"]:
        clean, noisy = audit46.signals(p["splits"]["test"]["seed"], record["task"])
        audit46.verify_ledger(record, clean, noisy, audit, budget=record["budget"])
        rows = record["measurements"]
        best = min(range(len(rows)), key=lambda i: rows[i]["cost"])
        require(type(record["returned"]) is int and record["returned"] == best,
                "returned point is not measured best")
        require(rows[best]["cost"] <= rows[0]["cost"], "return regresses from measured start")
        if record["method"].startswith("typed_seed_"):
            seed = int(record["method"].rsplit("_", 1)[1])
            typed_jobs.append((record, artifacts[seed], calibrations[seed]))
        else:
            verify_baseline(record)
    # Every independent filter remains in this parent and has already been
    # charged, even if one or more numerical certificates below fail.
    decisions, parallel_audit = verify_operating_parallel(typed_jobs, root=root, max_workers=4)
    rows, accounting, acceptance = audit46.statistics(raw, p)
    treeclose(report["rows"], rows, "independent operating statistics")
    treeclose(report["acceptance"], acceptance, "frozen independent acceptance")
    treeclose({k: v for k, v in report["accounting"].items() if k != "optimizer_fit"},
              accounting, "independent objective accounting")
    require(accounting["actual_objective_evaluations"] <= 83840, "prospective acquisition cap exceeded")
    phase_caps = {"train": 24832, "temperature": 3200, "conformal": 6400, "test": 6400, "operating": 43008}
    require(all(accounting["by_phase"][name] <= maximum for name, maximum in phase_caps.items()), "phase cap exceeded")
    fits = report["accounting"]["optimizer_fit"]
    require([fit["seed"] for fit in fits] == p["training"]["seeds"], "optimizer seed roster differs")
    for fit in fits:
        require(fit["examples"] == 1024 and fit["epochs"] == 100 and fit["optimizer_steps"] == 800,
                "final fixed-epoch training schedule differs")
        require(len(fit["epoch_losses"]) == 100 and np.isfinite(fit["epoch_losses"]).all(), "training loss trace incomplete")
        close(fit["first_epoch_loss"], fit["epoch_losses"][0], "first epoch loss")
        close(fit["last_epoch_loss"], fit["epoch_losses"][-1], "last epoch loss")
        require(fit["cpu_seconds"] >= 0 and fit["wall_seconds"] >= 0, "invalid measured fit time")
    if "amortization" in report:
        treeclose(report["amortization"], audit46.amortization(rows, accounting), "cost-versus-task-count")
    if check_document:
        require((root / audit46.DOC).read_text(encoding="utf-8") == audit46.render(report), "generated bilingual report differs")
    require(audit.evaluations == accounting["actual_objective_evaluations"],
            "audit replay count differs from recorded candidates")
    audit46._source_manifest(root, execution["source_hashes"], execution["source_hashes"])
    return {"ok": True, "audit_type": "original_recorded_evidence", "strict_cpu_replay_proven": False,
            "acceptance": acceptance, "raw_sha256": report["raw_sha256"], "accounting": report["accounting"],
            "additional_verification_objective_evaluations": audit.evaluations,
            "certified_operating_decisions": decisions, "numeric_certificates": numeric_certificates,
            "operating_parallel_audit": parallel_audit,
            "numeric_certification_assumptions": api.ASSUMPTIONS,
            "original_numeric_manifest": archive_manifest, "verification_scope": SCOPE,
            "audit_execution": execution}


def check(root=ROOT, output=None, *, receipt_root=None, check_document=True):
    root = Path(root).resolve()
    output = Path(output).resolve() if output else root / "research/results/nonpid_transfer"
    audit, started = audit46.AuditCompute(), datetime.now(timezone.utc).isoformat()
    receipt_dir = Path(receipt_root).resolve() if receipt_root else root / RECEIPTS
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = receipt_dir / (uuid.uuid4().hex + ".json")
    raw_hash = audit46.digest(output / "raw.json.gz") if (output / "raw.json.gz").exists() else None
    sources = ["scripts/52_verify_recorded_transfer.py", "scripts/46_verify_nonpid_transfer.py",
               "scripts/calibration_numeric_audit.py", "tests/test_recorded_transfer.py"]
    provenance = {name: audit46.digest(root / name, text=True) for name in sources if (root / name).exists()}
    base = {"schema_version": 1, "study_id": "nonpid_denoise_transfer_v0100", "started_utc": started,
            "raw_sha256": raw_hash, "verification_scope": SCOPE, "audit_source_hashes": provenance}
    try:
        result = _verify(root, output, audit, check_document=check_document)
    except Exception as exc:
        failure = {**base, "finished_utc": datetime.now(timezone.utc).isoformat(), "status": "failed",
                   "error": f"{type(exc).__name__}: {exc}",
                   "additional_verification_objective_evaluations": audit.evaluations}
        if hasattr(exc, "operating_parallel_audit"):
            failure["operating_parallel_audit"] = exc.operating_parallel_audit
        receipt.write_text(json.dumps(failure, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        raise ValueError(f"{exc}; additional_verification_objective_evaluations={audit.evaluations}; receipt={receipt}") from exc
    result.update({**base, "finished_utc": datetime.now(timezone.utc).isoformat(), "status": "passed"})
    receipt.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    result["receipt_path"] = str(receipt)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--check-recalibration", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--receipt-root", type=Path)
    args = parser.parse_args()
    try:
        result = (check_recalibration(args.root, receipt_root=args.receipt_root) if args.check_recalibration else
                  check(args.root, args.output_root, receipt_root=args.receipt_root))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
