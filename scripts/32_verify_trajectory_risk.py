"""Independently reconstruct the registered trajectory-risk study evidence.

This verifier never simulates, selects a model, or changes a threshold. It
replays the raw decision/accounting records, regenerates cohort identities,
refits the one prescribed estimator, and recomputes finite-sample statistics.
No empirical check establishes exchangeability or hardware safety.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
from scipy.special import expit
from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[1]
RESULT = Path('research/results/trajectory_risk.json')
BUCKETS = ('operating_initial', 'executed', 'diagnostic_rejected',
           'diagnostic_collected', 'diagnostic_training')
SCALES = (1., .5, .25)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same(actual, expected):
    """Exact structure/discrete values, roundoff tolerance only for real values."""
    if isinstance(expected, dict):
        return (isinstance(actual, dict) and actual.keys() == expected.keys()
                and all(same(actual[k], v) for k, v in expected.items()))
    if isinstance(expected, (list, tuple)):
        return (isinstance(actual, (list, tuple)) and len(actual) == len(expected)
                and all(same(a, e) for a, e in zip(actual, expected)))
    if isinstance(expected, (float, np.floating)):
        return (isinstance(actual, (int, float, np.number)) and not isinstance(actual, bool)
                and math.isfinite(float(actual)) and math.isclose(float(actual), float(expected),
                                                                 rel_tol=1e-12, abs_tol=1e-12))
    return type(actual) is type(expected) and actual == expected


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def hash_matches(path, expected, *, text=False):
    if not path.is_file():
        return False
    data = path.read_bytes()
    variants = [data]
    if text:
        lf = data.replace(b'\r\n', b'\n')
        variants += [lf, lf.replace(b'\n', b'\r\n')]
    return any(hashlib.sha256(value).hexdigest() == expected for value in variants)


def load_script(name):
    spec = importlib.util.spec_from_file_location('trajectory_evidence_' + name,
                                                ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probabilities(model, features):
    x = np.asarray(features, float).reshape(-1, 44)
    mean, scale, coefficient = (np.asarray(model[k], float) for k in ('mean', 'scale', 'coefficient'))
    require(all(a.shape == (44,) and np.isfinite(a).all() for a in (mean, scale, coefficient)),
            'risk model requires 44 finite parameters per vector')
    require(np.all(scale > 0) and math.isfinite(model['temperature']) and model['temperature'] > 0,
            'risk model scale and temperature must be positive')
    require(model['classes'] == ['noninferior', 'harmful'], 'risk class ordering differs')
    require(np.isfinite(x).all() and math.isfinite(model['intercept']), 'nonfinite risk input/intercept')
    z = ((x - mean) / scale @ coefficient + model['intercept']) / model['temperature']
    # Compute both tails stably: 1-expit(z) loses small nonzero probabilities,
    # corrupting NLL evidence even though a loose normalization check passes.
    return np.column_stack([expit(-z), expit(z)])


def counts(values):
    result = {k: int(values.get(k, 0)) for k in BUCKETS}
    result.update(operating=result['operating_initial'] + result['executed'],
                  total=sum(result.values()), requests=int(values.get('requests', 0)),
                  cache_hits=int(values.get('cache_hits', 0)),
                  execution_requests=int(values.get('execution_requests', 0)))
    return result


def gain_key(gains):
    a = np.asarray(gains, dtype='<f8')
    require(a.shape == (3,) and np.isfinite(a).all() and np.all((a >= 1e-4) & (a <= 1e3)),
            'gain vector must contain three finite bounded gains')
    return a.tobytes()


def verify_run(run, model, qhats=None, *, collect_step=None, diagnostic=True, priors=None):
    """Reconstruct decisions and actual simulation ledger from one raw shard.

    The formulas below intentionally do not call the trajectory runtime,
    decoder, risk model forward method, or runtime summary function.
    """
    mode, selector, feature_mode = (run[k] for k in ('mode', 'selector', 'feature_mode'))
    require(mode in ('training', 'monitor', 'gated', 'collect'), 'unknown run mode')
    require(selector in ('full_only', 'model_min_risk'), 'unknown selector')
    require(feature_mode in ('legacy', 'history_zero'), 'unknown feature mode')
    require(run['scales'] == list(SCALES), 'candidate scales differ')
    n, horizon = run['n_plants'], run['horizon']
    require(type(n) is int and n >= 0 and type(horizon) is int and horizon > 0, 'invalid run dimensions')
    plants, transitions = run['per_plant'], run['transitions']
    require(len(plants) == n and [p['plant_index'] for p in plants] == list(range(n)), 'plant index coverage')
    per_rows = [[] for _ in plants]
    order = [(t['stage'], t['plant_index']) for t in transitions]
    require(order == sorted(set(order)), 'transition ordering/uniqueness differs')
    for t in transitions:
        require(0 <= t['plant_index'] < n and 0 <= t['stage'] < horizon, 'transition index out of range')
        per_rows[t['plant_index']].append(t)
    flat_candidates = [c for t in transitions for c in t['candidates']]
    if model is not None and flat_candidates:
        expected_p = probabilities(model, [c['features'] for c in flat_candidates])
        require(np.allclose(np.asarray([c['probabilities'] for c in flat_candidates]), expected_p,
                            rtol=1e-12, atol=1e-12), 'risk probabilities disagree with frozen model')
    elif model is None:
        require(all(c['probabilities'] is None for c in flat_candidates), 'unfitted training data contains model probabilities')
    expected_collected = []
    total_counts = {key: 0 for key in (*BUCKETS, 'requests', 'cache_hits', 'execution_requests')}
    delta = np.log10(np.array([.5, .7, .87, 1., 1.15, 1.43, 2.]))
    var_ref = float(np.var(delta))
    for i, (plant, rows) in enumerate(zip(plants, per_rows)):
        where = f'plant {i}'
        require(plant['behavior_index'] == (i % 3 if mode == 'training' else None), where + ': behavior index')
        require(rows and [t['stage'] for t in rows] == list(range(len(rows))), where + ': nonconsecutive stages')
        current_g = plant['initial_gains']; current_j = plant['initial_J']
        require(current_j is not None and math.isfinite(current_j), where + ': nonfinite initial observation')
        cache = {gain_key(current_g): {'cost': current_j, 'id': 0, 'kind': 'operating_initial', 'stage': -1}}
        tally = {key: 0 for key in total_counts}
        tally.update(operating_initial=1, requests=1)
        history = [{'stage': -1, 'gains': current_g, 'cost': current_j,
                    'observed_finite': True, 'cache_hit': False, 'measurement_id': 0}]
        best_j, best_g, prev_j, prev_step, harmed, harmed2 = current_j, current_g, 0., np.zeros(3), False, False
        stopped = False
        for t in rows:
            s = t['stage']; context = f'{where} stage {s}'
            require(not stopped, context + ': action after a stop')
            require(t['plant_identity'] == plant['plant_identity'], context + ': plant identity mismatch')
            require(same(t['gains_before'], current_g) and same(t['cost_before'], current_j), context + ': state was not adopted history')
            cs = t['candidates']
            if not t['proposal_valid']:
                require(not cs and not t['measured'] and not t['executed'] and
                        t['reason'] in ('unstable', 'safety_threshold'), context + ': invalid safety stop')
                stopped = True
                continue
            require(len(cs) == 3, context + ': incomplete candidate set')
            p = np.asarray(t['choice_probabilities'], float)
            require(p.shape == (3, 7) and np.isfinite(p).all() and np.all((p >= 0) & (p <= 1))
                    and np.allclose(p.sum(-1), 1., atol=1e-10), context + ': choice distribution')
            mu = p @ delta
            base = np.clip(mu / (1 + np.maximum(p @ (delta*delta) - mu*mu, 0.) / var_ref), -.32, .32)
            require(np.allclose(t['base_step'], base, rtol=1e-12, atol=1e-12), context + ': expected/shrunk proposal mismatch')
            expected_selection = (i % 3 if mode == 'training' else 0 if mode == 'monitor' or selector == 'full_only'
                                  else int(np.argmin([c['probabilities'][1] for c in cs])))
            require(type(t['selected_index']) is int and t['selected_index'] == expected_selection,
                    context + ': candidate not selected by frozen pre-CP rule')
            chosen = cs[expected_selection]
            seen = {}
            for ci, (c, scale) in enumerate(zip(cs, SCALES)):
                require(c['index'] == ci and same(c['scale'], scale), context + ': candidate ordering')
                commanded = base * scale
                g = 10. ** np.clip(np.log10(current_g) + commanded, -4., 3.)
                g = np.where(commanded == 0., current_g, g)
                g = np.clip(g, 1e-4, 1e3)
                require(np.allclose(c['commanded_step'], commanded, rtol=1e-12, atol=1e-12)
                        and np.allclose(c['gains'], g, rtol=1e-12, atol=1e-12), context + ': bounded complete action')
                key = gain_key(c['gains']); first = seen.setdefault(key, c['index'])
                require(c['equivalent_to'] == first and c['changed'] == (key != gain_key(current_g)), context + ': exact candidate equivalence')
                applied = np.log10(np.asarray(c['gains']) / current_g)
                x = np.asarray(c['features'], float)
                require(x.shape == (44,) and np.isfinite(x).all(), context + ': feature shape/finiteness')
                history_change = 0. if feature_mode == 'history_zero' and s == 0 else float(np.float32(np.clip((prev_j-current_j)/5., -3., 3.)))
                require(same(x[16].item(), history_change), context + ': risk history feature semantics')
                require(np.array_equal(x[13:16], (np.clip(prev_step, -.5, .5)*4).astype(np.float32))
                        and x[17] == float(np.float32(np.clip(s/20., 0., 1.))), context + ': prior action/stage features')
                if priors is not None:
                    gzn, ku, tu = priors; g = np.asarray(current_g)
                    ratios = [g[0]/max(gzn[i, 0], 1e-9),
                              (g[1]+1e-6)/(gzn[i, 1]+1e-6),
                              (g[2]+1e-6)/(gzn[i, 2]+1e-6)]
                    gain_features = (np.clip(np.log10(np.maximum(ratios, 1e-9)), -3., 3.)/3.).astype(np.float32)
                    prior_features = np.asarray([np.clip(np.log10(max(ku[i]/max(g[0], 1e-9), 1e-9)), -3., 3.)/3.,
                                                 np.clip(tu[i]/10., 0., 5.)/5.], dtype=np.float32)
                    require(np.array_equal(x[10:13], gain_features) and np.array_equal(x[18:20], prior_features),
                            context + ': regenerated plant/gain state features')
                require(np.array_equal(x[:20], np.asarray(chosen['features'])[:20])
                        and np.allclose(c['applied_step'], applied, rtol=1e-12, atol=1e-12)
                        and np.array_equal(x[20:23], np.asarray(c['applied_step']))
                        and np.array_equal(x[23:], p.reshape(-1)), context + ': complete joint features')
            for field, selected_field in (('gains_proposed', 'gains'), ('proposed_step', 'commanded_step'),
                                          ('applied_step', 'applied_step'), ('features', 'features'), ('probabilities', 'probabilities')):
                require(same(t[field], chosen[selected_field]), context + ': selected ' + field)
            target = mode == 'collect' and s == collect_step
            cp = chosen['changed'] and mode != 'training' and not target and qhats is not None
            if cp:
                q = qhats[s]
                mask = ((1 - np.asarray(chosen['probabilities'])) <= q).tolist()
                accept = bool(mask[0] and not mask[1])
                require(same(t['prediction_set'], mask) and t['accepted'] is accept and same(t['qhat'], q)
                        and t['qhat_full_set'] is bool(q >= 1), context + ': incomplete or altered CP set')
            else:
                require(t['prediction_set'] is None and t['accepted'] is None and t['qhat'] is None
                        and t['qhat_full_set'] is False, context + ': CP evaluated on ineligible action')
            for c in cs:
                selected = c['index'] == expected_selection
                bucket = None
                if c['changed']:
                    if mode == 'training':
                        bucket = 'executed' if selected else 'diagnostic_training'
                    elif selected:
                        bucket = ('diagnostic_collected' if target else 'executed' if mode == 'monitor' or t['accepted']
                                  else 'diagnostic_rejected' if diagnostic else None)
                require(c['measured'] is (bucket is not None), context + ': candidate measurement eligibility')
                if bucket is None:
                    require(not c['simulation_performed'] and not c['cache_hit'] and c['cost_after'] is None,
                            context + ': unrequested candidate observation')
                    continue
                require(c['observed_finite'] is True and c['cost_after'] is not None and math.isfinite(c['cost_after']),
                        context + ': nonfinite candidate observation')
                key = gain_key(c['gains']); cached = key in cache
                tally['requests'] += 1; tally['execution_requests'] += int(bucket == 'executed')
                if cached:
                    tally['cache_hits'] += 1
                else:
                    cache[key] = {'cost': c['cost_after'], 'id': len(cache), 'kind': bucket, 'stage': s}
                    tally[bucket] += 1
                entry = cache[key]
                require(c['cache_hit'] is cached and c['simulation_performed'] is (not cached)
                        and c['measurement_kind'] == bucket and c['measurement_id'] == entry['id']
                        and c['measurement_source_kind'] == entry['kind']
                        and c['measurement_source_stage'] == entry['stage'] and same(c['cost_after'], entry['cost']),
                        context + ': cache/simulation provenance mismatch')
                label = int(c['cost_after'] > current_j)
                require(type(c['label']) is int and c['label'] == label and c['harmful'] is bool(label)
                        and c['harmful_gt2pct'] is bool(c['cost_after'] > current_j*1.02), context + ': paired label mismatch')
                if (mode == 'training' and c['equivalent_to'] == c['index']) or target:
                    expected_collected.append({'features': c['features'], 'labels': label, 'current_cost': current_j,
                        'proposed_cost': c['cost_after'], 'plant_index': i, 'plant_identity': plant['plant_identity'],
                        'stage': s, 'candidate_index': c['index'], 'scale': c['scale'],
                        'simulation_performed': c['simulation_performed'], 'cache_hit': c['cache_hit']})
            executed = bool(chosen['measured'] and chosen['measurement_kind'] == 'executed')
            require(t['executed'] is executed and t['measured'] is chosen['measured'], context + ': selected execution mismatch')
            if chosen['measured']:
                for field in ('simulation_performed', 'cache_hit', 'measurement_kind', 'cost_after', 'label',
                              'observed_finite', 'harmful', 'harmful_gt2pct', 'measurement_id',
                              'measurement_source_kind', 'measurement_source_stage'):
                    require(same(t[field], chosen[field]), context + ': selected observation ' + field)
            if executed:
                require(mode in ('training', 'monitor') or (t['accepted'] and not target), context + ': rejected execution')
                if mode in ('gated', 'collect') and chosen['label'] == 1:
                    require(not t['prediction_set'][1], context + ': harm not contained in miscoverage')
                harmed |= chosen['cost_after'] > current_j; harmed2 |= chosen['cost_after'] > 1.02*current_j
                prev_j, prev_step = current_j, np.asarray(chosen['applied_step'])
                current_j, current_g = chosen['cost_after'], chosen['gains']
                history.append({'stage': s, 'gains': current_g, 'cost': current_j, 'observed_finite': True,
                                'cache_hit': chosen['cache_hit'], 'measurement_id': chosen['measurement_id']})
                if current_j < best_j:
                    best_j, best_g = current_j, current_g
                require(t['reason'] in ('executed', 'executed_unstable', 'executed_safety_threshold'), context + ': executed reason')
                stopped = t['reason'] != 'executed'
                if current_j > max(3*best_j+1, 8):
                    require(stopped, context + ': safety cost veto omitted')
            else:
                expected_reason = 'no_action' if not chosen['changed'] else 'collected' if target else 'risk_rejected'
                require(t['reason'] == expected_reason, context + ': stop reason')
                stopped = True
        require(stopped or len(rows) == horizon, where + ': unexplained early stop')
        reason = rows[-1]['reason']
        expected_stop = reason.removeprefix('executed_') if reason != 'executed' else 'horizon'
        require(plant['stop_reason'] == expected_stop, where + ': final stop reason')
        require(same(plant['operating_history'], history), where + ': nonadopted diagnostic entered operating history')
        require(plant['best_valid'] is True and same(plant['best_J'], best_j) and same(plant['best_gains'], best_g)
                and same(plant['current_J'], current_j) and same(plant['current_gains'], current_g), where + ': final state/best not measured operating history')
        require(plant['any_harm'] is bool(harmed) and plant['any_harm_gt2pct'] is bool(harmed2), where + ': trajectory event')
        require(same(plant['simulation_counts'], counts(tally)), where + ': simulation counts')
        for key in total_counts:
            total_counts[key] += tally[key]
    require(same(run['simulation_counts'], counts(total_counts)), 'run simulation ledger mismatch')
    # Runtime records candidate-major within stage, then ascending plant index.
    expected_collected.sort(key=lambda row: (row['stage'], row['candidate_index'], row['plant_index']))
    expected = {key: [row[key] for row in expected_collected] for key in run['collected']}
    require(set(expected) == {'features', 'labels', 'current_cost', 'proposed_cost', 'plant_index',
                             'plant_identity', 'stage', 'candidate_index', 'scale', 'simulation_performed', 'cache_hit'},
            'unexpected collected dataset columns')
    require(same(run['collected'], expected), 'collected dataset differs from measured unique candidates')
    if mode == 'collect':
        require(all(s == collect_step for s in expected['stage']) and len(set(expected['plant_index'])) == len(expected['plant_index']),
                'calibration must have at most one target action per plant')
    return {'simulation_counts': counts(total_counts), 'collected': expected}


def summarize(run):
    plants, rows = run['per_plant'], run['transitions']; n = len(plants)
    require(n > 0, 'evaluation needs positive number of independent plants')
    executed = [r for r in rows if r['executed']]
    harmful = [r for r in executed if r['cost_after'] > r['cost_before']]
    legacy = [r for r in executed if r['cost_after'] > 1.02*r['cost_before']]
    measured = [r for r in rows if r['measured'] and r['prediction_set'] is not None]
    covered = sum(r['prediction_set'][int(r['cost_after'] > r['cost_before'])] for r in measured)
    def bound(k):
        return {'events': k, 'n': n, 'rate': k/n, 'confidence_one_sided': .95,
                'lower': 0. if k == 0 else float(beta.ppf(.05, k, n-k+1)),
                'upper': 1. if k == n else float(beta.ppf(.95, k+1, n-k))}
    costs = np.asarray([p['best_J'] for p in plants])
    return {'n_plants': n, 'n_executed': len(executed), 'n_harmful': len(harmful),
            'n_harmful_gt_2pct': len(legacy), 'harmful_rate': len(harmful)/len(executed) if executed else None,
            'harmful_gt_2pct_rate': len(legacy)/len(executed) if executed else None,
            'trajectory_harm': bound(len({r['plant_index'] for r in harmful})),
            'first_stage_execution': bound(len({r['plant_index'] for r in executed if r['stage'] == 0})),
            'final_cost': {'mean': float(costs.mean()), 'median': float(np.median(costs)), 'p90': float(np.percentile(costs, 90))},
            'measured_label_coverage': {'covered': covered, 'n': len(measured), 'rate': covered/len(measured) if measured else None},
            'simulation_counts': run['simulation_counts']}


def verify_runner_invocations(payload, manifest_hashes):
    """Bind each shard to an archived executing runner, including resumptions."""
    entries = {r['path']: r for r in payload['raw_files']}
    invocations = payload['runner_invocations']
    require(invocations and invocations[0]['phase'] in ('training_calibration', 'full_study'), 'missing original collection invocation')
    require(invocations[0]['source_sha256'] == manifest_hashes['scripts/31_trajectory_risk.py']
            and datetime.fromisoformat(invocations[0]['started_utc']) >= datetime.fromisoformat(payload['started_utc']),
            'initial runner snapshot differs from collection manifest')
    covered = set(); previous_start = datetime.fromisoformat(payload['started_utc'])
    for invocation in invocations:
        require(invocation['phase'] in ('training_calibration', 'evaluation', 'full_study'), 'unknown runner invocation phase')
        source = (ROOT/invocation['source_path']).resolve()
        require(source.is_relative_to((ROOT/'research/protocols/trajectory_risk_sources').resolve())
                and hash_matches(source, invocation['source_sha256'], text=True), 'executing runner snapshot hash mismatch')
        started = datetime.fromisoformat(invocation['started_utc'])
        require(started >= previous_start, 'runner invocation chronology differs')
        previous_start = started
        newly_written = invocation['raw_files']; reused = invocation.get('reused_raw_files', [])
        require(len(newly_written) == len(set(newly_written)) and len(reused) == len(set(reused)), 'duplicate invocation raw reference')
        require(set(reused) <= covered and not (set(newly_written) & covered), 'raw shard generated twice or reused before creation')
        require(set(newly_written) <= set(entries), 'invocation references missing raw shard')
        if invocation['phase'] == 'training_calibration':
            require(all(entries[path]['kind'] != 'evaluation' for path in newly_written), 'test collected before final model/calibration freeze')
        elif invocation['phase'] == 'evaluation':
            require(started >= datetime.fromisoformat(payload['training']['model_frozen_utc']), 'test invocation predates model freeze')
        covered.update(newly_written)
    require(covered == set(entries), 'raw shards lack unique executing runner provenance')


def verify_payload(payload):
    """Validate a complete study before or after acceptance fields are attached."""
    protocol_path = ROOT / 'research/protocols/trajectory_risk_v2.json'
    protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
    spec = protocol['specification']
    require(payload['protocol'] == protocol and spec['version'] == 2, 'registered protocol mismatch')
    protocol_hash = canonical_hash(protocol)
    require(payload['protocol_canonical_sha256'] == protocol_hash and
            hash_matches(protocol_path, payload['protocol_sha256'], text=True), 'protocol hashes differ')
    require(datetime.fromisoformat(protocol['registered_utc']) <= datetime.fromisoformat(payload['started_utc'])
            <= datetime.fromisoformat(payload['training']['model_frozen_utc']), 'protocol/model time order')
    old_path = ROOT / 'research/results/joint_risk.json'
    old_model = json.loads(old_path.read_text(encoding='utf-8'))['risk_model']
    require(canonical_hash(old_model) == spec['old_risk_model_sha256'], 'old model changed')
    for filename, digest in spec['old_results']['preserve_byte_identical'].items():
        require(hash_matches(ROOT / filename, digest, text=filename.endswith('.json')), 'old evidence changed: ' + filename)
    # Only numerical dependencies are pinned; adding a verifier or rendering
    # documentation after collection cannot change a recorded experiment.
    manifest_hashes = {str(k).replace('\\', '/'): v for k, v in payload['manifest']['file_sha256'].items()}
    numerical_sources = ['scripts/25_joint_risk.py',
        'scripts/_experiment_protocol.py'] + ['src/jev_tune/' + name + '.py' for name in
        ('trajectory_risk', 'risk', 'plants', 'metrics', 'state', 'decision', 'decode', 'primitives', 'model')]
    for filename in numerical_sources:
        require(filename in manifest_hashes and hash_matches(ROOT / filename, manifest_hashes[filename], text=True),
                'numerical source changed after collection: ' + filename)
    require(hash_matches(ROOT/'models/jev_head.pt', spec['proposal']['checkpoint_sha256']), 'proposal checkpoint changed')
    calibration = json.loads((ROOT/'models/calibration.json').read_text(encoding='utf-8'))
    require(calibration['choice_temperature'] == spec['proposal']['choice_temperature'], 'proposal temperatures changed')
    model = payload['risk_model']
    require(canonical_hash(model) == payload['training']['model_canonical_sha256'], 'new model hash mismatch')
    probabilities(model, [])  # Parameter/class validation, even if no arm reaches a stage.
    entries = payload['raw_files']
    by_path = {entry['path']: entry for entry in entries}
    require(len(by_path) == len(entries), 'duplicate raw manifest entries')
    verify_runner_invocations(payload, manifest_hashes)
    used = set(); used_seeds = set(); totals = {'training_total': 0, 'calibration_total': 0, 'evaluation_total': 0}
    cohort_cache = {}
    sampler = load_script('25_joint_risk').independent_plants
    from jev_tune.plants import ultimate_gain

    def read_run(path, *, seed, n, kind, risk, arguments, paired=False):
        require(path in by_path and path not in used, 'missing/reused raw shard: ' + path)
        entry = by_path[path]; used.add(path)
        resolved = (ROOT/path).resolve()
        require(resolved.is_relative_to((ROOT/'research/results/trajectory_risk_raw').resolve()), 'raw shard outside registered folder')
        require(hash_matches(resolved, entry['sha256']), 'raw shard hash mismatch: ' + path)
        run = json.loads(gzip.decompress(resolved.read_bytes()))
        metadata = {'protocol_canonical_sha256': protocol_hash, 'seed': seed, 'n_plants': n,
                    'kind': kind, 'arguments': arguments,
                    'engine_sha256': manifest_hashes['src/jev_tune/trajectory_risk.py'],
                    'risk_model_sha256': None if risk is None else canonical_hash(risk)}
        require(run['study_metadata'] == metadata, 'raw run frozen inputs differ: ' + path)
        require(entry['kind'] == kind and entry['seed'] == seed and entry['n_plants'] == n,
                'raw manifest cohort differs: ' + path)
        for key in ('mode', 'horizon', 'selector', 'feature_mode'):
            expected = arguments.get(key, {'selector': 'full_only', 'feature_mode': 'history_zero'}.get(key))
            require(run[key] == expected, 'raw runtime argument differs: ' + path + ':' + key)
            if key in entry:
                require(entry[key] == expected, 'manifest runtime argument differs: ' + key)
        require(run['n_plants'] == n, 'raw cohort size differs')
        if not paired:
            require(seed not in used_seeds, 'training/calibration cohort seed reused')
            used_seeds.add(seed)
        else:
            require(seed not in used_seeds, 'test seed reused by fitting/calibration')
        # A repeated noise_seed alone is not proof of dependent physical plants.
        # Regenerate the entire specified cohort and verify IDs and ZN gains.
        if (seed, n) not in cohort_cache:
            plants = sampler(n, seed); ku, tu = ultimate_gain(plants)
            gzn = np.column_stack([.6*ku, 1.2*ku/tu, .075*ku*tu])
            gains = np.clip(gzn, 1e-4, 1e3)
            cohort_cache[seed, n] = (plants.noise_seed.tolist(), gains, (gzn, ku, tu))
        identities, gains, priors = cohort_cache[seed, n]
        require([r['plant_identity'] for r in run['per_plant']] == identities and
                np.allclose([r['initial_gains'] for r in run['per_plant']], gains, rtol=1e-12, atol=1e-12),
                'cohort/analytic ZN differs from prescribed seed: ' + path)
        checked = verify_run(run, risk, arguments.get('qhats'), collect_step=arguments.get('collect_step'),
                             diagnostic=arguments.get('diagnostic', True), priors=priors)
        require(same(entry['simulation_counts'], checked['simulation_counts']), 'manifest simulation ledger differs: ' + path)
        totals[kind+'_total'] += checked['simulation_counts']['total']
        if not paired:
            del cohort_cache[seed, n]
        return run

    training = payload['training']; train_spec = spec['training']; datasets = {}
    require(set(training['datasets']) == {'train', 'temperature', 'development'}, 'training split registry differs')
    for name, settings in (('train', train_spec), ('temperature', train_spec['temperature']),
                           ('development', train_spec['development_audit'])):
        record = training['datasets'][name]
        run = read_run(record['raw_file'], seed=settings['seed'], n=settings['n_plants'], kind='training', risk=None,
                       arguments={'mode': 'training', 'horizon': 20, 'feature_mode': 'history_zero'})
        data = run['collected']; datasets[name] = data
        require(record['n_plants'] == settings['n_plants'] and record['seed'] == settings['seed']
                and record['n_rows'] == len(data['labels']) and record['harmful'] == sum(data['labels'])
                and same(record['simulation_counts'], run['simulation_counts']), 'training dataset summary differs: ' + name)
        # NPZ is an optional regenerated/release cache. Committed raw is sufficient.
        path = ROOT/record['npz_file']
        if path.exists():
            require(hash_matches(path, record['npz_sha256']), 'training NPZ hash mismatch: ' + name)
            with np.load(path, allow_pickle=False) as arrays:
                for column, source in (('features', 'features'), ('labels', 'labels'),
                                       ('plant_identity', 'plant_identity'), ('stage', 'stage')):
                    require(np.array_equal(arrays[column], np.asarray(data[source])), 'NPZ column differs from raw: ' + name + ':' + column)
        del run
    # Refit exactly the sole predeclared algorithm, using train and temperature
    # cohorts only. Tolerance permits optimizer/BLAS roundoff across platforms;
    # raw forwards above/below still must match the published model at 1e-12.
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score
    from threadpoolctl import threadpool_limits
    from jev_tune.primitives import calibrate_temperature
    x, y = np.asarray(datasets['train']['features']), np.asarray(datasets['train']['labels'])
    require(set(y.tolist()) == {0, 1}, 'training needs both classes')
    scaler = StandardScaler().fit(x)
    require(np.allclose(model['mean'], scaler.mean_, rtol=1e-12, atol=1e-12)
            and np.allclose(model['scale'], scaler.scale_, rtol=1e-12, atol=1e-12), 'scaler was not fit on training alone')
    settings = train_spec['model']
    require(settings == {'classifier': 'LogisticRegression', 'C': 1., 'solver': 'lbfgs', 'max_iter': 2000,
                         'random_state': 72601, 'class_weight': None}, 'fixed estimator specification differs')
    with threadpool_limits(limits=1):
        estimator = LogisticRegression(C=1., solver='lbfgs', max_iter=2000, random_state=72601,
                                       class_weight=None).fit(scaler.transform(x), y)
    require(int(estimator.n_iter_.max()) < 2000, 'fixed-estimator refit did not converge')
    require(np.allclose(model['coefficient'], estimator.coef_[0], rtol=1e-6, atol=1e-7)
            and math.isclose(model['intercept'], float(estimator.intercept_[0]), rel_tol=1e-6, abs_tol=1e-7),
            'serialized estimator differs from prescribed training refit')
    td = datasets['temperature']; tx = np.asarray(td['features'])
    z = (tx-np.asarray(model['mean']))/np.asarray(model['scale']) @ np.asarray(model['coefficient']) + model['intercept']
    fitted_temperature = calibrate_temperature(np.column_stack([np.zeros(len(z)), z]), np.asarray(td['labels'], int))
    require(math.isclose(model['temperature'], fitted_temperature, rel_tol=1e-8, abs_tol=1e-8),
            'temperature differs from independent temperature cohort NLL fit')
    for name, data in datasets.items():
        p = probabilities(model, data['features']); y = np.asarray(data['labels'], int)
        diagnostic = {'n_rows': len(y), 'harmful': int(y.sum()),
            'auroc': float(roc_auc_score(y, p[:, 1])) if len(np.unique(y)) == 2 else None,
            'brier': float(np.mean((p[:, 1]-y)**2)),
            'nll': float(-np.log(np.maximum(p[np.arange(len(y)), y], 1e-300)).mean())}
        require(same(training['diagnostics'][name], diagnostic), 'training/development diagnostic differs: ' + name)
    del datasets
    require(set(payload['arms']) == {c['name'] for c in spec['arms']}, 'study arms differ')
    for arm_index, config in enumerate(spec['arms']):
        name = config['name']; arm = payload['arms'][name]; risk = old_model if config['model'] == 'old' else model
        require(arm['configuration'] == config and len(arm['stages']) == 20 and len(arm['qhats']) == 20,
                'arm configuration/stage count differs: ' + name)
        prefix = []
        for stage_index, stage in enumerate(arm['stages']):
            where = f'{name} stage {stage_index}'
            unreachable = any(q >= 1 for q in prefix)
            target = None if config['calibration'] == 'initial512' else spec['calibration']['target_reached']
            cap = 512 if target is None else spec['calibration']['initial_cap_per_stage']
            fit_refs, fit_x, fit_y = [], [], []; n_initial = n_observed = 0
            require(stage['stage'] == stage_index and same(stage['prefix_qhats'], prefix), where + ': frozen prefix differs')
            require(not unreachable or not stage['raw_files'], where + ': simulated structurally unreachable stage')
            for batch, path in enumerate(stage['raw_files']):
                require(n_initial < cap and (target is None or len(fit_y) < target), where + ': score-independent sample quota exceeded')
                n = min(512, cap-n_initial); seed = 900000000 + arm_index*1000000 + stage_index*1000 + batch
                run = read_run(path, seed=seed, n=n, kind='calibration', risk=risk,
                    arguments={'mode': 'collect', 'horizon': 20, 'selector': config['selector'],
                               'feature_mode': config['feature_mode'], 'qhats': list(prefix),
                               'collect_step': stage_index, 'diagnostic': False})
                data = run['collected']; ordered = sorted(range(len(data['labels'])), key=lambda k: data['plant_index'][k])
                room = len(ordered) if target is None else target-len(fit_y)
                for index in ordered[:room]:
                    fit_x.append(data['features'][index]); fit_y.append(data['labels'][index])
                    fit_refs.append({'path': path, 'collected_index': index})
                n_initial += n; n_observed += len(ordered)
                del run
            require(unreachable or n_initial == cap or (target is not None and len(fit_y) == target),
                    where + ': early calibration stop before fixed quota/cap')
            p = probabilities(risk, fit_x); y = np.asarray(fit_y, int)
            scores = 1 - p[np.arange(len(y)), y]; rank = math.ceil((len(y)+1)*(1-spec['risk_budget']['alpha_per_stage'][stage_index]))
            rank_fallback = rank > len(y); quota_fallback = target is not None and len(y) < target
            q = 1. if rank_fallback or quota_fallback else float(np.sort(scores)[rank-1])
            reason = ('unreachable_frozen_prefix' if unreachable else 'quota_shortfall' if quota_fallback
                      else 'finite_sample_rank' if rank_fallback else None)
            expected = {'stage': stage_index, 'n_initial': n_initial, 'n_observed_reached': n_observed,
                'n_reached': len(y), 'alpha': .005, 'quantile_rank': rank, 'qhat': q,
                'all_labels_fallback': rank_fallback, 'rank_fallback': rank_fallback,
                'quota_fallback': quota_fallback, 'fallback_reason': reason,
                'prefix_qhats': prefix, 'fit_refs': fit_refs, 'score_sha_inputs': scores.tolist()}
            for key, value in expected.items():
                require(same(stage[key], value), where + ': stage statistic differs: ' + key)
            require(same(arm['qhats'][stage_index], q), where + ': arm quantile differs')
            prefix = prefix + [q]
    ev = spec['evaluation']; summaries = {}; evaluation_runs = {}
    require(set(payload['evaluation']) == set(ev['arms']) == set(payload['evaluation_raw']), 'evaluation arm registry differs')
    for name in ev['arms']:
        if name == 'monitor':
            risk = old_model
            args = {'mode': 'monitor', 'selector': 'full_only', 'feature_mode': 'legacy', 'qhats': [1.]*20}
        else:
            arm = payload['arms'][name]; config = arm['configuration']
            risk = old_model if config['model'] == 'old' else model
            args = {'mode': 'gated', 'selector': config['selector'], 'feature_mode': config['feature_mode'], 'qhats': arm['qhats']}
        args.update(horizon=20, diagnostic=True)
        run = read_run(payload['evaluation_raw'][name], seed=ev['seed'], n=ev['n_plants'],
                       kind='evaluation', risk=risk, arguments=args, paired=True)
        summaries[name] = summarize(run)
        require(same(payload['evaluation'][name], summaries[name]), 'evaluation summary differs: ' + name)
        evaluation_runs[name] = run
    monitor = evaluation_runs['monitor']
    mon_rows = {(t['plant_index'], t['stage']): t for t in monitor['transitions']}
    for name, run in evaluation_runs.items():
        require([(p['plant_identity'], p['initial_J'], p['initial_gains']) for p in run['per_plant']] ==
                [(p['plant_identity'], p['initial_J'], p['initial_gains']) for p in monitor['per_plant']],
                'evaluation arms do not use identical initial objects/measurements: ' + name)
        if run['selector'] == 'full_only':
            for actual, baseline in zip(run['per_plant'], monitor['per_plant']):
                require(actual['operating_history'] == baseline['operating_history'][:len(actual['operating_history'])],
                        'full-action gated history is not the matched monitor prefix: ' + name)
            for row in run['transitions']:
                baseline = mon_rows[row['plant_index'], row['stage']]
                for key in ('proposal_valid', 'base_step', 'choice_probabilities', 'gains_before', 'cost_before'):
                    require(same(row[key], baseline[key]), 'full-action matched proposal differs: ' + name + ':' + key)
    require(used == set(by_path), 'unaccounted or unrelated raw shards')
    totals['total'] = sum(totals.values())
    require(same(payload['simulation_counts'], totals), 'whole-study simulation accounting differs')
    primary = spec['primary_candidate']
    require(primary == 'trajectory_selected', 'post-test primary candidate selection')
    p, m = summaries[primary], summaries['monitor']
    criteria = {'trajectory_risk_upper': p['trajectory_harm']['upper'] <= .1,
        'first_stage_execution_lower': p['first_stage_execution']['lower'] >= .5,
        'empirical_mean_cost_noninferior': p['final_cost']['mean'] <= m['final_cost']['mean'],
        'empirical_p90_cost_noninferior': p['final_cost']['p90'] <= m['final_cost']['p90'],
        'operating_budget_noninferior': p['simulation_counts']['operating'] <= m['simulation_counts']['operating'],
        'integrity': True}
    acceptance = {'passed': all(criteria.values()), 'checks': criteria, 'failed': [k for k, ok in criteria.items() if not ok]}
    if 'acceptance' in payload:
        require(same(payload['acceptance'], acceptance), 'primary-only acceptance differs')
        deployment = {'enabled': acceptance['passed'],
            'status': 'validated_research_scope_only' if acceptance['passed'] else 'research_only',
            'primary_candidate': primary, 'generic_python_c_matlab_enabled': False,
            'failed_criteria': acceptance['failed'], 'scope': spec['scope']}
        require(payload['deployment'] == deployment, 'deployment scope/status disagrees with fixed acceptance')
    return {name: True for name in ('frozen_protocol_and_sources', 'independent_seed_domains',
        'training_and_temperature_refit', 'risk_features_and_model_probabilities',
        'complete_action_selected_before_cp', 'full_prediction_sets_and_harm_inclusion',
        'stagewise_reached_calibration_and_fixed_quota', 'matched_operating_histories_and_stops',
        'exact_cache_and_simulation_ledger', 'raw_summaries_and_primary_only_acceptance')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, default=RESULT)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        path = args.result if args.result.is_absolute() else ROOT / args.result
        checks = verify_payload(json.loads(path.read_text(encoding='utf-8')))
        result = {'ok': all(checks.values()), 'checks': checks}
    except (OSError, ValueError, KeyError, TypeError, IndexError, NotImplementedError) as exc:
        result = {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
