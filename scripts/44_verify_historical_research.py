"""Verify v0.8 research in an isolated historical source view.

The current runtime keeps its fixes. Six archived v0.8 files replace their
current counterparts only inside a temporary copy and a separate process.
Original verifiers, results, hashes and numerical tolerances are unchanged.
No simulations run. --smoke checks source/import isolation without refitting.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "research/protocols/v080_runtime_sources"
BASELINE_COMMIT = "2dbb339c5faabd6be5d88eb9363f0cc50bc63928"
BASELINE_TAG_OBJECT = "834cd7ff55d6da5285edd8f57943dc89264c2ae7"
OVERRIDES = tuple("src/jev_tune/" + name + ".py" for name in
                  ("baselines", "cli", "identified", "matlab_runner", "matlab_worker", "mcp_server"))
RECORDS = tuple("research/results/" + name for name in
                ("trajectory_risk.json", "trajectory_risk_reproduction.json", "batch_inference_diagnosis.json"))
MARKER = "JEV_HISTORICAL_AUDIT="


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_archives(root=ROOT):
    """Recover recorded bytes only after all three old records agree."""
    root = Path(root)
    manifest = read(root / ARCHIVE / "manifest.json")
    require(manifest["schema_version"] == 1 and manifest["baseline_tag"] == "v0.8.0"
            and manifest["baseline_commit"] == BASELINE_COMMIT
            and manifest["baseline_tag_object"] == BASELINE_TAG_OBJECT, "Historical archive identity differs")
    require(set(manifest["files"]) == set(OVERRIDES), "Historical source archive is incomplete")
    require(manifest["original_records"] == list(RECORDS), "Historical source records differ")
    records = [read(root / name) for name in RECORDS]
    maps = [{name.replace("\\", "/"): value for name, value in
             records[0]["manifest"]["file_sha256"].items()},
            records[1]["source_sha256"], records[2]["source_sha256"]]
    recovered = {}
    for name in OVERRIDES:
        entry = manifest["files"][name]
        expected = {mapping[name] for mapping in maps}
        require(len(expected) == 1 and entry["recorded_sha256"] in expected,
                "Historical records disagree on source: " + name)
        require(entry["archive_path"] == ARCHIVE + "/" + name, "Invalid historical archive path")
        data = (root / entry["archive_path"]).read_bytes()
        lf = data.replace(b"\r\n", b"\n")
        matched = next((value for value in (data, lf, lf.replace(b"\n", b"\r\n"))
                        if sha(value) == entry["recorded_sha256"]), None)
        require(matched is not None, "Historical source snapshot changed: " + name)
        transform = entry["tag_to_recorded_transform"]
        require(transform in ("byte_exact", "LF_to_CRLF"), "Unknown historical source transform")
        git_data = matched if transform == "byte_exact" else matched.replace(b"\r\n", b"\n")
        blob = hashlib.sha1(b"blob " + str(len(git_data)).encode() + b"\0" + git_data).hexdigest()
        require(sha(git_data) == entry["git_blob_sha256"] and blob == entry["git_blob"],
                "Historical Git blob provenance differs: " + name)
        recovered[name] = matched
    return manifest, recovered


def build_view(root, destination, *, smoke=False):
    """Make physical copies: resolving files never escapes to the live tree."""
    root, destination = Path(root), Path(destination)
    _, recovered = verify_archives(root)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for folder in ("src", "scripts"):
        shutil.copytree(root / folder, destination / folder, ignore=ignore)
    if smoke:
        shutil.copytree(root / ARCHIVE, destination / ARCHIVE, ignore=ignore)
        for name in RECORDS:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, target)
    else:
        for folder in ("research", "models"):
            shutil.copytree(root / folder, destination / folder, ignore=ignore)
    for name, data in recovered.items():
        (destination / name).write_bytes(data)
    verify_archives(destination)


def load_script(root, name):
    spec = importlib.util.spec_from_file_location("historical_" + name,
                                                Path(root) / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def imported_sources(root):
    root = Path(root).resolve()
    imported = {}
    for name, module in list(sys.modules.items()):
        if name == "jev_tune" or name.startswith("jev_tune."):
            path = Path(module.__file__).resolve()
            require(path.is_relative_to(root / "src"), "Live runtime module leaked into historical audit: " + name)
            imported[name] = path.relative_to(root).as_posix()
    return imported


def worker(root, *, smoke=False):
    root = Path(root).resolve()
    sys.path[:0] = [str(root / "src"), str(root / "scripts")]
    manifest, recovered = verify_archives(root)
    for name, data in recovered.items():
        require((root / name).read_bytes() == data, "Historical view was not restored: " + name)
        importlib.import_module("jev_tune." + Path(name).stem)
    imported_sources(root)
    checks = {}
    if smoke:
        for name in ("32_verify_trajectory_risk", "34_reproduce_trajectory_evaluation", "37_batch_inference_diagnosis"):
            load_script(root, name)
        checks["imports"] = {"ok": True, "detail": "Archived modules and unchanged verifiers load from the temporary view"}
    else:
        payload = read(root / RECORDS[0])
        for name in ("study", "reproduction"):
            try:
                if name == "study":
                    module = load_script(root, "32_verify_trajectory_risk")
                    values = module.verify_payload(payload, require_final=True)
                    require(bool(values) and all(value is True for value in values.values()), "Historical study checks failed")
                    diagnosis = read(root / module.PAIRING_DIAGNOSIS)
                    require(module.same(diagnosis, module.paired_diagnosis(payload)), "Historical pairing diagnosis differs")
                    validity = read(root / module.VALIDITY_ASSESSMENT)
                    require(module.same(validity, module.validity_assessment(payload)) and
                            validity["deployment_allowed"] is False, "Historical validity assessment differs")
                    checks[name] = {"ok": True, "detail": "Original full raw/model/calibration/accounting, pairing and validity checks pass", "checks": values}
                else:
                    module = load_script(root, "34_reproduce_trajectory_evaluation")
                    result = module.check(result_path=root / RECORDS[0], report_path=root / RECORDS[1])
                    require(result["schema_version"] == 1 and result["equal"] is True and
                            result["additional_independent_evidence"] is False and
                            result["acceptance_recomputed"] is False, "Historical replay evidence differs")
                    checks[name] = {"ok": True, "detail": "Original five-arm replay hashes and additional simulation ledger pass"}
            except Exception as exc:
                checks[name] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
    imported = imported_sources(root)
    return {"ok": all(value["ok"] is True for value in checks.values()), "checks": checks,
            "baseline_tag": "v0.8.0", "baseline_commit": manifest["baseline_commit"],
            "restored_sources": {name: sha(data) for name, data in recovered.items()},
            "imported_modules": imported, "additional_simulations": 0,
            "scope": "Historical source view only; current runtime fixes and original evidence remain unchanged"}


def check(root=ROOT, *, smoke=False):
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="jev-v080-audit-") as directory:
        view = Path(directory)
        build_view(root, view, smoke=smoke)
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((str(view / "src"), str(view / "scripts")))
        env["PYTHONUTF8"] = "1"
        command = [sys.executable, str(view / "scripts/44_verify_historical_research.py"), "--worker"]
        if smoke:
            command.append("--smoke")
        completed = subprocess.run(command, cwd=view, env=env, capture_output=True,
                                   text=True, encoding="utf-8", timeout=1800)
        records = [json.loads(line[len(MARKER):]) for line in completed.stdout.splitlines()
                   if line.startswith(MARKER)]
        require(len(records) == 1, "Historical audit process failed: " + completed.stdout[-2000:] + completed.stderr[-2000:])
        result = records[0]
        require(completed.returncode == (0 if result["ok"] else 1), "Historical process status disagrees with its report")
        require("error" not in result, "Historical audit process failed: " + result.get("error", ""))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run both historical verifiers (default)")
    parser.add_argument("--smoke", action="store_true", help="check source/import isolation without full raw verification")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        result = worker(ROOT, smoke=args.smoke) if args.worker else check(smoke=args.smoke)
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if args.worker:
        print(MARKER + json.dumps(result, separators=(",", ":")))
    else:
        print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
