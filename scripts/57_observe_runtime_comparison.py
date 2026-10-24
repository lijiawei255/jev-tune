"""Capture a new, zero-objective observation without replacing frozen 54 evidence."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from jev_tune.primitives import softmax

PROTOCOL = "research/protocols/runtime_comparison_observations_v0100.json"
LABELS = ("original_comparison_machine", "default_hosted_observer")
SOURCES = ["scripts/54_compare_calibration_runtimes.py", "scripts/45_nonpid_transfer.py",
           "scripts/51_diagnose_calibration_runtime.py", "scripts/57_observe_runtime_comparison.py",
           "scripts/58_verify_runtime_observations.py", "scripts/calibration_numeric_audit.py",
           "src/jev_tune/primitives.py", "src/jev_tune/decode.py", PROTOCOL,
           "tests/test_runtime_observations.py"]
SCOPE = "One observation machine decodes two archived input populations; these are not actions actually executed on two machines. No objectives, trajectories, training or new independent data."


def module(root, name):
    spec = importlib.util.spec_from_file_location("observation_"+name, root / "scripts" / (name+".py"))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def sha(path, text=False):
    data = Path(path).read_bytes()
    return hashlib.sha256(data.replace(b"\r\n", b"\n") if text else data).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def check_frozen_sources(root):
    root = Path(root)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    hashes = {}
    for name in SOURCES:
        blob = subprocess.check_output(["git", "show", revision+":"+name], cwd=root)
        pinned = hashlib.sha256(blob.replace(b"\r\n", b"\n")).hexdigest()
        if sha(root/name, text=True) != pinned:
            raise ValueError("Source not identical to frozen HEAD: "+name)
        hashes[name] = pinned
    protocol = json.loads((root/PROTOCOL).read_text(encoding="utf-8"))
    if (protocol.get("schema_version") != 1
            or protocol.get("study_type") != "post_incident_runtime_comparison_observations"
            or protocol.get("observation_labels") != list(LABELS)
            or protocol.get("cases_per_observation") != 96):
        raise ValueError("Observation protocol identity/roster changed")
    if protocol["source_hashes"] != {name: value for name, value in hashes.items() if name != PROTOCOL}:
        raise ValueError("Protocol source hash set is incomplete or changed")
    return revision, hashes


def input_manifest(root, names):
    return {name: {"sha256": sha(root/name, text=Path(name).suffix in {".json", ".md"}),
                   "observed_byte_sha256": sha(root/name),
                   "text_normalized": Path(name).suffix in {".json", ".md"}} for name in names}


def capture_cases(left, right, la, ra, runner):
    arrays, cases = {}, []
    for l, r in zip(left["rows"], right["rows"]):
        seed, n = l["seed"], l["n_temperature"]
        assert (seed, n) == (r["seed"], r["n_temperature"])
        for population in ("cp256", "saved_calibration_population"):
            for side, row, archive in (("root", l, la), ("hosted", r, ra)):
                source = row[population]
                for kind in ("refit", "saved"):
                    temperature_key = "refit_temperature" if kind == "refit" else "recorded_temperature"
                    temperatures = [axis[temperature_key] for axis in row["axes"]]
                    if kind == "refit":
                        q = [axis["qhat"] for axis in source["refit_t_order_statistic"]]
                        q_scope = "archived side refit rank threshold"
                    elif l[population]["saved_qhat"] is not None:
                        q = l[population]["saved_qhat"]
                        q_scope = "shared frozen left saved threshold, as in 54"
                    else:
                        q = [axis["qhat"] for axis in source["recorded_t_order_statistic"]]
                        q_scope = "archived side recorded-temperature rank threshold"
                    pkey = f"test_p_{side}_{seed}_{n}_{kind}"
                    if pkey not in arrays:
                        arrays[pkey] = softmax(archive[f"seed_{seed}_test_logits"],
                                              temperature=np.asarray(temperatures)[None, :, None])
                    cp_source_key = source["array_prefix"]+"_probabilities_"+("refit" if kind == "refit" else "recorded")+"_t"
                    cpkey = "cp_"+side+"_"+cp_source_key
                    arrays[cpkey] = archive[cp_source_key].copy()
                    decisions = [runner.action(p, {"qhat_per_axis": q}) for p in arrays[pkey]]
                    prefix = f"case_{len(cases):03d}"
                    for field in ("step", "held", "escalate"):
                        arrays[prefix+"_"+field] = np.stack([getattr(value, field) for value in decisions])
                    arrays[prefix+"_sets"] = np.stack([np.asarray(value.conformal_set, dtype=bool) for value in decisions])
                    cases.append({"id": prefix, "seed": seed, "n_temperature": n, "population": population,
                                  "side": side, "temperature_kind": kind, "temperatures": temperatures,
                                  "qhat": q, "qhat_scope": q_scope, "n_cp": source["n_calibration"],
                                  "test_probabilities": pkey, "CP_probabilities": cpkey,
                                  "CP_source_key": cp_source_key, "scope": SCOPE})
    return arrays, cases


def observe(out, *, label="original_comparison_machine", root=ROOT):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists():
        raise FileExistsError("Refuse to overwrite runtime observation: "+str(out))
    if label not in LABELS:
        raise ValueError("Use a preregistered observation label")
    revision, before = check_frozen_sources(root)
    compare = module(root, "54_compare_calibration_runtimes")
    runner = module(root, "45_nonpid_transfer")
    inputs = [compare.LEFT+"/diagnosis.json", compare.RIGHT+"/diagnosis.json",
              compare.BASE+"calibration_runtime_original_isa/diagnosis.json",
              compare.LEFT+"/canonical_arrays.npz", compare.RIGHT+"/canonical_arrays.npz",
              compare.BASE+"calibration_runtime_original_isa/canonical_arrays.npz", compare.RESULT,
              "research/results/nonpid_transfer/report.json", "research/results/nonpid_transfer/raw.json.gz",
              "research/protocols/nonpid_transfer_v0100.json", "models/calibration.json",
              "docs/NUMERICAL_REPRODUCIBILITY.md"]
    inputs += [f"research/results/nonpid_transfer/{kind}_{seed}.json"
               for kind in ("model", "calibration") for seed in (101, 202, 303)]
    inputs_before = input_manifest(root, inputs)
    out.mkdir(parents=True)
    environment = module(root, "51_diagnose_calibration_runtime").environment()
    write(out/"environment.json", environment)
    started = datetime.now(timezone.utc).isoformat()
    # This is deliberately the unchanged implementation, including its source
    # identity/ISA-arm assertions. Its newly observed result is not the old JSON.
    actual = compare.compare(root)
    write(out/"actual_54_comparison.json", actual)
    command = [sys.executable, str(root/"scripts/54_compare_calibration_runtimes.py")]
    original = subprocess.run(command, cwd=root, capture_output=True, text=True)
    (out/"original_54_check.stdout.txt").write_text(original.stdout, encoding="utf-8")
    (out/"original_54_check.stderr.txt").write_text(original.stderr, encoding="utf-8")
    left, right = [json.loads((root/name/"diagnosis.json").read_text(encoding="utf-8"))
                   for name in (compare.LEFT, compare.RIGHT)]
    with np.load(root/compare.LEFT/"canonical_arrays.npz", allow_pickle=False) as la, np.load(root/compare.RIGHT/"canonical_arrays.npz", allow_pickle=False) as ra:
        arrays, cases = capture_cases(left, right, la, ra, runner)
    np.savez_compressed(out/"arrays.npz", **arrays)
    if check_frozen_sources(root) != (revision, before) or input_manifest(root, inputs) != inputs_before:
        raise ValueError("Source/revision/input changed during observation")
    observed = {"schema_version": 1, "label": label, "scope": SCOPE,
        "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "git_revision": revision, "protocol": PROTOCOL,
        "additional_objective_evaluations": 0, "gradient_steps": 0,
        "environment_file": "environment.json", "environment_sha256": sha(out/"environment.json"),
        "source_hashes": before, "source_hashes_after": before, "input_hashes": inputs_before,
        "input_hashes_after": inputs_before,
        "arrays_sha256": sha(out/"arrays.npz"),
        "arrays": {key: {"shape": list(value.shape), "dtype": value.dtype.str,
                          "sha256": hashlib.sha256(value.tobytes()).hexdigest()} for key, value in arrays.items()},
        "cases": cases, "actual_54_file": "actual_54_comparison.json",
        "actual_54_sha256": sha(out/"actual_54_comparison.json"),
        "original_54_check": {"command": command, "returncode": original.returncode,
            "stdout_file": "original_54_check.stdout.txt", "stderr_file": "original_54_check.stderr.txt",
            "stdout_sha256": sha(out/"original_54_check.stdout.txt"), "stderr_sha256": sha(out/"original_54_check.stderr.txt")},
        "hash_scope": "Observation outputs and NPZ bytes exact; source/JSON/Markdown inputs normalize CRLF to LF"}
    write(out/"observation.json", observed)
    return {"ok": True, "cases": len(cases), "original_54_returncode": original.returncode,
            "additional_objective_evaluations": 0, "output": str(out), "scope": SCOPE}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label", choices=LABELS, default="original_comparison_machine")
    args = parser.parse_args()
    print(json.dumps(observe(args.out, label=args.label), indent=2))
