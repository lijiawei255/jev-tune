"""Joint rollout accounting separates operating trajectories from diagnostics."""
import json

import numpy as np
import pytest

import jev_tune.joint_rollout as rollout
from jev_tune.decode import ActionSpace
from jev_tune.primitives import Answer, Choice, Noul, Option


class Plants:
    def __init__(self, ids):
        self.ids = np.asarray(ids, int)
        self.n = len(ids)
        self.noise_seed = self.ids + 123
        self.noise_sigma = np.zeros(self.n)

    def take(self, indices):
        return Plants(self.ids[indices])


class Proposal:
    space = ActionSpace()

    def __init__(self, zero_ids=()):
        self.zero_ids = zero_ids
        self.states = []

    def answer(self, feats, curves):
        self.states.append(feats.copy())
        p = np.zeros((len(feats), self.space.k))
        p[np.arange(len(feats)), np.where(np.isin(feats[:, 0], self.zero_ids), 3, 6)] = 1.
        options = [Option(str(m), float(np.log10(m))) for m in self.space.multipliers]
        return Answer([Choice(name, options, p) for name in ("Kp", "Ki", "Kd")],
                      noul=Noul("healthy", np.ones(len(feats))))


class Risk:
    def __init__(self, reject_ids=()):
        self.reject_ids = reject_ids
        self.inputs = []

    def probabilities(self, features):
        self.inputs.append(features.copy())
        harmful = np.where(np.isin(features[:, 0], self.reject_ids), .9, .1)
        return np.column_stack([1 - harmful, harmful])


@pytest.fixture
def simulation(monkeypatch):
    calls = []

    def install(cost=lambda ids, gains: 1 / gains[:, 0]):
        def simulate(plants, gains, **kwargs):
            assert kwargs == {"horizon": 10., "ref": 1.}
            calls.append((plants.ids.copy(), gains.copy()))
            return {"metrics": np.column_stack([cost(plants.ids, gains), plants.ids]),
                    "y_curve": np.zeros((plants.n, 64)), "u_curve": np.zeros((plants.n, 64))}

        def state(metrics, y, u, gains, gzn, ku, tu, **kwargs):
            f = np.zeros((len(gains), 20))
            f[:, 0] = metrics[:, 1]
            f[:, 1] = kwargs["iteration"]
            f[:, 2] = kwargs["cost"]
            f[:, 3] = kwargs["prev_cost"]
            f[:, 4:7] = kwargs["prev_action"]
            return f, np.zeros((len(gains), 2, 64))

        monkeypatch.setattr(rollout, "simulate", simulate)
        monkeypatch.setattr(rollout, "cost_from_metrics", lambda m, **kw: m[:, 0])
        monkeypatch.setattr(rollout, "build_state", state)
        monkeypatch.setattr(rollout, "ultimate_gain", lambda p: (np.full(p.n, 5/3), np.full(p.n, 2.)))
        return calls

    return install


def run(ids=(0,), *, proposal=None, risk=None, horizon=3, qhats=None, **kwargs):
    return rollout.run_joint_rollout(proposal or Proposal(), risk or Risk(), Plants(ids),
                                     [.2] * horizon if qhats is None else qhats,
                                     horizon=horizon, **kwargs)


def test_monitor_executes_full_actions_while_reporting_rejecting_shadow_sets(simulation):
    calls = simulation()
    proposal = Proposal()
    r = run(proposal=proposal, risk=Risk(reject_ids=[0]), mode="monitor")
    assert len(calls) == 4 and sum(len(ids) for ids, _ in calls) == 4
    assert r["simulation_counts"] == dict(operating_initial=1, executed=3,
        diagnostic_rejected=0, diagnostic_collected=0, operating=4, total=4)
    assert all(t["executed"] and not t["accepted"] and t["measured"] for t in r["transitions"])
    assert all(t["prediction_set"] == [False, True] for t in r["transitions"])
    p = r["per_plant"][0]
    assert p["best_J"] == p["current_J"] == pytest.approx(.125)
    np.testing.assert_allclose(p["best_gains"], [8., 8., 2.], rtol=1e-14)
    assert p["stop_reason"] == "horizon" and not p["any_harm"]
    # Second proposal actually sees the first response and applied action.
    second = proposal.states[1][0]
    np.testing.assert_allclose(second[1:7], [1., .5, 1., *([np.log10(2.)] * 3)])
    json.dumps(r, allow_nan=False)


@pytest.mark.parametrize("diagnostic", [True, False])
def test_rejection_diagnostic_cannot_improve_operating_state_or_returned_gains(simulation, diagnostic):
    calls = simulation()
    r = run(risk=Risk(reject_ids=[0]), mode="gated", diagnostic=diagnostic)
    p, t = r["per_plant"][0], r["transitions"][0]
    assert len(calls) == 1 + diagnostic
    assert p["best_J"] == p["current_J"] == 1.
    assert len(p["operating_history"]) == 1
    assert p["best_gains"] == p["initial_gains"]
    assert not p["any_harm"] and p["stop_reason"] == "risk_rejected"
    assert t["proposal_valid"] and not t["executed"] and t["measured"] == diagnostic
    assert t["cost_after"] == (.5 if diagnostic else None)
    assert r["simulation_counts"]["diagnostic_rejected"] == int(diagnostic)


def test_collect_uses_only_frozen_prefix_and_target_labels_are_not_executed(simulation):
    calls = simulation()
    r = run(ids=(0, 1), risk=Risk(reject_ids=[1]), mode="collect", collect_step=1,
            qhats=[.2], diagnostic=False)
    assert [ids.tolist() for ids, _ in calls] == [[0, 1], [0], [0]]
    assert r["simulation_counts"] == dict(operating_initial=2, executed=1,
        diagnostic_rejected=0, diagnostic_collected=1, operating=3, total=4)
    assert r["collected"]["plant_index"] == [0]
    assert r["collected"]["labels"] == [0]
    assert np.asarray(r["collected"]["features"]).shape == (1, 44)
    assert r["collected"]["current_cost"] == [.5]
    assert r["collected"]["proposed_cost"] == [.25]
    assert r["per_plant"][0]["best_J"] == .5
    target = [t for t in r["transitions"] if t["stage"] == 1][0]
    assert target["prediction_set"] is None and target["accepted"] is None
    assert target["measured"] and not target["executed"]
    assert target["measurement_kind"] == "diagnostic_collected"
    assert len({(t["plant_index"], t["stage"]) for t in r["transitions"]}) == len(r["transitions"])


def test_no_action_stops_before_risk_or_collection_and_other_plants_continue(simulation):
    calls = simulation()
    risk = Risk()
    r = run(ids=(0, 1), proposal=Proposal(zero_ids=[0]), risk=risk, mode="gated")
    assert [ids.tolist() for ids, _ in calls] == [[0, 1], [1], [1], [1]]
    assert all(x[:, 0].tolist() == [1.] for x in risk.inputs)
    t = r["transitions"][0]
    assert t["reason"] == "no_action" and t["proposal_valid"]
    assert not t["measured"] and not t["executed"] and t["prediction_set"] is None
    assert r["per_plant"][0]["simulation_counts"]["total"] == 1
    collected = run(proposal=Proposal(zero_ids=[0]), mode="collect", collect_step=0, qhats=[])
    assert collected["collected"]["labels"] == []


def test_threshold_stops_without_uncalibrated_rollback_and_best_is_measured(simulation):
    calls = simulation(lambda ids, gains: np.where(gains[:, 0] == 1., 1., 10.))
    r = run(mode="gated")
    assert len(calls) == 2
    p, t = r["per_plant"][0], r["transitions"][0]
    assert p["stop_reason"] == "safety_threshold"
    assert p["current_J"] == 10. and p["best_J"] == 1.
    assert p["best_gains"] == p["initial_gains"]
    assert p["any_harm"] and p["any_harm_gt2pct"]
    assert t["label"] == 1 and t["reason"] == "executed_safety_threshold"


def test_initial_instability_has_no_proposal_and_nonfinite_executed_cost_fails_closed(simulation):
    calls = simulation(lambda ids, gains: np.full(len(ids), 50.))
    r = run(mode="gated")
    assert len(calls) == 1
    assert r["per_plant"][0]["stop_reason"] == "unstable"
    assert not r["transitions"][0]["proposal_valid"]
    simulation(lambda ids, gains: np.where(gains[:, 0] == 1., 1., np.nan))
    r = run(mode="gated")
    assert r["per_plant"][0]["any_harm"]
    assert not r["transitions"][0]["observed_finite"]
    assert r["transitions"][0]["cost_after"] is None
    assert r["per_plant"][0]["best_J"] == 1.
    json.dumps(r, allow_nan=False)
    simulation(lambda ids, gains: np.full(len(ids), np.nan))
    invalid_start = run(mode="gated")
    assert invalid_start["per_plant"][0]["any_harm"]
    assert not invalid_start["per_plant"][0]["best_valid"]
    assert invalid_start["per_plant"][0]["current_J"] is None
    assert not invalid_start["transitions"][0]["proposal_valid"]


@pytest.mark.parametrize("q", [1., np.inf])
def test_full_label_set_holds_and_empty_population_is_valid(simulation, q):
    simulation()
    r = run(qhats=[q] * 3, mode="gated", diagnostic=False)
    assert r["transitions"][0]["prediction_set"] == [True, True]
    assert not r["transitions"][0]["executed"]
    assert r["simulation_counts"]["total"] == 1
    empty = run(ids=(), qhats=[q] * 3)
    assert empty["per_plant"] == [] and empty["simulation_counts"]["total"] == 0
    json.dumps(r, allow_nan=False)


def test_zero_tolerance_harm_is_distinct_from_two_percent_harm(simulation):
    simulation(lambda ids, gains: np.where(gains[:, 0] == 1., 1., 1.01))
    r = run(horizon=1, mode="gated")
    assert r["per_plant"][0]["any_harm"]
    assert not r["per_plant"][0]["any_harm_gt2pct"]
    assert r["transitions"][0]["label"] == 1


def test_rejected_harmful_diagnostic_does_not_count_as_operating_harm(simulation):
    simulation(lambda ids, gains: gains[:, 0])
    r = run(risk=Risk(reject_ids=[0]), mode="gated")
    assert r["transitions"][0]["harmful"]
    assert not r["transitions"][0]["executed"]
    assert not r["per_plant"][0]["any_harm"]
    assert r["per_plant"][0]["current_J"] == 1.


def test_calibration_score_ties_are_included_without_subtraction_roundoff(simulation):
    simulation()

    class BoundaryRisk:
        def probabilities(self, features):
            return np.tile([.3, .7], (len(features), 1))

    r = run(risk=BoundaryRisk(), qhats=[.7], horizon=1, mode="gated", diagnostic=False)
    assert r["transitions"][0]["prediction_set"] == [True, True]
    assert not r["transitions"][0]["executed"]


def test_real_simulator_returned_best_cost_belongs_to_the_returned_gains():
    from pathlib import Path
    from jev_tune.decision import load_backend
    from jev_tune.metrics import cost_from_metrics
    from jev_tune.plants import sample_plants, simulate
    from jev_tune.risk import JointRiskModel

    root = Path(__file__).resolve().parents[1]
    spec = json.loads((root / "research/results/joint_risk.json").read_text())["risk_model"]
    risk = JointRiskModel(np.array(spec["mean"]), np.array(spec["scale"]),
                          np.array(spec["coefficient"]), spec["intercept"], spec["temperature"])
    plants = sample_plants(3, seed=82603)
    r = rollout.run_joint_rollout(load_backend(root / "models"), risk, plants,
                                  [.3, .3], horizon=2, mode="monitor")
    measured = simulate(plants, np.array([p["best_gains"] for p in r["per_plant"]]))
    j = cost_from_metrics(measured["metrics"], y_curve=measured["y_curve"])
    np.testing.assert_allclose(j, [p["best_J"] for p in r["per_plant"]], rtol=0, atol=1e-12)
    assert sum(p["simulation_counts"]["total"] for p in r["per_plant"]) == r["simulation_counts"]["total"]
    assert r["simulation_counts"]["executed"] == sum(t["executed"] for t in r["transitions"])
    assert all(p["best_J"] <= p["initial_J"] for p in r["per_plant"])
    json.dumps(r, allow_nan=False)
