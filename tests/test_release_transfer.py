"""Release packaging must reject prose, registry and input-evidence mutations."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('transfer_release_test', ROOT/'scripts/47_release_transfer.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.mark.parametrize('changed', ['README.md', 'docs/claims.json', 'research/results/latency.json'])
def test_package_rejects_changes_after_fresh_claims(tmp_path, monkeypatch, changed):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    for name in ('README.md', 'docs/claims.json', 'research/results/latency.json'):
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}\n', encoding='utf-8')
    monkeypatch.setattr(release, 'ROOT', tmp_path)
    monkeypatch.setattr(release, 'historical', lambda: SimpleNamespace(
        check_preserved=lambda: True,
        digest=lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()))
    monkeypatch.setattr(release, 'execution', lambda: ({}, {}, 83.))
    fixed = release.sources()
    assert {changed, 'README.md', 'docs/claims.json', 'research/results/latency.json'} <= set(fixed)
    payload = {'version':'0.10.0','ok':True,'framework_verified':True,'pytest_execution':{},
               'fresh_claims_execution':{'source_hashes':fixed}}
    (tmp_path/release.REPORT).write_text(json.dumps(payload), encoding='utf-8')
    (tmp_path/changed).write_text('changed after verification\n', encoding='utf-8')
    with pytest.raises(AssertionError):
        release.package()


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_primary_artifact_accepts_normalized_line_endings(tmp_path, monkeypatch, newline):
    canonical = b'{\n  "value": 12.5\n}\n'
    path = tmp_path / "model.json"
    path.write_bytes(canonical.replace(b"\n", newline))
    monkeypatch.setattr(release, "ROOT", tmp_path)
    expected = hashlib.sha256(canonical).hexdigest()
    release.verify_primary_artifact("model.json", expected)
    # Exact-byte release evidence deliberately distinguishes CRLF from LF.
    assert release.digest("model.json") == hashlib.sha256(path.read_bytes()).hexdigest()
    if newline == b"\r\n":
        assert release.digest("model.json") != expected


def test_primary_artifact_rejects_numeric_mutation(tmp_path, monkeypatch):
    canonical = b'{\n  "value": 12.5\n}\n'
    path = tmp_path / "model.json"
    path.write_bytes(canonical.replace(b"12.5", b"12.6").replace(b"\n", b"\r\n"))
    monkeypatch.setattr(release, "ROOT", tmp_path)
    with pytest.raises(AssertionError, match="Primary artifact changed"):
        release.verify_primary_artifact("model.json", hashlib.sha256(canonical).hexdigest())


def test_package_rejects_line_ending_change_even_when_sources_match(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    artifact = "research/results/model.json"
    path = tmp_path / artifact
    path.parent.mkdir(parents=True)
    canonical = b'{\n  "value": 12.5\n}\n'
    path.write_bytes(canonical)
    # Keep the real historical normalization and all production comparison
    # functions. Only preservation and pytest execution are unrelated here.
    history = release.historical()
    monkeypatch.setattr(history, "check_preserved", lambda: True)
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "historical", lambda: history)
    monkeypatch.setattr(release, "execution", lambda: ({}, {}, 83.))
    fixed = release.sources()
    payload = {
        "version": "0.10.0", "ok": True, "framework_verified": True,
        "pytest_execution": {}, "fresh_claims_execution": {"source_hashes": fixed},
        "evidence_hashes": {artifact: release.digest(artifact)}, "logs": {},
    }
    (tmp_path / release.REPORT).write_text(json.dumps(payload), encoding="utf-8")
    path.write_bytes(canonical.replace(b"\n", b"\r\n"))
    assert release.sources() == fixed
    with pytest.raises(AssertionError, match="Release evidence changed: " + artifact):
        release.package()


def receipt(root, kind, name, *, status="passed", count=0, raw="a" * 64, strict=False):
    path = root / release.RECEIPT_KINDS[kind] / (name + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"status": status, "strict_cpu_replay_proven": strict,
           "numeric_certification_assumptions": "synthetic explicit arithmetic assumptions"}
    if kind == "recorded_recalibration":
        row["additional_objective_evaluations"] = count
        row["original_supplement_manifest"] = {"input_hashes": {release.NONPID + "raw.json.gz": raw}}
    else:
        row["raw_sha256"] = raw
        row["additional_verification_objective_evaluations"] = count
    path.write_text(json.dumps(row), encoding="utf-8")
    return path.relative_to(root).as_posix()


def test_all_strict_and_recorded_successes_and_failures_are_counted_by_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    receipt(tmp_path, "strict_nonpid", "strict-pass", count=11)
    receipt(tmp_path, "strict_nonpid", "strict-fail", status="failed", count=3)
    receipt(tmp_path, "recorded_transfer", "recorded-pass", count=11)
    receipt(tmp_path, "recorded_transfer", "recorded-fail", status="failed", count=5)
    receipt(tmp_path, "recorded_recalibration", "cal-pass")
    receipt(tmp_path, "recorded_recalibration", "cal-fail", status="failed")
    # Old-raw receipts still consumed compute and must not silently disappear.
    receipt(tmp_path, "strict_nonpid", "old-raw-fail", status="failed", count=7, raw="b" * 64)
    audit = release.receipts("a" * 64)
    assert len(audit["receipts"]) == len(release.all_receipt_hashes()) == 7
    assert audit["passed_objective_evaluations"] == 22
    assert audit["failed_objective_evaluations"] == 15
    assert audit["by_kind"]["strict_nonpid"]["failed_objective_evaluations"] == 10
    assert audit["by_kind"]["recorded_transfer"]["passed_objective_evaluations"] == 11
    assert audit["by_kind"]["recorded_recalibration"]["failed_runs"] == 1
    assert sum(row["current_raw"] for row in audit["receipts"]) == 6


@pytest.mark.parametrize("problem", ["only_strict", "historical", "failed", "partial", "bitwise_claim"])
def test_fresh_claims_reject_missing_or_uncertified_original_record_proof(tmp_path, monkeypatch, problem):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    receipt(tmp_path, "strict_nonpid", "strict-pass", count=11, strict=True)
    receipt(tmp_path, "recorded_recalibration", "cal-pass")
    previous = {}
    if problem != "only_strict":
        path = receipt(tmp_path, "recorded_transfer", "transfer", count=10 if problem == "partial" else 11,
                       status="failed" if problem == "failed" else "passed", strict=problem == "bitwise_claim")
        if problem == "historical":
            previous[path] = release.digest(path)
    with pytest.raises(AssertionError, match="passing complete current-raw recorded-transfer"):
        release.fresh_recorded_receipts(release.receipts("a" * 64), previous, 11)


def test_fresh_claims_require_both_independent_recorded_propositions(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    transfer = receipt(tmp_path, "recorded_transfer", "fresh-transfer", count=11)
    with pytest.raises(AssertionError, match="recorded-recalibration"):
        release.fresh_recorded_receipts(release.receipts("a" * 64), {}, 11)
    calibration = receipt(tmp_path, "recorded_recalibration", "fresh-calibration")
    assert release.fresh_recorded_receipts(release.receipts("a" * 64), {}, 11) == {
        "recorded_transfer": [transfer], "recorded_recalibration": [calibration]}


@pytest.mark.parametrize("mutation", [None, "missing_main", "bitwise", "assumptions", "unverified", "research"])
def test_packaging_proof_binding_rejects_missing_or_overclaimed_certificates(tmp_path, monkeypatch, mutation):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    main = receipt(tmp_path, "recorded_transfer", "passing-main", count=11)
    calibration = receipt(tmp_path, "recorded_recalibration", "passing-calibration")
    report = {"verification_status": "conditional_original_record_checks_passed",
              "strict_cross_cpu_replay_proven": False, "research_status": "paused",
              "risk_head_deployment_enabled": False,
              "nonpid_accounting": {"actual_objective_evaluations": 11},
              "numeric_certification_assumptions": "synthetic explicit arithmetic assumptions",
              "fresh_claims_execution": {"recorded_evidence_receipts": {
                  "recorded_transfer": [main], "recorded_recalibration": [calibration]}}}
    if mutation == "missing_main":
        report["fresh_claims_execution"]["recorded_evidence_receipts"]["recorded_transfer"] = []
    elif mutation == "bitwise":
        report["strict_cross_cpu_replay_proven"] = True
    elif mutation == "assumptions":
        report["numeric_certification_assumptions"] = ""
    elif mutation == "unverified":
        report["verification_status"] = "producer_only"
    elif mutation == "research":
        report["risk_head_deployment_enabled"] = True
    if mutation is None:
        release.recorded_release_binding(report, release.receipts("a" * 64))
    else:
        with pytest.raises(AssertionError):
            release.recorded_release_binding(report, release.receipts("a" * 64))


@pytest.mark.parametrize("kind", list(release.RECEIPT_KINDS))
def test_package_rejects_receipt_addition_after_verification_even_if_sources_match(tmp_path, monkeypatch, kind):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(".local-audit/\n")
    raw = tmp_path / release.NONPID / "raw.json.gz"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"synthetic release fixture")
    monkeypatch.setattr(release, "ROOT", tmp_path)
    history = SimpleNamespace(check_preserved=lambda: True,
                              digest=lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest())
    monkeypatch.setattr(release, "historical", lambda: history)
    monkeypatch.setattr(release, "execution", lambda: ({}, {}, 83.))
    source_hashes = release.sources()
    payload = {"version": "0.10.0", "ok": True, "framework_verified": True, "pytest_execution": {},
               "fresh_claims_execution": {"source_hashes": source_hashes}, "evidence_hashes": {}, "logs": {},
               "local_verification_audits": release.receipts(release.digest(release.NONPID + "raw.json.gz")),
               "local_receipt_hashes": release.all_receipt_hashes()}
    (tmp_path / release.REPORT).write_text(json.dumps(payload))
    receipt(tmp_path, kind, "new-failed-audit", status="failed", count=0)
    assert release.sources() == source_hashes
    with pytest.raises(AssertionError, match="Receipt set changed"):
        release.package()


def test_recalibration_receipt_cannot_hide_objective_work(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    receipt(tmp_path, "recorded_recalibration", "unexpected-filter", count=1)
    with pytest.raises(AssertionError, match="executed an objective"):
        release.receipts("a" * 64)


def test_runtime_bundle_requires_public_proof_and_includes_every_source_file(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    required = [release.HOSTED_FAILURE, release.RECORDED_EVIDENCE,
                "docs/NUMERICAL_REPRODUCIBILITY.md", *release.PROTOCOLS[-2:]]
    for name in required:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n")
    extra = "research/results/calibration_runtime_sources/kept_failed_trace.txt"
    path = tmp_path / extra
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("preserved failure\n")
    assert set(required + [extra]) <= set(release.runtime_evidence_names())
    (tmp_path / release.RECORDED_EVIDENCE).unlink()
    with pytest.raises(AssertionError, match="Required numerical-runtime evidence missing"):
        release.runtime_evidence_names()


def test_prior_hosted_failure_cost_is_bound_to_its_real_log_not_local_receipts(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    log = "research/results/calibration_runtime_sources/failure.txt"
    path = tmp_path / log
    path.parent.mkdir(parents=True)
    path.write_bytes(b"original failing output\r\n")
    record = {"status": "observed_failure", "independent_new_samples": False, "receipt_exported": False,
              "additional_verification_objective_evaluations": 13, "source_log": log,
              "source_log_sha256": hashlib.sha256(b"original failing output\n").hexdigest()}
    (tmp_path / release.HOSTED_FAILURE).write_text(json.dumps(record))
    assert release.hosted_failure()["additional_verification_objective_evaluations"] == 13
    assert release.receipts("a" * 64)["failed_objective_evaluations"] == 0
    path.write_text("sanitized away failure\n")
    with pytest.raises(AssertionError):
        release.hosted_failure()
