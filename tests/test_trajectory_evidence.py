"""Adversarial evidence checks on small synthetic trajectories, not study data."""
import copy
import importlib.util
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
