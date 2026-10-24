"""Archive observed reference-machine arrays without training or objective calls.

This is post-incident evidence, not a prospective experiment. It refuses to
overwrite evidence or to claim a different machine is the reference machine.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/results/calibration_runtime_sources"


def module(name):
    spec = importlib.util.spec_from_file_location("_archive_" + name, ROOT / "scripts" / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def archive(source):
    source = Path(source).resolve()
    diagnostic = json.loads((source / "diagnosis.json").read_text(encoding="utf-8"))
    assert diagnostic["label"] == "original_machine_default"
    assert diagnostic["original_48_check"]["returncode"] == 0
    assert diagnostic["additional_objective_evaluations"] == 0
    target = OUT / "original_machine_arrays.npz"
    manifest = OUT / "original_machine_arrays.json"
    assert not target.exists() and not manifest.exists(), "Refuse to overwrite observed evidence"
    bench = module("48_recalibration_benchmark")
    diagnostic_api = module("51_diagnose_calibration_runtime")
    environment = diagnostic_api.environment()
    observed = json.loads((source / "environment.json").read_text(encoding="utf-8"))
    assert environment["windows_processor"] == observed["windows_processor"], "Reference CPU changed"
    context = bench._context(ROOT, ROOT / bench.PRIMARY)
    arrays = dict(np.load(source / "canonical_arrays.npz", allow_pickle=False))
    for seed in bench.SEEDS:
        artifact = context["models"][seed]
        model = context["runner"].load_model(artifact)
        calibration = bench.read(ROOT / bench.PRIMARY / f"calibration_{seed}.json")
        for split in ("temperature", "conformal", "test"):
            prefix = f"seed_{seed}_{split}"
            features, labels = context["arrays"][split]
            assert np.array_equal(arrays[prefix + "_features"], features)
            assert np.array_equal(arrays[prefix + "_labels"], labels)
            logits = np.stack([context["runner"].infer_logits(model, artifact, row) for row in features])
            assert np.array_equal(logits, arrays[prefix + "_logits"]), "Original inference bits changed"
            arrays[prefix + "_probabilities"] = np.stack([
                context["runner"].predict(model, artifact, row, calibration) for row in features])
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(target, **arrays)
    record = {"schema_version": 1, "recorded_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Post-incident observations on original CPU; not new independent samples or a training provenance proof",
              "original_diagnostic_revision": diagnostic["git_revision"],
              "observing_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "source_script_sha256": hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
              "input_hashes": context["input_hashes"],
              "archive": target.relative_to(ROOT).as_posix(),
              "archive_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
              "arrays": {name: {"shape": list(value.shape), "dtype": str(value.dtype),
                        "sha256": hashlib.sha256(value.tobytes()).hexdigest()} for name, value in arrays.items()},
              "original_48_passed_before_capture": True, "original_logits_bits_unchanged": True,
              "additional_objective_evaluations": 0, "gradient_steps": 0,
              "environment": environment}
    manifest.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"archive": record["archive"], "sha256": record["archive_sha256"],
                      "arrays": len(arrays), "additional_objective_evaluations": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    archive(parser.parse_args().source)
