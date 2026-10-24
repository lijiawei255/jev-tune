"""E2: select on one draw; validate separately against no-hold and random-hold.

The random control shuffles complete three-axis hold masks without cost labels.
It matches scheduled mask frequencies, not a claim of independent deployment.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from jev_tune.domains.pid.decision import load_backend
from jev_tune.core.policy import DEFAULT_ABSTAIN, AbstainPolicy
from jev_tune.domains.pid.evaluate import HARM_METRIC, evaluate_head
from jev_tune.domains.pid.plants import HELDOUT_FAMILIES, sample_plants, ultimate_gain
from _experiment_protocol import conformal_evidence_lines, manifest

GRID = (None, .30, .35, .40, .45, .50, .55, .60, .70)


def _draw(seed, n):
    p = sample_plants(n, seed=seed, families=HELDOUT_FAMILIES, heldout=True)
    ku, tu = ultimate_gain(p)
    return dict(seed=seed, plants=p, ku=ku, tu=tu,
                gzn=np.column_stack([.6*ku, 1.2*ku/tu, .075*ku*tu]))


def shuffled_mask_provider(axis_held, seed, valid=None):
    """Shuffle whole masks: preserve per-axis and joint mask frequencies."""
    masks = np.asarray(axis_held, bool).copy()
    flat = masks.reshape(-1, masks.shape[-1])
    usable = np.ones(len(flat), bool) if valid is None else np.asarray(valid, bool).ravel()
    selected = flat[usable]
    scheduled = np.zeros_like(flat)
    scheduled[usable] = selected[np.random.default_rng(seed).permutation(len(selected))]
    shuffled = scheduled.reshape(masks.shape)
    def provide(decision, iteration, plant_indices):
        return shuffled[np.asarray(plant_indices), iteration]
    return provide


def _run(backend, d, tau, *, policy_name=None, hold_provider=None, conformal=None, stop_on_no_action=False):
    policy = None if tau is None else AbstainPolicy(tau, max(0., tau-.1))
    r = evaluate_head(backend, d['plants'], d['gzn'], d['ku'], d['tu'],
        budget=20, seed=d['seed'], abstain=policy, hold_mask_provider=hold_provider,
        conformal=conformal, stop_on_no_action=stop_on_no_action)
    return {
        'policy': policy_name or ('no_abstention' if tau is None else 'threshold'),
        'tau_act': tau, 'conformal': conformal is not None,
        'draw_seed': d['seed'], 'median': float(np.median(r.best_j)),
        'p90': float(np.percentile(r.best_j, 90)), 'failures': int((r.best_j>=50).sum()),
        'mean_experiments': float(np.mean(r.actual_simulations)),
        'rollbacks': int(r.rollbacks.sum()),
        'per_plant': r.best_j.tolist(), **r.decision_report()}, r


def _summary(rows, policy):
    selected = [r for r in rows if r['policy']==policy]
    def mean(key):
        vals = [r[key] for r in selected if r.get(key) is not None]
        return float(np.mean(vals)) if vals else None
    return {'policy': policy, 'tau_act': selected[0]['tau_act'],
        'conformal': selected[0]['conformal'],
        'median_mean': mean('median'),
        'median_std': float(np.std([r['median'] for r in selected], ddof=1)) if len(selected)>1 else 0.,
        'coverage': mean('coverage'), 'measured_transition_coverage': mean('coverage'),
        'proposal_coverage': mean('proposal_coverage'),
        'n_measured_policy_transitions': sum(r['n_decisions'] for r in selected),
        'n_proposals': sum(r['n_proposals'] for r in selected),
        'axis_coverage': mean('axis_coverage'),
        'average_set_size': mean('average_set_size'),
        'conformal_hold_axis_rate': mean('conformal_hold_axis_rate'),
        'harmful_rate': mean('harmful_rate'), 'ece': mean('ece'),
        'harmful_gt_2pct_rate': mean('harmful_gt_2pct_rate'),
        'n_harmful': sum(r['n_harmful'] for r in selected),
        'n_harmful_gt_2pct': sum(r['n_harmful_gt_2pct'] for r in selected),
        'mean_experiments': mean('mean_experiments'),
        'p90_mean': mean('p90'),
        'rollbacks': sum(r['rollbacks'] for r in selected),
        'failures': sum(r['failures'] for r in selected)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plants', type=int, default=120)
    ap.add_argument('--draws', type=int, default=3, help='one selection draw plus validation draws')
    ap.add_argument('--seed0', type=int, default=7)
    ap.add_argument('--models', default='models')
    ap.add_argument('--out', default='research/results/abstention.json')
    ap.add_argument('--doc', default='docs/ABSTENTION.md')
    args = ap.parse_args()
    provenance = manifest(args, files=[Path(args.models)/'jev_head.pt', Path(args.models)/'calibration.json'])
    if args.draws < 2:
        ap.error('--draws requires one selection draw and at least one validation draw')
    b = load_backend(args.models)
    if getattr(b, 'conformal', None) is None:
        raise ValueError('the CP comparison requires split CP metadata; run 02_train.py --calibrate-only first')
    draws = [_draw(args.seed0+10*i, args.plants) for i in range(args.draws)]
    sweep = []
    for tau in GRID:
        row, _ = _run(b, draws[0], tau)
        sweep.append(row)
        print(f"[select] tau={tau} median={row['median']:.4f} coverage={row['coverage']:.3f}", flush=True)
    chosen = min((r for r in sweep if r['coverage']>=.5), key=lambda r:r['median'])
    tau = chosen['tau_act']
    validation = []
    for d in draws[1:]:
        off, _ = _run(b, d, None)
        on, r = _run(b, d, tau, policy_name='threshold')
        valid = r.decisions['valid'] & (r.decisions['event']!='rollback')
        provider = shuffled_mask_provider(r.decisions['axis_held'], d['seed']+1000, valid)
        random, _ = _run(b, d, None, policy_name='random_hold', hold_provider=provider)
        legacy, _ = _run(b, d, DEFAULT_ABSTAIN.tau_act, policy_name='legacy_pmax_0.35')
        cp, cr = _run(b, d, None, policy_name='temperature_CP', conformal='hard_hold')
        monitor, _ = _run(b, d, None, policy_name='CP_monitor', conformal='monitor', stop_on_no_action=True)
        stopped, _ = _run(b, d, None, policy_name='CP_hold_stop', conformal='hard_hold', stop_on_no_action=True)
        cp_valid = cr.decisions['valid'] & (cr.decisions['event']!='rollback')
        cp_provider = shuffled_mask_provider(cr.decisions['axis_held'], d['seed']+2000, cp_valid)
        cp_random, _ = _run(b, d, None, policy_name='CP_random_hold', hold_provider=cp_provider)
        validation.extend([off, on, random, legacy, cp, cp_random, monitor, stopped])
        print(f"[validate {d['seed']}] off={off['median']:.4f} threshold={on['median']:.4f} random={random['median']:.4f}", flush=True)
        print(f"[validate {d['seed']}] CP={cp['median']:.4f} CP-random={cp_random['median']:.4f}", flush=True)
    payload = {'plants_per_draw': args.plants, 'draws': [d['seed'] for d in draws],
        'harm_metric': dict(HARM_METRIC),
        'calibration_evidence': json.loads((Path(args.models)/'calibration.json').read_text(encoding='utf-8')),
        'sweep_draw_seed': draws[0]['seed'], 'validation_draw_seeds': [d['seed'] for d in draws[1:]],
        'selection_rule': 'lowest selection median among policies with joint action coverage >=0.50',
        'chosen_tau_act': tau, 'sweep': sweep, 'validation': validation,
        'legacy_tau_act': DEFAULT_ABSTAIN.tau_act,
        'default_policy': 'temperature plus split CP monitor; no CP veto or pmax heuristic',
        'summary': [_summary(validation, p) for p in ('no_abstention','threshold','random_hold','legacy_pmax_0.35','temperature_CP','CP_random_hold','CP_monitor','CP_hold_stop')],
        'random_control': 'shuffle whole three-axis masks across plants/time without outcome labels; report actual coverage separately',
        'manifest': provenance}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2), encoding='utf-8')
    Path(args.doc).write_text(_doc(payload), encoding='utf-8')


def _fmt(x):
    return 'n/a' if x is None else f'{x:.4f}'


def _doc(p):
    if p.get('harm_metric', {}).get('version') != HARM_METRIC['version']:
        raise ValueError('rerun E2: historical harmful_rate used the >2% definition')
    lines = ['# Explicit abstention: independent validation and random hold', '',
             '> [English](#english) · [简体中文](#简体中文)', '']
    for zh in (False, True):
        lines += ['## 简体中文' if zh else '## English', '',
            (f"只在seed {p['sweep_draw_seed']}选阈值；验证仅用{p['validation_draw_seeds']}，不计入选择集。"
             if zh else f"Select only on seed {p['sweep_draw_seed']}; validate only on {p['validation_draw_seeds']}, excluding selection data."),
            ('CP不在这些验证对象上调参；其qhat固定来自独立CP校准划分。动作覆盖率不同于专家标签集合覆盖率；后者及独立评估平均集合大小保存于JSON的calibration_evidence。'
             if zh else 'CP is not tuned on these validation plants: qhat is fixed from the independent CP calibration split. Action coverage differs from teacher-label set coverage; the latter and independent evaluation set sizes are preserved in the JSON calibration_evidence.'),
            f"N={p['plants_per_draw']}/draw; budget=20; selected tau_act={p['chosen_tau_act']}.", '',
            (f"当前默认是Temperature+CP monitor，完整集合仅作诊断，不否决轴、不叠加pmax阈值。temperature_CP行保留旧hard_hold重复观测；CP_hold_stop停止无动作重复。tau_act={p['legacy_tau_act']}是旧策略对照；候选阈值的本次选择不会修改生产策略。阈值扫描与其随机对照均关闭CP；另列CP及覆盖匹配随机保持。"
             if zh else f"The shipped default is Temperature+CP monitor without a CP veto or pmax threshold. temperature_CP preserves historical hard_hold repetitions; CP_hold_stop stops no-action repeats. tau_act={p['legacy_tau_act']} is a legacy control; selecting a candidate here does not change production. The threshold sweep and its random control disable CP; separate rows compare CP and matched random holds."), '',
        ]
        lines += conformal_evidence_lines(p.get('calibration_evidence', {}), zh=zh)
        lines += ['| selection tau | coverage | median J | p90 | harm >0 | legacy harm >2% | ECE |',
            '| ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for r in p['sweep']:
            lines.append(f"| {r['tau_act']} | {_fmt(r['coverage'])} | {_fmt(r['median'])} | {_fmt(r['p90'])} | {_fmt(r.get('harmful_rate'))} | {_fmt(r.get('harmful_gt_2pct_rate'))} | {_fmt(r.get('ece'))} |")
        lines += ['', ('| 验证策略 | 中位 J 均值 ± 标准差 | p90均值 | 提案覆盖率 | 已测转移覆盖率 | 已测轴覆盖率 | 有害 >0 | 旧口径有害 >2% | ECE | 实际实验次数 | 回滚 |'
                      if zh else '| validation policy | median J mean ± std | p90 mean | proposal coverage | measured transition coverage | measured axis coverage | harm >0 | legacy harm >2% | ECE | actual experiments | rollbacks |'),
                  '| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for r in p['summary']:
            lines.append(f"| {r['policy']} | {r['median_mean']:.4f} ± {r['median_std']:.4f} | {_fmt(r['p90_mean'])} | {_fmt(r['proposal_coverage'])} | {_fmt(r['measured_transition_coverage'])} | {_fmt(r['axis_coverage'])} | {_fmt(r['harmful_rate'])} | {_fmt(r['harmful_gt_2pct_rate'])} | {_fmt(r['ece'])} | {_fmt(r['mean_experiments'])} | {r['rollbacks']} |")
        stopped = next(r for r in p['summary'] if r['policy'] == 'CP_hold_stop')
        lines += ['', (
            f"提案覆盖率的分母包含终止提案；已测转移覆盖率（JSON的coverage别名）仅统计后续确有测量的策略决策，不含回滚。两者均以至少一轴获准为分子。覆盖率取各轮均值，计数为各轮合计。CP_hold_stop有{stopped['n_proposals']}个提案、{stopped['n_measured_policy_transitions']}个已测策略转移：全轴保持后的终止提案被排除在已测分母之外，所以已测覆盖率{stopped['measured_transition_coverage']:.4f}不表示没有弃权；其提案覆盖率为{stopped['proposal_coverage']:.4f}。"
            if zh else f"Proposal coverage includes terminal proposals in its denominator; measured transition coverage (the JSON coverage alias) includes only policy decisions followed by an actual measurement, excluding rollbacks. Both count at least one permitted axis. Rates are means across draws and counts are totals. CP_hold_stop has {stopped['n_proposals']} proposals and {stopped['n_measured_policy_transitions']} measured policy transitions. Fully held terminal proposals are excluded from the measured denominator, so its measured coverage {stopped['measured_transition_coverage']:.4f} does not mean abstention is absent; proposal coverage is {stopped['proposal_coverage']:.4f}."), '']
        lines += ['', (
            '随机对照打乱三轴保持mask，保留预定mask频率，不使用代价标签；它是覆盖匹配诊断，不是部署策略。回滚可能改变实际事件数，表中另报实际覆盖率。主有害口径为严格after > before，零容差；旧口径保留after > 1.02 × before，供v0.6比较。两种有害率均以至少一轴获准且实际测量的策略决策为分母，排除回滚和终止提案，不是无条件联合风险保证。ECE用三轴平均pmax与整步改善作描述性比较，不将它当已验证的联合成功概率。每种策略仅一个训练检查点；结果不是安全保证。'
            if zh else 'The random control shuffles whole three-axis hold masks without outcome labels. It preserves scheduled mask frequencies and is a matched-coverage diagnostic, not a deployment rule. Rollbacks may change actual event counts; measured coverage is reported. Canonical harm uses strict after > before with zero tolerance; legacy harm >2% retains after > 1.02 × before for comparison with v0.6. Both rates condition on measured policy decisions with at least one permitted axis, excluding rollbacks and terminal proposals; they are not unconditional joint-risk guarantees. ECE descriptively compares mean axis pmax with joint improvement; it does not establish a calibrated joint success probability. Each policy uses one trained checkpoint; these results do not establish safety.'), '']
    return '\n'.join(lines)


if __name__ == '__main__':
    main()
