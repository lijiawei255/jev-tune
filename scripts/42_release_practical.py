"""Preserve historical research and package the verified practical release."""
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
PRESERVED = "research/protocols/research_pause_v090.json"
PRESERVATION_SHA256 = "90317aa1ada52ccd4aa61e107b83193377ea78bd0ed72829b034ae7f7e32ee8a"
EXECUTION = ".local-audit/v090_pytest_execution.json"


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def digest(path):
    data = Path(path).read_bytes()
    if Path(path).suffix in {".py", ".json", ".md", ".m"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def prepare():
    for stem in ("matlab_runtime", "release_verification"):
        target = ROOT / f"research/results/{stem}_v080.json"
        if not target.exists():
            source = ROOT / f"research/results/{stem}.json"
            if stem == "release_verification":
                assert json.loads(source.read_text())["version"] == "0.8.0"
            target.write_bytes(source.read_bytes())
    target = ROOT / PRESERVED
    if target.exists():
        check_preserved()
        return
    tracked = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "v0.8.0", "research/results", "research/protocols"],
                                      cwd=ROOT, text=True).splitlines()
    tracked = [name for name in tracked if name not in {"research/results/matlab_runtime.json", "research/results/release_verification.json"}]
    tracked += ["research/results/matlab_runtime_v080.json", "research/results/release_verification_v080.json",
                "src/jev_tune/trajectory_risk.py"]
    tracked += [p.relative_to(ROOT).as_posix() for p in (ROOT / "scripts").glob("3[0-8]_*.py")]
    payload = {"schema_version": 1, "research_status": "paused", "deployment_enabled": False,
               "baseline_tag": "v0.8.0", "generated_utc": datetime.now(timezone.utc).isoformat(),
               "reproduction": ["python scripts/32_verify_trajectory_risk.py",
                                "python scripts/34_reproduce_trajectory_evaluation.py --check",
                                "python scripts/31_trajectory_risk.py --help"],
               "hash_normalization": "CRLF to LF for text; binary byte-exact",
               "sha256": {name: digest(ROOT / name) for name in sorted(set(tracked))}}
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    check_preserved()


def check_preserved(root=ROOT):
    root = Path(root)
    assert digest(root / PRESERVED) == PRESERVATION_SHA256, "Preservation manifest changed or lost entries"
    payload = json.loads((root / PRESERVED).read_text(encoding="utf-8"))
    assert payload["research_status"] == "paused" and payload["deployment_enabled"] is False
    for name, expected in payload["sha256"].items():
        assert digest(root / name) == expected, f"Historical evidence changed: {name}"
    return payload


def check_baseline():
    payload = check_preserved()
    for name, expected in payload["sha256"].items():
        baseline = name.replace("matlab_runtime_v080.json", "matlab_runtime.json").replace("release_verification_v080.json", "release_verification.json")
        data = subprocess.check_output(["git", "show", "v0.8.0:" + baseline], cwd=ROOT)
        if Path(baseline).suffix in {".py", ".json", ".md", ".m"}:
            data = data.replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == expected, "Preserved content differs from v0.8.0: " + name
    print(json.dumps({"baseline_tag": "v0.8.0", "matched_files": len(payload["sha256"])}))


def test_sources():
    names = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, text=True).splitlines()
    return {name: digest(ROOT / name) for name in sorted(set(names))
            if Path(name).suffix in {".py", ".m", ".c", ".h", ".yml", ".toml"}
            or name.startswith(("models/", "research/protocols/v080_runtime_sources/"))}


def run_tests():
    before = test_sources()
    started = datetime.now(timezone.utc).isoformat()
    junit = ROOT / ".local-audit/v090_final_pytest.xml"
    log = ROOT / ".local-audit/v090_final_pytest.log"
    command = [sys.executable, "-m", "pytest", "-q", "--cov", "--cov-report=term", "--cov-fail-under=66",
               "--junitxml=" + str(junit)]
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    assert result.returncode == 0, f"pytest failed; see {log}"
    assert test_sources() == before, "Sources changed while pytest was running"
    record = {"started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
              "command": command, "returncode": result.returncode, "source_hashes": before,
              "junit": junit.relative_to(ROOT).as_posix(), "junit_sha256": digest(junit),
              "log": log.relative_to(ROOT).as_posix(), "log_sha256": digest(log)}
    (ROOT / EXECUTION).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(log.read_text(encoding="utf-8")[-3000:])


def verify_execution(args):
    execution = read(EXECUTION)
    assert execution["returncode"] == 0 and execution["source_hashes"] == test_sources(), "Stale pytest execution"
    for path, kind in ((args.junit, "junit"), (args.pytest_log, "log")):
        assert Path(path).resolve() == (ROOT / execution[kind]).resolve()
        assert digest(path) == execution[kind + "_sha256"], "pytest evidence changed"
    return execution


def verify(args):
    check_preserved()
    execution = verify_execution(args)
    suites = list(ET.parse(args.junit).getroot().iter("testsuite"))
    totals = {k: sum(int(s.attrib.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
    assert totals["tests"] and not totals["failures"] and not totals["errors"]
    log = Path(args.pytest_log).read_text(encoding="utf-8")
    coverage = re.search(r"Total coverage: ([\d.]+)%", log)
    assert coverage, "Actual pytest coverage summary required"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/16_check_claims.py"), "--json"],
                            cwd=ROOT, capture_output=True, encoding="utf-8")
    claims_log = ROOT / ".local-audit/v090_final_claims.json"
    claims_log.write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        (ROOT / ".local-audit/v090_claims_failure_stderr.txt").write_text(result.stderr, encoding="utf-8")
        raise AssertionError(f"Claims verification failed; see {claims_log}")
    claims = json.loads(result.stdout)
    assert claims and all(row["ok"] is True for row in claims)
    practical = read("research/results/practical_budget.json")["summary"]
    head = next(r for r in practical["rows"] if r["group"] == "all" and r["method"] == "jev_head" and r["budget"] == 20)
    hill = next(r for r in practical["rows"] if r["group"] == "all" and r["method"] == "vocab_hill" and r["budget"] == 20)
    payload = {"version": "0.9.0", "ok": True, "generated_utc": datetime.now(timezone.utc).isoformat(),
               "pytest": totals, "coverage_percent": float(coverage[1]),
               "automatic_document_checks": len(claims), "unverified_claims": 0,
               "research_status": "paused", "risk_head_deployment_enabled": False,
               "pytest_execution": execution,
               "previous_release_verification": "research/results/release_verification_v080.json",
               "preservation_manifest": PRESERVED,
               "model_adaptation": read("research/results/model_adaptation.json")["test_results"],
               "matlab_runtime": read("research/results/matlab_runtime.json")["test_results"],
               "practical_budget_artifact": "research/results/practical_budget.json",
               "practical_budget_summary": practical,
               "evidence_hashes": {name: digest(ROOT / name) for name in (
                   "research/results/model_adaptation.json", "research/results/matlab_runtime.json",
                   "research/results/practical_budget.json", PRESERVED,
                   "research/protocols/v080_runtime_sources/manifest.json")},
               "logs": {str(Path(p).resolve().relative_to(ROOT).as_posix()): digest(p)
                        for p in (args.junit, args.pytest_log, str(claims_log))}}
    (ROOT / "research/results/release_verification.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stats = (f"{totals['tests'] - totals['skipped']} passed; {totals['skipped']} skipped; "
             f"coverage {float(coverage[1])}%; {len(claims)} automatic claims checks; 0 unverified.")
    doc = "# Release verification / 发布验证\n\n[English](#english) · [简体中文](#简体中文)\n\n## English\n\n" + stats + "\n\n" + (
        "v0.9.0 prioritizes model-adapter correctness and simulation-budget evidence. Real MATLAB adapter/controller regressions and the complete local pytest suite were rerun. Claims reconstruct registered evidence, including the preserved failed research, without treating old studies as new experiments. The new practical budget comparison has its own frozen protocol and raw trial ledger. Its synthetic plants do not establish performance on a user's real model.\n\n"
        "The release fixes Ideal PID conversion, ambiguous Scope selection, variable-step integration, original-file collisions and stale cross-job model/sweep reuse. CLI options and write-back failures are propagated, worker queue writes are atomic, and total simulation counts include discovery and setup. Simplex respects small budgets and gain bounds; failed identification cannot silently fall back to an oracle baseline.\n\n"
        f"The practical comparison used {practical['actual_simulations']} actual simulations. At budget 20, head/hill mean J is {head['final_J_mean']:.6f}/{hill['final_J_mean']:.6f}, p90 is {head['final_J_p90']:.6f}/{hill['final_J_p90']:.6f}, and mean actual calls are {head['actual_calls_mean']:.6f}/{hill['actual_calls_mean']:.6f}. Fewer calls did not establish overall superiority; scenario-specific benefits and failures are preserved. No parameters were tuned from these results.\n\n"
        "Deeper joint-risk research is paused; failed acceptance and unestablished coverage premises remain unchanged, with deployment disabled. Historical result files and reproduction entry points are checked against the preservation manifest. `python scripts/44_verify_historical_research.py --check` runs the original verifiers in an isolated historical source view; current runtime fixes are not substituted into old experiments. Original direct commands remain available on v0.8.0. Previous release verification is archived, including its original MATLAB objective. Corrected time integration changes current MATLAB costs; historical costs are not silently replaced or presented as comparable current results.\n\n"
        "Local MATLAB uses the recorded installation. Hosted Linux runtime/C99 tests and hosted Windows scientific-evidence checks retain their separate scopes; cross-platform bitwise research replay remains unestablished.\n\n"
        "[Model adaptation](MODEL_ADAPTATION.md) · [Practical budget](PRACTICAL_BUDGET.md) · [Machine-readable verification](../research/results/release_verification.json) · [Previous verification](../research/results/release_verification_v080.json)\n\n## 简体中文\n\n"
    ) + stats + "\n\n" + (
        "v0.9.0优先修复模型适配正确性并补充仿真预算证据。已重跑真实MATLAB适配器/控制器回归及完整本地pytest；claims重建已注册证据，也保留并复核旧研究失败，不将旧研究冒充新实验。新的实用预算对照具有独立冻结协议和逐次仿真账本，其合成对象不构成用户真实模型上的效果证据。\n\n"
        "本次修复Ideal PID转换、Scope测量歧义、可变步长积分、原件路径冲突及跨任务模型/扫描缓存污染；转发CLI选项与写回失败，队列文件原子发布，总仿真计入发现和准备。simplex遵守小预算和增益边界，辨识失败不再静默换成oracle基线。\n\n"
        f"实用对照实际仿真{practical['actual_simulations']}次。预算20时，head/hill平均J为{head['final_J_mean']:.6f}/{hill['final_J_mean']:.6f}，p90为{head['final_J_p90']:.6f}/{hill['final_J_p90']:.6f}，实际平均调用为{head['actual_calls_mean']:.6f}/{hill['actual_calls_mean']:.6f}。少调用没有证明总体更优，各场景收益与失败如实保留，没有按结果调参。\n\n"
        "暂停深化联合风险研究，验收失败与覆盖前提尚未建立的结论保持不变，部署关闭。历史结果与复现入口按保存清单核验；`python scripts/44_verify_historical_research.py --check`在隔离历史源码视图运行原检查器，不将当前运行时修复偷换进旧实验；原直接命令保留在v0.8.0。上一版发布验证及其MATLAB原目标已归档。实际时间积分修正会改变当前MATLAB代价，旧值不被偷偷替换，也不作为可直接比较的当前结果。\n\n"
        "本地MATLAB使用记录的安装环境。托管Linux运行时/C99测试与托管Windows科学证据检查的范围不同，研究跨平台逐位重放仍未建立。\n\n"
        "[模型适配](MODEL_ADAPTATION.md) · [实用预算](PRACTICAL_BUDGET.md) · [机器可读验证](../research/results/release_verification.json) · [上一版验证](../research/results/release_verification_v080.json)\n"
    )
    (ROOT / "docs/RELEASE_VERIFICATION.md").write_text(doc, encoding="utf-8")
    print(stats)


def package():
    report = read("research/results/release_verification.json")
    assert report["version"] == "0.9.0" and report["ok"]
    check_preserved()
    assert report["pytest_execution"]["source_hashes"] == test_sources(), "Sources changed after tested release"
    for name, expected in report["evidence_hashes"].items():
        assert digest(ROOT / name) == expected, name
    for name, expected in report["logs"].items():
        assert digest(ROOT / name) == expected, "Verification log changed: " + name
    for name, function in (("43_verify_practical_budget", "check"),
                           ("40_verify_model_adaptation", "check"),
                           ("41_sync_practical_docs", "check"),
                           ("44_verify_historical_research", "verify_archives")):
        spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        checked = getattr(module, function)(root=ROOT)
        assert checked, (name, checked)
    out = ROOT / ".local-audit/release-v0.9.0"
    out.mkdir(parents=True, exist_ok=True)
    paths = [ROOT / name for name in ("research/results/model_adaptation.json", "research/results/matlab_runtime.json",
             "research/results/practical_budget.json", "research/results/release_verification.json", PRESERVED)]
    paths += sorted((ROOT / "research/results").glob("practical_budget*.gz"))
    paths += sorted((ROOT / "research/protocols").glob("practical_budget*.json"))
    assets = []
    for path in paths:
        dest = out / path.name
        dest.write_bytes(path.read_bytes()); assets.append(dest)
    zipped = out / "verification_logs_v0.9.0.zip"
    logs = [ROOT / name for name in report["logs"]]
    logs += [ROOT / ".local-audit/v090_model_adaptation.log", ROOT / ".local-audit/v090_matlab_runtime.log"]
    with zipfile.ZipFile(zipped, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in logs:
            bundle.write(path, path.relative_to(ROOT).as_posix())
    assets.append(zipped)
    archived_sources = out / "v080_runtime_sources.zip"
    archive_root = ROOT / "research/protocols/v080_runtime_sources"
    with zipfile.ZipFile(archived_sources, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(archive_root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                bundle.write(path, path.relative_to(ROOT).as_posix())
    assets.append(archived_sources)
    notes = (ROOT / "docs/RELEASE_VERIFICATION.md").read_text(encoding="utf-8")
    notes = notes.replace("](MODEL_ADAPTATION.md)", "](https://github.com/lijiawei255/jev-tune/blob/v0.9.0/docs/MODEL_ADAPTATION.md)")
    notes = notes.replace("](PRACTICAL_BUDGET.md)", "](https://github.com/lijiawei255/jev-tune/blob/v0.9.0/docs/PRACTICAL_BUDGET.md)")
    notes = notes.replace("](../research/", "](https://github.com/lijiawei255/jev-tune/blob/v0.9.0/research/")
    notes += "\nHistorical research data remain attached to [v0.8.0](https://github.com/lijiawei255/jev-tune/releases/tag/v0.8.0). 历史研究数据附件继续保留在v0.8.0。\n"
    (out / "release_notes.md").write_text(notes, encoding="utf-8")
    (out / "SHA256SUMS.txt").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in assets), encoding="utf-8")
    print(json.dumps({"output": str(out), "assets": [p.name for p in assets]}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-baseline", action="store_true")
    parser.add_argument("--package", action="store_true")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--junit")
    parser.add_argument("--pytest-log")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.check:
        print(json.dumps({"preserved_files": len(check_preserved()["sha256"]), "ok": True}))
    elif args.check_baseline:
        check_baseline()
    elif args.package:
        package()
    elif args.run_tests:
        run_tests()
    else:
        assert args.junit and args.pytest_log, "Actual pytest evidence required"
        verify(args)


if __name__ == "__main__":
    main()
