"""Source-bound JSON receipts must authorize a complete, conditional summary.

These are publisher fixtures, not fabricated scientific outputs: source files
and their hashes are real, and no numerical audit function is replaced/stubbed.
The publisher validates existing receipt metadata; mathematical proofs are
covered by the independent numeric-audit tests.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("recorded_summary_tests", ROOT / "scripts/56_summarize_recorded_evidence.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def evidence(tmp_path):
    source_names = ("scripts/52_verify_recorded_transfer.py", "scripts/calibration_numeric_audit.py",
                    "scripts/56_summarize_recorded_evidence.py")
    originals = {}
    for name in source_names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        originals[name] = (ROOT / name).read_bytes()
        target.write_bytes(originals[name])
    sources = {name: publisher.digest(tmp_path / name) for name in source_names}
    assumptions = ast.get_docstring(ast.parse((ROOT / "scripts/calibration_numeric_audit.py").read_text(encoding="utf-8")), clean=False)
    raw_bytes = b"synthetic publisher-fixture acquisition evidence\n"
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    primary = {"raw_sha256": raw_sha, "acceptance": {"framework_transfer": True,
               "status": "negative_stop", "stable_empirical_policy_benefit": False},
               "accounting": {"actual_objective_evaluations": 76683,
                              "maximum_objective_evaluations": 83840}}
    primary_path = tmp_path / "research/results/nonpid_transfer/report.json"
    write_json(primary_path, primary)
    (primary_path.parent / "raw.json.gz").write_bytes(raw_bytes)
    certificate = {"ok": True, "conditional_certificate": True, "assumptions": assumptions}
    shared = {"status": "passed", "ok": True, "strict_cpu_replay_proven": False,
              "numeric_certification_assumptions": assumptions,
              "audit_execution": {"git_revision": "a" * 40, "source_hashes": sources}}
    transfer = {**copy.deepcopy(shared), "audit_type": "original_recorded_evidence",
                "raw_sha256": raw_sha, "acceptance": copy.deepcopy(primary["acceptance"]),
                "accounting": copy.deepcopy(primary["accounting"]),
                "additional_verification_objective_evaluations": 76683,
                "certified_operating_decisions": 19943,
                "numeric_certificates": [{"seed": seed, "temperature_certificates": [copy.deepcopy(certificate) for _ in range(2)]}
                                         for seed in (101, 202, 303)]}
    recalibration = {**copy.deepcopy(shared), "audit_type": "original_recorded_recalibration_evidence",
                     "additional_objective_evaluations": 0, "gradient_steps": 0, "rows": 9,
                     "recorded_timings_preserved": True,
                     "numeric_certificates": [{"model_seed": seed, "n_per_split": n,
                                               "temperature_certificates": [copy.deepcopy(certificate) for _ in range(2)]}
                                              for seed in (101, 202, 303) for n in (16, 32, 64)]}
    inputs = {"transfer": tmp_path / "local-inputs/transfer.json", "recalibration": tmp_path / "local-inputs/recalibration.json"}
    for name, value in (("transfer", transfer), ("recalibration", recalibration)):
        write_json(inputs[name], value)
    return {"root": tmp_path, "primary": primary, "primary_path": primary_path,
            "transfer": transfer, "recalibration": recalibration, "inputs": inputs, "original_sources": originals}


def publish(evidence):
    return publisher.publish(evidence["inputs"]["transfer"], evidence["inputs"]["recalibration"], root=evidence["root"])


def assert_no_public_outputs(root):
    assert not (root / publisher.RESULT).exists()
    assert all(not (root / name).exists() for name in publisher.RECEIPTS.values())


def test_complete_receipts_publish_actual_costs_24_conditional_proofs_and_real_source_hashes(evidence):
    source = evidence["inputs"]["transfer"]
    source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
    assert publish(evidence)["ok"] is True
    root = evidence["root"]
    result = publisher.summary(root)
    assert result["transfer_audit_objective_evaluations"] == evidence["primary"]["accounting"]["actual_objective_evaluations"] == 76683
    assert result["temperature_certificates"] == 24
    assert result["recalibration_audit_objective_evaluations"] == result["recalibration_gradient_steps"] == 0
    assert result["strict_cross_cpu_refit_passed"] is False
    assert result["research_status"] == "paused" and result["risk_head_deployment_enabled"] is False
    assert "not bitwise replay or causal training provenance" in result["scope"]
    for kind, path in publisher.RECEIPTS.items():
        assert (root / path).read_bytes() == evidence["inputs"][kind].read_bytes()
        assert result["source_receipts"][kind]["normalized_sha256"] == publisher.digest(root / path)
    for name, expected in result["source_hashes"].items():
        assert publisher.digest(root / name) == expected
    assert publisher.check(root)["additional_verification_objective_evaluations"] == 0


@pytest.mark.parametrize("mutation", [
    "transfer_failed", "recalibration_failed", "not_ok", "bitwise", "empty_assumptions",
    "different_assumptions", "certificate_assumptions", "unconditional", "certificate_failed",
    "certificate_missing", "wrong_seed", "duplicate_row", "incomplete_cost", "primary_cost",
    "accounting_details", "recalibration_objective", "gradient", "timing", "row_count",
    "empty_sources", "different_sources", "source_changed", "acceptance", "raw_binding",
])
def test_invalid_receipt_proof_or_primary_binding_is_rejected_before_any_copy_and_retry_succeeds(evidence, mutation):
    root = evidence["root"]
    transfer, recalibration = copy.deepcopy(evidence["transfer"]), copy.deepcopy(evidence["recalibration"])
    primary = copy.deepcopy(evidence["primary"])
    if mutation == "transfer_failed":
        transfer["status"] = "failed"
    elif mutation == "recalibration_failed":
        recalibration["status"] = "failed"
    elif mutation == "not_ok":
        transfer["ok"] = False
    elif mutation == "bitwise":
        recalibration["strict_cpu_replay_proven"] = True
    elif mutation == "empty_assumptions":
        transfer["numeric_certification_assumptions"] = " "
    elif mutation == "different_assumptions":
        recalibration["numeric_certification_assumptions"] += " changed"
    elif mutation == "certificate_assumptions":
        transfer["numeric_certificates"][0]["temperature_certificates"][0]["assumptions"] += " changed"
    elif mutation == "unconditional":
        recalibration["numeric_certificates"][0]["temperature_certificates"][0]["conditional_certificate"] = False
    elif mutation == "certificate_failed":
        transfer["numeric_certificates"][0]["temperature_certificates"][0]["ok"] = False
    elif mutation == "certificate_missing":
        recalibration["numeric_certificates"][0]["temperature_certificates"].pop()
    elif mutation == "wrong_seed":
        transfer["numeric_certificates"][1]["seed"] = 101
    elif mutation == "duplicate_row":
        recalibration["numeric_certificates"][1] = copy.deepcopy(recalibration["numeric_certificates"][0])
    elif mutation == "incomplete_cost":
        transfer["additional_verification_objective_evaluations"] -= 1
    elif mutation == "primary_cost":
        primary["accounting"]["actual_objective_evaluations"] += 1
    elif mutation == "accounting_details":
        transfer["accounting"]["maximum_objective_evaluations"] += 1
    elif mutation == "recalibration_objective":
        recalibration["additional_objective_evaluations"] = 1
    elif mutation == "gradient":
        recalibration["gradient_steps"] = 1
    elif mutation == "timing":
        recalibration["recorded_timings_preserved"] = False
    elif mutation == "row_count":
        recalibration["rows"] = 8
    elif mutation == "empty_sources":
        transfer["audit_execution"]["source_hashes"] = {}
    elif mutation == "different_sources":
        recalibration["audit_execution"]["source_hashes"].pop("scripts/52_verify_recorded_transfer.py")
    elif mutation == "source_changed":
        (root / "scripts/calibration_numeric_audit.py").write_text("# changed after audit\n")
    elif mutation == "acceptance":
        primary["acceptance"]["status"] = "validated_simulation_only"
    else:
        transfer["raw_sha256"] = "b" * 64
    write_json(evidence["inputs"]["transfer"], transfer)
    write_json(evidence["inputs"]["recalibration"], recalibration)
    write_json(evidence["primary_path"], primary)
    with pytest.raises(AssertionError):
        publish(evidence)
    assert_no_public_outputs(root)
    for name, data in evidence["original_sources"].items():
        (root / name).write_bytes(data)
    write_json(evidence["primary_path"], evidence["primary"])
    write_json(evidence["inputs"]["transfer"], evidence["transfer"])
    write_json(evidence["inputs"]["recalibration"], evidence["recalibration"])
    assert publish(evidence)["ok"] is True


def test_io_failure_rolls_back_complete_copies_and_allows_nonoverwriting_retry(evidence, monkeypatch):
    original, calls = publisher.os.link, []
    def fail_second(source, target):
        calls.append(target)
        if len(calls) == 2:
            raise OSError("deliberate second-publication failure")
        return original(source, target)
    monkeypatch.setattr(publisher.os, "link", fail_second)
    with pytest.raises(OSError, match="second-publication failure"):
        publish(evidence)
    assert_no_public_outputs(evidence["root"])
    assert not list(evidence["root"].glob(".recorded-evidence-stage-*"))
    monkeypatch.setattr(publisher.os, "link", original)
    assert publish(evidence)["ok"] is True


def test_existing_published_receipt_is_never_overwritten(evidence):
    target = evidence["root"] / publisher.RECEIPTS["recalibration"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"existing observation must survive")
    with pytest.raises(AssertionError, match="Refuse to overwrite"):
        publish(evidence)
    assert target.read_bytes() == b"existing observation must survive"
    assert not (evidence["root"] / publisher.RECEIPTS["transfer"]).exists()
    assert not (evidence["root"] / publisher.RESULT).exists()


@pytest.mark.parametrize("changed", ["summary", "receipt", "source", "primary"])
def test_postpublication_mutation_fails_recheck(evidence, changed):
    publish(evidence)
    root = evidence["root"]
    if changed == "summary":
        path = root / publisher.RESULT
        value = publisher.read(path)
        value["strict_cross_cpu_refit_passed"] = True
        write_json(path, value)
    elif changed == "receipt":
        path = root / publisher.RECEIPTS["transfer"]
        value = publisher.read(path)
        value["certified_operating_decisions"] -= 1
        write_json(path, value)
    elif changed == "source":
        (root / "scripts/52_verify_recorded_transfer.py").write_text("# stale source\n")
    else:
        value = copy.deepcopy(evidence["primary"])
        value["acceptance"]["stable_empirical_policy_benefit"] = True
        write_json(evidence["primary_path"], value)
    with pytest.raises(AssertionError):
        publisher.check(root)
