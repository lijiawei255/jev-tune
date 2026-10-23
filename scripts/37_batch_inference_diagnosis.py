"""Post-hoc fixed-input batch-shape diagnosis, not new acceptance evidence.

Recover plant 480 at stage 1 once, then repeat that same input in the eight
predeclared batch sizes. Exactly one plant simulation is additionally charged.
This copied-input experiment does not recreate the actual full cohort layout.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'research/results/batch_inference_diagnosis.json'
BATCH_SIZES = (1, 2, 16, 17, 32, 171, 512, 1024)
TARGET_PLANT = 480
TARGET_STAGE = 1


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_script(name):
    spec = importlib.util.spec_from_file_location('batch_diagnosis_' + name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def run():
    if REPORT.exists():
        raise ValueError('Diagnostic report already exists; use --check, never repeat/overwrite')
    import torch
    from jev_tune.decision import load_backend
    from jev_tune.decode import decide
    from jev_tune.metrics import cost_from_metrics
    from jev_tune.plants import simulate, ultimate_gain
    from jev_tune.state import build_state

    torch.set_num_threads(1)
    protocol_path = ROOT / 'research/protocols/trajectory_risk_v2.json'
    protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
    spec = protocol['specification']
    checkpoint = ROOT / 'models/jev_head.pt'; calibration = ROOT / 'models/calibration.json'
    if sha256(checkpoint) != spec['proposal']['checkpoint_sha256']:
        raise ValueError('Frozen proposal checkpoint changed')
    if json.loads(calibration.read_text(encoding='utf-8'))['choice_temperature'] != spec['proposal']['choice_temperature']:
        raise ValueError('Frozen proposal temperatures changed')
    raw_inputs = {}
    originals = {}
    for name in ('monitor', 'old_initial512'):
        path = ROOT / 'research/results/trajectory_risk_raw' / ('evaluation_' + name + '.json.gz')
        data = json.loads(gzip.decompress(path.read_bytes()))
        current = next(t for t in data['transitions'] if t['plant_index'] == TARGET_PLANT and t['stage'] == TARGET_STAGE)
        previous = next(t for t in data['transitions'] if t['plant_index'] == TARGET_PLANT and t['stage'] == TARGET_STAGE - 1)
        indices = [t['plant_index'] for t in data['transitions'] if t['stage'] == TARGET_STAGE and t['proposal_valid']]
        originals[name] = dict(current=current, previous=previous, active_batch_size=len(indices),
                               target_batch_position=indices.index(TARGET_PLANT))
        raw_inputs[name] = {'path': str(path.relative_to(ROOT)).replace('\\', '/'), 'sha256': sha256(path)}
    reference = originals['monitor']
    other = originals['old_initial512']
    if any(reference['current'][key] != other['current'][key] for key in ('gains_before', 'cost_before')):
        raise ValueError('Fixed diagnostic point no longer has identical current gains/cost')
    if reference['previous']['applied_step'] != other['previous']['applied_step']:
        raise ValueError('Fixed diagnostic point has different preceding action')
    plants = load_script('25_joint_risk').independent_plants(spec['evaluation']['n_plants'], spec['evaluation']['seed']).take([TARGET_PLANT])
    ku, tu = ultimate_gain(plants)
    gzn = np.column_stack([.6 * ku, 1.2 * ku / tu, .075 * ku * tu])
    current_gains = np.asarray([reference['current']['gains_before']], float)
    # The only new simulation in this diagnostic. It does not enter study data.
    response = simulate(plants, current_gains, horizon=10., ref=1.)
    costs = cost_from_metrics(response['metrics'], y_curve=response['y_curve'], horizon=10., ref=1.)
    features, curves = build_state(response['metrics'], response['y_curve'], response['u_curve'],
        current_gains, gzn, ku, tu,
        prev_action=np.asarray([reference['previous']['applied_step']], float),
        prev_cost=np.asarray([reference['previous']['cost_before']], float), cost=costs,
        iteration=np.asarray([TARGET_STAGE]), horizon=10., ref=1.)
    backend = load_backend(ROOT / 'models')
    batches = {}
    for n in BATCH_SIZES:
        answer = backend.answer(np.repeat(features, n, axis=0), np.repeat(curves, n, axis=0))
        probabilities = np.stack([c.probs for c in answer.choice], axis=1)
        decision = decide(answer, backend.space, use_expectation=True, shrinkage=1., abstain=None, conformal=None)
        batches[str(n)] = {'choice_probabilities': probabilities.tolist(), 'base_step': decision.step.tolist()}
    baseline = batches['1024']
    baseline_p = np.asarray(baseline['choice_probabilities'])[TARGET_PLANT]
    baseline_step = np.asarray(baseline['base_step'])[TARGET_PLANT]
    for n in BATCH_SIZES:
        p = np.asarray(batches[str(n)]['choice_probabilities']); step = np.asarray(batches[str(n)]['base_step'])
        batches[str(n)]['relative_to_reference_row'] = {
            'probability_max_abs': float(np.max(np.abs(p - baseline_p))),
            'base_step_max_abs': float(np.max(np.abs(step - baseline_step))),
            'nonidentical_probability_rows': int(np.any(p != baseline_p, axis=(1, 2)).sum())}
    original_comparisons = {}
    for name, rows in originals.items():
        actual = batches[str(rows['active_batch_size'])]
        pos = rows['target_batch_position']
        p = np.asarray(actual['choice_probabilities'])[pos]
        step = np.asarray(actual['base_step'])[pos]
        original_comparisons[name] = {'active_batch_size': rows['active_batch_size'], 'target_batch_position': pos,
            'original_choice_probabilities': rows['current']['choice_probabilities'],
            'original_base_step': rows['current']['base_step'],
            'probability_max_abs': float(np.max(np.abs(p - rows['current']['choice_probabilities']))),
            'base_step_max_abs': float(np.max(np.abs(step - rows['current']['base_step'])))}
    source_paths = list((ROOT / 'src/jev_tune').glob('*.py')) + [Path(__file__), ROOT / 'scripts/25_joint_risk.py']
    result = {
        'schema_version': 1, 'scope': 'Post-hoc numerical diagnosis of the already consumed test; copied input layout, not a new acceptance study.',
        'additional_independent_evidence': False, 'acceptance_recomputed': False,
        'completed_utc': datetime.now(timezone.utc).isoformat(), 'torch_threads': torch.get_num_threads(),
        'target': {'plant_index': TARGET_PLANT, 'plant_identity': int(plants.noise_seed[0]), 'stage': TARGET_STAGE,
                   'seed': spec['evaluation']['seed'], 'original_n_plants': spec['evaluation']['n_plants'],
                   'gains_before': current_gains[0].tolist()},
        'input_artifacts': {'protocol': {'path': str(protocol_path.relative_to(ROOT)).replace('\\', '/'), 'sha256': sha256(protocol_path)},
                            'checkpoint_sha256': sha256(checkpoint), 'calibration_sha256': sha256(calibration), 'raw': raw_inputs},
        'source_sha256': {str(path.relative_to(ROOT)).replace('\\', '/'): sha256(path) for path in source_paths},
        'recovered_input': {'features': features[0].tolist(), 'curves': curves[0].tolist(), 'cost': float(costs[0]),
                            'original_cost': reference['current']['cost_before'],
                            'cost_abs_difference': float(abs(costs[0] - reference['current']['cost_before'])),
                            'state_max_abs_difference': float(np.max(np.abs(features[0] - np.asarray(reference['current']['features'])[:20])))},
        'batch_sizes': list(BATCH_SIZES), 'reference': {'batch_size': 1024, 'row': TARGET_PLANT},
        'batches': batches, 'original_layout_position_comparisons': original_comparisons,
        'interpretation': 'Repeated identical tensors isolate batch-shape/row-position floating-point effects. The full real-cohort layout is not reconstructed; raw actions, CP boundaries and acceptance are unchanged.',
        'additional_simulation_counts': {'diagnostic_state_reconstruction': 1, 'total': 1},
        'inference_counts': {'forward_calls': len(BATCH_SIZES), 'rows': sum(BATCH_SIZES)}}
    for record in raw_inputs.values():
        if sha256(ROOT / record['path']) != record['sha256']:
            raise ValueError('Original raw changed during diagnostic')
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with REPORT.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return result


def check():
    result = json.loads(REPORT.read_text(encoding='utf-8'))
    replay = load_script('34_reproduce_trajectory_evaluation')
    if result['additional_independent_evidence'] is not False or result['acceptance_recomputed'] is not False:
        raise ValueError('Numerical diagnosis is not independent acceptance evidence')
    if result['batch_sizes'] != list(BATCH_SIZES) or result['additional_simulation_counts'] != {'diagnostic_state_reconstruction': 1, 'total': 1}:
        raise ValueError('Fixed diagnostic plan/accounting changed')
    if result['inference_counts'] != {'forward_calls': len(BATCH_SIZES), 'rows': sum(BATCH_SIZES)}:
        raise ValueError('Inference accounting changed')
    for path, digest in result['source_sha256'].items():
        if not replay._matches(ROOT / path, digest):
            raise ValueError('Diagnostic source changed: ' + path)
    inputs = result['input_artifacts']
    for entry in (inputs['protocol'], *inputs['raw'].values()):
        if not replay._matches(ROOT / entry['path'], entry['sha256']):
            raise ValueError('Diagnostic input hash changed: ' + entry['path'])
    for path, key in (('models/jev_head.pt', 'checkpoint_sha256'), ('models/calibration.json', 'calibration_sha256')):
        if not replay._matches(ROOT / path, inputs[key]):
            raise ValueError('Diagnostic model input changed: ' + path)
    ref = result['reference']; baseline = result['batches'][str(ref['batch_size'])]
    p0, d0 = (np.asarray(baseline[key])[ref['row']] for key in ('choice_probabilities', 'base_step'))
    for n in BATCH_SIZES:
        batch = result['batches'][str(n)]
        p, d = np.asarray(batch['choice_probabilities']), np.asarray(batch['base_step'])
        if p.shape != (n, 3, 7) or d.shape != (n, 3) or not np.isfinite(p).all() or not np.isfinite(d).all():
            raise ValueError('Invalid fixed-batch output')
        expected = {'probability_max_abs': float(np.max(np.abs(p-p0))),
                    'base_step_max_abs': float(np.max(np.abs(d-d0))),
                    'nonidentical_probability_rows': int(np.any(p != p0, axis=(1, 2)).sum())}
        if batch['relative_to_reference_row'] != expected:
            raise ValueError('Batch difference summary differs')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only hashes/summary checks; no simulation or forward call')
    args = parser.parse_args()
    result = check() if args.check else run()
    print(json.dumps({'additional_simulation_counts': result['additional_simulation_counts'],
                      'recovered_cost_difference': result['recovered_input']['cost_abs_difference'],
                      'recovered_state_difference': result['recovered_input']['state_max_abs_difference'],
                      'original_comparisons': result['original_layout_position_comparisons'],
                      'batch_differences': {n: b['relative_to_reference_row'] for n, b in result['batches'].items()}}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
