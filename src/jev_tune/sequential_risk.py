"""Finite-horizon research calibration and fixed-sample acceptance statistics.

Each stage needs a fresh IID cohort under its already frozen prefix. These
helpers do not make arbitrary adaptive trajectories exchangeable.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.stats import beta


def stage_calibration(probabilities, labels, alpha):
    p, y = np.asarray(probabilities, float), np.asarray(labels)
    if y.size and not np.issubdtype(y.dtype, np.integer):
        raise ValueError('labels must be binary integers')
    y = y.astype(int)
    if p.shape != (len(y), 2) or y.ndim != 1:
        raise ValueError('expected binary probabilities and one label per reached plant')
    if not 0 < alpha < 1 or not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError('invalid probabilities or alpha')
    if not np.allclose(p.sum(1), 1.) or np.any((y < 0) | (y > 1)):
        raise ValueError('invalid binary labels/probability normalization')
    n = len(y)
    rank = math.ceil((n + 1) * (1 - alpha))
    insufficient = rank > n
    scores = 1 - p[np.arange(n), y]
    # Scores are bounded by one: q=1 gives the same full set as +infinity.
    q = 1. if insufficient else float(np.sort(scores)[rank - 1])
    return {'n_reached': n, 'alpha': float(alpha), 'quantile_rank': rank,
            'qhat': q, 'all_labels_fallback': insufficient,
            'score_sha_inputs': scores.tolist()}


def binomial_bounds(events, total, confidence=.95):
    """Separate exact one-sided Clopper-Pearson bounds, not a joint CI."""
    if not 0 <= events <= total or total < 1 or not 0 < confidence < 1:
        raise ValueError('invalid binomial counts/confidence')
    k, n, delta = int(events), int(total), 1 - confidence
    return {'events': k, 'n': n, 'rate': k / n, 'confidence_one_sided': confidence,
            'lower': 0. if k == 0 else float(beta.ppf(delta, k, n-k+1)),
            'upper': 1. if k == n else float(beta.ppf(1-delta, k+1, n-k))}


def summarize_rollout(result):
    rows, transitions = result['per_plant'], result['transitions']
    costs = np.asarray([r['best_J'] for r in rows], float)
    if not len(rows) or not np.isfinite(costs).all():
        raise ValueError('every plant needs a finite measured final best cost')
    executed = [r for r in transitions if r['executed']]
    # Invalid executions count conservatively as harm and cannot pass integrity.
    harmful = [r for r in executed if not r['observed_finite'] or r['cost_after'] > r['cost_before']]
    legacy = [r for r in executed if not r['observed_finite'] or r['cost_after'] > r['cost_before'] * 1.02]
    events = len({r['plant_index'] for r in harmful})
    first = len({r['plant_index'] for r in executed if r['stage'] == 0})
    measured = [r for r in transitions if r['measured'] and r['prediction_set'] is not None and r['observed_finite']]
    covered = sum(bool(r['prediction_set'][int(r['cost_after'] > r['cost_before'])]) for r in measured)
    return {'n_plants':len(rows), 'n_executed':len(executed), 'n_harmful':len(harmful),
            'n_harmful_gt_2pct':len(legacy),
            'harmful_rate':len(harmful)/len(executed) if executed else None,
            'harmful_gt_2pct_rate':len(legacy)/len(executed) if executed else None,
            'trajectory_harm':binomial_bounds(events,len(rows)),
            'first_stage_execution':binomial_bounds(first,len(rows)),
            'final_cost':{'mean':float(costs.mean()),'median':float(np.median(costs)),
                          'p90':float(np.percentile(costs,90))},
            'measured_label_coverage':{'covered':covered,'n':len(measured),
                                      'rate':covered/len(measured) if measured else None},
            'simulation_counts':result['simulation_counts']}


def acceptance_checks(monitor, gated, integrity, *, trajectory_alpha=.1, minimum_execution=.5):
    """Frozen engineering criteria; mean/p90 are empirical checks, not theorems."""
    checks = {
        'trajectory_risk_upper':gated['trajectory_harm']['upper'] <= trajectory_alpha,
        'first_stage_execution_lower':gated['first_stage_execution']['lower'] >= minimum_execution,
        'empirical_mean_cost_noninferior':gated['final_cost']['mean'] <= monitor['final_cost']['mean'],
        'empirical_p90_cost_noninferior':gated['final_cost']['p90'] <= monitor['final_cost']['p90'],
        'operating_budget_noninferior':gated['simulation_counts']['operating'] <= monitor['simulation_counts']['operating'],
        'integrity':bool(integrity),
    }
    return {'passed':all(checks.values()), 'checks':checks,
            'failed':[name for name,ok in checks.items() if not ok]}
