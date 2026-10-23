"""Recompute a post-hoc diagnosis from published traces; no fitting or simulation."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from jev_tune.risk import JointRiskModel
from jev_tune.sequential_risk import binomial_bounds, stage_calibration
from jev_tune.state import FEATURE_NAMES

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'research/results/rollout_diagnosis.json'
DOC = ROOT / 'docs/ROLLOUT_DIAGNOSIS.md'


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def distribution(values):
    x = np.asarray(values, float)
    if not x.size:
        return {'n': 0}
    if not np.isfinite(x).all():
        raise ValueError('diagnostic values must be finite')
    return {'n': int(x.size), 'min': float(x.min()), 'mean': float(x.mean()),
            'median': float(np.median(x)), 'p90': float(np.quantile(x, .9)), 'max': float(x.max())}


def score_diagnosis(probabilities, labels, alpha, current, proposed, plant_indices):
    """A retrospective description, including calibration-set admission counts."""
    p, y = np.asarray(probabilities, float), np.asarray(labels)
    current, proposed = np.asarray(current, float), np.asarray(proposed, float)
    if (current.shape != y.shape or proposed.shape != y.shape or
            not np.isfinite(current).all() or not np.isfinite(proposed).all() or
            not np.array_equal(y, (proposed > current).astype(int))):
        raise ValueError('calibration labels must match the actual zero-tolerance cost pairs')
    fitted = stage_calibration(p, y, alpha)
    scores = np.asarray(fitted.pop('score_sha_inputs'))
    sets = (1-p) <= fitted['qhat']
    admitted = sets[:, 0] & ~sets[:, 1]
    tails = []
    for i in np.argsort(-scores, kind='stable')[:10]:
        tails.append({'plant_index': int(plant_indices[i]), 'label': int(y[i]),
                      'p_harmful': float(p[i, 1]), 'score': float(scores[i]),
                      'at_or_above_q': bool(scores[i] >= fitted['qhat']),
                      'current_J': float(current[i]), 'proposed_J': float(proposed[i]),
                      'delta_J': float(proposed[i]-current[i])})
    return {**fitted, 'noninferior': int((y == 0).sum()), 'harmful': int((y == 1).sum()),
            'p_harmful_by_label': {'noninferior': distribution(p[y == 0, 1]), 'harmful': distribution(p[y == 1, 1])},
            'harmful_p_below_01': int(((y == 1) & (p[:, 1] < .01)).sum()),
            'set_counts': dict(sorted(Counter(''.join('1' if b else '0' for b in row) for row in sets).items())),
            'calibration_admitted_noninferior': int((admitted & (y == 0)).sum()),
            'calibration_admitted_harmful': int((admitted & (y == 1)).sum()),
            'calibration_rejected_noninferior': int((~admitted & (y == 0)).sum()),
            'calibration_rejected_harmful': int((~admitted & (y == 1)).sum()),
            'empirical_score_max': float(scores.max()) if len(scores) else None,
            'tail': tails}


def fixed_path_diagnosis(monitor, gated, risk_limit, confidence=.95):
    """An oracle lower bound over truncations of these recorded paths only."""
    mp, gp = monitor['per_plant'], gated['per_plant']
    if len(mp) != len(gp) or not len(mp):
        raise ValueError('matched nonempty cohorts required')
    full, chosen, safe_prefix, mandatory = [], [], [], []
    largest_abs = 0.
    for m, g in zip(mp, gp):
        if (m['plant_identity'] != g['plant_identity'] or
                g['operating_history'] != m['operating_history'][:len(g['operating_history'])]):
            raise ValueError('gated operating history is not the matched monitor prefix')
        h = np.asarray([x['cost'] for x in m['operating_history']], float)
        gh = np.asarray([x['cost'] for x in g['operating_history']], float)
        if not len(h) or not len(gh) or not np.isfinite(h).all() or not np.isfinite(gh).all():
            raise ValueError('finite nonempty measured operating histories required')
        if m['best_J'] != float(h.min()) or g['best_J'] != float(gh.min()):
            raise ValueError('reported best must equal min of the executed history')
        full.append(float(h.min())); chosen.append(float(gh.min()))
        first = np.flatnonzero(h[1:] > h[:-1])
        before = float(h[:int(first[0])+1].min()) if len(first) else float(h.min())
        safe_prefix.append(before)
        gap = before-float(h.min())
        if gap > 0:
            mandatory.append({'plant_index': int(m['plant_index']), 'plant_identity': int(m['plant_identity']),
                              'first_harm_history_index': int(first[0])+1,
                              'pre_harm_best': before, 'monitor_best': float(h.min()), 'gap': gap})
        largest_abs = max(largest_abs, float(np.abs(h).max()))
    n, k = len(mp), len(mandatory)
    gaps = sorted(x['gap'] for x in mandatory)
    # Upper confidence bound <= alpha implies empirical rate <= alpha. This
    # looser event cap is sufficient for the impossibility certificate.
    empirical_cap = math.floor(risk_limit*n)
    strict_cap = max((i for i in range(empirical_cap+1)
                      if binomial_bounds(i, n, confidence)['upper'] <= risk_limit), default=-1)
    denied = max(0, k-empirical_cap)
    conservative = denied*gaps[0]/n if gaps and denied else 0.
    sharper = math.fsum(gaps[:denied])/n
    # A conservative forward bound for TWO binary64 means: at most n+2
    # rounding operations per sum/division path, eps rather than eps/2.
    eps = np.finfo(float).eps
    gamma = (n+2)*eps/(1-(n+2)*eps)
    roundoff = 2*gamma*largest_abs
    delta = np.asarray(chosen)-full
    if np.any(delta < 0):
        raise ValueError('a prefix cannot have a lower best than its full path')
    return {'n': n, 'exact_operating_prefix_verified': True,
            'monitor_final_best': distribution(full), 'gated_final_best': distribution(chosen),
            'per_plant_gap': delta.tolist(), 'paired_mean_gap': math.fsum(delta)/n,
            'mandatory_harm_plants': k, 'minimum_empirical_trajectory_harm_rate': k/n,
            'mandatory_harm_one_sided_bounds': binomial_bounds(k, n, confidence),
            'risk_limit': risk_limit, 'loose_empirical_event_cap': empirical_cap,
            'event_cap_for_actual_one_sided_upper': strict_cap,
            'smallest_mandatory_gap': gaps[0] if gaps else None,
            'conservative_mean_gap_lower_bound_under_risk_cap': conservative,
            'sorted_gap_mean_lower_bound_under_risk_cap': sharper,
            'binary64_two_mean_roundoff_bound': roundoff,
            'roundoff_bound_formula': '2 * gamma_(n+2) * max_abs_recorded_cost; gamma_m=m*eps/(1-m*eps)',
            'gap_lower_bound_minus_roundoff': conservative-roundoff,
            'joint_criteria_infeasible_on_recorded_paths': bool(k > empirical_cap and conservative > roundoff),
            'mandatory_plants': mandatory,
            'scope': 'post-hoc finite-cohort truncation bound; not a population theorem or impossibility for changed proposal paths'}


def evaluation_diagnosis(raw, path):
    monitor, gated = raw['evaluation']['monitor'], raw['evaluation']['gated']
    n = len(gated['per_plant']); gaps = np.asarray(path['per_plant_gap'])
    total_gap = math.fsum(gaps)
    groups, stages = [], []
    for t in sorted({r['stage'] for r in gated['transitions']}):
        rows = [r for r in gated['transitions'] if r['stage'] == t]
        exe = [r for r in rows if r['executed']]
        rejected = [r for r in rows if r['reason'] == 'risk_rejected']
        if any(not r['measured'] or not r['observed_finite'] for r in rejected):
            raise ValueError('rejection composition requires finite diagnostic labels')
        ids = [r['plant_index'] for r in rejected]
        stages.append({'stage': t+1, 'reached': len(rows), 'executed': len(exe),
                       'executed_harmful': sum(r['cost_after'] > r['cost_before'] for r in exe),
                       'rejected': len(rejected), 'rejected_noninferior': sum(r['cost_after'] <= r['cost_before'] for r in rejected),
                       'rejected_harmful': sum(r['cost_after'] > r['cost_before'] for r in rejected)})
        if ids:
            gap_sum = math.fsum(gaps[ids])
            groups.append({'rejection_stage': t+1, 'n': len(ids), 'gap_sum': gap_sum,
                           'contribution_to_cohort_mean_gap': gap_sum/n,
                           'share_of_total_gap': gap_sum/total_gap if total_gap else None,
                           'monitor_best_strictly_better': int((gaps[ids] > 0).sum())})
    return {'stages': stages, 'gap_by_rejection_stage': groups,
            'unassigned_gap_sum': total_gap-math.fsum(g['gap_sum'] for g in groups),
            'interpretation': 'arithmetic grouping by observed rejection stage; not a causal mediation or counterfactual attribution'}


def feature_diagnosis(raw, model_data):
    mean, scale, coef = (np.asarray(model_data[k]) for k in ('mean', 'scale', 'coefficient'))
    names = [*FEATURE_NAMES, 'joint_dlog_Kp', 'joint_dlog_Ki', 'joint_dlog_Kd',
             *[f'p_{axis}_{j}' for axis in ('Kp', 'Ki', 'Kd') for j in range(7)]]
    zero = [{'index': int(i), 'name': names[i], 'fitted_mean': float(mean[i]),
             'fitted_scale': float(scale[i]), 'coefficient': float(coef[i])}
            for i in np.flatnonzero(coef == 0)]
    ix = names.index('prev_dJ')
    stages = []
    for t, run in enumerate(raw['calibration']):
        x = np.asarray(run['collected']['features'], float).reshape(-1,44)
        if not len(x):
            continue
        z = (x[:,ix]-mean[ix])/scale[ix]
        stages.append({'stage': t+1, 'prev_dJ': distribution(x[:,ix]),
                       'standardized_prev_dJ': distribution(z),
                       'contribution_to_temperature_scaled_harm_logit': distribution(z*coef[ix]/model_data['temperature']),
                       'zero_coefficient_features_different_from_fitted_mean': {
                           names[r['index']]: int((x[:,r['index']] != mean[r['index']]).sum()) for r in zero}})
    checked, max_error = 0, 0.
    for run in [*raw['calibration'], *raw['evaluation'].values()]:
        previous_before = {}
        for r in run['transitions']:
            if r['features'] is None:
                continue
            i = r['plant_index']; prev = previous_before.get(i, 0.)
            expected = float(np.float32(np.clip((prev-r['cost_before'])/5., -3., 3.)))
            error = abs(r['features'][ix]-expected)
            max_error = max(max_error, error); checked += 1
            if r['executed']:
                previous_before[i] = r['cost_before']
    if max_error > 1e-7:
        raise ValueError('raw prev_dJ does not follow the published history formula')
    return {'source': 'published v1 fitted model metadata plus published calibration/rollout features; training NPZ not read',
            'zero_coefficients': zero,
            'training_variance_limit': 'scale=1 alone does not prove a constant training feature; no training min/max is inferred',
            'prev_dJ': {'index': ix, 'fitted_mean': float(mean[ix]), 'fitted_scale': float(scale[ix]),
                        'coefficient': float(coef[ix]), 'formula': 'clip((previous_J-current_J)/5,-3,3); initial previous_J=0',
                        'verified_raw_rows': checked, 'formula_max_abs_error': max_error, 'calibration_stages': stages},
            'interpretation': 'zero coefficients make these inputs irrelevant to this linear risk head; observed feature/logit shifts do not prove a causal source of the final cost gap'}


def build_diagnosis(root=ROOT):
    root = Path(root)
    paths = {'rollout': 'research/results/joint_risk_rollout.json',
             'initial_risk': 'research/results/joint_risk.json',
             'raw': 'research/results/joint_risk_rollout_raw.json.gz'}
    rollout, initial = (json.loads((root/paths[k]).read_text(encoding='utf-8')) for k in ('rollout','initial_risk'))
    raw_bytes = (root/paths['raw']).read_bytes()
    if hashlib.sha256(raw_bytes).hexdigest() != rollout['raw_sha256']:
        raise ValueError('published raw trace hash mismatch')
    md = initial['risk_model']
    if canonical_hash(md) != rollout['risk_model_sha256']:
        raise ValueError('published v1 model hash mismatch')
    raw = json.loads(gzip.decompress(raw_bytes))
    model = JointRiskModel(*(np.asarray(md[k]) for k in ('mean','scale','coefficient')), md['intercept'], md['temperature'])
    calibration = []
    for s, run in zip(rollout['stages'], raw['calibration'], strict=True):
        d = run['collected']; x = np.asarray(d['features']).reshape(-1,44)
        probs = model.probabilities(x) if len(x) else np.empty((0,2))
        result = score_diagnosis(probs, d['labels'], s['alpha'],
                                np.asarray(d['current_cost']), np.asarray(d['proposed_cost']), d['plant_index'])
        if result['quantile_rank'] != s['quantile_rank'] or result['n_reached'] != s['n_reached']:
            raise ValueError('published calibration sample count/rank mismatch')
        if not math.isclose(result['qhat'], s['qhat'], rel_tol=0, abs_tol=1e-14):
            raise ValueError('recomputed calibration quantile mismatch')
        np.testing.assert_allclose(1-probs[np.arange(len(x)),d['labels']],s['score_sha_inputs'],rtol=0,atol=1e-14)
        calibration.append({'stage':s['stage']+1, 'seed':s['seed'], 'n_initial':s['n_initial'], **result})
    spec = rollout['protocol']['specification']
    path = fixed_path_diagnosis(raw['evaluation']['monitor'],raw['evaluation']['gated'],
                               spec['acceptance']['trajectory_risk_upper_max'],spec['acceptance']['confidence_one_sided'])
    alpha = spec['alpha_per_stage'][0]
    min_n = next(n for n in range(1,100000) if math.ceil((n+1)*(1-alpha)) <= n)
    max_n = next(n for n in range(min_n,100000) if math.ceil((n+1)*(1-alpha)) < n)-1
    planning = []
    for s in calibration:
        if not s['n_reached']:
            continue
        rate = s['n_reached']/s['n_initial']
        planning.append({'stage':s['stage'],'observed_reach_rate':rate,
                         'expected_initial_plants_for_minimum':min_n/rate,
                         'extra_reached_to_minimum':max(0,min_n-s['n_reached']),
                         'expected_extra_initial_plants_to_minimum':max(0,min_n-s['n_reached'])/rate,
                         'expected_initial_plants_for_fixed_512_reached':512/rate})
    return {'schema_version':1, 'status':'post_hoc_diagnostic_only',
            'source_artifacts': {'raw':{'path':paths['raw'],'sha256':hashlib.sha256(raw_bytes).hexdigest()},
                                 'rollout':{'path':paths['rollout'],'canonical_json_sha256':canonical_hash(rollout)},
                                 'initial_risk':{'path':paths['initial_risk'],'canonical_json_sha256':canonical_hash(initial)}},
            'risk_model_sha256':canonical_hash(md), 'training_data_dependency':False,
            'calibration':calibration, 'evaluation':evaluation_diagnosis(raw,path),
            'feature_shift':feature_diagnosis(raw,md), 'fixed_path_feasibility':path,
            'sampling':{'alpha_per_stage':alpha,'minimum_reached_for_finite_rank':min_n,
                        'max_score_rank_n_range':[min_n,max_n],'planning':planning,
                        'limits':'Planning expectations use old frozen-prefix reach rates, not guaranteed budgets or actual simulation counts. A changed model/prefix invalidates these reach estimates.'},
            'limits':['post-hoc explanation, not a new independent test or parameter selection',
                      'old outputs and acceptance are preserved; no training, calibration, or simulations performed',
                      'only the recorded deterministic paths with accept-whole-proposal-or-stop support the feasibility bound',
                      'calibration admission counts reuse calibration labels and are not held-out performance',
                      'coverage does not guarantee useful acceptance, cost improvement, or physical safety']}


def same_evidence(actual, expected):
    """Counts/structure are exact; permit ULP-scale numerical recomputation."""
    if isinstance(expected, dict):
        return (isinstance(actual, dict) and actual.keys() == expected.keys()
                and all(same_evidence(actual[k], v) for k,v in expected.items()))
    if isinstance(expected, list):
        return (isinstance(actual, list) and len(actual) == len(expected)
                and all(same_evidence(a,b) for a,b in zip(actual,expected)))
    if isinstance(expected, float):
        return (isinstance(actual,(int,float)) and math.isfinite(actual)
                and math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-12))
    return type(actual) is type(expected) and actual == expected


def _doc(p):
    c=p['calibration']; e=p['evaluation']; f=p['feature_shift']; proof=p['fixed_path_feasibility']; sampling=p['sampling']
    lines=['# Rollout failure diagnosis / 多轮实验失败归因','',
           '[English](#english) · [简体中文](#简体中文)','']
    for zh in (False,True):
        lines += ['## 简体中文' if zh else '## English','',
            ('本报告对已发布原始轨迹做事后复算。没有新仿真、重新训练、调参或更换测试集；旧结果和原验收结论保持不变。所有数值来自公开原始轨迹及v1风险模型，不依赖未跟踪的训练NPZ。'
             if zh else 'This is a post-hoc recomputation of published raw traces. No new simulation, fitting, tuning or test replacement is performed; original results and acceptance remain intact. All numbers use public raw traces and the v1 risk model, without an untracked training NPZ.'),'',
            ('所有有害标签均为严格J_after > J_before，零容差；非劣为J_after ≤ J_before。轨迹有害事件表示至少一次实际执行的联合动作使代价上升，不是失稳或最终返回参数恶化。'
             if zh else 'Every harmful label uses strict J_after > J_before with zero tolerance; noninferior means J_after ≤ J_before. A trajectory harm event is at least one actually executed joint action increasing cost, not instability or degradation of the final returned parameters.'),'',
            '| 阶段 | 到达 n | 秩 | q | 实际非劣 / 有害 |' if zh else '| stage | reached n | rank | q | actual noninferior / harmful |',
            '| ---: | ---: | ---: | ---: | ---: |']
        for r in c:
            lines.append(f"| {r['stage']} | {r['n_reached']} | {r['quantile_rank']} | {r['qhat']:.12f} | {r['noninferior']} / {r['harmful']} |")
        driver=c[1]['tail'][0]
        lines += ['',
            (f"第2步已有{c[1]['n_reached']}个样本，极端q并非样本不足回退。决定最大分数的是实际非劣样本plant_index={driver['plant_index']}：J {driver['current_J']:.9f}→{driver['proposed_J']:.9f}，p(harmful)={driver['p_harmful']:.12f}。共同LAC阈值为包含这个真实标签而增大，也让其他样本更容易同时包含两标签；当q>0.5且只允许{{非劣}}，需p(harmful)<1-q，约{1-c[1]['qhat']:.12g}。"
             if zh else f"Stage 2 already has {c[1]['n_reached']} samples; its extreme q is not an insufficient-sample fallback. The maximum score comes from an actually noninferior case, plant_index={driver['plant_index']}: J {driver['current_J']:.9f}→{driver['proposed_J']:.9f}, p(harmful)={driver['p_harmful']:.12f}. A shared LAC threshold expands to include this true label and also puts both labels into other sets. With q>0.5 and only {{noninferior}} admitted, p(harmful) must be below 1-q, approximately {1-c[1]['qhat']:.12g}."),'',
            '| 阶段 | 有害样本p(harmful)中位数 / 最小值 | 非劣样本p(harmful)中位数 |' if zh else '| stage | harmful-case p(harmful) median / minimum | noninferior-case p(harmful) median |',
            '| ---: | ---: | ---: |']
        for r in c[:3]:
            h=r['p_harmful_by_label']['harmful']; safe=r['p_harmful_by_label']['noninferior']
            lines.append(f"| {r['stage']} | {h['median']:.6f} / {h['min']:.6f} | {safe['median']:.6f} |")
        lines += ['',('这些数值来自实际门控前缀下的校准对象，不是monitor后期状态；分数尾部同时存在有害动作低估和非劣动作高估。校准集接纳计数仅为回看，不是独立验证。'
                       if zh else 'These are calibration plants under the actual gated prefix, not later monitor states. The tails contain both underestimated harmful actions and overestimated noninferior actions. Calibration-set admission counts are retrospective, not independent validation.'),'',
            '| 拒绝阶段 | 拒绝数 | 其中非劣 / 有害 | 全体均值差贡献 | 总差份额 |' if zh else '| rejection stage | rejected | noninferior / harmful | contribution to cohort mean gap | share of total gap |',
            '| ---: | ---: | ---: | ---: | ---: |']
        for r,g in zip(e['stages'],e['gap_by_rejection_stage'],strict=True):
            lines.append(f"| {r['stage']} | {r['rejected']} | {r['rejected_noninferior']} / {r['rejected_harmful']} | {g['contribution_to_cohort_mean_gap']:.6f} | {100*g['share_of_total_gap']:.4f}% |")
        lines += ['',('前两步占大部分最终代价差；这只是按实际拒绝阶段对配对差值分组，不是反事实因果比例。第三步102个拒绝动作在诊断测量中均非劣，也不能据此修改已冻结的q。'
                       if zh else 'The first two stages account for most of the final cost gap. This groups observed paired differences by rejection stage; it is not causal mediation. All stage-3 rejected proposals were noninferior in diagnostic measurements, which does not authorize changing the frozen q.'),'',
            f"{'模型恰为零的系数数' if zh else 'Exactly zero model coefficients'}: {len(f['zero_coefficients'])}.",
            '`'+', '.join(r['name'] for r in f['zero_coefficients'])+'`','',
            ('这些输入对当前线性风险头没有贡献。公开scaler的mean/scale可核对，但scale=1本身不能证明训练方差为零；本报告不推断未读取的训练范围。初态训练协议仅覆盖每株一个解析ZN状态。'
             if zh else 'These inputs contribute nothing to this linear risk head. Public scaler means/scales can be checked, but scale=1 alone does not prove zero training variance; unread training ranges are not inferred. The training protocol covers one initial analytic-ZN state per plant.'),'',
            (f"prev_dJ：拟合均值={f['prev_dJ']['fitted_mean']:.6f}；scale={f['prev_dJ']['fitted_scale']:.6f}；系数={f['prev_dJ']['coefficient']:.6f}。"
             if zh else f"prev_dJ: fitted mean={f['prev_dJ']['fitted_mean']:.6f}; scale={f['prev_dJ']['fitted_scale']:.6f}; coefficient={f['prev_dJ']['coefficient']:.6f}."),
            ('其公式是clip((previous_J-current_J)/5,-3,3)。初态previous_J=0，因此编码为-current_J/5；后续则编码真实上一轮改善。原始轨迹已逐项核验公式。'
             if zh else 'The formula is clip((previous_J-current_J)/5,-3,3). Initially previous_J=0, so it encodes -current_J/5; later it encodes the previous measured improvement. The formula is checked against individual raw transitions.'),'',
            '| 校准阶段 | prev_dJ中位数 | 标准化中位数 | 温度缩放后有害logit贡献中位数 |' if zh else '| calibration stage | prev_dJ median | standardized median | median contribution to scaled harmful logit |',
            '| ---: | ---: | ---: | ---: |']
        for r in f['prev_dJ']['calibration_stages']:
            lines.append(f"| {r['stage']} | {r['prev_dJ']['median']:.6f} | {r['standardized_prev_dJ']['median']:.6f} | {r['contribution_to_temperature_scaled_harm_logit']['median']:.6f} |")
        lines += ['',('这些是特征与模型运算的迁移证据，不证明某一个特征独立造成最终性能差。'
                       if zh else 'These describe feature and model-computation shifts; they do not establish that one feature independently caused the final performance gap.'),'',
            (f"每步alpha={sampling['alpha_per_stage']}时，避免秩超过n至少需{sampling['minimum_reached_for_finite_rank']}个独立reached样本；n={sampling['max_score_rank_n_range'][0]}–{sampling['max_score_rank_n_range'][1]}仍取最大分数。样本足够不代表q小或有效接纳。第3步旧到达率为{sampling['planning'][2]['observed_reach_rate']:.6f}：补足最低数量需再收{sampling['planning'][2]['extra_reached_to_minimum']}个reached，按旧前缀预计{sampling['planning'][2]['expected_extra_initial_plants_to_minimum']:.1f}个新增初始植物；重新收满512个reached预计{sampling['planning'][2]['expected_initial_plants_for_fixed_512_reached']:.1f}个初始植物。它们不是保证预算，也不是实际仿真次数。"
             if zh else f"At alpha={sampling['alpha_per_stage']} per stage, avoiding rank>n needs at least {sampling['minimum_reached_for_finite_rank']} independent reached samples; n={sampling['max_score_rank_n_range'][0]}–{sampling['max_score_rank_n_range'][1]} still uses the maximum score. Adequate sample size does not ensure a small q or useful admission. Stage 3's old reach rate is {sampling['planning'][2]['observed_reach_rate']:.6f}: the minimum needs {sampling['planning'][2]['extra_reached_to_minimum']} further reached samples, approximately {sampling['planning'][2]['expected_extra_initial_plants_to_minimum']:.1f} new initial plants under the old prefix; collecting 512 reached from scratch needs approximately {sampling['planning'][2]['expected_initial_plants_for_fixed_512_reached']:.1f} initial plants. These are neither guaranteed budgets nor actual simulation counts."),'',
            (f"固定路径验收冲突：已验证全部{proof['n']}株gated操作历史是monitor前缀，返回代价为各自实测历史最小值。因此每株best_gated≥best_monitor，数学上的均值零松弛要求逐株相等。其中{proof['mandatory_harm_plants']}株的monitor最优严格低于首次有害动作之前的所有代价；保持这些最优至少要让{100*proof['minimum_empirical_trajectory_harm_rate']:.6f}%对象执行有害步，不能满足{100*proof['risk_limit']:.0f}%轨迹风险上界。"
             if zh else f"Fixed-path acceptance conflict: all {proof['n']} gated operating histories are verified monitor prefixes, and returned cost is the measured history minimum. Every best_gated≥best_monitor, so mathematical zero-slack mean noninferiority requires equality plant by plant. For {proof['mandatory_harm_plants']} plants, monitor's best is strictly below every pre-first-harm cost. Retaining those optima requires harmful execution on at least {100*proof['minimum_empirical_trajectory_harm_rate']:.6f}% of plants, incompatible with the {100*proof['risk_limit']:.0f}% trajectory-risk upper bound."),'',
            (f"即使宽松允许{proof['loose_empirical_event_cap']}株发生有害事件，均值损失仍至少{proof['conservative_mean_gap_lower_bound_under_risk_cap']:.12g}；两次binary64均值计算的保守舍入误差界为{proof['binary64_two_mean_roundoff_bound']:.12g}，余量{proof['gap_lower_bound_minus_roundoff']:.12g}>0。这排除了均值舍入掩盖冲突；未把数值舍入界当物理仿真误差界。"
             if zh else f"Even allowing the loose cap of {proof['loose_empirical_event_cap']} harmed plants, the mean gap is at least {proof['conservative_mean_gap_lower_bound_under_risk_cap']:.12g}. A conservative bound for two binary64 mean computations is {proof['binary64_two_mean_roundoff_bound']:.12g}, leaving margin {proof['gap_lower_bound_minus_roundoff']:.12g}>0. Mean rounding cannot hide the conflict; this is not a bound on physical simulation error."),'',
            ('该结论仅针对这批确定性轨迹、相同起点/时域、整动作执行或拒绝即停，不是总体定理或对其他动作路径的不可能性证明。只重训风险头及补样无法让这些固定路径同时通过原两项验收。改变动作路径是突破此限制的必要条件而非充分条件，改变后必须对实际执行联合动作重新校准和独立评估。'
             if zh else 'This conclusion concerns this finite deterministic cohort, the same starts/horizon, and accept-whole-action-or-stop gates. It is not a population theorem or an impossibility result for different action paths. Risk-head retraining and more calibration alone cannot make these fixed paths pass both original criteria. Changing the action path is necessary to escape this restriction, not sufficient for success; the actual executed joint action then needs new calibration and independent evaluation.'),'',
            ('后续研究应先在开发数据上训练多轮状态与实际联合动作风险，再冻结模型、温度、提案和预算。逐步使用独立新植物，按冻结前缀收满预注册reached配额；续采只看到达计数，不看目标标签、分数或q。达到预注册上限仍不足就保留完整集合。模型或前缀更新后重新校准，最终评估使用新保留集。覆盖不等于接纳率、闭环代价改善或物理安全；本页结果不用于从旧测试集选参。'
             if zh else 'Future work should train on development data covering multi-round states and actual joint actions, then freeze the model, temperature, proposal and budgets. Use independent new plants at each calibration stage under its frozen prefix, with preregistered reached quotas. Continue sampling based only on reach counts, never target labels, scores or q; retain the full set if the preregistered cap is insufficient. Recalibrate after model/prefix changes and use a fresh final holdout. Coverage does not imply execution rate, closed-loop cost improvement or physical safety; this report selects no parameters from the old test.'),'',
            '`python scripts/30_rollout_diagnosis.py`','',
            '`python scripts/30_rollout_diagnosis.py --check`','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='recompute raw evidence and compare without writing')
    parser.add_argument('--render-only',action='store_true')
    args=parser.parse_args()
    payload=json.loads(RESULT.read_text(encoding='utf-8')) if args.render_only else build_diagnosis()
    text=_doc(payload)
    if args.check:
        if not same_evidence(payload,json.loads(RESULT.read_text(encoding='utf-8'))):
            raise SystemExit('rollout_diagnosis.json differs from its published raw evidence')
        if text != DOC.read_text(encoding='utf-8'):
            raise SystemExit('ROLLOUT_DIAGNOSIS.md differs from the generated document')
        print('Diagnosis and bilingual document match published evidence')
    else:
        if not args.render_only:
            RESULT.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        DOC.write_text(text,encoding='utf-8')
        print(json.dumps({'mandatory_harm':payload['fixed_path_feasibility']['mandatory_harm_plants'],
                          'roundoff_margin':payload['fixed_path_feasibility']['gap_lower_bound_minus_roundoff'],
                          'zero_coefficients':len(payload['feature_shift']['zero_coefficients'])},indent=2))


if __name__ == '__main__':
    main()
