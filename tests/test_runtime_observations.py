"""Synthetic numeric and provenance mutations for the new observation obligation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import numpy as np
import pytest
from jev_tune.primitives import softmax

ROOT = Path(__file__).resolve().parents[1]
def module(name):
    spec = importlib.util.spec_from_file_location('test_observe_'+name, ROOT/'scripts'/(name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
observer = module('57_observe_runtime_comparison')
checker = module('58_verify_runtime_observations')
numeric = module('calibration_numeric_audit')
runner = module('45_nonpid_transfer')


def fixture_values():
    logits = np.random.default_rng(941).normal(size=(4, 2, 5))
    temperatures = [1.2, .8]
    p = softmax(logits, temperature=np.asarray(temperatures)[None, :, None])
    decisions = [runner.action(row, {'qhat_per_axis': [.8, .9]}) for row in p]
    return logits, temperatures, p, decisions


def test_real_softmax_and_action_intervals_and_numeric_mutations():
    logits, temperatures, p, decisions = fixture_values()
    checker.verify_test_probabilities(logits, temperatures, p, numeric)
    steps = np.stack([d.step for d in decisions])
    checker.verify_recorded_steps(p, steps, numeric)
    bad = p.copy(); bad[0, 0, 0] += 1e-4
    with pytest.raises(ValueError): checker.verify_test_probabilities(logits, temperatures, bad, numeric)
    with pytest.raises(ValueError): checker.verify_test_probabilities(logits, [1.3, .8], p, numeric)
    bad = steps.copy(); bad[0, 0] += 1e-4
    with pytest.raises(ValueError): checker.verify_recorded_steps(p, bad, numeric)


def test_full_sets_and_flags_are_exact():
    _, _, p, decisions = fixture_values()
    held = np.stack([d.held for d in decisions]); escalate = np.stack([d.escalate for d in decisions])
    sets = np.stack([d.conformal_set for d in decisions]).astype(bool)
    checker.verify_action_flags_and_sets(p, [.8, .9], held, escalate, sets)
    for field in ('sets', 'held', 'escalate'):
        values = {'sets': sets.copy(), 'held': held.copy(), 'escalate': escalate.copy()}
        values[field].flat[0] = not values[field].flat[0]
        with pytest.raises(ValueError): checker.verify_action_flags_and_sets(p, [.8, .9], **values)


def test_strict_rank_q_and_identity_mutations():
    _, _, p, _ = fixture_values()
    labels = np.zeros((4, 2), dtype=int)
    identities = [str(i) for i in range(4)]
    scores = 1-p[:, :, 0]; order = np.argsort(scores, axis=0, kind='stable')
    rows = [{'axis': a, 'rank': 5, 'qhat': 1., 'kth_index': None, 'kth_identity': None} for a in range(2)]
    assert np.array_equal(checker.strict_rank(p, labels, identities, rows), order)
    for field, value in [('rank', 4), ('qhat', np.nextafter(1., 0.)), ('kth_identity', '0')]:
        bad = [dict(row) for row in rows]; bad[0][field] = value
        with pytest.raises(ValueError): checker.strict_rank(p, labels, identities, bad)


def test_array_manifest_requires_exact_bytes_dtype_and_keys(tmp_path):
    p = fixture_values()[2]
    manifest = {'p': {'shape': list(p.shape), 'dtype': p.dtype.str, 'sha256': hashlib.sha256(p.tobytes()).hexdigest()}}
    for name, value in [('good', p), ('mutation', p+1e-10), ('dtype', p.astype('float32'))]:
        path = tmp_path/(name+'.npz'); np.savez(path, p=value)
        with np.load(path) as arrays:
            if name == 'good': checker.verify_array_manifest(arrays, manifest)
            else:
                with pytest.raises(ValueError): checker.verify_array_manifest(arrays, manifest)
    np.savez(tmp_path/'extra.npz', p=p, extra=p)
    with np.load(tmp_path/'extra.npz') as arrays:
        with pytest.raises(ValueError): checker.verify_array_manifest(arrays, manifest)


def test_one_ulp_action_difference_is_counted():
    left = {'step': np.ones((2, 2)), 'held': np.zeros((2, 2), bool), 'escalate': np.zeros((2, 2), bool)}
    right = {key: value.copy() for key, value in left.items()}
    right['step'][0, 1] = np.nextafter(1., 2.)
    assert checker.action_difference(left, right)['different_step_states_per_axis'] == [0, 1]


def test_only_specific_original_failure_is_admitted():
    trace = 'File "54_compare_calibration_runtimes.py", line 1, in check\n    assert actual == stored\nAssertionError: Archived runtime comparison changed\n'
    checker.verify_original_exit({'returncode': 1}, {'scope': 'new'}, {}, True, '', trace)
    for error in ['ImportError: missing', 'AssertionError: other', trace.replace('assert actual == stored', 'assert something')]:
        with pytest.raises(ValueError): checker.verify_original_exit({'returncode': 1}, {'scope': 'new'}, {}, True, '', error)


def test_two_distinct_registered_observers_required(tmp_path):
    for name in ('one', 'two'):
        path = tmp_path/name; path.mkdir()
        (path/'observation.json').write_text(json.dumps({'label': observer.LABELS[0]}))
    with pytest.raises(ValueError, match='exactly one'): checker.check(tmp_path, ['one', 'two'])
    with pytest.raises(FileExistsError): observer.observe(tmp_path)


def test_frozen_head_protocol_and_eol_hash_scope(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    hashes = {}
    for name in observer.SOURCES:
        path = tmp_path/name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'synthetic\n')
        if name != observer.PROTOCOL: hashes[name] = observer.sha(path, text=True)
    protocol = {'schema_version': 1, 'study_type': 'post_incident_runtime_comparison_observations',
                'observation_labels': list(observer.LABELS), 'cases_per_observation': 96, 'source_hashes': hashes}
    (tmp_path/observer.PROTOCOL).write_text(json.dumps(protocol))
    subprocess.run(['git', 'add', '.'], cwd=tmp_path, check=True)
    subprocess.run(['git', '-c', 'user.name=test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'freeze'], cwd=tmp_path, check=True)
    observer.check_frozen_sources(tmp_path)
    path = tmp_path/observer.SOURCES[0]; before = observer.input_manifest(tmp_path, [observer.SOURCES[0]])
    path.write_bytes(b'synthetic\r\n'); observer.check_frozen_sources(tmp_path)
    assert observer.sha(path, True) == hashes[observer.SOURCES[0]]
    assert observer.sha(path) != before[observer.SOURCES[0]]['observed_byte_sha256']
    path.write_bytes(b'mutation\n')
    with pytest.raises(ValueError, match='frozen HEAD'): observer.check_frozen_sources(tmp_path)


def test_synthetic_producer_records_complete_actions():
    logits, temperatures, p, _ = fixture_values()
    archive = {'seed_101_test_logits': logits}
    populations = {}
    for population in ('cp256', 'saved_calibration_population'):
        prefix = population
        populations[population] = {'array_prefix': prefix, 'n_calibration': len(p), 'saved_qhat': [.8, .9],
            'refit_t_order_statistic': [{'qhat': .8}, {'qhat': .9}],
            'recorded_t_order_statistic': [{'qhat': .8}, {'qhat': .9}]}
        for kind in ('refit', 'recorded'): archive[prefix+'_probabilities_'+kind+'_t'] = p.copy()
    row = {'seed': 101, 'n_temperature': 16, 'axes': [
        {'recorded_temperature': t, 'refit_temperature': t} for t in temperatures], **populations}
    arrays, cases = observer.capture_cases({'rows': [row]}, {'rows': [row]}, archive, archive, runner)
    assert len(cases) == 8
    for case in cases:
        key = case['id']; recorded = arrays[case['test_probabilities']]
        checker.verify_test_probabilities(logits, temperatures, recorded, numeric)
        checker.verify_recorded_steps(recorded, arrays[key+'_step'], numeric)
        checker.verify_action_flags_and_sets(recorded, case['qhat'], arrays[key+'_held'], arrays[key+'_escalate'], arrays[key+'_sets'])


def test_bilingual_document_uses_only_result_numbers():
    summary = {key: index for index, key in enumerate(('max_logits_difference', 'max_temperature_difference',
        'max_qhat_difference', 'max_refit_step_difference', 'changed_CP_options', 'changed_test_options'))}
    result = {'observations': [{'label': 'synthetic', 'cases': 96, 'unique_test_probability_arrays': 48,
        'original_54_returncode': 1, 'recorded_comparison_summary': summary}]}
    text = checker.render(result)
    assert '| synthetic | 96 | 48 | 1 | 0 | 1 | 2 | 3 | 4 | 5 |' in text
    assert '## English' in text and '## 简体中文' in text
    assert 'failure remains a failure' in text and '不证明未来逐位一致' in text
