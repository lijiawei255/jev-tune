"""Behavioural regression tests for measured transitions and shared budgets."""

import numpy as np
import pytest

import jev_tune.baselines as baselines
import jev_tune.evaluate as evaluator
from jev_tune.decode import ActionSpace
from jev_tune.primitives import Answer, Choice, Noul, Option, Score


class Plants:
    def __init__(self, ids):
        self.ids = np.asarray(ids)
        self.n = len(self.ids)

    def take(self, indices):
        return Plants(self.ids[indices])


class Policy:
    def __init__(self, partial=False, stop_first=False):
        self.partial = partial
        self.stop_first = stop_first

    def answer(self, feats, curves, questions=None):
        space = ActionSpace()
        options = [Option(f"x{m:g}", float(np.log10(m))) for m in space.multipliers]
        p = np.zeros((len(feats), space.k))
        p[:, -1] = 1
        choices = [
            Choice(name, options, np.ones_like(p) / space.k if self.partial and axis else p)
            for axis, name in enumerate(("Kp", "Ki", "Kd"))
        ]
        score = np.zeros((len(feats), 5))
        bands = np.where((feats[:, 0] == 0) & self.stop_first, 0, 2)
        score[np.arange(len(feats)), bands] = 1
        return Answer(choices, Score("quality", list("abcde"), score), Noul("healthy", np.ones(len(feats))))


@pytest.fixture
def simulation(monkeypatch):
    calls = []

    def install(cost):
        def simulate(plants, gains, **kwargs):
            calls.append((plants.ids.copy(), gains.copy()))
            return {
                "metrics": np.column_stack([cost(plants.ids, gains), plants.ids]),
                "y_curve": np.zeros((plants.n, 64)),
                "u_curve": np.zeros((plants.n, 64)),
            }

        def state(metrics, y, u, gains, *args, **kwargs):
            feats = np.zeros((len(gains), 20))
            feats[:, 0] = metrics[:, 1]
            return feats, np.zeros((len(gains), 2, 64))

        monkeypatch.setattr(evaluator, "simulate", simulate)
        monkeypatch.setattr(evaluator, "build_state", state)
        monkeypatch.setattr(evaluator, "cost_from_metrics", lambda m, **kw: m[:, 0])
        return calls

    return install


def run(ids=(0,), policy=None, **kwargs):
    p = Plants(ids)
    return evaluator.evaluate_head(
        policy or Policy(), p, np.ones((p.n, 3)), np.ones(p.n), np.ones(p.n),
        budget=kwargs.pop("budget", 3), **kwargs,
    )


def test_each_action_has_one_real_outcome_and_final_gain_cost_match(simulation):
    calls = simulation(lambda ids, g: 1 / g[:, 0])
    r = run()
    assert len(calls) == 3
    assert np.array_equal(r.gains, [[4, 4, 4]])
    assert np.array_equal(r.best_j, [0.25])
    assert r.decisions["valid"].tolist() == [[True, True]]
    assert r.decisions["cost_before"].tolist() == [[1, 0.5]]
    assert r.decisions["after"].tolist() == [[0.5, 0.25]]
    report = r.decision_report()
    assert report["n_decisions"] == 2
    assert report["improvement_rate"] == 1
    assert report["ece"] == 0
    assert np.array_equal(r.trajectory["gains"][:, 1:], r.decisions["gains_after"])


def test_harmful_rate_is_not_diluted_by_self_comparisons(simulation):
    simulation(lambda ids, g: g[:, 0])
    report = run().decision_report()
    assert report["n_decisions"] == 2
    assert report["harmful_rate"] == 1
    assert report["improvement_rate"] == 0


def test_partial_axis_hold_counts_the_executed_transition(simulation):
    simulation(lambda ids, g: 1 / g[:, 0])
    r = run(policy=Policy(partial=True))
    assert np.array_equal(r.gains, [[4, 1, 1]])
    assert not r.decisions["held"].any()
    assert r.decisions["axis_held"].tolist() == [[[False, True, True]] * 2]
    report = r.decision_report()
    assert report["coverage"] == 1
    assert report["axis_coverage"] == pytest.approx(1 / 3)
    assert report["partial_hold_rate"] == 1
    assert report["n_actions"] == 2
    assert report["improvement_rate"] == 1


def test_rollback_does_not_change_unrelated_plants_or_policy_labels(simulation):
    simulation(lambda ids, g: np.where(ids == 0, np.where(g[:, 0] > 1.5, 100, 1), 10 / g[:, 0]))
    batch = run(ids=(0, 1))
    alone = run(ids=(1,))
    assert np.array_equal(batch.trajectory["gains"][1], alone.trajectory["gains"][0])
    assert np.array_equal(batch.trajectory["cost"][1], alone.trajectory["cost"][0])
    assert batch.rollbacks.tolist() == [1, 0]
    assert batch.decisions["event"].tolist() == [["proposal", "rollback"], ["proposal", "proposal"]]
    assert batch.decisions["gains_before"][0, 1].tolist() == [2, 2, 2]
    assert batch.decisions["gains_after"][0, 1].tolist() == [.6, .6, .6]
    report = batch.decision_report()
    assert report["n_transitions"] == 4
    assert report["n_decisions"] == 3
    assert report["n_rollbacks"] == 1
    assert report["harmful_rate"] == pytest.approx(1 / 3)


def test_early_stop_removes_only_stopped_plants_from_real_simulations(simulation):
    calls = simulation(lambda ids, g: 1 / g[:, 0])
    r = run(ids=(0, 1), policy=Policy(stop_first=True), budget=4, early_stop=True, sims_already_spent=7)
    assert [ids.tolist() for ids, _ in calls] == [[0, 1], [1], [1], [1]]
    assert sum(len(ids) for ids, _ in calls) == 5
    assert r.actual_simulations.tolist() == [8, 11]
    assert r.stop_iter.tolist() == [8, 11]
    assert r.measurement_counts.tolist() == [[8, 8, 8, 8], [8, 9, 10, 11]]
    assert r.trajectory["measured"].tolist() == [[True, False, False, False], [True] * 4]
    assert r.decisions["valid"].tolist() == [[False] * 3, [True] * 3]
    assert r.decision_report()["n_decisions"] == 3
    assert r.sims_per_plant == 9.5
    assert r.sims_to_target(np.array([1, .25])).tolist() == [8, 10]


def test_all_stopped_has_no_fictitious_transitions(simulation):
    calls = simulation(lambda ids, g: 1 / g[:, 0])
    r = run(policy=Policy(stop_first=True), budget=6, early_stop=True)
    assert len(calls) == 1
    assert r.actual_simulations.tolist() == [1]
    assert np.array_equal(r.history, np.ones((1, 6)))
    report = r.decision_report()
    assert report["n_decisions"] == 0
    assert report["n_transitions"] == 0
    assert report["ece"] is None


def test_external_hold_changes_only_execution_not_proposals_or_confidence(simulation):
    simulation(lambda ids, g: 1 / g[:, 0])
    base = run()
    held = run(hold_mask_provider=lambda decision, k, ids: np.ones_like(decision.held))
    assert np.array_equal(held.gains, [[1, 1, 1]])
    assert np.array_equal(held.decisions["proposed"], base.decisions["proposed"])
    assert np.array_equal(held.decisions["choice_probs"], base.decisions["choice_probs"])
    assert held.decision_report()["coverage"] == 0
    assert held.decision_report()["n_actions"] == 0


def test_command_clipped_at_gain_bound_is_not_an_applied_action(simulation):
    simulation(lambda ids, g: 1 / g[:, 0])
    r = evaluator.evaluate_head(
        Policy(), Plants([0]), np.full((1, 3), 1e3), np.ones(1), np.ones(1), budget=3,
    )
    assert (r.decisions["step"] > 0).all()
    assert (r.decisions["applied_step"] == 0).all()
    assert r.decision_report()["coverage"] == 1
    assert r.decision_report()["n_actions"] == 0


def test_opt_in_value_filter_runs_with_trainable_parameters():
    torch = pytest.importorskip("torch")
    from jev_tune.model import ValueNet

    value = ValueNet()
    assert all(p.requires_grad for p in value.parameters())
    decision, _ = evaluator._propose(
        Policy(), value, np.zeros((2, 20)), np.zeros((2, 2, 64)), ActionSpace(),
        use_value_filter=True,
    )
    assert decision.step.shape == (2, 3)
    assert np.isfinite(decision.step).all()
    assert all(p.grad is None for p in value.parameters())


@pytest.mark.parametrize("sim_kwargs", [{}, {"horizon": 2.0, "ref": 0.5}])
def test_runtime_cost_and_policy_state_use_the_actual_simulation_scale(sim_kwargs):
    from jev_tune.metrics import cost_from_metrics
    from jev_tune.plants import simulate
    from jev_tune.scenarios import make_plant
    from jev_tune.state import build_state

    class RecordingPolicy(Policy):
        def answer(self, feats, curves, questions=None):
            self.feats, self.curves = feats.copy(), curves.copy()
            return super().answer(feats, curves, questions)

    plants = make_plant([1.], [.5, 1., 0.])
    gains = np.array([[1.6, .8, .02]])
    ku = tu = np.ones(1)
    policy = RecordingPolicy()
    result = evaluator.evaluate_head(
        policy, plants, gains, ku, tu, budget=2, **sim_kwargs,
    )
    initial = simulate(plants, gains, **sim_kwargs)
    j = cost_from_metrics(initial["metrics"], y_curve=initial["y_curve"], **sim_kwargs)
    feats, curves = build_state(
        initial["metrics"], initial["y_curve"], initial["u_curve"],
        gains, gains, ku, tu, cost=j, **sim_kwargs,
    )
    np.testing.assert_array_equal(policy.feats, feats)
    np.testing.assert_array_equal(policy.curves, curves)
    np.testing.assert_array_equal(result.trajectory["cost"][:, 0], j)
    final = simulate(plants, result.gains, **sim_kwargs)
    expected = cost_from_metrics(final["metrics"], y_curve=final["y_curve"], **sim_kwargs)
    np.testing.assert_array_equal(result.best_j, expected)


@pytest.mark.parametrize("sim_kwargs", [{}, {"horizon": 2.0, "ref": 0.5}])
def test_expert_cost_and_training_state_use_the_actual_simulation_scale(sim_kwargs):
    from jev_tune.expert import generate
    from jev_tune.metrics import cost_from_metrics
    from jev_tune.plants import sample_plants, simulate, ultimate_gain
    from jev_tune.state import build_state

    plants = sample_plants(2, seed=5)
    data, gains, final_j, gzn = generate(plants, steps=1, verbose=False, **sim_kwargs)
    initial_gains = np.clip(gzn, 1e-4, 1e3)
    initial = simulate(plants, initial_gains, **sim_kwargs)
    j = cost_from_metrics(initial["metrics"], y_curve=initial["y_curve"], **sim_kwargs)
    ku, tu = ultimate_gain(plants)
    feats, curves = build_state(
        initial["metrics"], initial["y_curve"], initial["u_curve"],
        initial_gains, gzn, ku, tu, cost=j, **sim_kwargs,
    )
    np.testing.assert_array_equal(data.feats, feats)
    np.testing.assert_array_equal(data.curves, curves)
    np.testing.assert_array_equal(data.cost, j.astype(np.float32))
    final = simulate(plants, gains, **sim_kwargs)
    expected = cost_from_metrics(final["metrics"], y_curve=final["y_curve"], **sim_kwargs)
    np.testing.assert_array_equal(final_j, expected)


@pytest.mark.parametrize("method", [baselines.run_cmaes, baselines.run_bo])
@pytest.mark.parametrize("budget", [1, 3, 7])
def test_baseline_measures_common_start_within_exact_budget(monkeypatch, method, budget):
    calls = []
    start = np.ones((2, 3))

    def objective(plants, gains):
        calls.append(gains.copy())
        return np.square(np.log10(gains)).sum(axis=-1)

    monkeypatch.setattr(baselines, "_eval", objective)
    r = method(Plants([0, 1]), start, budget=budget)
    assert np.array_equal(calls[0], start)
    assert sum(len(g) for g in calls) == 2 * budget
    assert r.eval_axis[0] == 1
    assert r.eval_axis[-1] == budget
    assert np.array_equal(r.history[:, 0], [0, 0])
    assert np.array_equal(r.gains, start)
    assert np.array_equal(r.best_j, [0, 0])


@pytest.mark.parametrize("method", [baselines.run_cmaes, baselines.run_bo])
def test_baseline_returns_the_measured_winner_not_distribution_mean(monkeypatch, method):
    calls = []
    target = np.array([.17, -.13, .08])

    def objective(plants, gains):
        calls.extend(gains.copy())
        return np.square(np.log10(gains) - target).sum(axis=-1)

    monkeypatch.setattr(baselines, "_eval", objective)
    r = method(Plants([0, 1]), np.ones((2, 3)), budget=11, seed=8)
    assert np.allclose(r.best_j, np.square(np.log10(r.gains) - target).sum(axis=-1))
    for gain in r.gains:
        assert any(np.array_equal(gain, seen) for seen in calls)


def test_grid_returns_gains_for_its_reported_best_cost(monkeypatch):
    monkeypatch.setattr(baselines, "_eval", lambda p, g: np.square(g[:, 0] - .5))
    r = baselines.run_grid(Plants([0]), np.ones((1, 3)), kp=(.5, 1), ki=(1,), kd=(1,))
    assert np.array_equal(r.gains, [[.5, 1, 1]])
    assert np.array_equal(r.best_j, [0])
