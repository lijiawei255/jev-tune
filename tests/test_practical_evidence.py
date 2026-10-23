"""Saved adapter evidence must fail closed when its source or log changes."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_adapter_evidence_and_research_preservation():
    assert load_script("40_verify_model_adaptation").check()["ok"]
    assert load_script("42_release_practical").check_preserved()["deployment_enabled"] is False


@pytest.mark.parametrize("mutation", ["source", "log", "result"])
def test_adapter_evidence_rejects_mutations(tmp_path, mutation):
    module = load_script("40_verify_model_adaptation")
    report = json.loads((ROOT / module.RESULT).read_text(encoding="utf-8"))
    for name in report["source_hashes"]:
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    if mutation == "source":
        path = tmp_path / "matlab/jev_metrics.m"
        path.write_text(path.read_text(encoding="utf-8") + "\n% changed metric\n", encoding="utf-8")
    elif mutation == "log":
        report["source_log"] += "not the recorded execution\n"
    else:
        report["test_results"]["unmeasured_success"] = True
    target = tmp_path / module.RESULT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(AssertionError):
        module.check(root=tmp_path)


@pytest.mark.parametrize("body", [
    "<!-- practical-mainline:en:start -->broken",
    "<!-- practical-mainline:en:end -->broken",
    "<!-- practical-mainline:en:end --><!-- practical-mainline:en:start -->",
    "<!-- practical-mainline:en:start --><!-- practical-mainline:en:start --><!-- practical-mainline:en:end -->",
])
def test_generated_status_rejects_broken_markers(body):
    module = load_script("41_sync_practical_docs")
    with pytest.raises(AssertionError):
        module.replace_section(body, "replacement", "en", "# heading")


def test_research_preservation_rejects_missing_manifest_entries(tmp_path):
    module = load_script("42_release_practical")
    payload = json.loads((ROOT / module.PRESERVED).read_text(encoding="utf-8"))
    payload["sha256"].pop(next(iter(payload["sha256"])))
    target = tmp_path / module.PRESERVED
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AssertionError, match="manifest"):
        module.check_preserved(root=tmp_path)


def test_research_preservation_accepts_only_newline_changes_in_text_log(tmp_path, monkeypatch):
    module = load_script("42_release_practical")
    manifest = json.loads((ROOT / module.PRESERVED).read_text(encoding="utf-8"))
    names = [name for name in manifest["sha256"] if Path(name).suffix == ".txt"]
    assert names == ["research/results/cohort_portability_sources/linux_evidence_log.txt"]
    name = names[0]
    target = tmp_path / name
    target.parent.mkdir(parents=True)
    lf = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
    target.write_bytes(lf.replace(b"\n", b"\r\n"))
    manifest_path = tmp_path / module.PRESERVED
    manifest_path.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / module.PRESERVED, manifest_path)
    original_digest = module.digest

    def view_digest(path):
        relative = Path(path).relative_to(tmp_path)
        # The two mutable fixture files are real copies; all other preserved
        # inputs are read from their unchanged repository locations.
        selected = path if relative.as_posix() in (name, module.PRESERVED) else ROOT / relative
        return original_digest(selected)

    monkeypatch.setattr(module, "digest", view_digest)
    assert module.check_preserved(root=tmp_path)["sha256"][name] == manifest["sha256"][name]
    target.write_bytes(target.read_bytes() + b"changed historical evidence\r\n")
    with pytest.raises(AssertionError, match="Historical evidence changed"):
        module.check_preserved(root=tmp_path)


def test_baseline_text_log_comparison_normalizes_newlines_only(monkeypatch):
    module = load_script("42_release_practical")
    manifest = json.loads((ROOT / module.PRESERVED).read_text(encoding="utf-8"))
    name = "research/results/cohort_portability_sources/linux_evidence_log.txt"
    expected = manifest["sha256"][name]
    lf = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
    monkeypatch.setattr(module, "check_preserved", lambda: {"sha256": {name: expected}})
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kwargs: lf.replace(b"\n", b"\r\n"))
    module.check_baseline()
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kwargs: lf + b"changed\n")
    with pytest.raises(AssertionError, match="differs from v0.8.0"):
        module.check_baseline()


@pytest.mark.parametrize("suffix", [".json.gz", ".pt"])
def test_binary_preservation_hashes_do_not_normalize_newlines(tmp_path, suffix):
    module = load_script("42_release_practical")
    path = tmp_path / ("binary" + suffix)
    path.write_bytes(b"\x00binary\ncontent\x00")
    before = module.digest(path)
    path.write_bytes(b"\x00binary\r\ncontent\x00")
    assert module.digest(path) != before
