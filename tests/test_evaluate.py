"""Accounting tests for the closed-loop evaluator.

These exist because version 0.3 reported a cost that did not belong to the
gains it returned (the last experiment updated ``best_cost`` but not
``best_gains``).  The four properties below are the contract the README quotes.
"""

import numpy as np
import pytest

from jev_tune.decode import ActionSpace, decode_answer, decode_choice
from jev_tune.evaluate import evaluate_head
from jev_tune.metrics import cost_from_metrics
from jev_tune.plants import make_plant, simulate
from jev_tune.primitives import Answer, Choice, Noul, Option, Score


class _Stub:
    """A backend with a fixed answer distribution (no torch, deterministic)."""

    def __init__(self, *, band: int = 2, p_true: float = 0.0, opts=None):
        self.space = ActionSpace()
        self.probs = np.asarray(
            opts if opts is not None else np.full(self.space.k, 1.0 / self.space.k),
            dtype=float,
        )
        self.band = band
        self.p_true = p_true

    def answer(self, feats, curves, questions=None) -> Answer:
        n = np.asarray(feats).shape[0]
        probs = np.tile(self.probs, (n, 1))
        choices = [
            Choice(
                question=f"step:{a}",
                options=[
                    Option(f"x{m:g}", float(np.log10(m)))
                    for m in self.space.multipliers
                ],
                probs=probs,
            )
            for a in ("Kp", "Ki", "Kd")
        ]
        dist = np.zeros((n, len(LEVELS)))
        dist[:, self.band] = 1.0
        return Answer(
            choice=choices,
            score=Score("quality", list(LEVELS), dist),
            noul=Noul("healthy", np.full(n, self.p_true)),
        )


LEVELS = ("a", "b", "c", "d", "e")


def _plants(n=5):
    p = make_plant([1.0], [0.5, 1.0, 0.0])
    return p.take(np.zeros(n, dtype=int))


def _gnz(plants):
    # a start that is neither optimal nor divergent, so the loop actually moves
    g = np.tile(np.array([[1.6, 0.8, 0.02]]), (plants.n, 1))
    return g, g[:, 0].copy(), np.full(plants.n, 3.0)


def test_reported_cost_belongs_to_returned_gains():
    plants = _plants()
    gzn, ku, tu = _gnz(plants)
    stub = _Stub()
    r = evaluate_head(stub, plants, gzn, ku, tu, budget=8, seed=0)
    res = simulate(plants, r.gains)
    j = cost_from_metrics(res["metrics"], y_curve=res["y_curve"])
    assert np.allclose(j, r.best_j), "best_j must be the cost of the returned gains"


def test_history_is_monotone_and_ends_at_best_j():
    plants = _plants()
    gzn, ku, tu = _gnz(plants)
    r = evaluate_head(
        _Stub(),
        plants,
        gzn,
        ku,
        tu,
        budget=10,
        seed=0,
    )
    assert r.history.shape == (plants.n, 10)
    assert np.all(np.diff(r.history, axis=1) <= 1e-12), "best-so-far cannot get worse"
    assert np.allclose(r.history[:, -1], r.best_j)


def test_budget_is_spent_exactly_once_per_plant():
    plants = _plants(3)
    gzn, ku, tu = _gnz(plants)
    r = evaluate_head(_Stub(), plants, gzn, ku, tu, budget=7, seed=0)
    assert r.budget == 7
    assert r.eval_axis.tolist() == list(range(1, 8))
    assert r.sims_per_plant == 7.0


def test_legacy_iters_means_iters_plus_one_experiments():
    plants = _plants(3)
    gzn, ku, tu = _gnz(plants)
    r = evaluate_head(_Stub(), plants, gzn, ku, tu, iters=6, seed=0)
    assert r.budget == 7 and r.history.shape[1] == 7


def test_early_stop_fires_only_in_the_best_band():
    plants = _plants(3)
    gzn, ku, tu = _gnz(plants)
    hi = evaluate_head(
        _Stub(band=0, p_true=0.99),
        plants,
        gzn,
        ku,
        tu,
        budget=10,
        early_stop=True,
        seed=0,
    )
    lo = evaluate_head(
        _Stub(band=4, p_true=0.99),
        plants,
        gzn,
        ku,
        tu,
        budget=10,
        early_stop=True,
        seed=0,
    )
    off = evaluate_head(
        _Stub(band=0, p_true=0.99),
        plants,
        gzn,
        ku,
        tu,
        budget=10,
        early_stop=False,
        seed=0,
    )
    assert np.all(hi.stop_iter == 1), (
        "band 0 + healthy must stop after the first experiment"
    )
    assert np.all(lo.stop_iter == 10), "the worst band must not stop the loop"
    assert np.all(off.stop_iter == 10)
    # stopping freezes the gains: every later best-so-far equals the first
    assert np.allclose(hi.history[:, 1:], hi.history[:, :1])


def test_gate_does_not_fire_on_a_well_behaved_loop():
    plants = _plants(3)
    gzn, ku, tu = _gnz(plants)
    stub = _Stub()
    on = evaluate_head(stub, plants, gzn, ku, tu, budget=6, safety_gate=True, seed=0)
    off = evaluate_head(stub, plants, gzn, ku, tu, budget=6, safety_gate=False, seed=0)
    assert int(on.rollbacks.sum()) == 0
    assert np.allclose(on.best_j, off.best_j)


def test_decode_answer_matches_decode_choice():
    rng = np.random.default_rng(3)
    space = ActionSpace()
    probs = rng.dirichlet(np.ones(space.k), size=(2, 3))
    answer = Answer(
        choice=[
            Choice(
                "q",
                [Option(f"x{m:g}", float(np.log10(m))) for m in space.multipliers],
                probs[:, i],
            )
            for i in range(3)
        ]
    )
    assert np.allclose(decode_answer(answer, space), decode_choice(probs, space))
    assert np.allclose(
        decode_answer(answer, space, use_expectation=False),
        decode_choice(probs, space, use_expectation=False),
    )


# --------------------------------------------------------------------------- #
# Explicit abstention: it must be wired into the loop, not just available
# --------------------------------------------------------------------------- #


class _Confident(_Stub):
    """A stub whose answer is one-hot on the 'hold' option (p_max = 1)."""

    def __init__(self):
        opts = np.zeros(ActionSpace().k)
        opts[ActionSpace().multipliers.index(1.00)] = 1.0
        super().__init__(opts=opts, band=2, p_true=0.9)


def test_abstention_holds_when_confidence_is_low():
    from jev_tune.decode import AbstainPolicy, decide

    plants = _plants(3)
    gzn, ku, tu = _gnz(plants)
    # a uniform distribution has p_max = 1/7 ~ 0.14, below tau_act
    r = evaluate_head(
        _Stub(),
        plants,
        gzn,
        ku,
        tu,
        budget=6,
        seed=0,
        abstain=AbstainPolicy(tau_act=0.6, tau_esc=0.4),
    )
    assert np.allclose(r.gains, gzn), "every axis must be held at the start gains"
    report = r.decision_report()
    assert report["coverage"] == 0.0
    assert report["abstain_rate"] == 1.0


def test_abstention_executes_when_confidence_is_high():
    plants = _plants(3)
    gzn, ku, tu = _gnz(plants)
    from jev_tune.decode import AbstainPolicy

    r = evaluate_head(
        _Confident(),
        plants,
        gzn,
        ku,
        tu,
        budget=6,
        seed=0,
        abstain=AbstainPolicy(tau_act=0.6),
    )
    report = r.decision_report()
    assert report["coverage"] == 1.0
    assert report["abstain_rate"] == 0.0


def test_default_loop_abstains_on_a_low_confidence_backend():
    plants = _plants(3)
    gzn, ku, tu = _gnz(plants)
    # the shipped default is AbstainPolicy(tau_act=0.35); a uniform answer has
    # p_max = 1/7, so every axis is held
    r = evaluate_head(_Stub(), plants, gzn, ku, tu, budget=6, seed=0)
    assert np.allclose(r.gains, gzn), "the default policy must hold when unsure"
    assert r.decision_report()["abstain_rate"] == 1.0


def test_abstention_can_be_disabled_explicitly():
    plants = _plants(3)
    gzn, ku, tu = _gnz(plants)
    r = evaluate_head(_Stub(), plants, gzn, ku, tu, budget=6, seed=0, abstain=None)
    assert not np.allclose(r.gains, gzn), "with abstain=None the loop must move"
    assert r.decision_report()["abstain_rate"] == 0.0


def test_abstention_reason_codes():
    from jev_tune.decode import (
        AbstainPolicy,
        REASON_ACT,
        REASON_ESCALATE,
        REASON_LOW_CONFIDENCE,
        REASON_NOUL,
        decide,
    )

    space = ActionSpace()
    opts = [Option(f"x{m:g}", float(np.log10(m))) for m in space.multipliers]
    probs = np.full((1, space.k), 1.0 / space.k)  # p_max = 0.143

    def _ans(p, noul):
        return Answer(
            choice=[Choice("q", opts, p) for _ in range(3)],
            score=Score("s", list(LEVELS), np.full((1, 5), 0.2)),
            noul=Noul("h", np.array([noul])),
        )

    d = decide(_ans(probs, 0.9), space, abstain=AbstainPolicy(0.6, 0.4))
    assert d.reason[0, 0] == REASON_ESCALATE and d.held.all()
    assert np.all(d.step == 0.0)

    d = decide(_ans(probs, 0.9), space, abstain=AbstainPolicy(0.10, 0.05))
    assert d.reason[0, 0] == REASON_ACT and not d.held.any()

    d = decide(
        _ans(probs, 0.05), space, abstain=AbstainPolicy(0.10, 0.05, tau_noul=0.5)
    )
    assert d.reason[0, 0] == REASON_NOUL and d.held.all()

    d = decide(_ans(probs, 0.9), space, abstain=None)
    assert d.reason[0, 0] == REASON_ACT and not d.held.any()
