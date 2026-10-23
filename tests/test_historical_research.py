"""Old research must use its archived runtime, without weakening hash checks."""
import importlib.abc
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load_script("44_verify_historical_research")


@pytest.fixture
def archive(tmp_path):
    shutil.copytree(ROOT / audit.ARCHIVE, tmp_path / audit.ARCHIVE)
    for name in audit.RECORDS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


def test_archived_sources_match_all_original_records_and_git_blobs():
    manifest, recovered = audit.verify_archives()
    assert len(recovered) == 6
    assert manifest["baseline_commit"] != manifest["baseline_tag_object"]
    assert set(recovered) == set(audit.OVERRIDES)
    assert all(audit.sha(value) == manifest["files"][name]["recorded_sha256"]
               for name, value in recovered.items())


def test_git_checkout_line_endings_recover_original_recorded_bytes(archive):
    _, before = audit.verify_archives(archive)
    for name in audit.OVERRIDES:
        path = archive / audit.ARCHIVE / name
        data = path.read_bytes()
        lf = data.replace(b"\r\n", b"\n")
        path.write_bytes(lf if lf != data else lf.replace(b"\n", b"\r\n"))
    assert audit.verify_archives(archive)[1] == before


@pytest.mark.parametrize("mutation", ["source", "missing", "record", "blob", "tag_commit"])
def test_archive_mutation_is_never_blessed(archive, mutation):
    manifest_path = archive / audit.ARCHIVE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    name = audit.OVERRIDES[0]
    if mutation == "source":
        path = archive / audit.ARCHIVE / name
        path.write_bytes(path.read_bytes() + b"\n# different source\n")
    elif mutation == "record":
        path = archive / audit.RECORDS[2]
        record = json.loads(path.read_text())
        record["source_sha256"][name] = "0" * 64
        path.write_text(json.dumps(record), encoding="utf-8")
    else:
        if mutation == "missing":
            del manifest["files"][name]
        elif mutation == "blob":
            manifest["files"][name]["git_blob"] = "0" * 40
        else:
            manifest["baseline_commit"] = manifest["baseline_tag_object"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        audit.verify_archives(archive)


def test_isolated_smoke_keeps_current_import_and_source_unchanged():
    import jev_tune.baselines as current
    source = ROOT / "src/jev_tune/baselines.py"
    before = source.read_bytes()
    result = audit.check(smoke=True)
    assert result["ok"] and result["additional_simulations"] == 0
    assert result["imported_modules"]["jev_tune.baselines"] == "src/jev_tune/baselines.py"
    assert sys.modules["jev_tune.baselines"] is current
    assert Path(current.__file__).resolve() == source.resolve()
    assert source.read_bytes() == before
    assert result["restored_sources"]["src/jev_tune/baselines.py"] != audit.sha(before)


def test_current_tree_imports_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "jev_tune.external_fixture",
                        SimpleNamespace(__file__=str(ROOT / "src/jev_tune/baselines.py")))
    with pytest.raises(ValueError, match="leaked into historical audit"):
        audit.imported_sources(tmp_path)


def test_subprocess_failure_preserves_both_component_outcomes(monkeypatch):
    monkeypatch.setattr(audit, "build_view", lambda *args, **kwargs: None)
    report = {"ok": False, "checks": {
        "study": {"ok": False, "detail": "Original raw hash differs"},
        "reproduction": {"ok": True, "detail": "Original replay checked"}}}
    calls = []

    def failed_process(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, audit.MARKER + json.dumps(report) + "\n", "")

    monkeypatch.setattr(audit.subprocess, "run", failed_process)
    assert audit.check() == report
    assert len(calls) == 1


def test_claims_run_one_isolated_audit_and_keep_independent_failures(monkeypatch):
    claims = load_script("16_check_claims")
    calls = []
    report = {"ok": False, "checks": {
        "study": {"ok": False, "detail": "Original raw hash differs"},
        "reproduction": {"ok": True, "detail": "Original replay checked"}}}

    class FakeLoader(importlib.abc.Loader):
        def create_module(self, spec):
            return None

        def exec_module(self, module):
            if module.__name__ == "historical_research":
                def check(root):
                    calls.append(root)
                    return report
                module.check = check
            else:
                module.build_diagnosis = lambda root: {}
                module.same_evidence = lambda *args: True

    original = importlib.util.spec_from_file_location

    def specification(name, path, *args, **kwargs):
        if name in ("historical_research", "30_rollout_diagnosis"):
            return importlib.machinery.ModuleSpec(name, FakeLoader())
        return original(name, path, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "spec_from_file_location", specification)
    rows = claims.trajectory_evidence()
    assert len(calls) == 1
    assert [row["ok"] for row in rows] == [True, False, True]
    assert "Original raw hash differs" in rows[1]["detail"]
