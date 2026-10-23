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
