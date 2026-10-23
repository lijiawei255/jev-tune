"""Audit the frozen practical study without changing its recorded evidence.

The original checker remains mandatory. Only LF/CRLF differences in its
recorded source, protocol and calibration text are accepted; binary evidence
remains byte-exact. This script does not simulate or regenerate plants.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_study(root):
    spec = importlib.util.spec_from_file_location(
        "_frozen_practical_budget_audit", Path(root) / "scripts/39_practical_budget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compatible_sha(root, expected, text_paths, normalized_paths):
    """Return the recorded digest only for a proven newline-only difference."""
    root = Path(root).resolve()

    def digest(path):
        path = Path(path)
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        relative = path.resolve().relative_to(root).as_posix()
        recorded = expected.get(relative)
        if actual == recorded or relative not in text_paths:
            return actual
        lf = data.replace(b"\r\n", b"\n")
        variants = (lf, lf.replace(b"\n", b"\r\n"))
        if any(hashlib.sha256(candidate).hexdigest() == recorded for candidate in variants):
            normalized_paths.add(relative)
            return recorded
        return actual

    return digest


def verify_roster(raw, protocol):
    """Require the complete protocol roster, including every scenario size."""
    expected = []
    for cohort in protocol["cohorts"]:
        name, count = cohort["name"], cohort["n"]
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValueError("protocol cohort size must be a positive integer")
        if "scenarios" in cohort:
            names = cohort["scenarios"]
            if not names or len(set(names)) != len(names) or count % len(names):
                raise ValueError("protocol scenario roster or equal allocation is invalid")
            expected.extend({"name": scenario, "group": name, "n": count // len(names)}
                            for scenario in names)
        else:
            expected.append({"name": name, "group": name, "n": count})
    if len({row["name"] for row in expected}) != len(expected):
        raise ValueError("protocol cohort names are not unique")
    if sum(row["n"] for row in expected) != protocol["n_plants"]:
        raise ValueError("protocol cohort totals differ from n_plants")
    observed = [{"name": row["name"], "group": row["group"], "n": len(row["plants"])}
                for row in raw["cohorts"]]
    if observed != expected:
        raise ValueError(f"protocol cohort roster mismatch: expected {expected!r}; observed {observed!r}")
    return expected


def check(root=ROOT):
    root = Path(root).resolve()
    study = _load_study(root)
    report = json.loads((root / study.RESULT).read_text(encoding="utf-8"))
    expected = {**report["source_sha256"], **report["model_sha256"],
                study.PROTOCOL: report["protocol_sha256"]}
    # Do not extend newline compatibility to gzip, model weights or arbitrary
    # result files. The original manifest-set checks still run below.
    text_paths = {name for name in study.SOURCES if Path(name).suffix == ".py"}
    text_paths.update({study.PROTOCOL, "models/calibration.json"})
    normalized_paths = set()
    original_sha = study.sha
    study.sha = _compatible_sha(root, expected, text_paths, normalized_paths)
    try:
        errors = study.check(root=root)
    finally:
        study.sha = original_sha
    if errors != []:
        raise ValueError("Frozen practical checker failed: " + repr(errors))
    protocol = json.loads((root / study.PROTOCOL).read_text(encoding="utf-8"))
    with gzip.open(root / study.RAW, "rt", encoding="utf-8") as stream:
        raw = json.load(stream)
    roster = verify_roster(raw, protocol)
    return {"ok": True, "normalized_paths": sorted(normalized_paths),
            "normalization": "Only original-hash-matching LF/CRLF source, protocol and calibration text",
            "cohort_roster": roster, "n_plants": sum(row["n"] for row in roster),
            "existing_checker_errors": errors,
            "raw_sha256": report["raw_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify saved evidence (the default)")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = check(root=args.root)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
