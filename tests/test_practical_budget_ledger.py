"""Raw accounting and failures remain visible in the descriptive budget study."""
import copy
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
spec = importlib.util.spec_from_file_location("practical39", ROOT/"scripts/39_practical_budget.py")
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


def fixture():
    protocol = {"methods": ["jev_head", "vocab_hill"], "budgets": [2], "n_plants": 1,
        "shared_start": [.6, 1.2, .075], "gain_bounds": [.0001, 1000],
        "accounting": {"maximum_simulations": 4}}
    physical = {"test": True}
    identity = study.hashlib.sha256(study.canonical(physical)).hexdigest()
    trials = [{"gains": [.6, 1.2, .075], "J": 1., "failed": False, "diverged": False},
        {"gains": [1., 1., 1.], "J": 50., "failed": True, "diverged": True}]
    row = {"index": 0, "trials": trials, "actual_calls": 2, "reported_calls": 2,
        "returned_gains": trials[0]["gains"], "returned_J": 1.}
    raw = {"cohorts": [{"name": "example", "group": "out_of_zoo", "plants": [{"id": identity, "physical": physical}]}],
        "runs": [{"cohort": "example", "method": method, "budget": 2,
                  "plants": [copy.deepcopy(row)], "simulation_batches": [[0], [0]]}
                 for method in protocol["methods"]]}
    return raw, protocol


def test_ledger_retains_divergent_trial_while_returning_best():
    raw, protocol = fixture()
    result = study.summarize(raw, protocol)
    head = next(r for r in result["rows"] if r["group"] == "all" and r["method"] == "jev_head")
    assert result["actual_simulations"] == 4
    assert head["final_J_mean"] == 1
    assert head["plants_with_divergent_trial"] == 1
    assert head["returned_divergent_plants"] == 0
    assert head["plants_with_trial_worse_than_start"] == 1


@pytest.mark.parametrize("change", ["calls", "gain", "best", "pair", "duplicate"])
def test_ledger_rejects_false_budget_pairing_or_measured_best(change):
    raw, protocol = fixture()
    row = raw["runs"][0]["plants"][0]
    if change == "calls":
        row["reported_calls"] = 1
    elif change == "gain":
        row["trials"][1]["gains"][0] = 1001
    elif change == "best":
        row["returned_J"] = .5
    elif change == "pair":
        raw["runs"][1]["plants"][0]["trials"][0]["J"] = 1.1
    else:
        raw["runs"].append(copy.deepcopy(raw["runs"][0]))
    with pytest.raises(ValueError):
        study.summarize(raw, protocol)


def test_capture_counts_actual_batched_simulations_without_remeasurement():
    from types import SimpleNamespace
    from jev_tune.plants import make_plant, simulate
    p = make_plant([1.], [.2, 1.])
    module = SimpleNamespace(simulate=simulate)
    with study.capture_simulations(module, p) as (trials, batches):
        module.simulate(p.take([0, 0]), np.array([[.6, 1.2, .075], [1., 1., .1]]))
    assert module.simulate is simulate
    assert len(trials[0]) == 2
    assert batches == [[0, 0]]
    assert all(np.isfinite(t["J"]) for t in trials[0])
