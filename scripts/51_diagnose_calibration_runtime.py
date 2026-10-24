"""Read-only calibration-runtime diagnosis; no objective execution or training.

Preserves the original 48 checker and its exit status. New files are diagnostic
records only, not replacement calibration, selection or acceptance evidence.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from jev_tune.primitives import calibrate_temperature, conformal_quantile, softmax


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def environment():
    from numpy._core import _multiarray_umath as cpu
    runtime, configuration = io.StringIO(), io.StringIO()
    with redirect_stdout(runtime):
        np.show_runtime()
    with redirect_stdout(configuration):
        np.show_config()
    result = {
        "python": sys.version, "platform": platform.platform(), "processor": platform.processor(),
        "numpy_cpu": {"baseline": list(getattr(cpu, "__cpu_baseline__", [])),
                      "dispatch": list(getattr(cpu, "__cpu_dispatch__", [])),
                      "features": {k: bool(v) for k, v in getattr(cpu, "__cpu_features__", {}).items()}},
        "numpy_show_runtime": runtime.getvalue(), "numpy_show_config": configuration.getvalue(),
        "torch_config": torch.__config__.show(), "torch_parallel_info": torch.__config__.parallel_info(),
        "torch_cpu_capability": torch.backends.cpu.get_cpu_capability(),
        "torch_threads": torch.get_num_threads(), "torch_interop_threads": torch.get_num_interop_threads(),
        "packages": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "torch", "scikit-learn")},
        "environment": {name: os.environ.get(name) for name in (
            "NPY_DISABLE_CPU_FEATURES", "MKL_ENABLE_INSTRUCTIONS", "MKL_CBWR", "ATEN_CPU_CAPABILITY",
            "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")},
        "additional_objective_evaluations": 0,
    }
    try:
        from threadpoolctl import threadpool_info
        result["threadpools"] = threadpool_info()
    except Exception as exc:
        result["threadpool_error"] = f"{type(exc).__name__}: {exc}"
    if platform.system() == "Windows":
        command = ["powershell", "-NoProfile", "-Command",
                   "Get-CimInstance Win32_Processor | Select-Object Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json -Compress"]
        info = subprocess.run(command, capture_output=True, text=True)
        result["windows_processor"] = {"returncode": info.returncode, "stdout": info.stdout, "stderr": info.stderr}
    return result


def nll(logits, labels, temperature):
    p = softmax(logits, axis=1, temperature=temperature)
    return float(-np.mean(np.log(np.clip(p[np.arange(len(labels)), labels], 1e-12, 1.))))


def ulps(left, right):
    # NLL is nonnegative; monotonically ordered IEEE-754 bit patterns suffice.
    return abs(int(np.float64(left).view(np.uint64)) - int(np.float64(right).view(np.uint64)))


def golden_trace(logits, labels):
    """Copy the frozen scalar search exactly, recording every original branch."""
    lo, hi, trace = .05, 20., []
    for iteration in range(60):
        m1, m2 = lo + .382 * (hi - lo), lo + .618 * (hi - lo)
        left, right = nll(logits, labels, m1), nll(logits, labels, m2)
        branch = left < right
        trace.append({"iteration": iteration, "lo": lo, "hi": hi, "m1": m1, "m2": m2,
                      "nll_m1": left, "nll_m2": right, "nll_m1_minus_m2": left-right,
                      "nll_ulp_distance": ulps(left, right), "branch": "hi=m2" if branch else "lo=m1"})
        if branch:
            hi = m2
        else:
            lo = m1
    return float(np.clip(.5 * (lo + hi), .05, 20.)), trace


def sorted_scores(scores, identities, alpha=.1):
    rank = int(np.ceil((len(scores) + 1) * (1-alpha)))
    order = np.argsort(scores, axis=0, kind="stable")
    threshold = conformal_quantile(scores, alpha)
    rows = []
    for axis in range(scores.shape[1]):
        values = scores[order[:, axis], axis]
        index = rank-1
        if rank > len(scores):
            rows.append({"axis": axis, "rank": rank, "qhat": 1., "kth_index": None,
                         "kth_identity": None, "previous_gap": None, "next_gap": None})
        else:
            kth = int(order[index, axis])
            rows.append({"axis": axis, "rank": rank, "qhat": float(threshold[axis]),
                         "kth_index": kth, "kth_identity": identities[kth],
                         "previous_score": None if index == 0 else float(values[index-1]),
                         "next_score": None if index+1 == len(values) else float(values[index+1]),
                         "previous_gap": None if index == 0 else float(values[index]-values[index-1]),
                         "next_gap": None if index+1 == len(values) else float(values[index+1]-values[index])})
    return threshold, order, rows


def set_comparison(left_prob, left_q, right_prob, right_q, labels):
    left, right = (1-left_prob) <= left_q[None, :, None], (1-right_prob) <= right_q[None, :, None]
    unequal = left != right
    return {"differing_options_per_axis": unequal.sum(axis=(0, 2)).tolist(),
            "differing_state_axes_per_axis": unequal.any(axis=-1).sum(axis=0).tolist(),
            "recorded_temperature_mean_set_size": left.sum(axis=-1).mean(axis=0).tolist(),
            "refit_temperature_mean_set_size": right.sum(axis=-1).mean(axis=0).tolist(),
            "recorded_temperature_label_coverage": np.take_along_axis(left, labels[..., None], -1)[..., 0].mean(axis=0).tolist(),
            "refit_temperature_label_coverage": np.take_along_axis(right, labels[..., None], -1)[..., 0].mean(axis=0).tolist()}


def cp_comparison(arrays, prefix, logits, labels, identities, test_logits, test_labels, recorded_t, refit_t, saved_q=None):
    probabilities = [softmax(logits, temperature=np.asarray(t)[None, :, None]) for t in (recorded_t, refit_t)]
    test = [softmax(test_logits, temperature=np.asarray(t)[None, :, None]) for t in (recorded_t, refit_t)]
    scores = [1-np.take_along_axis(p, labels[..., None], -1)[..., 0] for p in probabilities]
    qrec, order_rec, rec = sorted_scores(scores[0], identities)
    qfit, order_fit, fit = sorted_scores(scores[1], identities)
    for name, values in {"probabilities_recorded_t": probabilities[0], "probabilities_refit_t": probabilities[1],
                         "scores_recorded_t": scores[0], "scores_refit_t": scores[1],
                         "sort_recorded_t": order_rec, "sort_refit_t": order_fit}.items():
        arrays[prefix+"_"+name] = values
    result = {"n_calibration": len(labels), "recorded_t_order_statistic": rec,
              "refit_t_order_statistic": fit, "saved_qhat": saved_q,
              "refit_qhat_minus_recorded_t_qhat": (qfit-qrec).tolist(),
              "cp_set_difference": set_comparison(*[probabilities[0], qrec, probabilities[1], qfit, labels]),
              "test_set_difference": set_comparison(test[0], qrec, test[1], qfit, test_labels),
              "array_prefix": prefix}
    if saved_q is not None:
        result["saved_qhat_minus_current_recorded_t_qhat"] = (np.asarray(saved_q)-qrec).tolist()
        result["saved_vs_refit_test_sets"] = set_comparison(test[0], np.asarray(saved_q), test[1], qfit, test_labels)
    return result


def original_check(root, out):
    command = [sys.executable, str(root / "scripts/48_recalibration_benchmark.py"), "--check"]
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True)
    (out / "original_48_check.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (out / "original_48_check.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    return {"command": command, "returncode": completed.returncode, "passed": completed.returncode == 0,
            "stdout_file": "original_48_check.stdout.txt", "stderr_file": "original_48_check.stderr.txt"}


def diagnose(out, *, label):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError("Refuse to overwrite runtime diagnosis: " + str(out))
    out.mkdir(parents=True)
    started, wall = datetime.now(timezone.utc).isoformat(), time.perf_counter()
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    write(out / "environment.json", environment())
    benchmark = load_module(ROOT / "scripts/48_recalibration_benchmark.py", "_runtime_diagnostic_benchmark")
    context = benchmark._context(ROOT, ROOT / "research/results/nonpid_transfer")
    recorded = benchmark.read(ROOT / benchmark.RESULT)
    recorded_rows = {(r["model_seed"], r["n_per_split"]): r for r in recorded["rows"]}
    runner, archive, rows = context["runner"], {}, []
    before = {f"model_{seed}.json": sha(ROOT / "research/results/nonpid_transfer" / f"model_{seed}.json") for seed in benchmark.SEEDS}
    for seed in benchmark.SEEDS:
        model, artifact = runner.load_model(context["models"][seed]), context["models"][seed]
        primary = benchmark.read(ROOT / "research/results/nonpid_transfer" / f"calibration_{seed}.json")
        full = {name: np.stack([runner.infer_logits(model, artifact, f) for f in context["arrays"][name][0]])
                for name in ("temperature", "conformal", "test")}
        for name in full:
            archive[f"seed_{seed}_{name}_logits"] = full[name]
            archive[f"seed_{seed}_{name}_labels"] = context["arrays"][name][1]
            archive[f"seed_{seed}_{name}_features"] = context["arrays"][name][0]
        for n in (16, 32, 64, 128):
            calibration = primary if n == 128 else recorded_rows[(seed, n)]["calibration"]
            recorded_t, refit_t, axes = calibration["temperatures"], [], []
            for axis in range(2):
                logits, labels = full["temperature"][:n, axis], context["arrays"]["temperature"][1][:n, axis]
                actual = calibrate_temperature(logits, labels)
                traced, trace = golden_trace(logits, labels)
                loss_rec, loss_fit = nll(logits, labels, recorded_t[axis]), nll(logits, labels, actual)
                refit_t.append(actual)
                axes.append({"axis": axis, "recorded_temperature": recorded_t[axis], "refit_temperature": actual,
                             "delta_temperature": actual-recorded_t[axis], "trace_temperature": traced,
                             "trace_matches_frozen_function_exactly": traced == actual,
                             "same_logits_nll_at_recorded_t": loss_rec, "same_logits_nll_at_refit_t": loss_fit,
                             "delta_nll": loss_fit-loss_rec, "nll_ulp_distance": ulps(loss_rec, loss_fit),
                             "golden_iterations": trace,
                             "logits_array": f"seed_{seed}_temperature_logits[:{n},{axis},:]",
                             "labels_array": f"seed_{seed}_temperature_labels[:{n},{axis}]"})
            cp_labels, test_labels = context["arrays"]["conformal"][1], context["arrays"]["test"][1]
            cp256 = cp_comparison(archive, f"seed_{seed}_n{n}_cp256", full["conformal"], cp_labels,
                                 context["identities"]["conformal"], full["test"], test_labels,
                                 recorded_t, refit_t, primary["qhat_per_axis"] if n == 128 else None)
            own_n = 256 if n == 128 else n
            own = cp256 if own_n == 256 else cp_comparison(
                archive, f"seed_{seed}_n{n}_cp{own_n}", full["conformal"][:own_n], cp_labels[:own_n],
                context["identities"]["conformal"][:own_n], full["test"], test_labels,
                recorded_t, refit_t, calibration["qhat_per_axis"])
            rows.append({"seed": seed, "n_temperature": n, "saved_calibration_cp_n": own_n,
                         "recorded_temperature_source": "primary" if n == 128 else "peripheral_benchmark",
                         "axes": axes, "cp256": cp256, "saved_calibration_population": own})
    np.savez_compressed(out / "canonical_arrays.npz", **archive)
    check = original_check(ROOT, out)
    after = {name: sha(ROOT / "research/results/nonpid_transfer" / name) for name in before}
    report = {"schema_version": 1, "label": label, "started_utc": started,
              "completed_utc": datetime.now(timezone.utc).isoformat(), "wall_seconds": time.perf_counter()-wall,
              "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "tracked_worktree_dirty": bool(subprocess.check_output(
                  ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True).strip()),
              "diagnostic_source_hashes": {name: sha(ROOT / name) for name in (
                  "scripts/51_diagnose_calibration_runtime.py", ".github/workflows/calibration_runtime_diagnosis.yml")},
              "source_hashes": {name: benchmark.digest(ROOT / name) for name in benchmark.SOURCES},
              "input_hashes": context["input_hashes"], "model_hashes_before": before, "model_hashes_after": after,
              "model_bytes_unchanged": before == after, "additional_objective_evaluations": 0,
              "training_gradient_steps": 0, "original_48_check": check, "rows": rows,
              "canonical_arrays_sha256": sha(out / "canonical_arrays.npz"),
              "scope": "Read-only runtime diagnosis; no new independent data, retuning, changed checks, tolerance changes or acceptance selection"}
    write(out / "diagnosis.json", report)
    write(out / "summary.json", {"label": label, "rows": len(rows), "axes": sum(len(r["axes"]) for r in rows),
          "max_abs_temperature_difference": max(abs(a["delta_temperature"]) for r in rows for a in r["axes"]),
          "max_nll_ulp_distance": max(a["nll_ulp_distance"] for r in rows for a in r["axes"]),
          "original_48_check_returncode": check["returncode"], "additional_objective_evaluations": 0,
          "model_bytes_unchanged": before == after, "output_directory": str(out)})
    return read_summary(out), check["returncode"]


def read_summary(out):
    return json.loads((out / "summary.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label", default="default")
    arguments = parser.parse_args()
    existed_before = arguments.out.exists()
    try:
        summary, status = diagnose(arguments.out, label=arguments.label)
        print(json.dumps(summary, indent=2))
    except Exception as exc:
        if not existed_before and arguments.out.exists():
            (arguments.out / "diagnostic_failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}", "additional_objective_evaluations": 0}))
        status = 2
    raise SystemExit(status)
