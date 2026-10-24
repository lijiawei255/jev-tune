"""Frozen non-PID transfer: acquisition, training and measured budget loops."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import itertools
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
from scipy.optimize import minimize
from scipy.stats import qmc
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from examples.denoise_transfer.task import DenoiseTask
from jev_tune.decode import ConformalPolicy, decide
from jev_tune.calibration import fit_frozen_calibration
from jev_tune.primitives import (Answer, Choice, Noul, Option,
    calibrate_temperature, fit_split_conformal, softmax)

PROTOCOL = "research/protocols/nonpid_transfer_v0100.json"
PROTOCOL_SHA256 = "cdaa0d5028f8c5789a2aa6b25a1a9b9569c807d16ba8c188372d6ad25448a2c5"
SOURCES = [PROTOCOL, "scripts/45_nonpid_transfer.py", "examples/denoise_transfer/task.py",
           "src/jev_tune/primitives.py", "src/jev_tune/decode.py", "src/jev_tune/calibration.py",
           "scripts/46_verify_nonpid_transfer.py", "tests/test_nonpid_transfer.py",
           "tests/test_frozen_calibration.py", "tests/test_shell_contract.py"]
DELTAS = np.array([-.2, -.05, 0., .05, .2])
START = np.array([.5, .5])
DEFAULT_OUTPUT = ROOT / "research/results/nonpid_transfer"


def digest(path):
    data = Path(path).read_bytes()
    if Path(path).suffix in {".py", ".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def protocol(root=ROOT):
    assert digest(Path(root) / PROTOCOL) == PROTOCOL_SHA256, "Frozen protocol changed"
    return json.loads((Path(root) / PROTOCOL).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


class StopBudget(Exception):
    """No objective execution took place for the rejected request."""


class Ledger:
    """One object and one arm own their observations; no global cache."""

    def __init__(self, task, budget=None, proposal_cap=None):
        self.task, self.budget, self.proposal_cap = task, budget, proposal_cap
        self.measurements, self.requests, self.cache = [], [], {}

    def observe(self, theta):
        theta = np.asarray(theta, dtype=np.float64)
        if theta.shape != (2,) or not np.isfinite(theta).all() or ((theta < 0) | (theta > 1)).any():
            raise ValueError("theta must have two finite normalized parameters")
        if self.proposal_cap is not None and len(self.requests) >= self.proposal_cap:
            raise StopBudget("proposal_cap")
        key = tuple(float(x) for x in theta)
        if key in self.cache:
            idx = self.cache[key]
            self.requests.append({"theta": theta.tolist(), "measurement": idx, "cached": True})
            return idx
        if self.budget is not None and len(self.measurements) >= self.budget:
            raise StopBudget("budget")
        idx = len(self.measurements)
        row = {"theta": theta.tolist()}
        self.measurements.append(row)  # failed attempts are charged, then abort
        try:
            row.update(self.task.evaluate(theta))
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            exc.nonpid_ledger = self.export()
            raise
        self.cache[key] = idx
        self.requests.append({"theta": theta.tolist(), "measurement": idx, "cached": False})
        return idx

    def best(self):
        return min(range(len(self.measurements)), key=lambda i: self.measurements[i]["cost"])

    def export(self):
        return {"measurements": self.measurements, "requests": self.requests}


def observation(ledger, index, previous_cost=None):
    row = ledger.measurements[index]
    features = list(row["features"])
    features[3] = 0. if previous_cost is None else float(np.log1p(row["cost"]) - np.log1p(previous_cost))
    return features


def teacher_object(seed, index, stages):
    ledger = Ledger(DenoiseTask(seed, index))
    try:
        return _teacher_with_ledger(ledger, seed, index, stages)
    except Exception as exc:
        exc.nonpid_ledger = ledger.export()
        raise


def _teacher_with_ledger(ledger, seed, index, stages):
    current, previous = ledger.observe(START), None
    states = []
    pairs = list(itertools.product(range(5), repeat=2))
    for _ in range(stages):
        theta = np.asarray(ledger.measurements[current]["theta"])
        candidates = [ledger.observe(np.clip(theta + DELTAS[list(pair)], 0., 1.)) for pair in pairs]
        winner = min(range(25), key=lambda j: (ledger.measurements[candidates[j]]["cost"],
                     float(np.sum(DELTAS[list(pairs[j])] ** 2)), pairs[j]))
        states.append({"measurement": current, "features": observation(ledger, current, previous),
                       "candidate_measurements": candidates, "labels": list(pairs[winner]),
                       "selected": candidates[winner]})
        previous = ledger.measurements[current]["cost"]
        current = candidates[winner]
    return {"task": index, "split_seed": seed, "states": states, **ledger.export()}


def collect(split, target=None):
    target = [] if target is None else target
    for index in range(split["n"]):
        try:
            target.append(teacher_object(split["seed"], index, split["teacher_stages"]))
        except Exception as exc:
            if hasattr(exc, "nonpid_ledger"):
                target.append({"task": index, "split_seed": split["seed"], "failed": True, **exc.nonpid_ledger})
            raise
    return target


def training_arrays(objects):
    states = [s for obj in objects for s in obj["states"]]
    return np.asarray([s["features"] for s in states]), np.asarray([s["labels"] for s in states], dtype=np.int64)


class TransferHead(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(16, 32), nn.Tanh(), nn.Linear(32, 32),
                                 nn.Tanh(), nn.Linear(32, 10))
        self.double()

    def forward(self, x):
        return self.net(x).reshape(-1, 2, 5)


def train_model(x, y, seed, settings):
    torch.manual_seed(seed)
    model = TransferHead()
    mean, scale = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-8)
    tx, ty = torch.from_numpy((x - mean) / scale), torch.from_numpy(y)
    optimizer = torch.optim.Adam(model.parameters(), lr=settings["learning_rate"])
    rng = np.random.default_rng(seed)
    steps, losses = 0, []
    wall, cpu = time.perf_counter(), time.process_time()
    for _ in range(settings["epochs"]):
        order = rng.permutation(len(x))
        total = 0.
        for start in range(0, len(x), settings["batch_size"]):
            idx = order[start:start + settings["batch_size"]]
            optimizer.zero_grad()
            loss = nn.functional.cross_entropy(model(tx[idx]).reshape(-1, 5), ty[idx].reshape(-1))
            loss.backward()
            optimizer.step()
            total += loss.item() * len(idx)
            steps += 1
        losses.append(total / len(x))
    model.eval()
    artifact = {"seed": seed, "normalization_mean": mean.tolist(), "normalization_scale": scale.tolist(),
                "state_dict": {k: v.detach().numpy().tolist() for k, v in model.state_dict().items()},
                "architecture": [16, 32, 32, 10], "dtype": "float64", "inference_shape": [1, 16]}
    fit = {"seed": seed, "examples": len(x), "epochs": settings["epochs"], "optimizer_steps": steps,
           "first_epoch_loss": losses[0], "last_epoch_loss": losses[-1], "epoch_losses": losses,
           "wall_seconds": time.perf_counter() - wall, "cpu_seconds": time.process_time() - cpu}
    return artifact, fit


def load_model(artifact):
    model = TransferHead()
    model.load_state_dict({k: torch.tensor(v, dtype=torch.float64) for k, v in artifact["state_dict"].items()})
    model.eval()
    return model


def infer_logits(model, artifact, features):
    # Canonical one-object mapping for calibration, diagnosis and all rollouts.
    x = (np.asarray(features) - artifact["normalization_mean"]) / artifact["normalization_scale"]
    if x.shape != (16,) or not np.isfinite(x).all():
        raise ValueError("finite 16-feature observation required")
    with torch.no_grad():
        return model(torch.from_numpy(x.reshape(1, 16)))[0].numpy()


def predict(model, artifact, features, calibration):
    return softmax(infer_logits(model, artifact, features), temperature=np.asarray(calibration["temperatures"])[:, None])


def action(probabilities, calibration):
    answer = Answer(choice=[Choice(name, [Option(str(d), float(d)) for d in DELTAS], probabilities[a])
                            for a, name in enumerate(("winsor_threshold", "lowpass_cutoff"))],
                    noul=Noul("finite observation", 1.))
    return decide(answer, max_step=.2, shrinkage=1., abstain=None,
                  conformal=ConformalPolicy(tuple(calibration["qhat_per_axis"]), mode="monitor"))


def fit_calibration(model, artifact, temperature_objects, conformal_objects):
    tx, ty = training_arrays(temperature_objects)
    cx, cy = training_arrays(conformal_objects)
    tl = np.stack([infer_logits(model, artifact, x) for x in tx])
    cl = np.stack([infer_logits(model, artifact, x) for x in cx])
    identity = hashlib.sha256(json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    fitted = fit_frozen_calibration(tl, ty, cl, cy,
        temperature_ids=[f"{o['split_seed']}:{o['task']}" for o in temperature_objects],
        conformal_ids=[f"{o['split_seed']}:{o['task']}" for o in conformal_objects], model_sha256=identity)
    return {"seed": artifact["seed"], **fitted}


def rollout(seed, task_index, method, budget, *, artifact=None, calibration=None):
    ledger = Ledger(DenoiseTask(seed, task_index), budget, 4 * budget)
    try:
        return _rollout_with_ledger(ledger, task_index, method, budget, artifact=artifact, calibration=calibration)
    except Exception as exc:
        exc.nonpid_ledger = ledger.export()
        raise


def _rollout_with_ledger(ledger, task_index, method, budget, *, artifact=None, calibration=None):
    current = ledger.observe(START)
    previous, decisions, stop = None, [], "budget"
    model = load_model(artifact) if artifact is not None else None
    try:
        if method.startswith("typed_seed_"):
            while True:
                features = observation(ledger, current, previous)
                probabilities = predict(model, artifact, features, calibration)
                decision = action(probabilities, calibration)
                theta = np.clip(np.asarray(ledger.measurements[current]["theta"]) + decision.step, 0., 1.)
                new_index = ledger.observe(theta)
                decisions.append({"current": current, "features": features, "probabilities": probabilities.tolist(),
                                  "sets": [np.asarray(s, dtype=bool).tolist() for s in decision.conformal_set],
                                  "step": decision.step.tolist(), "next_theta": theta.tolist(), "measurement": new_index})
                if np.array_equal(theta, ledger.measurements[current]["theta"]):
                    stop = "no_action"
                    break
                previous = ledger.measurements[current]["cost"]
                current = new_index
        elif method == "space_filling":
            sampler = qmc.Halton(2, scramble=False)
            sampler.fast_forward(1)
            while True:
                ledger.observe(sampler.random(1)[0])
        elif method == "coordinate_search":
            cycle = 0
            while True:
                center = np.asarray(ledger.measurements[ledger.best()]["theta"])
                step = [.2, .1, .05, .025][min(cycle, 3)]
                for axis, sign in itertools.product(range(2), (-1, 1)):
                    point = center.copy()
                    point[axis] = np.clip(point[axis] + sign * step, 0., 1.)
                    ledger.observe(point)
                cycle += 1
        elif method == "simplex":
            def objective(theta):
                return ledger.measurements[ledger.observe(theta)]["cost"]
            minimize(objective, START.copy(), method="Nelder-Mead", bounds=[(0., 1.)] * 2,
                     options={"initial_simplex": np.array([[.5, .5], [.7, .5], [.5, .7]]),
                              "maxiter": 4 * budget, "maxfev": 4 * budget, "xatol": 0., "fatol": 0.})
            stop = "optimizer_end"
        else:
            raise ValueError("Unknown frozen method")
    except StopBudget as exc:
        stop = str(exc)
    except Exception as exc:
        exc.nonpid_ledger = ledger.export()
        raise
    return {"task": task_index, "method": method, "budget": budget, "returned": ledger.best(),
            "stop": stop, "decisions": decisions, **ledger.export()}


def summarize(raw, p):
    rows = []
    for budget in p["operating"]["budgets"]:
        for method in p["operating"]["methods"]:
            runs = [r for r in raw["operating"] if r["budget"] == budget and r["method"] == method]
            costs = [r["measurements"][r["returned"]]["cost"] for r in runs]
            counts = [len(r["measurements"]) for r in runs]
            rows.append({"budget": budget, "method": method, "n": len(runs),
                         "mean_final_MSE": float(np.mean(costs)), "median_final_MSE": float(np.median(costs)),
                         "p90_final_MSE": float(np.quantile(costs, .9)), "mean_calls": float(np.mean(counts)),
                         "min_calls": min(counts), "max_calls": max(counts), "total_calls": sum(counts),
                         "trial_increases": sum(sum(m["cost"] > r["measurements"][0]["cost"] for m in r["measurements"][1:]) for r in runs),
                         "returned_worse_than_start": sum(c > r["measurements"][0]["cost"] for c, r in zip(costs, runs))})
    by_phase = {name: sum(len(obj["measurements"]) for obj in objects) for name, objects in raw["teacher"].items()}
    by_phase["operating"] = sum(len(r["measurements"]) for r in raw["operating"])
    accounting = {"actual_objective_evaluations": sum(by_phase.values()),
                  "maximum_objective_evaluations": p["accounting"]["maximum_objective_evaluations"],
                  "by_phase": by_phase,
                  "standalone_offline_per_model": sum(by_phase[s] for s in ("train", "temperature", "conformal"))}
    primary = {r["method"]: r for r in rows if r["budget"] == p["operating"]["primary_budget"]}
    comparisons = []
    for seed in p["training"]["seeds"]:
        head = primary[f"typed_seed_{seed}"]
        for name in ("coordinate_search", "space_filling", "simplex"):
            baseline = primary[name]
            comparisons.append({"seed": seed, "baseline": name,
                                "mean_at_least_five_percent_better": head["mean_final_MSE"] <= .95 * baseline["mean_final_MSE"],
                                "p90_noninferior": head["p90_final_MSE"] <= baseline["p90_final_MSE"]})
    benefit = all(c["mean_at_least_five_percent_better"] and c["p90_noninferior"] for c in comparisons)
    return rows, accounting, {"framework_transfer": True, "stable_empirical_policy_benefit": benefit,
            "status": "validated_simulation_only" if benefit else "negative_stop", "comparisons": comparisons,
            "complex_risk_research": "paused", "generic_pid_deployment_changed": False,
            "further_policy_deepening": False if not benefit else "requires_new_prospective_protocol"}


def amortization(rows, accounting):
    primary = {r["method"]: r for r in rows if r["budget"] == 20}
    offline = accounting["standalone_offline_per_model"]
    result = []
    for seed in (101, 202, 303):
        head = primary[f"typed_seed_{seed}"]
        for baseline in ("coordinate_search", "space_filling", "simplex"):
            other = primary[baseline]
            saving = other["mean_calls"] - head["mean_calls"]
            result.append({"seed": seed, "baseline": baseline,
                "standalone_offline_objectives": offline,
                "learned_mean_operating_calls": head["mean_calls"], "baseline_mean_operating_calls": other["mean_calls"],
                "call_only_break_even_tasks": None if saving <= 0 else int(np.ceil(offline / saving)),
                "task_counts": [{"tasks": n, "learned_total_calls": offline + n * head["mean_calls"],
                                 "baseline_total_calls": n * other["mean_calls"]} for n in (1, 10, 100, 1000)]})
    return result


def committed_sources():
    hashes = {name: digest(ROOT / name) for name in SOURCES}
    for name, expected in hashes.items():
        data = subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT)
        if Path(name).suffix in {".py", ".json", ".md", ".txt"}:
            data = data.replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == expected, "Uncommitted execution dependency: " + name
    return hashes


def run(output=DEFAULT_OUTPUT):
    p = protocol()
    output = Path(output)
    if output.exists():
        raise FileExistsError("Refuse to replace an existing study or replay: " + str(output))
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True)
    assert not dirty.strip(), "Commit implementation before acquisition"
    hashes = committed_sources()
    output.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    started = datetime.now(timezone.utc).isoformat()
    raw = {"schema_version": 1, "teacher": {}, "operating": []}
    artifacts, calibrations, fits = {}, {}, []
    wall_start, cpu_start, method_timing = time.perf_counter(), time.process_time(), []
    try:
        for name in ("train", "temperature", "conformal"):
            raw["teacher"][name] = []
            collect(p["splits"][name], raw["teacher"][name])
            print("acquired " + name, flush=True)
        x, y = training_arrays(raw["teacher"]["train"])
        for seed in p["training"]["seeds"]:
            artifact, fit = train_model(x, y, seed, p["training"])
            calibration = fit_calibration(load_model(artifact), artifact, raw["teacher"]["temperature"], raw["teacher"]["conformal"])
            write_json(output / f"model_{seed}.json", artifact)
            write_json(output / f"calibration_{seed}.json", calibration)
            artifacts[seed], calibrations[seed] = artifact, calibration
            fits.append(fit)
            print("frozen model/calibration " + str(seed), flush=True)
        # No test object has been constructed or used before every fit freezes.
        raw["teacher"]["test"] = []
        collect(p["splits"]["test"], raw["teacher"]["test"])
        cp_diagnostics = []
        tx, ty = training_arrays(raw["teacher"]["test"])
        for seed, artifact in artifacts.items():
            model, calibration = load_model(artifact), calibrations[seed]
            probs = np.stack([predict(model, artifact, f, calibration) for f in tx])
            from jev_tune.primitives import conformal_prediction_set
            sets = conformal_prediction_set(probs, np.asarray(calibration["qhat_per_axis"]))
            coverage = np.take_along_axis(sets, ty[..., None], -1)[..., 0].mean(axis=0)
            cp_diagnostics.append({"seed": seed, "n": len(tx), "coverage_per_axis": coverage.tolist(),
                                   "mean_set_size_per_axis": sets.sum(axis=-1).mean(axis=0).tolist()})
        for budget in p["operating"]["budgets"]:
            for method in p["operating"]["methods"]:
                method_wall, method_cpu = time.perf_counter(), time.process_time()
                seed = int(method.rsplit("_", 1)[1]) if method.startswith("typed_seed_") else None
                for task in range(p["splits"]["test"]["n"]):
                    try:
                        raw["operating"].append(rollout(p["splits"]["test"]["seed"], task, method, budget,
                             artifact=artifacts.get(seed), calibration=calibrations.get(seed)))
                    except Exception as exc:
                        if hasattr(exc, "nonpid_ledger"):
                            raw["operating"].append({"task": task, "method": method, "budget": budget,
                                                      "failed": True, **exc.nonpid_ledger})
                        raise
                method_timing.append({"budget": budget, "method": method,
                                      "wall_seconds": time.perf_counter() - method_wall,
                                      "cpu_seconds": time.process_time() - method_cpu})
                print(f"measured budget={budget} method={method}", flush=True)
        assert hashes == {name: digest(ROOT / name) for name in SOURCES}, "Execution source changed"
        rows, accounting, acceptance = summarize(raw, p)
        assert accounting["actual_objective_evaluations"] <= accounting["maximum_objective_evaluations"]
        accounting["optimizer_fit"] = fits
        raw_path = output / "raw.json.gz"
        with raw_path.open("wb") as handle, gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=0) as zipped:
            zipped.write(json.dumps(raw, separators=(",", ":"), allow_nan=False).encode())
        report = {"schema_version": 1, "study_id": p["study_id"], "protocol": PROTOCOL,
                  "source_hashes": hashes, "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
                  "environment": {"python": platform.python_version(), "platform": platform.platform(),
                                  "packages": {n: importlib.metadata.version(n) for n in ("numpy", "scipy", "torch")}},
                  "artifacts": {f.name: digest(f) for f in output.glob("*.json")},
                  "raw_sha256": digest(raw_path), "rows": rows, "accounting": accounting,
                  "cp_diagnostics": cp_diagnostics, "acceptance": acceptance,
                  "verification_status": "pending_independent_check",
                  "amortization": amortization(rows, accounting),
                  "compute": {"method_timing": method_timing, "total_wall_seconds": time.perf_counter() - wall_start,
                              "total_cpu_seconds": time.process_time() - cpu_start}}
        write_json(output / "report.json", report)
        print(json.dumps({"accounting": {k: v for k, v in accounting.items() if k != "optimizer_fit"}, "acceptance": acceptance}, indent=2))
    except Exception as exc:
        charged = sum(len(o["measurements"]) for objects in raw["teacher"].values() for o in objects)
        charged += sum(len(r["measurements"]) for r in raw["operating"])
        write_json(output / "failure.json", {"error": f"{type(exc).__name__}: {exc}", "raw_partial": raw,
                                             "charged_objective_evaluations": charged})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.output_root)
