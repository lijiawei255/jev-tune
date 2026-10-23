"""Real evaluation accounting and transparent baseline failure, without MATLAB."""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

from jev_tune import baselines, identified, matlab_baseline
from jev_tune.plants import make_plant


@pytest.mark.parametrize("budget", [1, 2, 3, 4, 8, 20])
def test_simplex_measures_start_and_obeys_small_budget_and_bounds(monkeypatch, budget):
    plants = make_plant([1.], [.2, 1.])
    measured = []
    def evaluate(p, gains):
        measured.extend(gains.copy())
        return np.sum(gains, axis=1)
    monkeypatch.setattr(baselines, "_eval", evaluate)
    result = baselines.run_simplex(plants, np.array([[1e3, 1e-4, .3]]), budget=budget)
    all_gains = np.asarray(measured)
    assert len(measured) == budget
    assert np.array_equal(all_gains[0], [1e3, 1e-4, .3])
    assert np.all((all_gains >= 1e-4) & (all_gains <= 1e3))
    assert result.eval_axis.tolist() == list(range(1, budget+1))
    assert result.best_j[0] == np.sum(result.gains[0]) == np.sum(all_gains, axis=1).min()


def test_simplex_batch_contractions_can_win_even_for_other_plants(monkeypatch):
    p = make_plant([1.], [.2, 1.]).take([0, 0])
    # Plant 0 accepts the reflection; plant 1 requests a contraction. A real
    # batch-wide contraction produces an incidental best sample for plant 0.
    values = iter([[10, 10], [9, 9], [8, 8], [7, 7], [6, 20], [1, 15]])
    calls = []
    def evaluate(plants, gains):
        calls.append(gains.copy())
        return np.asarray(next(values), float)
    monkeypatch.setattr(baselines, "_eval", evaluate)
    result = baselines.run_simplex(p, np.ones((2, 3)), budget=6)
    assert result.best_j.tolist() == [1., 7.]
    assert np.array_equal(result.gains[0], calls[5][0])


def test_simplex_rejects_zero_budget_without_simulation(monkeypatch):
    monkeypatch.setattr(baselines, "_eval", lambda *a: pytest.fail("unexpected simulation"))
    with pytest.raises(ValueError, match="positive"):
        baselines.run_simplex(make_plant([1], [1, 1]), np.ones((1, 3)), budget=0)


@pytest.mark.parametrize("available, gains, expected_count, status", [
    (False, np.ones((1, 3)), 0, "unavailable"),
    (True, np.array([[np.nan, 1., 1.]]), 1, "failed_design"),
])
def test_identify_does_not_replace_unavailable_or_invalid_design_with_oracle(monkeypatch, available, gains, expected_count, status):
    monkeypatch.setattr(matlab_baseline, "matlab_available", lambda: available)
    monkeypatch.setattr(matlab_baseline, "pidtune_gains", lambda *a: (gains, 0.))
    monkeypatch.setattr(baselines, "zn_gains", lambda *a: pytest.fail("oracle fallback"))
    monkeypatch.setattr(identified, "_eval", lambda *a: pytest.fail("invalid verification"))
    with pytest.raises(identified.IdentificationUnavailable) as exc:
        identified.run_identify_pidtune(make_plant([1.], [.2, 1.]))
    assert exc.value.status == status
    assert exc.value.simulations_per_plant == expected_count


@pytest.mark.parametrize("kwargs", [{"u_max": .1}, {"dead_zone": .1}, {"noise_sigma": .01}])
def test_linear_identification_rejects_unimplemented_probe_physics(monkeypatch, kwargs):
    monkeypatch.setattr(matlab_baseline, "matlab_available", lambda: True)
    monkeypatch.setattr(identified, "open_loop_step", lambda *a: pytest.fail("unsupported probe"))
    with pytest.raises(identified.IdentificationUnavailable) as exc:
        identified.run_identify_pidtune(make_plant([1.], [.2, 1.], **kwargs))
    assert exc.value.status == "unsupported_probe_physics"
    assert exc.value.simulations_per_plant == 0


def test_benchmark_uses_actual_head_counts_and_separate_output_directory():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root/"scripts"))
    spec = importlib.util.spec_from_file_location("benchmark03", root/"scripts/03_evaluate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from types import SimpleNamespace
    result = SimpleNamespace(actual_simulations=np.array([2, 7]), eval_axis=np.arange(1, 21))
    assert module.actual_simulation_counts(result).tolist() == [2, 7]
    assert module.default_table_path("new-run", "thermal_deadtime") == Path("new-run/benchmark_table_thermal_deadtime.md")
