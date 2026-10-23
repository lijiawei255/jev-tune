"""Adversarial evidence checks on small synthetic trajectories, not study data."""
import copy
import gzip
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

import jev_tune.trajectory_risk as engine
from jev_tune.decode import ActionSpace
from jev_tune.primitives import Answer, Choice, Noul, Option
from jev_tune.risk import JointRiskModel
from jev_tune.sequential_risk import summarize_rollout

spec = importlib.util.spec_from_file_location('trajectory_evidence',
    Path(__file__).parents[1] / 'scripts/32_verify_trajectory_risk.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


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

    def __init__(self, zero=False, only_kp=False):
        self.zero, self.only_kp = zero, only_kp

    def answer(self, state, curves):
        options = [Option(str(m), float(np.log10(m))) for m in self.space.multipliers]
        choices = []
        for axis in range(3):
            p = np.zeros((len(state), 7))
            p[:, 3 if self.zero or (axis and self.only_kp) else 6] = 1.
            choices.append(Choice(str(axis), options, p))
        return Answer(choices, noul=Noul('healthy', np.ones(len(state))))


@pytest.fixture
def synthetic(monkeypatch):
    def setup(*, ku=5/3, increasing=False):
        def simulate(plants, gains, **kwargs):
            cost = gains[:, 0] if increasing else 1/gains[:, 0]
            metrics = np.zeros((plants.n, 9)); metrics[:, 0] = cost
            metrics[:, 4:6] = 1.
            return {'metrics': metrics, 'y_curve': np.ones((plants.n, 64)),
                    'u_curve': np.zeros((plants.n, 64))}
        monkeypatch.setattr(engine, 'simulate', simulate)
        monkeypatch.setattr(engine, 'cost_from_metrics', lambda metrics, **kw: metrics[:, 0])
        monkeypatch.setattr(engine, 'ultimate_gain', lambda p: (np.full(p.n, ku), np.full(p.n, 2.)))
        coefficient = np.zeros(44); coefficient[20] = 2.
        return JointRiskModel(np.zeros(44), np.ones(44), coefficient, -3., 1.)
    return setup


def test_independent_verifier_accepts_training_and_reconstructs_labels(synthetic):
    synthetic()
    run = engine.run_trajectory_risk(Proposal(), None, Plants([0, 1, 2]), horizon=3, mode='training')
    checked = verifier.verify_run(run, None)
    assert checked['collected'] == run['collected']
    assert checked['simulation_counts']['requests'] == 30
    assert verifier.same(verifier.summarize(run), summarize_rollout(run))
    run['collected']['labels'][0] = 1
    with pytest.raises(ValueError, match='collected dataset'):
        verifier.verify_run(run, None)


def test_independent_verifier_checks_selection_before_cp_and_full_set(synthetic):
    model = synthetic()
    run = engine.run_trajectory_risk(Proposal(), model, Plants([0, 1]), [.07, .07],
        horizon=2, mode='gated', selector='model_min_risk')
    verifier.verify_run(run, model.as_dict(), [.07, .07])
    assert run['transitions'][0]['selected_index'] == 2
    bad = copy.deepcopy(run); bad['transitions'][0]['selected_index'] = 1
    with pytest.raises(ValueError, match='pre-CP'):
        verifier.verify_run(bad, model.as_dict(), [.07, .07])
    bad = copy.deepcopy(run); bad['transitions'][0]['prediction_set'][1] = True
    with pytest.raises(ValueError, match='altered CP set'):
        verifier.verify_run(bad, model.as_dict(), [.07, .07])


def test_independent_verifier_rejects_model_and_history_feature_tampering(synthetic):
    model = synthetic()
    run = engine.run_trajectory_risk(Proposal(), model, Plants([0]), horizon=2, mode='monitor')
    verifier.verify_run(run, model.as_dict())
    bad = copy.deepcopy(run); bad['transitions'][0]['candidates'][0]['probabilities'] = [.5, .5]
    with pytest.raises(ValueError, match='risk probabilities'):
        verifier.verify_run(bad, model.as_dict())
    bad = copy.deepcopy(run); bad['transitions'][0]['candidates'][0]['features'][16] = -.2
    with pytest.raises(ValueError, match='history feature'):
        verifier.verify_run(bad, model.as_dict())


def test_rejected_diagnostic_cannot_be_promoted_to_operating_best(synthetic):
    model = synthetic()
    run = engine.run_trajectory_risk(Proposal(), model, Plants([0]), [1., 1.], horizon=2, mode='gated')
    verifier.verify_run(run, model.as_dict(), [1., 1.])
    assert run['transitions'][0]['cost_after'] < run['per_plant'][0]['best_J']
    run['per_plant'][0]['best_J'] = run['transitions'][0]['cost_after']
    with pytest.raises(ValueError, match='final state/best'):
        verifier.verify_run(run, model.as_dict(), [1., 1.])


def test_exact_cache_accounting_and_source_are_reconstructed(synthetic):
    synthetic(ku=1500.)
    run = engine.run_trajectory_risk(Proposal(only_kp=True), None, Plants([0, 1, 2]), horizon=1, mode='training')
    verifier.verify_run(run, None)
    assert run['per_plant'][1]['simulation_counts']['executed'] == 0
    assert run['per_plant'][1]['simulation_counts']['execution_requests'] == 1
    bad = copy.deepcopy(run); bad['per_plant'][1]['simulation_counts']['executed'] = 1
    with pytest.raises(ValueError, match='simulation counts'):
        verifier.verify_run(bad, None)
    bad = copy.deepcopy(run); bad['transitions'][1]['candidates'][1]['measurement_source_kind'] = 'executed'
    with pytest.raises(ValueError, match='cache/simulation provenance'):
        verifier.verify_run(bad, None)


def test_collect_uses_only_reached_selected_actions_and_no_padding(synthetic):
    model = synthetic()
    run = engine.run_trajectory_risk(Proposal(), model, Plants([0, 1]), [.2], horizon=2,
        mode='collect', collect_step=1, diagnostic=False)
    verifier.verify_run(run, model.as_dict(), [.2], collect_step=1, diagnostic=False)
    assert len(run['collected']['labels']) == 2
    assert all(p['operating_history'][-1]['stage'] == 0 for p in run['per_plant'])
    bad = copy.deepcopy(run); bad['transitions'][-1]['executed'] = True
    with pytest.raises(ValueError, match='selected execution'):
        verifier.verify_run(bad, model.as_dict(), [.2], collect_step=1, diagnostic=False)
    held = engine.run_trajectory_risk(Proposal(), model, Plants([0, 1]), [1.], horizon=2,
        mode='collect', collect_step=1, diagnostic=False)
    verifier.verify_run(held, model.as_dict(), [1.], collect_step=1, diagnostic=False)
    assert held['collected']['labels'] == []
    held['transitions'][0]['cost_after'] = .01
    with pytest.raises(ValueError, match='unmeasured selected observation'):
        verifier.verify_run(held, model.as_dict(), [1.], collect_step=1, diagnostic=False)


def test_unchanged_stops_and_no_later_action_is_allowed(synthetic):
    model = synthetic()
    run = engine.run_trajectory_risk(Proposal(zero=True), model, Plants([0]), [.1, .1], horizon=2, mode='gated')
    verifier.verify_run(run, model.as_dict(), [.1, .1])
    extra = copy.deepcopy(run['transitions'][0]); extra['stage'] = 1
    run['transitions'].append(extra)
    with pytest.raises(ValueError, match='action after a stop'):
        verifier.verify_run(run, model.as_dict(), [.1, .1])


def test_nonfinite_measured_evidence_fails_closed(synthetic):
    model = synthetic()
    run = engine.run_trajectory_risk(Proposal(), model, Plants([0]), horizon=1, mode='monitor')
    run['transitions'][0]['candidates'][0]['cost_after'] = None
    with pytest.raises(ValueError, match='nonfinite candidate'):
        verifier.verify_run(run, model.as_dict())


def test_hash_allows_only_checkout_text_line_endings(tmp_path):
    path = tmp_path/'source.py'; path.write_bytes(b'a\r\nb\r\n')
    digest = verifier.hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_bytes(b'a\nb\n')
    assert verifier.hash_matches(path, digest, text=True)
    assert not verifier.hash_matches(path, digest)
    path.write_bytes(b'a\nchanged\n')
    assert not verifier.hash_matches(path, digest, text=True)


def test_cohort_failure_separates_exact_ids_from_unchanged_gain_tolerance():
    records = [{'plant_identity': 100, 'initial_gains': [1., 2., 3.]},
               {'plant_identity': 200, 'initial_gains': [4., 5., 6.]}]
    gains = np.asarray([record['initial_gains'] for record in records])
    comparison = verifier.verify_cohort(records, [100, 200], gains, 'synthetic.gz')
    assert comparison['identity_exact_match'] and comparison['gains_within_tolerance']
    changed = gains.copy(); changed[0, 0] += 1e-13
    comparison = verifier.cohort_comparison(records, [100, 201], changed)
    assert comparison['identity_mismatch_count'] == 1
    assert comparison['first_identity_mismatch'] == {'plant_index': 1, 'recorded': 200, 'regenerated': 201}
    assert comparison['gains_within_tolerance']
    assert comparison['gains_max_abs_difference'] == abs(1. - changed[0, 0])
    with pytest.raises(ValueError, match='"identity_exact_match": false'):
        verifier.verify_cohort(records, [100, 201], changed, 'synthetic.gz')
    changed[1, 2] += 1e-9
    comparison = verifier.cohort_comparison(records, [100, 200], changed)
    assert comparison['identity_exact_match'] and not comparison['gains_within_tolerance']
    assert comparison['gains_mismatch_count'] == 1
    assert comparison['first_gain_mismatch']['index'] == [1, 2]
    assert comparison['gains_rtol'] == comparison['gains_atol'] == 1e-12
    assert comparison['gains_max_relative_difference'] == np.max(np.abs(gains - changed) / np.abs(changed))
    with pytest.raises(ValueError, match='"gains_within_tolerance": false'):
        verifier.verify_cohort(records, [100, 200], changed, 'synthetic.gz')


def test_cohort_diagnostics_fail_closed_on_malformed_or_nonfinite_arrays():
    records = [{'plant_identity': 100, 'initial_gains': [1., 2., 3.]}]
    comparison = verifier.cohort_comparison(records, [100, 200], [[1., 2., 3.], [4., 5., 6.]])
    assert comparison['identity_mismatch_count'] == 1
    assert not comparison['gains_shape_match']
    records[0]['initial_gains'][0] = float('nan')
    comparison = verifier.cohort_comparison(records, [100], [[1., 2., 3.]])
    assert not comparison['gains_finite'] and not comparison['gains_within_tolerance']
    json.dumps(comparison, allow_nan=False)
    with pytest.raises(ValueError, match='"gains_finite": false'):
        verifier.verify_cohort(records, [100], [[1., 2., 3.]], 'synthetic.gz')


def test_runner_snapshots_cover_each_shard_once_and_do_not_reclassify_reuse(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier, 'ROOT', tmp_path)
    folder = tmp_path/'research/protocols/trajectory_risk_sources'; folder.mkdir(parents=True)
    path = folder/'original.py'; path.write_text('frozen runner\n')
    relative = path.relative_to(tmp_path).as_posix()
    digest = verifier.hashlib.sha256(path.read_bytes()).hexdigest()
    payload = {'started_utc': '2026-10-23T01:00:00+00:00',
        'training': {'model_frozen_utc': '2026-10-23T02:00:00+00:00'},
        'raw_files': [{'path': 'train.gz', 'kind': 'training'}, {'path': 'eval.gz', 'kind': 'evaluation'}],
        'runner_invocations': [
            {'phase': 'training_calibration', 'source_path': relative, 'source_sha256': digest,
             'started_utc': '2026-10-23T01:00:00+00:00', 'raw_files': ['train.gz']},
            {'phase': 'evaluation', 'source_path': relative, 'source_sha256': digest,
             'started_utc': '2026-10-23T03:00:00+00:00', 'raw_files': ['eval.gz'], 'reused_raw_files': ['train.gz']}]}
    verifier.verify_runner_invocations(payload, {'scripts/31_trajectory_risk.py': digest})
    bad = copy.deepcopy(payload); bad['runner_invocations'][1]['raw_files'].append('train.gz')
    with pytest.raises(ValueError, match='generated twice'):
        verifier.verify_runner_invocations(bad, {'scripts/31_trajectory_risk.py': digest})
    bad = copy.deepcopy(payload); bad['runner_invocations'][0]['raw_files'].append('eval.gz')
    with pytest.raises(ValueError, match='test collected before'):
        verifier.verify_runner_invocations(bad, {'scripts/31_trajectory_risk.py': digest})
    path.write_text('changed runner\n')
    with pytest.raises(ValueError, match='snapshot hash'):
        verifier.verify_runner_invocations(payload, {'scripts/31_trajectory_risk.py': digest})


def test_published_result_cannot_omit_failed_acceptance_or_deployment_status():
    with pytest.raises(ValueError, match='lacks final acceptance'):
        verifier.verify_payload({'risk_model': {}}, require_final=True)


def test_pairing_requires_identical_initial_objects_not_unregistered_exact_paths(synthetic, tmp_path, monkeypatch):
    model=synthetic()
    monitor=engine.run_trajectory_risk(Proposal(), model, Plants([0]), horizon=1, mode='monitor')
    gated=copy.deepcopy(monitor)
    gated['transitions'][0]['base_step'][0] += float(np.finfo(np.float32).eps)
    gated['per_plant'][0]['operating_history'][-1]['cost'] += 1e-9
    verifier.verify_initial_pairing({'monitor':monitor,'full':gated})
    monkeypatch.setattr(verifier,'ROOT',tmp_path)
    payload={'raw_files':[],'evaluation_raw':{}}
    for name,raw in [('monitor',monitor),('full',gated)]:
        path=tmp_path/(name+'.gz')
        path.write_bytes(gzip.compress(json.dumps(raw).encode(),mtime=0))
        payload['evaluation_raw'][name]=path.name
        payload['raw_files'].append({'path':path.name,'sha256':verifier.hashlib.sha256(path.read_bytes()).hexdigest()})
    diagnostic=verifier.paired_diagnosis(payload)
    assert diagnostic['changes_acceptance_or_thresholds'] is False
    assert diagnostic['additional_simulations']==0
    assert diagnostic['arms']['full']['different_operating_histories_exact']==1
    assert diagnostic['arms']['full']['different_proposal_rows_exact']==1
    assert diagnostic['arms']['full']['max_abs_base_step_difference']==np.finfo(np.float32).eps
    gated['per_plant'][0]['initial_J'] += 1e-9
    with pytest.raises(ValueError,match='identical initial'):
        verifier.verify_initial_pairing({'monitor':monitor,'full':gated})


def test_additional_validity_audit_preserves_frozen_acceptance_and_disables_deployment():
    acceptance={'passed':False,'checks':{'mean':False},'failed':['mean']}
    payload={'acceptance':acceptance,'deployment':{'enabled':False,'generic_python_c_matlab_enabled':False}}
    report={'batches':{'171':{'relative_to_reference_row':{'probability_max_abs':1e-7,
        'base_step_max_abs':1e-8,'nonidentical_probability_rows':2}},
        '1024':{'relative_to_reference_row':{'probability_max_abs':1e-7,
        'base_step_max_abs':1e-8,'nonidentical_probability_rows':4}}},
        'original_layout_position_comparisons':{'monitor':{'probability_max_abs':0.,'base_step_max_abs':0.},
                                                'old':{'probability_max_abs':0.,'base_step_max_abs':0.}}}
    assessment=verifier.assess_validity(payload,report)
    assert assessment['frozen_numerical_acceptance']==acceptance
    assert assessment['cp_exchangeability_established'] is False
    assert assessment['trajectory_event_independence_established'] is False
    assert assessment['canonical_per_object_mapping_established'] is False
    assert assessment['deployment_allowed'] is False
    assert assessment['additional_simulations']==0
    assert assessment['observed_batch_dependence']['nonidentical_batch_groups']==[171,1024]
    payload['deployment']['enabled']=True
    with pytest.raises(ValueError,match='cannot authorize deployment'):
        verifier.assess_validity(payload,report)


def test_batch_diagnosis_cannot_forge_original_layout_or_recovered_input_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier,'ROOT',tmp_path)
    p=np.zeros((3,7));p[:,3]=1.
    row={'plant_index':480,'plant_identity':99,'stage':1,'proposal_valid':True,
         'choice_probabilities':p.tolist(),'base_step':[0.,0.,0.],'gains_before':[1.,1.,1.],
         'cost_before':2.,'features':[0.]*44}
    raw={'study_metadata':{'seed':9},'n_plants':1024,'transitions':[row]}
    path=tmp_path/'raw.gz';path.write_bytes(gzip.compress(json.dumps(raw).encode(),mtime=0))
    entry={'path':'raw.gz','sha256':verifier.hashlib.sha256(path.read_bytes()).hexdigest()}
    comparison={'active_batch_size':1,'target_batch_position':0,'original_choice_probabilities':p.tolist(),
                'original_base_step':[0.,0.,0.],'probability_max_abs':0.,'base_step_max_abs':0.}
    report={'schema_version':1,'additional_independent_evidence':False,'acceptance_recomputed':False,
        'target':{'plant_index':480,'plant_identity':99,'stage':1,'seed':9,'original_n_plants':1024,'gains_before':[1.,1.,1.]},
        'reference':{'batch_size':1024,'row':480},'input_artifacts':{'raw':{'monitor':entry,'old':entry}},
        'batches':{'1':{'choice_probabilities':[p.tolist()],'base_step':[[0.,0.,0.]]}},
        'original_layout_position_comparisons':{'monitor':comparison,'old':copy.deepcopy(comparison)},
        'recovered_input':{'features':[0.]*20,'curves':np.zeros((2,64)).tolist(),'cost':2.,'original_cost':2.,
                           'cost_abs_difference':0.,'state_max_abs_difference':0.}}
    verifier.validate_batch_diagnosis(report)
    bad=copy.deepcopy(report);bad['original_layout_position_comparisons']['old']['probability_max_abs']=1e-5
    with pytest.raises(ValueError,match='original batch-layout comparison'):
        verifier.validate_batch_diagnosis(bad)
    bad=copy.deepcopy(report);bad['recovered_input']['cost_abs_difference']=.1
    with pytest.raises(ValueError,match='recovered numerical input comparison'):
        verifier.validate_batch_diagnosis(bad)
