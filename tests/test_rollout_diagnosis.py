"""Post-hoc diagnostics must follow measured paths, not fitted conclusions."""
import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('rollout_diagnosis',ROOT/'scripts/30_rollout_diagnosis.py')
diagnosis=importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnosis)


def plant(i,costs):
    history=[{'stage':j-1,'gains':[float(j+1)]*3,'cost':float(c),'observed_finite':True}
             for j,c in enumerate(costs)]
    return {'plant_index':i,'plant_identity':100+i,'best_J':min(costs),'operating_history':history}


def test_fixed_path_certificate_counts_only_improvement_after_first_harm():
    # Plant 0 needs a harmful transition for its final best. Plant 2 need not
    # cross its harmful transition because its final best was already present.
    monitor={'per_plant':[plant(0,[3.,4.,1.]),plant(1,[5.,4.,3.]),plant(2,[2.,3.,2.])]}
    gated={'per_plant':[plant(0,[3.]),plant(1,[5.,4.]),plant(2,[2.])]}
    result=diagnosis.fixed_path_diagnosis(monitor,gated,.1)
    assert result['mandatory_harm_plants']==1
    assert result['minimum_empirical_trajectory_harm_rate']==1/3
    assert result['conservative_mean_gap_lower_bound_under_risk_cap']==2/3
    assert result['gap_lower_bound_minus_roundoff']>.66
    assert result['joint_criteria_infeasible_on_recorded_paths']
    assert result['mandatory_plants'][0]['first_harm_history_index']==1


def test_fixed_path_certificate_refuses_changed_actions_and_fake_best():
    monitor={'per_plant':[plant(0,[3.,4.,1.])]}
    gated={'per_plant':[plant(0,[3.,4.])]}
    changed=copy.deepcopy(gated)
    changed['per_plant'][0]['operating_history'][1]['gains'][0]=999.
    with pytest.raises(ValueError,match='prefix'):
        diagnosis.fixed_path_diagnosis(monitor,changed,.1)
    changed=copy.deepcopy(gated);changed['per_plant'][0]['best_J']=.1
    with pytest.raises(ValueError,match='min of the executed'):
        diagnosis.fixed_path_diagnosis(monitor,changed,.1)


def test_safe_but_confidently_misclassified_point_can_drive_shared_q_and_hold_all():
    p=np.tile([.999,.001],(245,1))
    p[-1]=[.00001,.99999]
    result=diagnosis.score_diagnosis(p,np.zeros(245,dtype=int),.005,
        np.ones(245),np.full(245,.9),np.arange(245))
    assert result['quantile_rank']==245 and not result['all_labels_fallback']
    assert result['tail'][0]['label']==0
    assert result['qhat']==pytest.approx(.99999)
    assert result['calibration_admitted_noninferior']==0
    assert result['calibration_rejected_noninferior']==245


def test_reached_minimum_does_not_imply_useful_admission():
    p=np.tile([.5,.5],(199,1));labels=np.zeros(199,dtype=int)
    result=diagnosis.score_diagnosis(p,labels,.005,np.ones(199),np.ones(199),np.arange(199))
    assert result['quantile_rank']==199 and result['qhat']==.5
    assert not result['all_labels_fallback']
    assert result['calibration_admitted_noninferior']==0
    short=diagnosis.score_diagnosis(p[:198],labels[:198],.005,np.ones(198),np.ones(198),np.arange(198))
    assert short['all_labels_fallback'] and short['qhat']==1.


def test_labels_are_checked_against_actual_full_action_costs():
    with pytest.raises(ValueError,match='zero-tolerance'):
        diagnosis.score_diagnosis(np.array([[.9,.1]]),np.array([0]),.005,
            np.array([1.]),np.array([np.nextafter(1.,np.inf)]),np.array([0]))


def test_same_evidence_preserves_exact_counts_but_allows_roundoff():
    assert diagnosis.same_evidence({'n':700,'q':.99},{'n':700,'q':.99+1e-15})
    assert not diagnosis.same_evidence({'n':699,'q':.99},{'n':700,'q':.99})
    assert not diagnosis.same_evidence({'n':700.,'q':.99},{'n':700,'q':.99})


def test_published_diagnosis_recomputes_from_tracked_evidence_without_training_npz():
    # This parses the published raw trace and recomputes statistics only. It
    # performs no simulation, model fit, or read of ignored training arrays.
    actual=diagnosis.build_diagnosis(ROOT)
    expected=json.loads((ROOT/'research/results/rollout_diagnosis.json').read_text(encoding='utf-8'))
    assert diagnosis.same_evidence(actual,expected)
    assert not actual['training_data_dependency']
    assert actual['feature_shift']['prev_dJ']['formula_max_abs_error']==0
    assert actual['fixed_path_feasibility']['exact_operating_prefix_verified']
    assert diagnosis._doc(actual)==(ROOT/'docs/ROLLOUT_DIAGNOSIS.md').read_text(encoding='utf-8')
