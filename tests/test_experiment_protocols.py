"""Acceptance tests for measured costs, matched controls and calibration units."""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from _experiment_protocol import expectation_preserving_probs, training_indices
from jev_tune.decode import ActionSpace, AbstainPolicy, apply_abstention, decode_choice


def script(name):
    spec = importlib.util.spec_from_file_location('experiment_'+name, ROOT/'scripts'/name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_continuous_regression_adapter_does_not_quantize_the_prediction():
    space = ActionSpace()
    x = np.array([[-.2, .2, .03], [-.6, 0., .6]])
    probs = expectation_preserving_probs(x, space.deltas)
    decoded = decode_choice(probs, space, shrinkage=0.)
    expected = np.clip(x, space.deltas[0], space.deltas[-1])
    np.testing.assert_allclose(decoded, expected, atol=1e-14)
    np.testing.assert_allclose(probs.sum(axis=-1), 1.)
    assert np.all(probs >= 0)


def test_regression_training_split_excludes_the_same_calibration_states():
    module = script('17_ablation.py')
    from jev_tune.expert import ExpertData
    n = 20
    data = ExpertData(**{key:np.arange(n) for key in
        ('feats','curves','choice','score','noul','cost','act_state','act_delta','act_cost','act_best')})
    subset, train, calibration = module.regression_training_subset(data)
    expected = np.random.default_rng(0).permutation(n)
    np.testing.assert_array_equal(train, expected[:18])
    np.testing.assert_array_equal(subset.feats, expected[:18])
    assert not set(subset.feats) & set(calibration)


def test_temperature_threshold_selection_matches_the_runtime_joint_mask():
    module = script('22_calibrate_only.py')
    # Very confident first axes, uncertain second/third axes: the old mean
    # confidence selector and all-axis report disagreed on precisely this case.
    p = np.array([[[.95,.05],[.52,.48],[.51,.49]],
                  [[.8,.2],[.52,.48],[.51,.49]],
                  [[.7,.3],[.52,.48],[.51,.49]],
                  [[.6,.4],[.52,.48],[.51,.49]],
                  [[.55,.45],[.52,.48],[.51,.49]]])
    tau = module.pick_tau(p, .6)
    confidence = p.max(axis=-1)
    d = apply_abstention(np.ones_like(confidence), confidence, np.ones(len(p)),
                         AbstainPolicy(tau, max(0.,tau-.1)))
    actual = (~d.held).any(axis=-1).mean()
    assert actual == pytest.approx(.6)
    assert module.runtime_coverage(p,tau) == actual


def test_temperature_reconstruction_matches_checkpoint_backend_without_tail_floor():
    module = script('22_calibrate_only.py')
    from jev_tune.decision import load_backend, NumericBackend
    loaded = load_backend(ROOT/'models')
    # Fix the test's source temperature while using the real checkpoint, so
    # recalibrating the released model cannot turn this into an underflow test.
    backend = NumericBackend(loaded.model, space=loaded.space,
                             temperature=np.ones(3), calibrate=True)
    rng = np.random.default_rng(31)
    feats = rng.standard_normal((10,20))
    curves = rng.standard_normal((10,2,64))
    source = np.stack([c.probs for c in backend.answer(feats,curves).choice],axis=1)
    changed = NumericBackend(backend.model, space=backend.space,
                             temperature=backend.temperature*4., calibrate=True)
    target = np.stack([c.probs for c in changed.answer(feats,curves).choice],axis=1)
    assert source.min() > 0  # No information has been lost to underflow here.
    assert source.min() < 1e-12
    np.testing.assert_allclose(module.transformed_probs(source,4.),target,
                               atol=1e-14,rtol=1e-12)
    transformed = module.transformed_probs(np.array([[0.,1e-150,1.]]),4.)
    assert transformed[0,0] == 0
    assert 0 < transformed[0,1] < 1e-30
    np.testing.assert_allclose(transformed.sum(axis=-1),1.)


def test_random_control_preserves_joint_masks_and_does_not_read_outcomes():
    module = script('20_abstention.py')
    masks = np.array([[[False,True,True],[False,False,False]],
                      [[True,True,True],[True,False,True]]])
    provider = module.shuffled_mask_provider(masks,23)
    shuffled = np.stack([provider(None,k,np.arange(2)) for k in range(2)],axis=1)
    original_counts = np.unique(masks.reshape(-1,3),axis=0,return_counts=True)
    new_counts = np.unique(shuffled.reshape(-1,3),axis=0,return_counts=True)
    for a,b in zip(original_counts,new_counts):
        np.testing.assert_array_equal(a,b)


@pytest.mark.parametrize('name,render',[
    ('17_ablation.py','_doc'),('20_abstention.py','_doc'),
    ('22_calibrate_only.py','_doc'),('26_cp_diagnosis.py','render'),
])
def test_new_harm_documents_refuse_to_relabel_historical_numbers(name,render):
    module=script(name)
    with pytest.raises(ValueError,match='historical'):
        getattr(module,render)({})


def test_counterfactual_harm_uses_zero_tolerance_with_separate_legacy_count():
    module=script('26_cp_diagnosis.py')
    after=np.array([1.,np.nextafter(1.,np.inf),1.01,1.02,np.nextafter(1.02,np.inf)])
    result=module.paired_outcomes(after,np.ones(5),np.ones(5,dtype=bool))
    assert result['harmful_count']==4
    assert result['harmful_gt_2pct_count']==result['harm_more_than_2pct_count']==1


def test_performance_diagnosis_uses_exact_new_counts_and_rejects_old_reports():
    module=script('27_cp_performance_diagnosis.py')
    from jev_tune.evaluate import HARM_METRIC
    report={'harm_metric':dict(HARM_METRIC),'n_decisions':3,'n_executed':3,
            'n_harmful':2,'n_harmful_gt_2pct':1,'harmful_rate':.667,
            'improvement_rate':1/3,'partial_hold_rate':0.,'axis_coverage':1.,'n_rollbacks':0}
    actual=module.exposure([report])
    assert actual['harmful_count']==2 and actual['harmful_gt_2pct_count']==1
    assert actual['harmful_per_executed']==2/3
    assert actual['harmful_gt_2pct_per_executed']==1/3
    with pytest.raises(ValueError,match='historical'):
        module.exposure([{k:v for k,v in report.items() if k!='harm_metric'}])


def test_failed_sweep_uses_one_shared_non_oracle_prior():
    module = script('03_evaluate.py')
    ku,tu,ok = module.sweep_prior(np.array([np.nan,4.,0.]),np.array([1.,2.,np.nan]))
    np.testing.assert_array_equal(ku,[1.,4.,1.])
    np.testing.assert_array_equal(tu,[1.,2.,1.])
    np.testing.assert_array_equal(ok,[False,True,False])


def test_expert_reports_every_actual_simulated_plant(monkeypatch):
    from jev_tune import expert
    from jev_tune.plants import sample_plants
    plants = sample_plants(3,seed=7)
    actual = []
    original = expert.simulate
    def measured(p,*args,**kwargs):
        actual.append(p.n)
        return original(p,*args,**kwargs)
    monkeypatch.setattr(expert,'simulate',measured)
    data,*_ = expert.generate(plants,steps=2,verbose=False)
    counts = data.simulation_counts
    assert counts['total'] == sum(actual)
    assert counts['single_axis_candidates'] == 3*2*21
    assert counts['total'] == sum(v for k,v in counts.items() if k!='total')


def test_calibration_collect_uses_one_measurement_per_transition_plus_start(monkeypatch):
    module = script('22_calibrate_only.py')
    from jev_tune import evaluate
    from jev_tune.decision import load_backend
    from jev_tune.plants import sample_plants
    original = evaluate.simulate
    actual = []
    def measured(p,*args,**kwargs):
        actual.append(p.n)
        return original(p,*args,**kwargs)
    monkeypatch.setattr(evaluate,'simulate',measured)
    original_evaluate = module.evaluate_head
    def cp_off_collection(*args, **kwargs):
        # This diagnostic changes T without refitting qhat; never silently
        # inherit the backend's now-default conformal policy.
        assert 'conformal' in kwargs and kwargs['conformal'] is None
        return original_evaluate(*args, **kwargs)
    monkeypatch.setattr(module,'evaluate_head',cp_off_collection)
    plants = sample_plants(2,seed=7)
    probs,labels,account = module.collect(load_backend(ROOT/'models'),plants,steps=3,seed=0)
    assert account['simulations'] == sum(actual) == 2*(3+1)
    assert len(probs) == len(labels) == account['recorded_samples']
    assert len(probs) + account['rollback_transitions'] == 2*3
