"""Joint-risk evidence targets actual paired cost and never edits the action."""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

from jev_tune.primitives import fit_split_conformal
from jev_tune.risk import (JointRiskModel, joint_acceptance, paired_cost_labels,
                           risk_features, risk_report, select_joint_gains)


def test_noninferiority_uses_zero_tolerance_including_equality():
    j=np.array([1.,1.,1.])
    after=np.array([1.,np.nextafter(1.,2.),np.nextafter(1.,0.)])
    np.testing.assert_array_equal(paired_cost_labels(j,after),[0,1,0])
    with pytest.raises(ValueError,match='finite'):
        paired_cost_labels([1.],[np.nan])


def test_gate_preserves_entire_measured_joint_action_or_exact_current_gains():
    sets=np.array([[True,False],[False,True],[True,True],[False,False]])
    current=np.tile([.02,1.7,22.],(4,1))
    # Deliberately mixed-sign changes; the whole assessed action is accepted.
    candidate=current*np.array([1.2,.8,1.1])
    selected=select_joint_gains(current,candidate,sets)
    np.testing.assert_array_equal(joint_acceptance(sets),[True,False,False,False])
    np.testing.assert_array_equal(selected[0],candidate[0])
    np.testing.assert_array_equal(selected[1:],current[1:])
    with pytest.raises(ValueError,match='boolean'):
        joint_acceptance(sets.astype(int))


def test_harmful_execution_is_pointwise_subset_of_miscoverage_all_binary_sets():
    # All four possible sets crossed with both possible true labels.
    sets=np.repeat([[False,False],[True,False],[False,True],[True,True]],2,axis=0)
    labels=np.tile([0,1],4)
    current=np.ones(8);proposed=np.where(labels,1.01,.99)
    report=risk_report(np.full((8,2),.5),labels,sets,current,proposed)
    assert report['harmful_execution_subset_miscoverage']
    assert report['harmful_execution_count']==1
    assert report['miscoverage_count']==4
    assert report['conditional_harmful_rate']==.5
    assert report['unconditional_harmful_execution_rate']==.125
    assert report['selected_minus_current']['worse_count']==1


def test_risk_features_keep_all_axes_and_probabilities():
    state=np.zeros((2,20));step=np.array([[.1,-.2,.03],[-.1,.2,-.03]])
    probs=np.full((2,3,7),1/7)
    x=risk_features(state,step,probs)
    assert x.shape==(2,44)
    np.testing.assert_array_equal(x[:,20:23],step)
    with pytest.raises(ValueError,match='normalized'):
        risk_features(state,step,probs*2)


def test_independent_temperature_and_cp_do_not_refit_risk_model():
    rng=np.random.default_rng(532)
    train=rng.normal(size=(128,44));y=(train[:,0]+train[:,1]>.2).astype(int)
    model=JointRiskModel.fit(train,y)
    np.testing.assert_allclose(model.mean,train.mean(0))
    coefficient=model.coefficient.copy();mean=model.mean.copy()
    cp_x=rng.normal(size=(64,44));cp_y=(cp_x[:,0]+cp_x[:,1]>.2).astype(int)
    model.temperature=1.7
    cp=fit_split_conformal(model.probabilities(cp_x),cp_y,.1)
    eval_x=rng.normal(size=(32,44));labels=(eval_x[:,0]+eval_x[:,1]>.2).astype(int)
    probs=model.probabilities(eval_x);sets=cp.prediction_set(probs)
    report=risk_report(probs,labels,sets,np.ones(32),np.where(labels,1.1,.9))
    assert report['harmful_execution_subset_miscoverage']
    np.testing.assert_array_equal(model.coefficient,coefficient)
    np.testing.assert_array_equal(model.mean,mean)


def test_collection_measures_complete_current_and_proposal_once(monkeypatch):
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/'scripts'))
    spec=importlib.util.spec_from_file_location('joint_risk_script',root/'scripts/25_joint_risk.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    from jev_tune.decision import load_backend
    original=module.simulate;measured=[]
    def count(plants,gains,**kwargs):
        measured.append((plants.n,gains.copy()))
        return original(plants,gains,**kwargs)
    monkeypatch.setattr(module,'simulate',count)
    arrays,meta=module.collect_split(load_backend(root/'models'),3,82601)
    assert meta['simulation_counts']['total']==sum(n for n,_ in measured)==6
    assert len(measured)==2
    np.testing.assert_array_equal(measured[0][1],arrays['current_gains'])
    np.testing.assert_array_equal(measured[1][1],arrays['proposed_gains'])
    np.testing.assert_array_equal(arrays['labels'],(arrays['proposed_cost']>arrays['current_cost']).astype(int))
