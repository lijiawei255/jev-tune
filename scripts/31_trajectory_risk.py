"""Prospective trajectory-trained risk and pre-CP alternative joint actions."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import time

import numpy as np

from _experiment_protocol import manifest, sha256

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT/'research/protocols/trajectory_risk_v2.json'
RESULT = ROOT/'research/results/trajectory_risk.json'
RAW_DIR = ROOT/'research/results/trajectory_risk_raw'
DOC = ROOT/'docs/TRAJECTORY_RISK.md'


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def fixed_specification():
    initial = json.loads((ROOT/'research/results/joint_risk.json').read_text(encoding='utf-8'))
    return {
        'name': 'trajectory_risk_and_preconformal_joint_action_selection_v2', 'version': 2,
        'old_results': {'preserve_byte_identical': {
            str(p.relative_to(ROOT)).replace('\\', '/'): sha256(p) for p in [
                ROOT/'research/results/joint_risk.json',
                ROOT/'research/results/joint_risk_rollout.json',
                ROOT/'research/results/joint_risk_rollout_raw.json.gz']},
            'usage': 'Old evaluation is retrospective diagnosis only; never fitting, tuning, early stopping or candidate selection.'},
        'proposal': initial['protocol']['specification']['proposal'],
        'old_risk_model_sha256': canonical_hash(initial['risk_model']),
        'scope': {'families': initial['protocol']['specification']['families'],
            'sampling': 'IID uniform six-family mixture', 'initial': 'analytic ZN clipped [1e-4,1e3]',
            'simulation': '10 second unit step, zero measurement noise',
            'horizon': 20, 'safety': 'existing divergence/cost veto stops; no recovery',
            'return': 'best actually executed observation including initial',
            'not_covered': ['initial measurement safety', 'identification', 'recovery', 'domain shift', 'hardware safety', 'generic Python/C/MATLAB deployment']},
        'candidates': {'scales': [1., .5, .25],
            'construction': 'Scale the complete Temp Only expected/shrunk log10 step; then apply original gain bounds.',
            'selection': 'model_min_risk chooses lowest frozen temperature-scaled p(harmful), stable first index on ties, before any CP set.',
            'duplicates': 'Keep candidate metadata; deduplicate exact post-bound gains for labels/simulation; first index represents ties.',
            'unchanged': 'Selected unchanged candidate stops; it is not a reached changed calibration point.',
            'cp_rejection': 'Stop. Do not retry another candidate after observing a CP set.'},
        'risk_features': {'n': 44, 'new': '20 existing state descriptors +3 actually bounded steps +21 original choice probabilities; risk-only state[16]=0 at stage0, true previous cost change thereafter.',
            'old': 'Unmodified legacy 44 inputs, including initial state[16]=-J/5.',
            'proposal_inputs': 'Unchanged: feature correction is confined to the new risk head.'},
        'training': {'n_plants': 1024, 'seed': 910000001, 'horizon': 20,
            'behavior': 'plant_index modulo 3 selects scale index for the entire trajectory; stop on unchanged behavior or safety.',
            'labels': 'Measure all distinct changed joint candidates at each reached state. Only behavior action advances state; others diagnostic.',
            'model': {'classifier': 'LogisticRegression', 'C': 1., 'solver': 'lbfgs', 'max_iter': 2000, 'random_state': 72601, 'class_weight': None},
            'weighting': 'All collected candidate rows equally weighted; within-plant dependence is allowed in training, not IID calibration evidence.',
            'temperature': {'n_plants': 256, 'seed': 910000002, 'method': 'NLL fit using independent complete trajectory cohort, same fixed behavior mixture'},
            'development_audit': {'n_plants': 256, 'seed': 910000003, 'usage': 'Fixed diagnostic cohort only; no hyperparameter, feature, temperature, action scale, threshold, budget or sample-size search.'}},
        'risk_budget': {'trajectory_alpha': .1, 'alpha_per_stage': [.005]*20,
            'harmful': 'J_after > J_before, zero tolerance; legacy >2% only secondary',
            'accept_set': [True, False],
            'coverage': 'Stagewise marginal selected-action label coverage under fresh reached-sample exchangeability conditional on frozen prefix; union bound over 20 stages. Not conditional-on-execution risk.'},
        'arms': [
            {'name': 'old_initial512', 'model': 'old', 'selector': 'full_only', 'feature_mode': 'legacy', 'calibration': 'initial512'},
            {'name': 'old_reached2000', 'model': 'old', 'selector': 'full_only', 'feature_mode': 'legacy', 'calibration': 'reached2000'},
            {'name': 'trajectory_full', 'model': 'new', 'selector': 'full_only', 'feature_mode': 'history_zero', 'calibration': 'reached2000'},
            {'name': 'trajectory_selected', 'model': 'new', 'selector': 'model_min_risk', 'feature_mode': 'history_zero', 'calibration': 'reached2000'}],
        'primary_candidate': 'trajectory_selected',
        'calibration': {'target_reached': 2000, 'initial_cap_per_stage': 20000, 'batch_size': 512,
            'seed_formula': '900000000 + arm_index*1000000 + stage_zero_based*1000 + batch_zero_based',
            'sampling': 'New independent plants for every arm/stage/batch; follow that arm frozen earlier thresholds. One selected changed candidate per reached plant at target stage.',
            'quota': 'Take first 2000 reached in batch/plant generation order. Collection continuation depends only on reach count, never target score/label/q.',
            'batch_excess': 'All actually measured excess candidates remain raw and charged; exclude only by predetermined order beyond quota.',
            'rank': 'ceil((n+1)*(1-alpha_t))',
            'initial512': 'Exactly 512 initial plants; actual reached n; rank>n -> q=1.',
            'quota_shortfall': 'For reached2000, cap without quota -> q=1 even if rank<=n; explicitly engineering quota fallback, distinct from mathematical rank fallback.',
            'unreachable': 'If any frozen earlier q>=1, every selected candidate at that stage holds: later stages structurally unreachable; record zero samples/full set without wasteful new simulations.'},
        'evaluation': {'n_plants': 1024, 'seed': 920000001, 'fixed_once': True,
            'arms': ['monitor', 'old_initial512', 'old_reached2000', 'trajectory_full', 'trajectory_selected'],
            'paired': 'Same new plants across arms; no cross-arm calibration or evaluation fitting.',
            'monitor': 'Original full proposal and safety-stop behavior, no risk veto.',
            'rejected_diagnostics': 'Measure selected rejected action once for diagnosis, never feed state/history/best.',
            'selection': 'Primary arm fixed before data; other arms explanatory only; no winner selection using test.'},
        'acceptance': {'trajectory_harm_one_sided_95_upper_max': .1,
            'first_stage_execution_one_sided_95_lower_min': .5,
            'mean_cost': 'primary <= monitor, zero slack', 'p90_cost': 'primary <= monitor, zero slack',
            'operating_actual_simulations': 'primary <= monitor', 'integrity_required': True,
            'interpretation': 'Separate exact one-sided bounds, not joint 95%; mean/p90 are empirical gates.',
            'failure': 'research_only; preserve all results; no threshold/alpha/model/sample tweaks after test',
            'pass_scope': 'Only exact new research runner/scoped population; generic runtime defaults remain unchanged.'},
        'accounting': {'actual': 'Count every actual plant simulation once in initial/executed/diagnostic buckets; report cache hits and operating requests separately.',
            'cache': 'Per-plant exact float64 gain tuple, deterministic simulator only; include every result-affecting setting via fixed protocol. No cross-plant reuse.',
            'diagnostic': 'May enter operating history only if that exact action is later truly adopted; never update best merely from observing a rejected/alternative candidate.'},
        'artifacts': 'Raw per-batch compressed shards with SHA256; training data and serialized model from scripts only; summaries/docs generated from JSON.',
    }


def register():
    spec = fixed_specification()
    if PROTOCOL.exists():
        if json.loads(PROTOCOL.read_text(encoding='utf-8'))['specification'] != spec:
            raise SystemExit('Refusing to replace frozen protocol')
    else:
        PROTOCOL.write_text(json.dumps({'registered_utc': datetime.now(timezone.utc).isoformat(),
                                       'specification': spec}, indent=2)+'\n', encoding='utf-8')
    print(f'Frozen {PROTOCOL}; no new study data collected')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--register-only', action='store_true')
    args = parser.parse_args()
    if args.register_only:
        register()
    else:
        raise SystemExit('Study runner is being implemented; no data collected.')
