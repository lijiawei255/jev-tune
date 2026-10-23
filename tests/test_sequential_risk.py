"""Statistical boundaries of the frozen sequential protocol, without data tuning."""
import importlib.util
from pathlib import Path
import math

import numpy as np
import pytest

from jev_tune.sequential_risk import stage_calibration, binomial_bounds, acceptance_checks


def test_small_stage_keeps_all_labels_instead_of_relaxing_alpha():
    for n in (0,1,198):
        result=stage_calibration(np.tile([.999,.001],(n,1)),np.zeros(n,int),.005)
        assert result['qhat']==1. and result['all_labels_fallback']
        assert result['quantile_rank']==n+1
    enough=stage_calibration(np.tile([.999,.001],(199,1)),np.zeros(199,int),.005)
    assert enough['quantile_rank']==199 and not enough['all_labels_fallback']


def test_stage_uses_exact_finite_sample_order_statistic_with_ties():
    scores=np.linspace(0,1,512)
    p=np.column_stack([1-scores,scores])
    result=stage_calibration(p,np.zeros(512,int),.005)
    assert result['quantile_rank']==511
    assert result['qhat']==scores[510]
    assert np.count_nonzero((1-p[:,0])<=result['qhat'])==511
    assert math.fsum([.005]*20)==.1


@pytest.mark.parametrize('p,y', [([[1.1,-.1]],[0]), ([[.5,.6]],[1]), ([[.5,.5]],[2]), ([[.5,.5]],[.2])])
def test_invalid_calibration_inputs_cannot_create_a_certificate(p,y):
    with pytest.raises(ValueError):
        stage_calibration(p,y,.005)


def test_binomial_bounds_exact_endpoints_and_fixed_denominator():
    zero=binomial_bounds(0,1024)
    assert zero['lower']==0
    assert zero['upper']==pytest.approx(1-.05**(1/1024))
    all_events=binomial_bounds(1024,1024)
    assert all_events['upper']==1
    assert all_events['lower']==pytest.approx(.05**(1/1024))
    with pytest.raises(ValueError):
        binomial_bounds(0,0)


def test_all_hold_cannot_pass_nontrivial_execution_gate():
    monitor={'final_cost':{'mean':1.,'p90':2.},'simulation_counts':{'operating':200}}
    gated={'final_cost':{'mean':1.,'p90':2.},'simulation_counts':{'operating':100},
           'trajectory_harm':binomial_bounds(0,1024),'first_stage_execution':binomial_bounds(0,1024)}
    result=acceptance_checks(monitor,gated,True)
    assert not result['passed']
    assert result['failed']==['first_stage_execution_lower']
    gated['first_stage_execution']=binomial_bounds(1024,1024)
    gated['final_cost']['mean']=1.000001
    assert 'empirical_mean_cost_noninferior' in acceptance_checks(monitor,gated,True)['failed']
    assert not acceptance_checks(monitor,gated,False)['checks']['integrity']


def test_registered_protocol_matches_sources_without_collecting_data():
    root=Path(__file__).resolve().parents[1]
    import sys,json
    sys.path.insert(0,str(root/'scripts'))
    spec=importlib.util.spec_from_file_location('rollout_study',root/'scripts/29_joint_risk_rollout.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    protocol=json.loads(module.PROTOCOL.read_text(encoding='utf-8'))
    assert module.fixed_specification()==protocol['specification']
    seeds=protocol['specification']['calibration']['seeds']
    assert len(seeds)==len(set(seeds))==20
    assert protocol['specification']['evaluation']['seed'] not in seeds
