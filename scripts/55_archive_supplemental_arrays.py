"""Record small-sample diagnostic probabilities on the original CPU; zero objectives."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
from jev_tune.primitives import softmax

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research/results/calibration_runtime_sources"


def digest(path):
    data = Path(path).read_bytes()
    if Path(path).suffix in {".py", ".json"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def archive():
    target, manifest = BASE/"small_sample_arrays.npz", BASE/"small_sample_arrays.json"
    assert not target.exists() and not manifest.exists(), "Refuse to overwrite observed arrays"
    source = json.loads((BASE/"original_machine_arrays.json").read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("_supplement_environment", ROOT/"scripts/51_diagnose_calibration_runtime.py")
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    observed = diagnostic.environment()
    assert source["environment"]["windows_processor"] == observed["windows_processor"], "Reference CPU changed"
    original = BASE/"original_machine_arrays.npz"
    assert digest(original) == source["archive_sha256"]
    with np.load(original, allow_pickle=False) as saved:
        logits = {seed: saved[f"seed_{seed}_test_logits"] for seed in (101, 202, 303)}
    benchmark_path = ROOT/"research/results/recalibration_benchmark.json"
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    arrays = {f"seed_{row['model_seed']}_n{row['n_per_split']}_test_probabilities":
              softmax(logits[row["model_seed"]], temperature=np.asarray(row["calibration"]["temperatures"])[None, :, None])
              for row in benchmark["rows"]}
    assert len(arrays) == 9
    np.savez_compressed(target, **arrays)
    record = {"schema_version": 1, "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Post-incident original-machine observations on already paid-for test features; no model or threshold selection",
        "archive": target.relative_to(ROOT).as_posix(), "archive_sha256": digest(target),
        "primary_archive_sha256": source["archive_sha256"], "benchmark_sha256": digest(benchmark_path),
        "input_hashes": source["input_hashes"], "source_script_sha256": digest(__file__),
        "arrays": {name: {"shape": list(value.shape), "dtype": str(value.dtype),
            "sha256": hashlib.sha256(value.tobytes()).hexdigest()} for name, value in arrays.items()},
        "additional_objective_evaluations": 0, "gradient_steps": 0, "environment": observed}
    manifest.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"archive": record["archive"], "sha256": record["archive_sha256"], "arrays": len(arrays)}))


if __name__ == "__main__":
    archive()
