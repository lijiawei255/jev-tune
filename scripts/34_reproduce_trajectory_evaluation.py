"""Repeat the frozen five-arm evaluation; this is not new acceptance evidence.

Run only after trajectory_risk.json is final. --check reads hashes/accounting
without sampling plants or executing the simulator. Original artifacts are
never written and a reproduction report cannot be overwritten.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'research/results/trajectory_risk.json'
REPORT = ROOT / 'research/results/trajectory_risk_reproduction.json'
ARMS = ('monitor', 'old_initial512', 'old_reached2000', 'trajectory_full',
        'trajectory_selected')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def canonical_hash(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def resolve(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT.resolve())).replace('\\', '/')


def _matches(path, expected):
    data = path.read_bytes()
    variants = [data]
    if path.suffix in ('.py', '.json'):
        lf = data.replace(b'\r\n', b'\n')
        variants += [lf, lf.replace(b'\n', b'\r\n')]
    return any(hashlib.sha256(value).hexdigest() == expected for value in variants)


def validate_sources(payload):
    """Bind simulator/proposal/feature/model dependencies to original collection."""
    sources = {}
    for name, recorded in payload['manifest']['file_sha256'].items():
        normalized = name.replace('\\', '/')
        if not (normalized.startswith('src/jev_tune/') or normalized.endswith(
                ('scripts/25_joint_risk.py', 'models/jev_head.pt', 'models/calibration.json'))):
            continue
        path = resolve(name)
        require(_matches(path, recorded), 'Numerical source changed: ' + name)
        sources[relative(path)] = sha256(path)
    for package, version in payload['manifest']['packages'].items():
        require(importlib.metadata.version(package) == version,
                'Numerical package changed: ' + package)
    proposal = payload['protocol']['specification']['proposal']
    require(sha256(ROOT / 'models/jev_head.pt') == proposal['checkpoint_sha256'],
            'Proposal checkpoint differs from registered study')
    require(read_json(ROOT / 'models/calibration.json')['choice_temperature'] ==
            proposal['choice_temperature'], 'Proposal temperatures differ from registered study')
    # Record the runner too, without requiring it to predate the original study.
    sources[relative(Path(__file__))] = sha256(Path(__file__))
    return sources


def load_inputs(result_path):
    payload = read_json(result_path)
    require(bool(payload.get('completed_utc')) and 'acceptance' in payload,
            'Final published study is required; never reproduce an in-progress evaluation')
    require(bool(payload.get('integrity')) and all(payload['integrity'].values()),
            'Original study integrity must pass before reproduction')
    protocol_path = ROOT / 'research/protocols/trajectory_risk_v2.json'
    require(read_json(protocol_path) == payload['protocol'], 'Registered protocol differs')
    require(_matches(protocol_path, payload['protocol_sha256']), 'Protocol hash differs')
    spec = payload['protocol']['specification']
    require(tuple(spec['evaluation']['arms']) == ARMS and
            set(payload['evaluation']) == set(ARMS) and
            set(payload['evaluation_raw']) == set(ARMS), 'All five final evaluation arms are required')
    require(payload['protocol_canonical_sha256'] == canonical_hash(payload['protocol']),
            'Protocol canonical hash differs')
    source_hashes = validate_sources(payload)
    old_path = ROOT / 'research/results/joint_risk.json'
    require(sha256(old_path) == spec['old_results']['preserve_byte_identical'][relative(old_path)],
            'Frozen old model artifact changed')
    old = read_json(old_path)['risk_model']
    require(canonical_hash(old) == spec['old_risk_model_sha256'], 'Old risk model differs')
    require(canonical_hash(payload['risk_model']) == payload['training']['model_canonical_sha256'],
            'New frozen risk model differs')
    raw_entries = {entry['path']: entry for entry in payload['raw_files']}
    configs = {arm['name']: arm for arm in spec['arms']}
    plans = {}
    for name in ARMS:
        if name == 'monitor':
            model = old
            kwargs = dict(mode='monitor', selector='full_only', feature_mode='legacy',
                          qhats=[1.] * spec['scope']['horizon'])
        else:
            config = configs[name]
            arm = payload['arms'][name]
            require(arm['configuration'] == config, 'Frozen arm configuration differs: ' + name)
            require(len(arm['qhats']) == spec['scope']['horizon'] and
                    arm['qhats'] == [stage['qhat'] for stage in arm['stages']],
                    'Frozen per-stage thresholds incomplete/different: ' + name)
            model = old if config['model'] == 'old' else payload['risk_model']
            kwargs = dict(mode='gated', selector=config['selector'],
                          feature_mode=config['feature_mode'], qhats=list(arm['qhats']))
        kwargs.update(horizon=spec['scope']['horizon'], diagnostic=True)
        raw_name = payload['evaluation_raw'][name]
        raw_path = resolve(raw_name)
        entry = raw_entries[raw_name]
        require(entry['kind'] == 'evaluation' and sha256(raw_path) == entry['sha256'],
                'Original evaluation raw hash/kind differs: ' + name)
        plans[name] = dict(model=model, kwargs=kwargs, path=raw_name, sha256=entry['sha256'])
    return payload, plans, source_hashes


def _runtime():
    """Imported only for real reproduction, never by --check."""
    import numpy as np
    from jev_tune.decision import load_backend
    from jev_tune.risk import JointRiskModel
    from jev_tune.trajectory_risk import run_trajectory_risk
    spec = importlib.util.spec_from_file_location('reproduce_sampler', ROOT / 'scripts/25_joint_risk.py')
    sampler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sampler)

    def load_model(value):
        return JointRiskModel(*(np.asarray(value[key], float) for key in ('mean', 'scale', 'coefficient')),
                              value['intercept'], value['temperature'])

    return load_backend(ROOT / 'models'), load_model, sampler.independent_plants, run_trajectory_risk


def original_run(payload, plan):
    raw = json.loads(gzip.decompress(resolve(plan['path']).read_bytes()))
    metadata = raw.pop('study_metadata')
    spec = payload['protocol']['specification']
    require(metadata['protocol_canonical_sha256'] == payload['protocol_canonical_sha256'] and
            metadata['seed'] == spec['evaluation']['seed'] and
            metadata['n_plants'] == spec['evaluation']['n_plants'] and
            metadata['kind'] == 'evaluation' and metadata['arguments'] == plan['kwargs'] and
            metadata['risk_model_sha256'] == canonical_hash(plan['model']),
            'Original raw invocation differs from frozen plan: ' + plan['path'])
    require(_matches(ROOT / 'src/jev_tune/trajectory_risk.py', metadata['engine_sha256']),
            'Original raw engine differs from current engine')
    return raw


def sum_counts(arms):
    counts = {}
    for arm in arms.values():
        for key, value in arm['additional_simulation_counts'].items():
            require(isinstance(value, int) and value >= 0, 'Invalid simulation ledger')
            counts[key] = counts.get(key, 0) + value
    return counts


def reproduce(result_path=RESULT, report_path=REPORT):
    require(not report_path.exists(), 'Reproduction report already exists; use --check (no overwrite)')
    payload, plans, source_hashes = load_inputs(result_path)
    result_hash = sha256(result_path)
    backend, load_model, sampler, run = _runtime()
    evaluation = payload['protocol']['specification']['evaluation']
    report = {'schema_version': 1, 'purpose': 'Exact deterministic replay of the already consumed five-arm test; not a new acceptance test.',
        'additional_independent_evidence': False, 'acceptance_recomputed': False,
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'original_result': {'path': relative(result_path), 'sha256': result_hash},
        'original_protocol_canonical_sha256': payload['protocol_canonical_sha256'],
        'engine_sha256': sha256(ROOT / 'src/jev_tune/trajectory_risk.py'),
        'source_sha256': source_hashes, 'packages': dict(payload['manifest']['packages']),
        'evaluation_seed': evaluation['seed'], 'n_plants_per_arm': evaluation['n_plants'], 'arms': {}}
    for name, plan in plans.items():
        expected = original_run(payload, plan)
        actual = run(backend, load_model(plan['model']),
                     sampler(evaluation['n_plants'], evaluation['seed']), **plan['kwargs'])
        expected_bytes, actual_bytes = canonical(expected), canonical(actual)
        report['arms'][name] = {'equal': expected_bytes == actual_bytes,
            'original_raw': {'path': plan['path'], 'sha256': plan['sha256']},
            'original_canonical_sha256': hashlib.sha256(expected_bytes).hexdigest(),
            'reproduced_canonical_sha256': hashlib.sha256(actual_bytes).hexdigest(),
            'additional_simulation_counts': actual['simulation_counts']}
        print(f"REPRODUCED {name}: equal={report['arms'][name]['equal']} actual_simulations={actual['simulation_counts']['total']}", flush=True)
        del expected, actual, expected_bytes, actual_bytes
    require(sha256(result_path) == result_hash and
            all(sha256(resolve(plan['path'])) == plan['sha256'] for plan in plans.values()),
            'Original artifacts changed during reproduction')
    require(validate_sources(payload) == source_hashes, 'Numerical sources changed during reproduction')
    report['equal'] = all(arm['equal'] for arm in report['arms'].values())
    report['additional_simulation_counts'] = sum_counts(report['arms'])
    report['completed_utc'] = datetime.now(timezone.utc).isoformat()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report


def check(result_path=RESULT, report_path=REPORT):
    """Validate saved replay hashes/accounting without a simulator invocation."""
    payload, plans, _ = load_inputs(result_path)
    report = read_json(report_path)
    require(report['additional_independent_evidence'] is False and report['acceptance_recomputed'] is False,
            'A replay cannot be independent acceptance evidence')
    require(report['original_result'] == {'path': relative(result_path), 'sha256': sha256(result_path)},
            'Original result hash differs from replay report')
    require(report['original_protocol_canonical_sha256'] == payload['protocol_canonical_sha256'],
            'Replay protocol hash differs')
    require(set(report['arms']) == set(ARMS), 'Replay must include all five arms')
    for path, expected in report['source_sha256'].items():
        require(_matches(resolve(path), expected), 'Replay source changed: ' + path)
    require(_matches(ROOT / 'src/jev_tune/trajectory_risk.py', report['engine_sha256']),
            'Replay engine changed')
    evaluation = payload['protocol']['specification']['evaluation']
    require(report['evaluation_seed'] == evaluation['seed'] and
            report['n_plants_per_arm'] == evaluation['n_plants'], 'Replay population differs')
    for name, plan in plans.items():
        arm = report['arms'][name]
        original = original_run(payload, plan)
        require(arm['original_raw'] == {'path': plan['path'], 'sha256': plan['sha256']} and
                arm['original_canonical_sha256'] == canonical_hash(original), 'Replay raw hash differs: ' + name)
        require(arm['equal'] == (arm['original_canonical_sha256'] == arm['reproduced_canonical_sha256']),
                'Replay comparison flag differs: ' + name)
        if arm['equal']:
            require(arm['additional_simulation_counts'] == original['simulation_counts'],
                    'Equal replay has a different simulation ledger: ' + name)
    require(report['additional_simulation_counts'] == sum_counts(report['arms']), 'Replay total ledger differs')
    require(report['equal'] == all(arm['equal'] for arm in report['arms'].values()), 'Replay overall flag differs')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', '--verify-only', action='store_true', dest='check',
                        help='Check the saved reproduction report without any simulation')
    args = parser.parse_args()
    report = check() if args.check else reproduce()
    print(json.dumps({'equal': report['equal'], 'additional_independent_evidence': False,
                      'additional_simulation_counts': report['additional_simulation_counts']}, indent=2))
    return 0 if report['equal'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
