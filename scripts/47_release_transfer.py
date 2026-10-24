"""Source-bound v0.10.0 test execution, release verification and packaging."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ".local-audit/"
EXECUTION = AUDIT + "v0100_pytest_execution.json"
JUNIT = AUDIT + "v0100_final_pytest.xml"
TESTLOG = AUDIT + "v0100_final_pytest.log"
CLAIMS = AUDIT + "v0100_final_claims.json"
REPORT = "research/results/release_verification.json"
NONPID = "research/results/nonpid_transfer/"
PROTOCOLS = ["research/protocols/nonpid_transfer_v0100.json", "research/protocols/shell_recalibration_v0100.json",
             "research/protocols/calibration_runtime_v0100.json", "research/protocols/recorded_evidence_audit_v0100.json"]
RECEIPT_KINDS = {"strict_nonpid": AUDIT + "nonpid_transfer_verification",
                 "recorded_transfer": AUDIT + "recorded_transfer_verification",
                 "recorded_recalibration": AUDIT + "recorded_recalibration_verification"}
HOSTED_FAILURE = "research/results/calibration_runtime_ci_failure_v0100.json"
RECORDED_EVIDENCE = "research/results/recorded_evidence_audit_v0100.json"
LOGS = [JUNIT, TESTLOG, CLAIMS, EXECUTION, AUDIT + "v0100_model_adaptation.log",
        AUDIT + "v0100_matlab_runtime.log", AUDIT + "v0100_nonpid_acquisition.log",
        AUDIT + "v0100_recalibration.log", AUDIT + "v0100_helper_inputs.log",
        AUDIT + "v0100_external_checkout.json"]

def now():
    return datetime.now(timezone.utc).isoformat()

def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

def write(name, value):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

def digest(name):
    # Release evidence is byte-exact; the inherited tested-source set uses its
    # documented CRLF normalization separately.
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()

def verify_primary_artifact(name, expected):
    """Check the producer's normalized text hash, not release byte identity.

    Primary model/calibration JSON hashes normalize CRLF to LF, matching 45/46.
    Release evidence_hashes, gzip raw evidence and packaged asset checksums
    continue to bind exact bytes through digest(). These hashes describe the
    verified local files and distributed packages. Git text checkout may change
    line endings, so a new checkout must rerun verification before packaging.
    """
    data = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == expected, "Primary artifact changed: " + name


def open_source_inventory():
    spec = importlib.util.spec_from_file_location("open_source_inventory", ROOT / "scripts/50_open_source_inventory.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def historical():
    spec = importlib.util.spec_from_file_location("release_v090", ROOT / "scripts/42_release_practical.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def sources():
    # Bind prose, the registry and raw evidence as well as executable source.
    # The two generated release outputs are separately hashed after verify.
    names = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    excluded = {REPORT, 'docs/RELEASE_VERIFICATION.md'}
    return {name: historical().digest(ROOT/name) for name in sorted(set(names))
            if name not in excluded and (ROOT/name).is_file()}

def run_tests():
    archive_previous()
    before = sources()
    started = now()
    (ROOT / AUDIT).mkdir(exist_ok=True)
    command = [sys.executable, "-m", "pytest", "-q", "--cov", "--cov-report=term", "--cov-fail-under=66", "--junitxml=" + JUNIT]
    with (ROOT / TESTLOG).open("w", encoding="utf-8") as output:
        result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    after = sources()
    record = {"started_utc": started, "completed_utc": now(), "command": command,
              "returncode": result.returncode, "source_hashes": before,
              "source_hashes_after": after, "junit": JUNIT, "junit_sha256": digest(JUNIT),
              "log": TESTLOG, "log_sha256": digest(TESTLOG)}
    write(EXECUTION, record)
    assert result.returncode == 0, "pytest failed: " + TESTLOG
    assert before == after, "Sources changed during pytest"
    print((ROOT / TESTLOG).read_text(encoding="utf-8")[-3000:])

def execution():
    data = read(EXECUTION)
    assert data["returncode"] == 0
    assert data["source_hashes"] == data["source_hashes_after"] == sources(), "Stale tested sources"
    assert data["junit"] == JUNIT and data["log"] == TESTLOG
    assert data["junit_sha256"] == digest(JUNIT) and data["log_sha256"] == digest(TESTLOG)
    suites = list(ET.parse(ROOT / JUNIT).getroot().iter("testsuite"))
    totals = {k: sum(int(s.attrib.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
    assert totals["tests"] > 0 and all(totals[k] == 0 for k in ("failures", "errors", "skipped")), "Full local suite must have zero skips/failures/errors"
    log = (ROOT / TESTLOG).read_text(encoding="utf-8")
    match = re.search(r"Total coverage: ([\d.]+)%", log)
    assert match and float(match[1]) >= 66, "Missing actual passing coverage"
    return data, totals, float(match[1])

def receipts(raw_hash):
    rows = []
    for kind, directory in RECEIPT_KINDS.items():
        for path in sorted((ROOT / directory).glob("*.json")):
            name = path.relative_to(ROOT).as_posix()
            row = read(name)
            assert row["status"] in {"passed", "failed"}, name
            count = row.get("additional_verification_objective_evaluations",
                            row.get("additional_objective_evaluations"))
            assert type(count) is int and count >= 0, name
            if kind == "recorded_recalibration":
                assert count == 0, "Recalibration audit executed an objective: " + name
            bound_raw = row.get("raw_sha256") or row.get("original_supplement_manifest", {}).get(
                "input_hashes", {}).get(NONPID + "raw.json.gz")
            rows.append({"path": name, "sha256": digest(name), "kind": kind, "status": row["status"],
                         "objective_evaluations": count, "raw_sha256": bound_raw,
                         "current_raw": bound_raw == raw_hash,
                         "strict_cpu_replay_proven": row.get("strict_cpu_replay_proven")})
    def summarize(selected):
        return {"receipts": selected,
                "passed_runs": sum(r["status"] == "passed" for r in selected),
                "failed_runs": sum(r["status"] == "failed" for r in selected),
                "passed_objective_evaluations": sum(r["objective_evaluations"] for r in selected if r["status"] == "passed"),
                "failed_objective_evaluations": sum(r["objective_evaluations"] for r in selected if r["status"] == "failed")}
    return {"raw_sha256": raw_hash, **summarize(rows),
            "by_kind": {kind: summarize([row for row in rows if row["kind"] == kind]) for kind in RECEIPT_KINDS},
            "scope": "All retained local successful and failed audit receipts, separately by strict replay and conditional original-record audit; additional compute, not independent samples or acquisition"}

def all_receipt_hashes():
    return {p.relative_to(ROOT).as_posix(): digest(p.relative_to(ROOT).as_posix())
            for directory in RECEIPT_KINDS.values() for p in sorted((ROOT / directory).glob("*.json"))}


def fresh_recorded_receipts(audit, previous, expected_evaluations):
    """A historical strict pass cannot authorize the new evidence proposition."""
    fresh = [r for r in audit["receipts"] if r["path"] not in previous and r["status"] == "passed" and r["current_raw"]]
    transfer = [r for r in fresh if r["kind"] == "recorded_transfer"
                and r["objective_evaluations"] == expected_evaluations
                and r["strict_cpu_replay_proven"] is False]
    recalibration = [r for r in fresh if r["kind"] == "recorded_recalibration"
                     and r["objective_evaluations"] == 0 and r["strict_cpu_replay_proven"] is False]
    assert transfer, "Fresh claims must emit a passing complete current-raw recorded-transfer receipt"
    assert recalibration, "Fresh claims must emit a passing current-raw recorded-recalibration receipt"
    return {"recorded_transfer": [r["path"] for r in transfer],
            "recorded_recalibration": [r["path"] for r in recalibration]}


def recorded_release_binding(report, audit):
    """Packaging requires the complete, conditionally scoped proofs verified above."""
    assert report.get("verification_status") == "conditional_original_record_checks_passed", "Release lacks conditional recorded-evidence verification"
    assert report.get("strict_cross_cpu_replay_proven") is False, "Cross-CPU strict replay is not established"
    assert report.get("research_status") == "paused" and report.get("risk_head_deployment_enabled") is False
    recorded = report["fresh_claims_execution"].get("recorded_evidence_receipts", {})
    assert set(recorded) == {"recorded_transfer", "recorded_recalibration"}, "Release lacks both recorded-evidence propositions"
    chosen = set(path for values in recorded.values() for path in values)
    previous = {row["path"]: row["sha256"] for row in audit["receipts"] if row["path"] not in chosen}
    valid = fresh_recorded_receipts(audit, previous, report["nonpid_accounting"]["actual_objective_evaluations"])
    assert valid == recorded, "Recorded release proof binding differs"
    assumptions = report.get("numeric_certification_assumptions")
    assert isinstance(assumptions, str) and assumptions.strip(), "Missing numerical certificate assumptions"
    for path in chosen:
        assert read(path).get("numeric_certification_assumptions") == assumptions, "Numerical certificate assumptions changed"


def hosted_failure():
    row = read(HOSTED_FAILURE)
    assert row["status"] == "observed_failure" and row["independent_new_samples"] is False
    assert row["receipt_exported"] is False, "Historical missing receipt must not be presented as exported"
    assert type(row["additional_verification_objective_evaluations"]) is int
    assert row["additional_verification_objective_evaluations"] > 0
    assert hashlib.sha256((ROOT / row["source_log"]).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == row["source_log_sha256"]
    return row


def runtime_evidence_names():
    files = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "research/results/calibration_runtime_sources").rglob("*")) if p.is_file()]
    files += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "research/results").glob("calibration_runtime*.json")) if p.is_file()]
    required = [HOSTED_FAILURE, RECORDED_EVIDENCE, "docs/NUMERICAL_REPRODUCIBILITY.md", *PROTOCOLS[-2:]]
    for name in required:
        assert (ROOT / name).is_file(), "Required numerical-runtime evidence missing: " + name
    assert files, "Original-machine numerical evidence is missing"
    return sorted(set(files + required))


def archive_previous():
    archive = "research/results/release_verification_v090.json"
    if not (ROOT / archive).exists():
        assert read(REPORT)["version"] == "0.9.0", "Previous v0.9.0 report required"
        (ROOT / archive).write_bytes((ROOT / REPORT).read_bytes())
    assert read(archive)["version"] == "0.9.0", "Invalid historical archive"
    return archive

def document(report, primary, calibration):
    stats = f"{report['pytest']['tests']} passed; 0 skipped; coverage {report['coverage_percent']}%; {report['automatic_document_checks']} claims checks."
    actual = primary["accounting"]["actual_objective_evaluations"]
    status = primary["acceptance"]["status"]
    audit = report["local_verification_audits"]
    hosted = report["prior_hosted_failed_audit"]
    audit_table = ["| audit kind | passing / failed runs | passing / failed objective evaluations |",
                   "| :--- | ---: | ---: |"]
    for kind, values in audit["by_kind"].items():
        audit_table.append(f"| `{kind}` | {values['passed_runs']} / {values['failed_runs']} | "
                           f"{values['passed_objective_evaluations']} / {values['failed_objective_evaluations']} |")
    audit_text = "\n".join(audit_table)
    timing = [{"seed": r["model_seed"], "n_per_split": r["n_per_split"], "timing_statistics_ms": r["timing_statistics_ms"]} for r in calibration["rows"]]
    links = "[Non-PID transfer](NONPID_TRANSFER.md) · [Recalibration](RECALIBRATION.md) · [Numerical reproducibility](NUMERICAL_REPRODUCIBILITY.md) · [Safety shell](SAFETY_SHELL.md) · [Compute](COMPUTE.md) · [Verification](../research/results/release_verification.json)"
    return ("# Release verification / 发布验证\n\n[English](#english) · [简体中文](#简体中文)\n\n## English\n\n" + stats +
        f"\n\nv0.10.0 provides a checked C decision chain and reusable frozen calibration shell, with a trained non-PID denoising transfer experiment. The primary acquisition used {actual} objective evaluations; acceptance is `{status}`. All three trained seeds failed to establish the preregistered stable benefit over the baselines. Fresh original-record evidence checks passed under the documented arithmetic assumptions. This does not establish policy superiority, recover bitwise replay, prove the causal history of training, or make current-CPU actions equivalent to the original trajectories. The raw report's verification_status remains a producer statement.\n\n" +
        "Original strict 46/48 replay passed on the original machine but failed on the hosted CPU; both failures and the predefined runtime diagnostic arms are preserved. A local strict pass is not a cross-CPU pass. The separate 52 audit certifies recorded evidence conditionally and uses independently checked recorded probabilities to reconstruct the original action chain. Its scope and numerical assumptions are linked below.\n\n" +
        f"All retained local receipts, including failures, are listed by kind. These are audit evaluations of recorded candidates, separate from the {actual} prospective evaluations, and are not independent new samples.\n\n{audit_text}\n\n" +
        f"The earlier hosted failed audit separately consumed {hosted['additional_verification_objective_evaluations']} objective evaluations in [run {hosted['source_run_id']}]({hosted['source_url']}). Its receipt file was not exported; the original failure log and explicit accounting JSON are preserved. This cost is not hidden in local receipts or acquisition. Final hosted CI must pass before publication; these local results alone are not hosted acceptance.\n\n" +
        f"Recalibration adds {calibration['additional_objective_evaluations']} objective evaluations and {calibration['gradient_steps']} gradient steps. Its total host wall time is {calibration['overall_wall_seconds']} seconds; per-size measured fit timings in milliseconds follow. These exclude label acquisition and target-device execution.\n\n```json\n" + json.dumps(timing, indent=2) + "\n```\n\nComplex risk research remains paused and risk-head deployment disabled. Host measurements are not target-board timing or safety guarantees. Existing v0.8.0/v0.9.0 research and failed conclusions remain preserved.\n\n" + links +
        "\n\n## 简体中文\n\n" + stats +
        f"\n\nv0.10.0提供经过输入和逐层输出检查的C决策整链，以及冻结模型的复用校准壳，并完成新训练的非PID去噪迁移实验。主实验实际目标评估{actual}次，验收为`{status}`；三个训练种子都没有建立优于基线的预注册稳定收益。新claims通过的是具有明确算术假设的原记录证据核验，不说明策略更优，不恢复逐位重放，不证明训练历史的因果真实性，也不承诺当前CPU的动作等价于原轨迹。原始报告verification_status仍是生产侧状态。\n\n" +
        "原46/48严格复现在原机通过、在托管CPU失败；原失败及预先固定的运行时诊断两臂完整保留。本机严格通过不等于跨CPU通过。独立52审计在算术假设下验证原记录，并使用独立检查过的原概率重建原动作链；范围和数值前提见下方链接。\n\n" +
        f"所有本地成功和失败receipt按kind分别列于上表，与{actual}次前瞻主实验分开，不构成独立新样本。较早托管失败审计在[run {hosted['source_run_id']}]({hosted['source_url']})实际执行{hosted['additional_verification_objective_evaluations']}次目标函数；当时没有导出receipt文件，原失败日志及单独计账JSON继续保留，不混入本地receipt或采集成本。最终托管CI通过后才可发布，本地结果本身不能代替托管验收。\n\n" +
        f"再校准额外目标评估{calibration['additional_objective_evaluations']}次、梯度步骤{calibration['gradient_steps']}次，宿主总耗时{calibration['overall_wall_seconds']}秒；各规模实测拟合时间见上方JSON，排除标签采集和目标板执行。复杂风险研究继续暂停，风险头部署关闭，宿主测试不提供目标板时限或安全保证。v0.8.0/v0.9.0历史研究与失败结论继续保留。\n\n" + links + "\n")

def verify():
    historical().check_preserved()
    inventory_module = open_source_inventory()
    inventory = inventory_module.check(root=ROOT)
    inventory_module.validate_data(ROOT, inventory, required=True)
    tested, totals, coverage = execution()
    archive = archive_previous()
    before = sources()
    receipts_before = all_receipt_hashes()
    started = now()
    result = subprocess.run([sys.executable, "scripts/16_check_claims.py", "--json"], cwd=ROOT, capture_output=True, encoding="utf-8")
    (ROOT / CLAIMS).write_text(result.stdout, encoding="utf-8")
    assert result.returncode == 0, "Fresh claims failed: " + result.stderr
    claims = json.loads(result.stdout)
    assert claims and all(row["ok"] is True for row in claims)
    assert before == sources(), "Sources changed during claims verification"
    primary = read(NONPID + "report.json")
    calibration = read("research/results/recalibration_benchmark.json")
    raw_hash = digest(NONPID + "raw.json.gz")
    assert primary["raw_sha256"] == raw_hash
    audit = receipts(raw_hash)
    fresh_receipts = fresh_recorded_receipts(audit, receipts_before, primary["accounting"]["actual_objective_evaluations"])
    main_proof = read(fresh_receipts["recorded_transfer"][-1])
    recalibration_proof = read(fresh_receipts["recorded_recalibration"][-1])
    assumptions = main_proof["numeric_certification_assumptions"]
    assert isinstance(assumptions, str) and assumptions.strip(), "Missing numerical certificate assumptions"
    assert recalibration_proof["numeric_certification_assumptions"] == assumptions, "Different numeric assumptions across audits"
    hosted = hosted_failure()
    names = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / NONPID).rglob("*")) if p.is_file()]
    names += ["research/results/open_source_inventory_v0100.json", "docs/OPEN_SOURCE.md", "LICENSE", "NOTICE.md"]
    names += PROTOCOLS + ["research/results/recalibration_benchmark.json", "research/results/model_adaptation.json", "research/results/matlab_runtime.json", "research/results/matlab_parity_v0100.json", "research/results/hardware_v0100.json", "research/results/latency_v0100.json", historical().PRESERVED, archive]
    names += runtime_evidence_names()
    for artifact, expected in primary["artifacts"].items():
        verify_primary_artifact(NONPID + artifact, expected)
    for name in LOGS:
        assert (ROOT / name).is_file(), "Required execution log missing: " + name
    payload = {"version": "0.10.0", "ok": True, "generated_utc": now(), "pytest": totals,
        "coverage_percent": coverage, "pytest_execution": tested,
        "automatic_document_checks": len(claims), "unverified_claims": 0,
        "fresh_claims_execution": {"started_utc": started, "completed_utc": now(), "returncode": result.returncode, "source_hashes": before, "recorded_evidence_receipts": fresh_receipts},
        "verification_status": "conditional_original_record_checks_passed", "framework_verified": True,
        "strict_cross_cpu_replay_proven": False, "numeric_certification_assumptions": assumptions,
        "framework_verification_scope": "Original-record evidence under explicit arithmetic assumptions; not recovered bitwise replay, causal training provenance, or cross-CPU trajectory equivalence",
        "primary_verification_status": primary["verification_status"],
        "nonpid_acceptance": primary["acceptance"], "nonpid_accounting": primary["accounting"],
        "local_deterministic_replay": audit["by_kind"]["strict_nonpid"],
        "local_verification_audits": audit, "prior_hosted_failed_audit": hosted,
        "local_receipt_hashes": all_receipt_hashes(), "research_status": "paused", "risk_head_deployment_enabled": False,
        "model_adaptation": read("research/results/model_adaptation.json")["test_results"],
        "matlab_runtime": read("research/results/matlab_runtime.json")["test_results"],
        "recalibration_timing": [{k: row[k] for k in ("model_seed", "n_per_split", "timing_statistics_ms")} for row in calibration["rows"]],
        "evidence_hash_scope": "Byte-exact verified local evidence and distributed packages; Git text checkout may normalize line endings and requires renewed verification before packaging",
        "evidence_hashes": {name: digest(name) for name in sorted(set(names))},
        "logs": {name: digest(name) for name in LOGS}, "previous_release_verification": archive}
    (ROOT / "docs/RELEASE_VERIFICATION.md").write_text(document(payload, primary, calibration), encoding="utf-8")
    payload["release_document_sha256"] = digest("docs/RELEASE_VERIFICATION.md")
    write(REPORT, payload)
    print(json.dumps({"version": payload["version"], "ok": True, "pytest": totals}))

def package():
    report = read(REPORT)
    assert report["version"] == "0.10.0" and report["ok"] and report["framework_verified"]
    historical().check_preserved()
    tested, _, _ = execution()
    assert tested == report["pytest_execution"]
    assert report["fresh_claims_execution"]["source_hashes"] == sources()
    for field in ("evidence_hashes", "logs"):
        for name, expected in report[field].items():
            assert digest(name) == expected, "Release evidence changed: " + name
    assert receipts(digest(NONPID + "raw.json.gz")) == report["local_verification_audits"], "Receipt set changed; rerun verify"
    assert report["local_receipt_hashes"] == all_receipt_hashes(), "Local receipts added, removed or changed"
    recorded_release_binding(report, report["local_verification_audits"])
    assert report["prior_hosted_failed_audit"] == hosted_failure(), "Hosted failed audit accounting changed"
    assert set(runtime_evidence_names()) <= set(report["evidence_hashes"]), "Unbound numerical-runtime release evidence"
    assert report["release_document_sha256"] == digest("docs/RELEASE_VERIFICATION.md"), "Release document changed"
    claims = read(CLAIMS)
    assert claims and all(row["ok"] is True for row in claims)
    out = ROOT / AUDIT / "release-v0.10.0"
    out.mkdir(parents=True, exist_ok=True)
    assets = []
    standalone = ["research/results/recalibration_benchmark.json", REPORT, "research/results/model_adaptation.json", "research/results/matlab_runtime.json", "research/results/matlab_parity_v0100.json", "research/results/hardware_v0100.json", "research/results/latency_v0100.json"] + PROTOCOLS
    for name in standalone:
        target = out / Path(name).name
        target.write_bytes((ROOT / name).read_bytes())
        assets.append(target)
    assets.append(open_source_inventory().package(out, root=ROOT))
    bundles = {"nonpid_transfer_v0.10.0.zip": [n for n in report["evidence_hashes"] if n.startswith(NONPID)],
               "verification_logs_v0.10.0.zip": list(report["logs"]) + list(report["local_receipt_hashes"]),
               "runtime_evidence_v0.10.0.zip": runtime_evidence_names()}
    for name, paths in bundles.items():
        target = out / name
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(set(paths)):
                bundle.write(ROOT / path, path)
        assets.append(target)
    notes = (ROOT / "docs/RELEASE_VERIFICATION.md").read_text(encoding="utf-8")
    def absolute(match):
        label, url = match.group(1), match.group(2)
        if url.startswith(("#", "https://", "http://")):
            return match.group(0)
        path = ("docs/" + url) if not url.startswith("../") else url[3:]
        return f"[{label}](https://github.com/lijiawei255/jev-tune/blob/v0.10.0/{path})"
    notes = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", absolute, notes)
    notes += "\nHistorical research assets / 历史研究附件: [v0.8.0](https://github.com/lijiawei255/jev-tune/releases/tag/v0.8.0) · [v0.9.0](https://github.com/lijiawei255/jev-tune/releases/tag/v0.9.0).\n"
    target = out / "release_notes.md"
    target.write_text(notes, encoding="utf-8")
    assets.append(target)
    (out / "SHA256SUMS.txt").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in assets), encoding="utf-8")
    print(json.dumps({"output": str(out), "assets": [p.name for p in assets] + ["SHA256SUMS.txt"]}, indent=2))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument("--run-tests", action="store_true")
    flags.add_argument("--verify", action="store_true")
    flags.add_argument("--package", action="store_true")
    args = parser.parse_args()
    if args.run_tests:
        run_tests()
    elif args.verify:
        verify()
    else:
        package()

if __name__ == "__main__":
    main()
