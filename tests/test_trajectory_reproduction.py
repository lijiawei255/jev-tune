"""Replay orchestration tests with fabricated artifacts; no study plants sampled."""
import copy
import gzip
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('trajectory_reproduction',
    Path(__file__).parents[1] / 'scripts/34_reproduce_trajectory_evaluation.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False, indent=2) + '\n', encoding='utf-8')


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, 'ROOT', tmp_path)
    source = tmp_path / 'src/jev_tune/trajectory_risk.py'
    source.parent.mkdir(parents=True); source.write_text('# frozen engine\n')
    sampler = tmp_path / 'scripts/25_joint_risk.py'
    sampler.parent.mkdir(parents=True); sampler.write_text('# frozen sampler\n')
    runner = tmp_path / 'scripts/34_reproduce_trajectory_evaluation.py'
    runner.write_text('# fixed reproduction runner\n')
    monkeypatch.setattr(replay, '__file__', str(runner))
    checkpoint = tmp_path / 'models/jev_head.pt'
    checkpoint.parent.mkdir(); checkpoint.write_bytes(b'frozen weights')
    calibration = tmp_path / 'models/calibration.json'
    write(calibration, {'choice_temperature': [1., 2., 3.]})
    old_path = tmp_path / 'research/results/joint_risk.json'
    old_model, new_model = {'tag': 'old'}, {'tag': 'new'}
    write(old_path, {'risk_model': old_model})
    configs = [{'name': name, 'model': 'old' if name.startswith('old') else 'new',
        'selector': 'model_min_risk' if name.endswith('selected') else 'full_only',
        'feature_mode': 'legacy' if name.startswith('old') else 'history_zero'}
        for name in replay.ARMS[1:]]
    protocol = {'registered_utc': 'before synthetic collection', 'specification': {
        'proposal': {'checkpoint_sha256': replay.sha256(checkpoint), 'choice_temperature': [1., 2., 3.]},
        'scope': {'horizon': 2}, 'evaluation': {'arms': list(replay.ARMS), 'seed': 42, 'n_plants': 3},
        'arms': configs, 'old_results': {'preserve_byte_identical': {
            replay.relative(old_path): replay.sha256(old_path)}},
        'old_risk_model_sha256': replay.canonical_hash(old_model)}}
    protocol_path = tmp_path / 'research/protocols/trajectory_risk_v2.json'
    write(protocol_path, protocol)
    sources = {replay.relative(p): replay.sha256(p) for p in (source, sampler, checkpoint, calibration)}
    payload = {'completed_utc': 'after synthetic evaluation', 'acceptance': {'passed': False},
        'integrity': {'synthetic_check': True}, 'protocol': protocol,
        'protocol_sha256': replay.sha256(protocol_path),
        'protocol_canonical_sha256': replay.canonical_hash(protocol),
        'manifest': {'file_sha256': sources, 'packages': {}}, 'risk_model': new_model,
        'training': {'model_canonical_sha256': replay.canonical_hash(new_model)},
        'evaluation': {name: {} for name in replay.ARMS}, 'evaluation_raw': {},
        'raw_files': [], 'arms': {}}
    calls = []

    def synthetic_run(backend, model, plants, **kwargs):
        calls.append((model, plants, copy.deepcopy(kwargs)))
        return {'fixed_action_cost': 1.25, 'model': model, 'plants': list(plants), 'arguments': kwargs,
                'simulation_counts': {'operating_initial': 3, 'executed': 6, 'diagnostic_rejected': 1,
                    'diagnostic_collected': 0, 'diagnostic_training': 0, 'operating': 9,
                    'total': 10, 'requests': 11, 'cache_hits': 1, 'execution_requests': 7}}

    for i, name in enumerate(replay.ARMS):
        if name == 'monitor':
            model = old_model
            kwargs = dict(mode='monitor', selector='full_only', feature_mode='legacy', qhats=[1., 1.])
        else:
            config = configs[i-1]
            qhats = [.01 * i, .02 * i]
            payload['arms'][name] = {'configuration': config, 'qhats': qhats,
                                     'stages': [{'qhat': q} for q in qhats]}
            model = old_model if config['model'] == 'old' else new_model
            kwargs = dict(mode='gated', selector=config['selector'], feature_mode=config['feature_mode'], qhats=qhats)
        kwargs.update(horizon=2, diagnostic=True)
        raw = synthetic_run(None, model, (3, 42), **kwargs)
        raw['study_metadata'] = {'protocol_canonical_sha256': payload['protocol_canonical_sha256'],
            'seed': 42, 'n_plants': 3, 'kind': 'evaluation', 'arguments': kwargs,
            'risk_model_sha256': replay.canonical_hash(model), 'engine_sha256': replay.sha256(source)}
        raw_path = tmp_path / 'research/results/trajectory_risk_raw' / f'evaluation_{name}.json.gz'
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(gzip.compress(json.dumps(raw).encode(), mtime=0))
        path = replay.relative(raw_path)
        payload['evaluation_raw'][name] = path
        payload['raw_files'].append({'path': path, 'sha256': replay.sha256(raw_path), 'kind': 'evaluation'})
    calls.clear()
    result_path = tmp_path / 'research/results/trajectory_risk.json'
    report_path = tmp_path / 'research/results/trajectory_risk_reproduction.json'
    write(result_path, payload)
    monkeypatch.setattr(replay, '_runtime', lambda: (None, lambda x: x, lambda n, seed: (n, seed), synthetic_run))
    return result_path, report_path, payload, calls, synthetic_run


def test_five_arm_exact_replay_is_separate_charged_and_read_only_check(artifacts, monkeypatch):
    result, report, payload, calls, _ = artifacts
    originals = {path: path.read_bytes() for path in (result, *[replay.resolve(p) for p in payload['evaluation_raw'].values()])}
    outcome = replay.reproduce(result, report)
    assert outcome['equal'] is True and len(calls) == 5
    assert outcome['additional_independent_evidence'] is False
    assert outcome['acceptance_recomputed'] is False
    assert outcome['additional_simulation_counts']['total'] == 50
    assert outcome['additional_simulation_counts']['cache_hits'] == 5
    assert calls[-1][2]['selector'] == 'model_min_risk'
    assert all(path.read_bytes() == original for path, original in originals.items())
    monkeypatch.setattr(replay, '_runtime', lambda: pytest.fail('check/overwrite must never invoke runtime'))
    assert replay.check(result, report) == outcome
    with pytest.raises(ValueError, match='already exists'):
        replay.reproduce(result, report)


def test_exact_comparison_exposes_even_small_float_difference(artifacts, monkeypatch):
    result, report, _, _, original = artifacts

    def changed(*args, **kwargs):
        run = original(*args, **kwargs)
        if kwargs['selector'] == 'model_min_risk':
            run['fixed_action_cost'] += 1e-15
        return run

    monkeypatch.setattr(replay, '_runtime', lambda: (None, lambda x: x, lambda n, s: (n, s), changed))
    outcome = replay.reproduce(result, report)
    assert outcome['equal'] is False
    assert [name for name, arm in outcome['arms'].items() if not arm['equal']] == ['trajectory_selected']
    assert replay.check(result, report)['equal'] is False


@pytest.mark.parametrize('problem', ['incomplete', 'raw_hash', 'source', 'proposal_temperature'])
def test_preflight_failure_never_samples_test_plants(artifacts, monkeypatch, problem):
    result, report, payload, _, _ = artifacts
    if problem == 'incomplete':
        del payload['completed_utc']; write(result, payload)
    elif problem == 'raw_hash':
        replay.resolve(payload['evaluation_raw']['monitor']).write_bytes(b'changed raw')
    elif problem == 'source':
        (replay.ROOT / 'src/jev_tune/trajectory_risk.py').write_text('# changed simulator\n')
    else:
        write(replay.ROOT / 'models/calibration.json', {'choice_temperature': [9., 9., 9.]})
    monkeypatch.setattr(replay, '_runtime', lambda: pytest.fail('invalid source must not sample test plants'))
    with pytest.raises(ValueError):
        replay.reproduce(result, report)
    assert not report.exists()


def test_check_rejects_saved_replay_ledger_corruption_without_simulation(artifacts, monkeypatch):
    result, report, _, _, _ = artifacts
    outcome = replay.reproduce(result, report)
    outcome['arms']['monitor']['additional_simulation_counts']['total'] += 1
    write(report, outcome)
    monkeypatch.setattr(replay, '_runtime', lambda: pytest.fail('check must not simulate'))
    with pytest.raises(ValueError, match='different simulation ledger'):
        replay.check(result, report)


def test_check_relocates_windows_manifest_and_accepts_only_json_newline_changes(artifacts, monkeypatch):
    result, report, payload, _, _ = artifacts
    hashes = payload['manifest']['file_sha256']
    for name in ('models/jev_head.pt', 'models/calibration.json'):
        hashes['X:/original/checkout/' + name] = hashes.pop(name)
    write(result, payload)
    replay.reproduce(result, report)
    for path in (result, replay.ROOT / 'models/calibration.json',
                 replay.ROOT / 'research/results/joint_risk.json'):
        path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
    monkeypatch.setattr(replay, '_runtime', lambda: pytest.fail('portable check must not simulate'))
    assert replay.check(result, report)['equal']
    # Normalization is deliberately limited to line endings, never values.
    changed = replay.read_json(result); changed['acceptance']['passed'] = True; write(result, changed)
    with pytest.raises(ValueError, match='Original result hash'):
        replay.check(result, report)


def test_package_versions_strict_for_reproduction_not_read_only_check(artifacts, monkeypatch):
    result, report, payload, _, _ = artifacts
    payload['manifest']['packages'] = {'numpy': 'original-version'}
    write(result, payload)
    monkeypatch.setattr(replay.importlib.metadata, 'version', lambda name: 'original-version')
    replay.reproduce(result, report)
    monkeypatch.setattr(replay.importlib.metadata, 'version', lambda name: 'other-version')
    monkeypatch.setattr(replay, '_runtime', lambda: pytest.fail('check must not simulate'))
    assert replay.check(result, report)['equal']
    with pytest.raises(ValueError, match='Numerical package changed'):
        replay.reproduce(result, report.with_name('another-report.json'))
