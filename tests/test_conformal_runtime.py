"""The online CP veto is distinct from numeric step selection and safety."""
import numpy as np
import pytest

from jev_tune.decode import AbstainPolicy, ConformalPolicy, decide
from jev_tune.primitives import Answer, Choice, Noul, Option


def decision(p, q=.7, *, kmax=3, noul=.9, abstain=None, mode="hard_hold"):
    return decide(Answer([Choice('offset', [Option('down', -.1), Option('zero', 0), Option('up', .1)], np.array(p))],
                         noul=Noul('valid', noul)), shrinkage=0,
                  conformal=ConformalPolicy((q,), k_max=kmax, mode=mode), abstain=abstain)


@pytest.mark.parametrize('p,q,kmax,reason', [
    ([.3, .4, .3], .1, 3, 4),
    ([.3, .4, .3], 1., 2, 5),
    ([.5, 0., .5], .6, 3, 6),
])
def test_ambiguous_sets_hold_before_actuation(p, q, kmax, reason):
    d=decision(p,q,kmax=kmax)
    assert d.step[0] == 0 and d.held[0] and d.escalate[0]
    assert d.reason[0] == reason


def test_compact_set_uses_full_distribution_not_conditional_distribution():
    d=decision([.2,.1,.7], .35)
    assert d.set_size[0] == 1 and not d.held[0]
    assert d.step[0] == pytest.approx(.05)
    assert d.conformal_set[0].tolist() == [False,False,True]


def test_zero_option_and_exact_boundary_are_not_abstention():
    d=decision([0.,1.,0.], .2)
    assert d.step[0] == 0 and not d.held[0]
    d=decision([.3,.7,0.], 1-.3)
    assert d.set_size[0] == 2 and not d.held[0]


def test_singleton_zero_label_does_not_truncate_tail_expectation():
    d=decision([.01,.8,.19], .3)
    assert d.set_size[0] == 1 and d.conformal_set[0].tolist() == [False,True,False]
    assert not d.held[0] and d.step[0] == pytest.approx(.018)


def test_noul_override_has_priority_and_sets_are_still_auditable():
    d=decision([.5,0.,.5],.6,noul=.1,abstain=AbstainPolicy(0,0,.5))
    assert d.reason[0] == 3 and d.held[0] and d.set_size[0] == 2


def test_per_axis_coverage_does_not_mean_joint_action_guarantee():
    with pytest.raises(ValueError,match='number of axes'):
        decide(Answer([Choice('q',[Option('a',0)],np.array([1.]))]),conformal=ConformalPolicy((.8,.8)))


def test_cp_disabled_keeps_legacy_decode_and_empty_metadata():
    d=decide(Answer([Choice('q',[Option('a',0)],np.array([1.]))]))
    assert not d.conformal_applied and d.set_size[0] == 0
    assert not d.conformal_set[0].any()
    assert d.conformal_mode == "off"
    assert not d.conformal_would_hold.any() and not d.conformal_reason.any()


@pytest.mark.parametrize('p,q,kmax,reason', [
    ([.2, .3, .5], .1, 3, 4),
    ([.2, .3, .5], 1., 2, 5),
    ([.4, 0., .6], .6, 3, 6),
])
def test_monitor_preserves_actions_but_retains_the_complete_hard_hold_evidence(p, q, kmax, reason):
    plain = decide(Answer([Choice('offset', [Option('down', -.1), Option('zero', 0), Option('up', .1)],
                                  np.array(p))], noul=Noul('valid', .9)), shrinkage=0)
    monitor = decision(p, q, kmax=kmax, mode="monitor")
    hard = decision(p, q, kmax=kmax, mode="hard_hold")
    for field in ("step", "proposed", "held", "escalate", "reason", "confidence"):
        np.testing.assert_array_equal(getattr(monitor, field), getattr(plain, field))
    assert monitor.conformal_mode == "monitor"
    assert monitor.conformal_would_hold.tolist() == [True]
    assert monitor.conformal_reason.tolist() == [reason]
    assert hard.step.tolist() == [0.]
    for field in ("conformal_set", "set_size", "conformal_would_hold", "conformal_reason"):
        np.testing.assert_array_equal(getattr(monitor, field), getattr(hard, field))


@pytest.mark.parametrize("mode", ["monitor", "hard_hold"])
def test_noul_override_and_cp_reason_remain_separate(mode):
    d = decision([.4, 0., .6], .6, noul=.1, abstain=AbstainPolicy(0, 0, .5), mode=mode)
    assert d.reason.tolist() == [3]
    assert d.held.all() and d.step.tolist() == [0.]
    assert d.conformal_reason.tolist() == [6]
    assert d.conformal_would_hold.all()


def test_calibration_without_mode_defaults_to_monitor_and_explicit_mode_is_validated(tmp_path):
    import json
    from jev_tune.decision import read_conformal

    data = {"split_conformal": {"qhat_per_axis": [.8], "alpha": .1, "k_max": 3}}
    assert ConformalPolicy((.8,)).mode == "monitor"
    assert ConformalPolicy.from_calibration(data).mode == "monitor"
    (tmp_path / "calibration.json").write_text(json.dumps(data), encoding="utf-8")
    assert read_conformal(tmp_path).mode == "monitor"
    assert read_conformal(tmp_path, mode="hard_hold").mode == "hard_hold"
    with pytest.raises(ValueError, match="mode"):
        ConformalPolicy((.8,), mode="unknown")
    with pytest.raises(ValueError, match="mode"):
        read_conformal(tmp_path, mode="unknown")
