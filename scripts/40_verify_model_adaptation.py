"""Run real Simulink adapter regressions and retain source-bound evidence.

--check verifies the saved log, results and source hashes without MATLAB.
Fixtures are generated in a temporary directory; no user model is touched.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RESULT = "research/results/model_adaptation.json"
MARKER = "JEV_ADAPTATION_RESULT="


def digest(path):
    data = Path(path).read_bytes()
    if Path(path).suffix in {".m", ".py", ".json"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def source_files():
    return sorted([p.relative_to(ROOT).as_posix() for p in (ROOT / "matlab").glob("*.m")] +
                  ["scripts/40_verify_model_adaptation.py", "models/calibration.json", "models/jev_head_weights.mat"])


def check(root=ROOT):
    root = Path(root)
    report = json.loads((root / RESULT).read_text(encoding="utf-8"))
    assert report["schema_version"] == 1 and report["ok"] is True
    assert report["test_results"]["ok"] is True
    assert report["source_hashes"].keys() == set(source_files())
    for name, expected in report["source_hashes"].items():
        assert digest(root / name) == expected, f"Stale adapter evidence: {name}"
    log = report["source_log"]
    assert hashlib.sha256(log.encode("utf-8")).hexdigest() == report["source_log_sha256"]
    records = [json.loads(line[len(MARKER):]) for line in log.splitlines() if line.startswith(MARKER)]
    assert records == [report["test_results"]], "Saved log and result differ"
    assert report["user_model_used"] is False
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        report = check()
        print(json.dumps({"ok": report["ok"], "source_files": len(report["source_hashes"])}))
        return
    from jev_tune.matlab_runner import find_matlab
    matlab = find_matlab()
    if not matlab.ok:
        raise SystemExit(f"MATLAB unavailable: {matlab}")
    before = {name: digest(ROOT / name) for name in source_files()}
    with tempfile.TemporaryDirectory(prefix="jev-adaptation-") as directory:
        code = (f"addpath('{(ROOT / 'matlab').as_posix()}'); "
                f"R=test_model_adaptation('{Path(directory).as_posix()}'); "
                f"fprintf('{MARKER}%s\\n',jsonencode(R));")
        result = subprocess.run([str(matlab.executable), "-batch", code], cwd=ROOT,
                                capture_output=True, encoding="utf-8", errors="replace", timeout=900)
    log = (result.stdout + "\nSTDERR:\n" + result.stderr).replace("\r\n", "\n")
    log_path = ROOT / ".local-audit/v090_model_adaptation.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(log, encoding="utf-8", newline="\n")
    records = [json.loads(line[len(MARKER):]) for line in log.splitlines() if line.startswith(MARKER)]
    if result.returncode or len(records) != 1 or records[0].get("ok") is not True:
        raise SystemExit(f"Adapter regression failed ({result.returncode}); see {log_path}")
    assert before == {name: digest(ROOT / name) for name in source_files()}, "Sources changed during MATLAB execution"
    report = {
        "schema_version": 1, "ok": True, "generated_by": "scripts/40_verify_model_adaptation.py",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "reproduce": "PYTHONPATH=src python scripts/40_verify_model_adaptation.py",
        "user_model_used": False, "test_results": records[0],
        "scope": "Generated Simulink regression fixtures, not external-plant or hardware acceptance",
        "source_hashes": before,
        "hash_normalization": "CRLF to LF for source text; embedded log UTF-8 with LF",
        "source_log_sha256": hashlib.sha256(log.encode("utf-8")).hexdigest(), "source_log": log,
    }
    (ROOT / RESULT).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    check()
    print(json.dumps(report["test_results"], ensure_ascii=False))


if __name__ == "__main__":
    main()
