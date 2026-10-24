"""Run real MATLAB controller regressions and save self-contained evidence.

Reproduce from the repository root with PYTHONPATH=src:
    python scripts/24_verify_matlab_runtime.py
The model fixture is generated in a temporary directory; no user model is used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from jev_tune.matlab_runner import find_matlab

ROOT = Path(__file__).resolve().parents[1]
MARKER = "JEV_RUNTIME_RESULT="
SOURCES = (
    "matlab/test_tune_history.m", "matlab/test_decode_contract.m", "matlab/make_demo_model.m",
    "matlab/jev_tune_model.m", "matlab/jev_tune_json.m", "matlab/jev_decode.m",
    "matlab/jev_head_forward.m", "matlab/jev_state.m", "matlab/jev_metrics.m",
    "matlab/jev_assert_distinct_paths.m", "matlab/jev_read_signal.m",
    "matlab/jev_pid_parallel_gains.m", "matlab/jev_simulation_counts.m",
    "matlab/jev_write_json_atomic.m", "matlab/jev_validate_pid_conversion.m",
    "models/jev_head.pt", "models/jev_head_weights.mat", "models/calibration.json",
    "scripts/24_verify_matlab_runtime.py",
)


def file_hash(path):
    data = Path(path).read_bytes()
    if Path(path).suffix in (".m", ".py", ".json"):
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="research/results/matlab_runtime.json")
    parser.add_argument("--log", default=".local-audit/matlab_runtime.log")
    args = parser.parse_args()
    matlab = find_matlab()
    if not matlab.ok:
        raise SystemExit(f"MATLAB unavailable: {matlab}")
    before = {name: file_hash(ROOT / name) for name in SOURCES}
    with tempfile.TemporaryDirectory(prefix="jev-runtime-") as directory:
        code = (f"addpath('{(ROOT / 'matlab').as_posix()}'); "
                f"R=test_tune_history('{Path(directory).as_posix()}'); "
                f"fprintf('{MARKER}%s\\n',jsonencode(R));")
        result = subprocess.run([str(matlab.executable), "-batch", code], cwd=ROOT,
                                capture_output=True, encoding="utf-8", errors="replace", timeout=300)
    log = (result.stdout + "\nSTDERR:\n" + result.stderr).replace("\r\n", "\n")
    log_path = ROOT / args.log
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(log, encoding="utf-8", newline="\n")
    records = [line[len(MARKER):] for line in log.splitlines() if line.startswith(MARKER)]
    if result.returncode or len(records) != 1:
        raise SystemExit(f"MATLAB runtime verification failed ({result.returncode}); see {log_path}")
    evidence = json.loads(records[0])
    if not evidence.get("ok"):
        raise SystemExit(f"MATLAB runtime assertions failed; see {log_path}")
    assert before == {name: file_hash(ROOT / name) for name in SOURCES}, "Sources changed during MATLAB execution"
    report = {
        "schema_version": 1, "ok": True, "generated_by": "scripts/24_verify_matlab_runtime.py",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "reproduce": "PYTHONPATH=src python scripts/24_verify_matlab_runtime.py",
        "test_results": evidence,
        "measurement_scope": "n_experiments counts loop/final attempts; n_total_simulations includes discovery and setup in the job ledger",
        "source_hashes": before,
        "hash_normalization": "CRLF to LF for source text; binary byte-exact; embedded log UTF-8 with LF",
        "source_log_sha256": hashlib.sha256(log.encode("utf-8")).hexdigest(),
        "source_log": log,
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(out), "test_results": evidence}))


if __name__ == "__main__":
    main()
