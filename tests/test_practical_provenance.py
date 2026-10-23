"""Frozen practical evidence accepts newline conversions, not changed results."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("practical_provenance43",
    ROOT / "scripts/43_verify_practical_budget.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.fixture
def evidence(tmp_path):
    report = json.loads((ROOT / "research/results/practical_budget.json").read_text(encoding="utf-8"))
    paths = set(report["source_sha256"]) | set(report["model_sha256"])
    paths.update({"research/protocols/practical_budget_v090.json",
                  "research/results/practical_budget.json",
                  "research/results/practical_budget_raw.json.gz", "docs/PRACTICAL_BUDGET.md"})
    for name in paths:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


def test_actual_evidence_has_the_complete_protocol_roster():
    result = audit.check()
    assert result["ok"] and result["n_plants"] == 64
    assert [row["n"] for row in result["cohort_roster"]] == [12, 12] + [4] * 10
    assert result["existing_checker_errors"] == []


@pytest.mark.parametrize("name", ["scripts/39_practical_budget.py",
    "research/protocols/practical_budget_v090.json", "models/calibration.json"])
def test_only_recorded_newline_conversion_is_accepted(evidence, name):
    target = evidence / name
    original = target.read_bytes()
    lf = original.replace(b"\r\n", b"\n")
    report = json.loads((evidence / "research/results/practical_budget.json").read_text(encoding="utf-8"))
    expected = {**report["source_sha256"], **report["model_sha256"],
                "research/protocols/practical_budget_v090.json": report["protocol_sha256"]}
    # The checkout may itself have converted line endings. Always exercise the
    # representation differing from the recorded execution, on either OS.
    converted = next(value for value in (lf, lf.replace(b"\n", b"\r\n"))
                     if hashlib.sha256(value).hexdigest() != expected[name])
    target.write_bytes(converted)
    result = audit.check(root=evidence)
    assert result["ok"] and name in result["normalized_paths"]
    # Checking never rewrites the evidence or its original digest.
    assert target.read_bytes() == converted
    assert (evidence / "research/results/practical_budget.json").read_bytes() == (
        ROOT / "research/results/practical_budget.json").read_bytes()


@pytest.mark.parametrize("name,addition", [
    ("src/jev_tune/metrics.py", b"\n# changed semantics/source\n"),
    ("models/calibration.json", b" \n"),
    ("models/jev_head.pt", b"\r\n"),
    ("research/results/practical_budget_raw.json.gz", b"\r\n"),
    ("docs/PRACTICAL_BUDGET.md", b"\nUnsupported conclusion\n"),
])
def test_non_newline_changes_and_binary_changes_remain_failures(evidence, name, addition):
    target = evidence / name
    target.write_bytes(target.read_bytes() + addition)
    with pytest.raises(ValueError, match="Frozen practical checker failed"):
        audit.check(root=evidence)


def roster_fixture():
    protocol = {"n_plants": 8, "cohorts": [
        {"name": "two_mass", "n": 2}, {"name": "thermal_jitter", "n": 2},
        {"name": "out_of_zoo", "n": 4, "scenarios": ["scenario_a", "scenario_b"]}]}
    raw = {"cohorts": [
        {"name": "two_mass", "group": "two_mass", "plants": [0, 1]},
        {"name": "thermal_jitter", "group": "thermal_jitter", "plants": [0, 1]},
        {"name": "scenario_a", "group": "out_of_zoo", "plants": [0, 1]},
        {"name": "scenario_b", "group": "out_of_zoo", "plants": [0, 1]}]}
    return raw, protocol


@pytest.mark.parametrize("mutation", ["name", "group", "duplicate", "redistribute", "missing"])
def test_roster_rejects_same_total_but_wrong_protocol_allocation(mutation):
    raw, protocol = roster_fixture()
    assert audit.verify_roster(raw, protocol)
    if mutation == "name":
        raw["cohorts"][2]["name"] = "different_scenario"
    elif mutation == "group":
        raw["cohorts"][2]["group"] = "two_mass"
    elif mutation == "duplicate":
        raw["cohorts"][3] = copy.deepcopy(raw["cohorts"][2])
    elif mutation == "redistribute":
        raw["cohorts"][0]["plants"].append(raw["cohorts"][1]["plants"].pop())
    else:
        raw["cohorts"][2]["plants"].extend(raw["cohorts"].pop()["plants"])
    assert sum(len(row["plants"]) for row in raw["cohorts"]) == protocol["n_plants"]
    with pytest.raises(ValueError, match="cohort roster mismatch"):
        audit.verify_roster(raw, protocol)
