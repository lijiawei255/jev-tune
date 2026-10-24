"""Publish a summary from real, complete recorded-evidence audit receipts."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = "research/results/calibration_runtime_sources/"
RESULT = "research/results/recorded_evidence_audit_v0100.json"
RECEIPTS = {"transfer": BASE+"recorded_transfer_receipt.json",
            "recalibration": BASE+"recorded_recalibration_receipt.json"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _summary(root, transfer, recalibration, receipt_hashes):
    root = Path(root).resolve()
    primary = read(root/"research/results/nonpid_transfer/report.json")
    for record, kind in ((transfer, "original_recorded_evidence"),
                         (recalibration, "original_recorded_recalibration_evidence")):
        assert record["status"] == "passed" and record["ok"] is True
        assert record["audit_type"] == kind and record["strict_cpu_replay_proven"] is False
        assert isinstance(record["numeric_certification_assumptions"], str) and record["numeric_certification_assumptions"].strip()
        sources = record["audit_execution"]["source_hashes"]
        assert isinstance(sources, dict) and sources, "Missing audit source manifest"
        for name, expected in sources.items():
            source = (root/name).resolve()
            assert source.is_relative_to(root), "Audit source path escapes repository"
            assert digest(source) == expected, "Published audit source changed: " + name
    assert transfer["numeric_certification_assumptions"] == recalibration["numeric_certification_assumptions"]
    assert transfer["audit_execution"]["source_hashes"] == recalibration["audit_execution"]["source_hashes"], "Audit source manifests differ"
    assert transfer["raw_sha256"] == primary["raw_sha256"]
    assert transfer["acceptance"] == primary["acceptance"]
    assert transfer["accounting"] == primary["accounting"], "Primary acquisition accounting differs"
    assert transfer["additional_verification_objective_evaluations"] == primary["accounting"]["actual_objective_evaluations"]
    assert recalibration["additional_objective_evaluations"] == recalibration["gradient_steps"] == 0
    assert recalibration["rows"] == 9 and recalibration["recorded_timings_preserved"] is True
    assert [row["seed"] for row in transfer["numeric_certificates"]] == [101, 202, 303]
    assert [(row["model_seed"], row["n_per_split"]) for row in recalibration["numeric_certificates"]] == [
        (seed, n) for seed in (101, 202, 303) for n in (16, 32, 64)]
    assert all(len(row["temperature_certificates"]) == 2 for row in
               transfer["numeric_certificates"] + recalibration["numeric_certificates"])
    certificates = [certificate for row in transfer["numeric_certificates"]
                    for certificate in row["temperature_certificates"]]
    certificates += [certificate for row in recalibration["numeric_certificates"]
                     for certificate in row["temperature_certificates"]]
    assert len(certificates) == 24
    assert all(certificate["ok"] is True and certificate["conditional_certificate"] is True
               for certificate in certificates)
    assert all(certificate["assumptions"] == transfer["numeric_certification_assumptions"]
               for certificate in certificates), "Certificate assumptions differ"
    return {"schema_version": 1,
        "status": "conditional_original_record_evidence_passed",
        "strict_cross_cpu_refit_passed": False,
        "scope": "Post-incident consistency audit of original recorded evidence under explicit arithmetic assumptions; not bitwise replay or causal training provenance",
        "source_receipts": {name: {"path": path, "normalized_sha256": receipt_hashes[name]} for name, path in RECEIPTS.items()},
        "numeric_certification_assumptions": transfer["numeric_certification_assumptions"],
        "primary_acceptance": transfer["acceptance"], "raw_sha256": transfer["raw_sha256"],
        "certified_operating_decisions": transfer["certified_operating_decisions"],
        "temperature_certificates": len(certificates),
        "transfer_audit_objective_evaluations": transfer["additional_verification_objective_evaluations"],
        "recalibration_audit_objective_evaluations": recalibration["additional_objective_evaluations"],
        "recalibration_gradient_steps": recalibration["gradient_steps"],
        "research_status": "paused", "risk_head_deployment_enabled": False,
        "source_hashes": transfer["audit_execution"]["source_hashes"]}


def summary(root=ROOT):
    root = Path(root).resolve()
    records = {name: read(root/path) for name, path in RECEIPTS.items()}
    return _summary(root, records["transfer"], records["recalibration"],
                    {name: digest(root/path) for name, path in RECEIPTS.items()})


def check(root=ROOT):
    assert read(Path(root)/RESULT) == summary(root), "Published recorded-evidence summary changed"
    return {"ok": True, "strict_cross_cpu_refit_passed": False,
            "additional_verification_objective_evaluations": 0}


def publish(transfer, recalibration, root=ROOT):
    root = Path(root).resolve()
    destinations = [root/path for path in RECEIPTS.values()] + [root/RESULT]
    assert not any(path.exists() for path in destinations), "Refuse to overwrite published observations or receipts"
    # Read each supplied observation once and validate everything before exposing
    # any public receipt. A failed validation must leave a clean retry possible.
    payloads = {"transfer": Path(transfer).read_bytes(), "recalibration": Path(recalibration).read_bytes()}
    records = {kind: json.loads(value.decode("utf-8")) for kind, value in payloads.items()}
    value = _summary(root, records["transfer"], records["recalibration"],
                     {kind: hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
                      for kind, data in payloads.items()})
    outputs = [(root/RECEIPTS[kind], payloads[kind]) for kind in RECEIPTS]
    outputs.append((root/RESULT, (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8")))
    created = []
    with tempfile.TemporaryDirectory(prefix=".recorded-evidence-stage-", dir=root) as temporary:
        try:
            for index, (target, data) in enumerate(outputs):
                staged = Path(temporary)/str(index)
                staged.write_bytes(data)
                target.parent.mkdir(parents=True, exist_ok=True)
                # Same-filesystem hard links expose only complete staged bytes,
                # fail if a destination exists, and never overwrite observations.
                os.link(staged, target)
                created.append(target)
            return check(root)
        except BaseException:
            for target in reversed(created):
                target.unlink()
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transfer", type=Path)
    parser.add_argument("--recalibration", type=Path)
    args = parser.parse_args()
    assert bool(args.transfer) == bool(args.recalibration), "Supply both receipts"
    print(json.dumps(publish(args.transfer, args.recalibration) if args.transfer else check()))
