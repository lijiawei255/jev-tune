"""Frozen-weight adaptation with separate temperature and threshold interventions.

The collection policy uses the production evaluator, including state history,
gate and accepted actions. Temperature fitting uses source-policy outcomes as
a surrogate, not a guarantee of calibrated success for the changed actions.
Independent held-out rollouts evaluate base / T-only / tau-only / combined.
All arms disable CP; this adaptation diagnostic is not the shipped CP policy.
"""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
import numpy as np
from jev_tune.decision import load_backend
from jev_tune.decode import DEFAULT_ABSTAIN, AbstainPolicy, apply_abstention
from jev_tune.evaluate import HARM_METRIC, evaluate_head
from jev_tune.plants import ultimate_gain
from jev_tune.scenarios import _stack, variants
from _experiment_protocol import manifest


def _gzn(plants):
    ku, tu = ultimate_gain(plants)
    ku = np.where(np.isfinite(ku)&(ku>0), ku, 1.)
    tu = np.where(np.isfinite(tu)&(tu>0), tu, 1.)
    return np.column_stack([.6*ku, 1.2*ku/tu, .075*ku*tu]), ku, tu


def collect(backend, plants, *, steps, seed):
    """Collect true transition labels; reuse each response as the next state."""
    r = evaluate_head(backend, plants, *_gzn(plants), budget=steps+1,
                      seed=seed, abstain=None, conformal=None, record=True)
    d = r.decisions
    valid = d['valid'] & (d['event'] != 'rollback')
    probs = d['choice_probs'][valid]
    return probs, d['improved'][valid].astype(float), {
        'simulations': int(np.sum(r.actual_simulations)),
        'initial_simulations': plants.n,
        'recorded_samples': int(valid.sum()),
        'rollback_transitions': int((d['valid'] & (d['event']=='rollback')).sum()),
        'zero_source_probabilities': int(np.sum(probs == 0)),
        'smallest_positive_source_probability': float(np.min(probs[probs > 0])),
        'collection_policy': 'production evaluator with CP disabled; abstain=None; normal history, state updates, and deterministic gate',
    }


def transformed_probs(probs, T):
    """Rescale temperature without inventing probability mass in tiny tails.

    Zero input probabilities remain zero: once a source softmax underflows,
    probabilities alone cannot recover the discarded logits.
    """
    p = np.asarray(probs, dtype=np.float64)
    if not np.isfinite(T) or T <= 0:
        raise ValueError('temperature scale must be finite and positive')
    if (not np.isfinite(p).all() or np.any(p < 0)
            or np.any(p.sum(axis=-1) <= 0)):
        raise ValueError('probabilities must be finite, nonnegative and have positive mass')
    with np.errstate(divide='ignore'):
        logp = np.log(p)
    # Center before division, as in the production softmax. This also avoids
    # overflow for very small positive temperature scales.
    with np.errstate(over='ignore'):
        logp = (logp-logp.max(axis=-1, keepdims=True))/T
    q = np.exp(logp)
    return q/q.sum(axis=-1, keepdims=True)


def _mean_pmax(probs, T):
    return transformed_probs(probs, T).max(axis=-1).mean(axis=-1)


def fit_temperature(probs, improved):
    """Fit a scalar concentration surrogate on source-policy outcomes."""
    best = (np.inf, 1.)
    for T in np.linspace(.5, 4., 36):
        q = np.clip(_mean_pmax(probs, T), 1e-4, 1-1e-4)
        loss = -np.mean(improved*np.log(q)+(1-improved)*np.log(1-q))
        if loss < best[0]:
            best = (float(loss), float(T))
    return best[1]


def runtime_coverage(probs, tau):
    axis_conf = np.asarray(probs).max(axis=-1)
    decision = apply_abstention(np.ones_like(axis_conf), axis_conf,
        np.ones(len(axis_conf)), AbstainPolicy(tau, max(0., tau-.1)))
    return float((~decision.held).any(axis=-1).mean())


def pick_tau(probs, coverage_target=.6):
    """Select using the actual per-axis runtime mask and joint coverage rule."""
    conf = np.asarray(probs).max(axis=-1)
    candidates = np.unique(np.r_[0., conf.max(axis=-1), 1.])
    eligible = [(runtime_coverage(probs, t), float(t)) for t in candidates
                if runtime_coverage(probs, t) >= coverage_target]
    # Most selective feasible threshold; ties keep the higher threshold.
    return min(eligible, key=lambda pair:(pair[0], -pair[1]))[1]


def _row(result):
    return {'median': float(np.median(result.best_j)),
            'p90': float(np.percentile(result.best_j,90)),
            'per_plant': result.best_j.tolist(),
            'mean_experiments': float(np.mean(result.actual_simulations)),
            **result.decision_report()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scenario', default='valve_dead_zone')
    ap.add_argument('--plants', type=int, default=8)
    ap.add_argument('--held', type=int, default=40)
    ap.add_argument('--steps', type=int, default=6)
    ap.add_argument('--models', default='models')
    ap.add_argument('--out', default='research/results/calibrate_only.json')
    ap.add_argument('--doc', default='docs/CALIBRATE_ONLY.md')
    args = ap.parse_args()
    provenance = manifest(args, files=[Path(args.models)/'jev_head.pt', Path(args.models)/'calibration.json'],
                          extra={'calibration_seed':101,'held_out_seed':202,'evaluation_seed':7})
    b = load_backend(args.models)
    cal = _stack([variants(args.scenario, args.plants, seed=101)])
    held = _stack([variants(args.scenario, args.held, seed=202)])
    t0 = time.perf_counter()
    probs, improved, collection = collect(b, cal, steps=args.steps, seed=0)
    collect_s = time.perf_counter()-t0
    t0 = time.perf_counter()
    T = fit_temperature(probs, improved)
    tau_base = pick_tau(probs)
    transformed = transformed_probs(probs, T)
    tau = pick_tau(transformed)
    fit_ms = 1000*(time.perf_counter()-t0)
    base_T = np.asarray(b.temperature, float)
    adapted = type(b)(b.model, space=b.space, temperature=base_T*T, calibrate=True)
    arms = {}
    for name, backend, threshold in (
        ('base', b, DEFAULT_ABSTAIN.tau_act),
        ('temperature_only', adapted, DEFAULT_ABSTAIN.tau_act),
        ('threshold_only', b, tau_base),
        ('combined', adapted, tau)):
        policy = AbstainPolicy(threshold, max(0., threshold-.1))
        result = evaluate_head(backend, held, *_gzn(held), budget=20, seed=7,
                               abstain=policy, conformal=None)
        arms[name] = {'temperature_scale': T if backend is adapted else 1.,
                      'tau_act': threshold, **_row(result)}
        print(f"[calib] {name}: median {arms[name]['median']:.4f}, coverage {arms[name]['coverage']:.4f}", flush=True)
    payload = {'scenario': args.scenario, 'calibration_plants': cal.n,
        'harm_metric': dict(HARM_METRIC),
        'calibration_samples': len(improved), 'steps_per_plant': args.steps,
        'calibration_simulations': collection['simulations'], 'collection': collection,
        'simulations_per_sample': collection['simulations']/len(improved),
        'held_out_plants': held.n, 'base_temperature': base_T.tolist(),
        'fitted_temperature_scale': T, 'fitted_abstain_tau': tau,
        'fitted_base_abstain_tau': tau_base, 'base_abstain_tau': DEFAULT_ABSTAIN.tau_act,
        'selection_coverage': {'threshold_only': runtime_coverage(probs,tau_base),
                               'combined': runtime_coverage(transformed,tau)},
        'wall_s_collect': collect_s, 'fit_ms': fit_ms,
        'arms': arms, 'base': arms['base'], 'adapted': arms['combined'],
        'conformal_enabled': False,
        'note': 'CP disabled in collection and every arm; this is not the shipped CP policy. Frozen weights; temperature changes expected actions. Source-policy outcome fit is a surrogate, not calibrated success for the changed policy. A deployment with changed temperature must fit CP again on independent data. All four arms are evaluated on independent held-out plants.',
        'manifest': provenance}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload,indent=2),encoding='utf-8')
    Path(args.doc).write_text(_doc(payload),encoding='utf-8')


def _fmt(x):
    return 'n/a' if x is None else f'{x:.4f}'


def _doc(p):
    if p.get('harm_metric', {}).get('version') != HARM_METRIC['version']:
        raise ValueError('rerun E3: historical harmful_rate used the >2% definition')
    lines = ['# Frozen-weight temperature and threshold adaptation', '',
             '> [English](#english) · [简体中文](#简体中文)', '']
    for zh in (False, True):
        lines += ['## 简体中文' if zh else '## English','',
            ('本实验在采集及四个验证臂均关闭CP，不代表当前出厂的Temperature+CP策略。温度改变后若需部署CP，必须使用独立校准数据重新拟合qhat；这里不复用旧qhat，也不声称具有CP覆盖保证。'
             if zh else 'CP is disabled during collection and in all four arms; this diagnostic does not represent the shipped Temperature+CP policy. Deploying CP after a temperature change requires refitting qhat on independent calibration data; this experiment does not reuse old qhat or claim CP coverage.'), '',
            (f"冻结所有权重；用{p['calibration_plants']}株模拟对象采集{p['calibration_samples']}个真实转移，实际{p['calibration_simulations']}次仿真（包含初始测量）。采样{p['wall_s_collect']:.3f}秒，标量拟合{p['fit_ms']:.3f}毫秒。"
             if zh else f"All weights are frozen. {p['calibration_samples']} measured transitions from {p['calibration_plants']} simulated plants cost {p['calibration_simulations']} simulations including initial responses; collection {p['wall_s_collect']:.3f}s, scalar fitting {p['fit_ms']:.3f}ms."),
            (f"校准seed101、独立验证seed202；在{p['held_out_plants']}株验证对象上，各臂预算20次。"
             if zh else f"Calibration seed 101 and independent validation seed 202; each arm receives 20 experiments on {p['held_out_plants']} held-out plants."), '',
            ('主有害口径为严格after > before，零容差；另列旧口径after > 1.02 × before，供v0.6比较。两者均以至少一轴获准且实际测量的策略决策为分母，排除回滚和终止提案，不是无条件联合风险保证。'
             if zh else 'Canonical harm uses strict after > before with zero tolerance. The legacy after > 1.02 × before rate remains for comparison with v0.6. Both condition on measured policy decisions with at least one permitted axis, excluding rollbacks and terminal proposals; they are not unconditional joint-risk guarantees.'), '',
            '| arm | T scale | tau | median J | p90 | coverage | harm >0 | legacy harm >2% | ECE |',
            '| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for name,r in p['arms'].items():
            lines.append(f"| {name} | {r['temperature_scale']:.3f} | {r['tau_act']:.4f} | {r['median']:.4f} | {r['p90']:.4f} | {_fmt(r['coverage'])} | {_fmt(r.get('harmful_rate'))} | {_fmt(r.get('harmful_gt_2pct_rate'))} | {_fmt(r.get('ece'))} |")
        lines += ['', (
            '采样复用生产运行器的历史特征、动作接受与安全门；每个响应只测一次。阈值选择直接调用运行时逐轴mask，coverage与验证同样按至少一轴获准计。温度会改变期望解码和方差缩步，因此权重冻结不等于策略冻结。拟合的NLL使用原策略动作结果作为代理目标，不能保证新动作的成功概率已校准；四臂独立验证用于测量结果而非保证安全。ECE以三轴平均pmax与整步改善作描述性比较。该单场景小样本实验不证明真机迁移、从零少样本学习或普遍改进，负结果必须保留。'
            if zh else 'Collection reuses production state history, accepted actions and the deterministic gate, with each response measured once. Threshold selection calls the runtime per-axis mask and uses the same joint coverage definition (at least one permitted axis). Temperature changes expectation decoding and variance shrinkage: frozen weights do not mean a frozen policy. NLL on source-policy outcomes is a surrogate and does not establish calibrated success for changed actions. Independent four-arm rollouts measure outcomes, not safety. ECE descriptively compares mean axis pmax with joint improvement. This single-scenario small-sample experiment does not prove real-device transfer, few-shot learning from scratch or universal gains; negative results are retained.'), '']
    return '\n'.join(lines)


if __name__ == '__main__':
    main()
