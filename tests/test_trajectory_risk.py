"""Synthetic behavioral tests; no registered study cohort is sampled here."""
import json

import numpy as np
import pytest

import jev_tune.trajectory_risk as engine
from jev_tune.decode import ActionSpace, apply_step
from jev_tune.primitives import Answer, Choice, Noul, Option


class Plants:
    def __init__(self, ids):
        self.ids = np.asarray(ids, int)
        self.n = len(self.ids)
        self.noise_seed = self.ids + 100
        self.noise_sigma = np.zeros(self.n)

    def take(self, indices):
        return Plants(self.ids[indices])


class Proposal:
    space = ActionSpace()

    def __init__(self, *, only_kp=False, zero=False, option_index=6):
        self.only_kp, self.zero = only_kp, zero
        self.option_index = option_index
        self.inputs = []

    def answer(self, feats, curves):
        self.inputs.append(feats.copy())
        options = [Option(str(m), float(np.log10(m))) for m in self.space.multipliers]
        choices = []
        for axis in range(3):
            p = np.zeros((len(feats), 7))
            p[:, 3 if self.zero or (self.only_kp and axis) else self.option_index] = 1
            choices.append(Choice(str(axis), options, p))
        return Answer(choices, noul=Noul("healthy", np.ones(len(feats))))


class Risk:
    def __init__(self, rule=None):
        self.rule = rule or (lambda x: np.full(len(x), .1))
        self.inputs = []

    def probabilities(self, features):
        self.inputs.append(features.copy())
        harmful = self.rule(features)
        return np.column_stack([1 - harmful, harmful])


@pytest.fixture
def simulation(monkeypatch):
    calls = []

    def install(cost=lambda ids, gains: 1 / gains[:, 0], ku=5/3):
        def simulate(plants, gains, **kwargs):
            assert kwargs == {"horizon": 10., "ref": 1.}
            calls.append((plants.ids.copy(), gains.copy()))
            return {"metrics": np.column_stack([cost(plants.ids, gains), plants.ids]),
                    "y_curve": np.zeros((plants.n, 64)), "u_curve": np.zeros((plants.n, 64))}

        def state(metrics, y, u, gains, gzn, ku, tu, **kwargs):
            x = np.zeros((len(gains), 20))
            x[:, 0] = metrics[:, 1]
            x[:, 1] = kwargs["iteration"]
            x[:, 2] = kwargs["cost"]
            x[:, 3] = kwargs["prev_cost"]
            x[:, 4:7] = kwargs["prev_action"]
            x[:, 16] = (kwargs["prev_cost"] - kwargs["cost"]) / 5
            return x, np.zeros((len(gains), 2, 64))

        monkeypatch.setattr(engine, "simulate", simulate)
        monkeypatch.setattr(engine, "cost_from_metrics", lambda m, **kw: m[:, 0])
        monkeypatch.setattr(engine, "build_state", state)
        monkeypatch.setattr(engine, "ultimate_gain", lambda p: (np.full(p.n, ku), np.full(p.n, 2.)))
        return calls

    return install


def run(ids=(0,), *, proposal=None, risk=None, qhats=None, horizon=2, **kwargs):
    return engine.run_trajectory_risk(proposal or Proposal(), risk, Plants(ids), qhats,
                                      horizon=horizon, **kwargs)


def test_risk_history_fix_never_changes_base_proposal_input(simulation):
    simulation()
    proposal = Proposal(); model = Risk()
    r = run(proposal=proposal, risk=model, mode="monitor")
    assert proposal.inputs[0][0, 16] == -.2
    assert all(c["features"][16] == 0 for c in r["transitions"][0]["candidates"])
    assert r["transitions"][1]["features"][16] == proposal.inputs[1][0, 16] == .1
    legacy = run(risk=Risk(), mode="monitor", feature_mode="legacy")
    assert legacy["transitions"][0]["features"][16] == -.2
    assert legacy["per_plant"][0]["operating_history"] == r["per_plant"][0]["operating_history"]
    np.testing.assert_array_equal(proposal.inputs[0][0, 16], -.2)


def test_training_measures_all_candidates_but_follows_preassigned_behavior(simulation):
    calls = simulation()
    r = run(ids=(0, 1, 2), mode="training", horizon=1)
    assert sum(len(ids) for ids, _ in calls) == 12
    assert r["simulation_counts"]["executed"] == 3
    assert r["simulation_counts"]["diagnostic_training"] == 6
    assert len(r["collected"]["labels"]) == 9
    for i, (p, t) in enumerate(zip(r["per_plant"], r["transitions"])):
        assert p["behavior_index"] == t["selected_index"] == i
        assert p["current_gains"] == t["candidates"][i]["gains"]
        assert len(p["operating_history"]) == 2
        assert p["best_J"] == t["candidates"][i]["cost_after"]
        assert all(c["measured"] for c in t["candidates"])
    # The larger diagnostic move for behavior 1 would improve more, but is excluded.
    assert r["transitions"][1]["candidates"][0]["cost_after"] < r["per_plant"][1]["best_J"]
    json.dumps(r, allow_nan=False)


def test_min_risk_selection_precedes_cp_and_only_selected_action_is_measured(simulation):
    calls = simulation()
    model = Risk(lambda x: np.where(np.isclose(x[:, 20], np.log10(2) / 2), .05, .3))
    r = run(risk=model, mode="gated", selector="model_min_risk", qhats=[.1], horizon=1)
    t = r["transitions"][0]
    assert t["selected_index"] == 1 and t["prediction_set"] == [True, False]
    assert t["executed"]
    assert [c["measured"] for c in t["candidates"]] == [False, True, False]
    assert sum(len(ids) for ids, _ in calls) == 2
    np.testing.assert_array_equal(r["per_plant"][0]["current_gains"],
                                  apply_step(np.array(t["gains_before"]), np.array(t["base_step"]) * .5))


def test_min_risk_ties_choose_first_and_full_only_cannot_choose_cheaper_candidate(simulation):
    simulation()
    tied = run(risk=Risk(), mode="gated", selector="model_min_risk", qhats=[.2], horizon=1)
    assert tied["transitions"][0]["selected_index"] == 0
    full = run(risk=Risk(lambda x: x[:, 20]), mode="gated", selector="full_only", qhats=[.5], horizon=1)
    assert full["transitions"][0]["selected_index"] == 0


def test_collect_target_is_labeled_without_execution_and_uses_frozen_prefix(simulation):
    calls = simulation()
    r = run(risk=Risk(), mode="collect", selector="model_min_risk",
            qhats=[.2], collect_step=1)
    assert sum(len(ids) for ids, _ in calls) == 3
    assert r["collected"]["stage"] == [1]
    assert r["collected"]["labels"] == [0]
    assert np.asarray(r["collected"]["features"]).shape == (1, 44)
    t = r["transitions"][1]
    assert t["prediction_set"] is None and t["accepted"] is None
    assert t["measured"] and not t["executed"] and t["reason"] == "collected"
    assert r["per_plant"][0]["best_J"] == .5


def test_rejected_diagnostic_cannot_update_returned_best_or_operating_harm(simulation):
    simulation(lambda ids, gains: gains[:, 0])
    r = run(risk=Risk(lambda x: np.full(len(x), .9)), mode="gated", qhats=[.2, .2])
    t, p = r["transitions"][0], r["per_plant"][0]
    assert t["harmful"] and t["measured"] and not t["executed"]
    assert p["best_J"] == p["current_J"] == 1
    assert not p["any_harm"] and len(p["operating_history"]) == 1
    assert sum(c["measured"] for c in t["candidates"]) == 1


def test_exact_cache_deduplicates_bounded_candidates_and_adopts_only_when_selected(simulation):
    calls = simulation(ku=1500.)
    r = run(ids=(0, 1), proposal=Proposal(only_kp=True), mode="training", horizon=1)
    assert sum(len(ids) for ids, _ in calls) == 4  # initial + one distinct bounded candidate each
    assert len(r["collected"]["labels"]) == 2
    t, p = r["transitions"][1], r["per_plant"][1]
    assert [c["equivalent_to"] for c in t["candidates"]] == [0, 0, 0]
    assert t["selected_index"] == 1 and t["cache_hit"] and t["executed"]
    assert t["measurement_source_kind"] == "diagnostic_training"
    assert t["measurement_kind"] == "executed" and not t["simulation_performed"]
    assert p["simulation_counts"]["executed"] == 0
    assert p["simulation_counts"]["execution_requests"] == 1
    assert p["simulation_counts"]["cache_hits"] == 2
    assert p["simulation_counts"]["total"] == 2
    assert p["best_J"] == .001 and len(p["operating_history"]) == 2
    assert r["simulation_counts"]["requests"] == r["simulation_counts"]["total"] + r["simulation_counts"]["cache_hits"]


def test_cache_does_not_merge_nearby_but_bitwise_different_gains(simulation, monkeypatch):
    calls = simulation()
    neighbour = float(np.nextafter(np.float64(2.), np.float64(np.inf)))
    # This test exercises exact cache identity, not exp/log rounding. Supply
    # bounded candidates directly: stage 0 diagnoses 2, while plant 1 later
    # adopts its next representable neighbour through its fixed half-scale arm.
    kp_candidates = iter((2., 1.5, 1.25, 3., neighbour, 1.75))

    def fixed_bounded_candidates(gains, step):
        candidate = np.asarray(gains, dtype=np.float64).copy()
        candidate[:, 0] = next(kp_candidates)
        return candidate

    monkeypatch.setattr(engine, "apply_step", fixed_bounded_candidates)
    r = run(ids=(0, 1), proposal=Proposal(only_kp=True), mode="training")
    first = next(t for t in r["transitions"] if t["plant_index"] == 1 and t["stage"] == 0)
    second = next(t for t in r["transitions"] if t["plant_index"] == 1 and t["stage"] == 1)
    assert first["candidates"][0]["gains"][0] == 2.
    assert second["gains_proposed"][0] == neighbour != 2.
    assert second["gains_proposed"][0] == pytest.approx(2.)
    assert not second["cache_hit"] and second["simulation_performed"]
    assert second["measurement_id"] != first["candidates"][0]["measurement_id"]
    assert any(gain[0] == neighbour for ids, gains in calls for i, gain in zip(ids, gains) if i == 1)


def test_prior_diagnostic_enters_history_only_when_selected_at_a_later_stage(simulation):
    simulation()
    r = run(ids=(0, 1), proposal=Proposal(only_kp=True, option_index=4), mode="training")
    first, second = [t for t in r["transitions"] if t["plant_index"] == 1]
    diagnostic = first["candidates"][0]
    p = r["per_plant"][1]
    assert p["operating_history"][1]["cost"] > diagnostic["cost_after"]
    assert diagnostic["measurement_kind"] == "diagnostic_training"
    assert second["gains_proposed"] == diagnostic["gains"]
    assert second["executed"] and second["cache_hit"] and not second["simulation_performed"]
    assert second["measurement_source_stage"] == 0
    assert second["measurement_id"] == diagnostic["measurement_id"]
    assert p["operating_history"][2]["measurement_id"] == diagnostic["measurement_id"]
    assert p["best_J"] == diagnostic["cost_after"]
    assert p["simulation_counts"]["executed"] == 1
    assert p["simulation_counts"]["execution_requests"] == 2


def test_selected_unchanged_candidate_stops_without_cp_or_measurement(simulation):
    calls = simulation()
    r = run(proposal=Proposal(zero=True), risk=Risk(), mode="gated",
            selector="model_min_risk", qhats=[.2, .2])
    assert len(calls) == 1
    t = r["transitions"][0]
    assert t["selected_index"] == 0 and t["reason"] == "no_action"
    assert t["prediction_set"] is None and not t["measured"] and not t["executed"]


def test_selector_does_not_drop_unchanged_candidate_when_other_scales_move(simulation):
    calls = simulation()

    class TinyProposal(Proposal):
        def answer(self, feats, curves):
            answer = super().answer(feats, curves)
            p = np.zeros((len(feats), 7))
            p[:, 3], p[:, 6] = 1 - 5e-16, 5e-16
            answer.choice[0].probs = p
            return answer

    model = Risk(lambda x: .1 + np.abs(x[:, 20]) * 1e12)
    r = run(proposal=TinyProposal(only_kp=True), risk=model, mode="gated",
            selector="model_min_risk", qhats=[.2, .2])
    t = r["transitions"][0]
    assert t["candidates"][0]["changed"]
    assert not t["candidates"][t["selected_index"]]["changed"]
    assert t["reason"] == "no_action" and len(calls) == 1
    assert t["prediction_set"] is None


def test_output_is_compatible_with_existing_rollout_statistics(simulation):
    from jev_tune.sequential_risk import summarize_rollout

    simulation()
    r = run(mode="monitor")
    summary = summarize_rollout(r)
    assert summary["n_plants"] == 1 and summary["n_executed"] == 2
    assert summary["n_harmful"] == 0
    assert summary["simulation_counts"]["operating"] == 3
    assert summary["final_cost"]["mean"] == .25


def test_threshold_stops_without_rollback_and_training_diagnostics_cannot_trigger_it(simulation):
    simulation(lambda ids, gains: np.where(gains[:, 0] >= 2., 10., 1 / gains[:, 0]))
    r = run(ids=(0, 1), mode="training", horizon=1)
    assert r["per_plant"][0]["stop_reason"] == "safety_threshold"
    assert r["per_plant"][0]["best_J"] == 1.
    assert r["per_plant"][1]["stop_reason"] == "horizon"
    assert not r["per_plant"][1]["any_harm"]


def test_finite_failure_is_visible_and_empty_runs_do_not_measure(simulation):
    calls = simulation(lambda ids, gains: np.where(gains[:, 0] == 1., 1., np.nan))
    r = run(mode="monitor")
    assert r["per_plant"][0]["any_harm"] and r["per_plant"][0]["best_J"] == 1.
    assert r["transitions"][0]["cost_after"] is None
    assert not r["transitions"][0]["observed_finite"]
    before = len(calls)
    empty = run(ids=(), mode="training")
    assert len(calls) == before and empty["simulation_counts"]["total"] == 0
    json.dumps(r, allow_nan=False)
