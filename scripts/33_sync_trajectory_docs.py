"""Generate the v2 research summaries from completed, preserved evidence.

No experiment runs on import or here. The independent verifier (32) validates
raw evidence; this module checks entire generated prose blocks and claim source
definitions. A missing final result is an error, never a fabricated result.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSIS = 'research/results/rollout_diagnosis.json'
TRAJECTORY = 'research/results/trajectory_risk.json'
MARKER = 'trajectory-risk-v2'


def _read(root, name):
    return json.loads((Path(root) / name).read_text(encoding='utf-8-sig'))


def _validate(diagnosis, trajectory):
    if diagnosis['status'] != 'post_hoc_diagnostic_only':
        raise ValueError('Diagnosis must remain explicitly retrospective')
    if not trajectory.get('completed_utc'):
        raise ValueError('Only a completed final trajectory result can be published')
    spec = trajectory['protocol']['specification']
    primary = spec['primary_candidate']
    p, m = trajectory['evaluation'][primary], trajectory['evaluation']['monitor']
    limits = spec['acceptance']
    integrity = trajectory['integrity']
    checks = {
        'trajectory_risk_upper': p['trajectory_harm']['upper'] <= limits['trajectory_harm_one_sided_95_upper_max'],
        'first_stage_execution_lower': p['first_stage_execution']['lower'] >= limits['first_stage_execution_one_sided_95_lower_min'],
        'empirical_mean_cost_noninferior': p['final_cost']['mean'] <= m['final_cost']['mean'],
        'empirical_p90_cost_noninferior': p['final_cost']['p90'] <= m['final_cost']['p90'],
        'operating_budget_noninferior': p['simulation_counts']['operating'] <= m['simulation_counts']['operating'],
        'integrity': bool(integrity) and all(integrity.values()),
    }
    acceptance = trajectory['acceptance']
    passed = all(checks.values())
    if (acceptance['checks'] != checks or acceptance['passed'] != passed
            or acceptance['failed'] != [name for name, ok in checks.items() if not ok]):
        raise ValueError('Stored acceptance differs from registered criteria and measured summaries')
    deployment = trajectory['deployment']
    status = 'validated_research_scope_only' if passed else 'research_only'
    if (deployment['status'] != status or deployment['enabled'] != passed
            or deployment['primary_candidate'] != primary
            or deployment['generic_python_c_matlab_enabled'] is not False):
        raise ValueError('Deployment status must retain the registered research-only scope')


def claim_definitions(trajectory=None):
    """Source definitions only; 23 reads each value and generates the register."""
    defs = []

    def add(identifier, path, label, source=DIAGNOSIS, **extra):
        script = '30_rollout_diagnosis' if source == DIAGNOSIS else '31_trajectory_risk'
        defs.append({'id': identifier, 'label': label, 'source': source, 'path': path,
                     'reproduce': f'python scripts/{script}.py', **extra})

    add('diagnosis_path_n', 'fixed_path_feasibility.n', 'Retrospective fixed paths / 事后固定轨迹数')
    add('diagnosis_mandatory_harm', 'fixed_path_feasibility.mandatory_harm_plants',
        'Paths whose full optimum requires a harmful transition / 保留完整路径最优必须经过有害转移的轨迹数')
    add('diagnosis_mandatory_harm_rate', 'fixed_path_feasibility.minimum_empirical_trajectory_harm_rate',
        'Retrospective minimum harmed fraction for preserving all optima / 事后保留全部最优的最低有害轨迹比例')
    add('diagnosis_roundoff_margin', 'fixed_path_feasibility.gap_lower_bound_minus_roundoff',
        'Fixed-path mean-gap lower bound minus binary64 roundoff / 固定路径均值差下界减binary64舍入余量')
    for stage in (1, 2, 3):
        add(f'diagnosis_stage{stage}_gap_share', f'evaluation.gap_by_rejection_stage[rejection_stage={stage}].share_of_total_gap',
            f'Stage {stage} arithmetic share of old final-cost gap, not causal / 旧最终代价差按第{stage}步分组的算术占比，非因果')
        add(f'diagnosis_stage{stage}_qhat', f'calibration[stage={stage}].qhat',
            f'Old stage {stage} calibration qhat / 旧第{stage}步校准qhat')
    add('diagnosis_zero_coefficients', 'feature_shift.zero_coefficients',
        'Exactly zero fitted risk coefficients / 拟合风险头中精确零系数数目', reduce='count:index')
    add('diagnosis_minimum_reached', 'sampling.minimum_reached_for_finite_rank',
        'Minimum reached count for finite empirical rank, not useful acceptance / 经验秩有限的最低到达数，不保证有效接纳')
    if trajectory is None:
        return defs
    primary = trajectory['protocol']['specification']['primary_candidate']
    for name, prefix in ((primary, 'trajectory_primary'), ('monitor', 'trajectory_monitor')):
        for suffix, path, label in (
            ('n', 'n_plants', 'independent test plants / 独立测试对象'),
            ('harm_events', 'trajectory_harm.events', 'trajectories with any harmful execution / 至少一次有害执行的轨迹'),
            ('risk_upper', 'trajectory_harm.upper', 'exact one-sided trajectory-risk upper bound / 轨迹风险精确单侧上界'),
            ('first_lower', 'first_stage_execution.lower', 'exact one-sided first-execution lower bound / 首步执行率精确单侧下界'),
            ('mean', 'final_cost.mean', 'final mean J / 最终平均J'),
            ('p90', 'final_cost.p90', 'final p90 J / 最终p90 J'),
            ('operating_sims', 'simulation_counts.operating', 'actual operating simulations / 实际运行仿真数'),
        ):
            add(prefix+'_'+suffix, f'evaluation.{name}.{path}', name+': '+label, TRAJECTORY)
    add('trajectory_acceptance', 'acceptance.passed',
        'Sole primary passes every registered criterion, 1=yes / 唯一主要候选通过全部预注册判据，1为是', TRAJECTORY)
    for key, label in (
        ('training_total', 'training/temperature/development / 训练、温度、开发'),
        ('calibration_total', 'stage calibration / 逐步校准'),
        ('evaluation_total', 'final evaluation / 最终评估'),
        ('total', 'all study simulations / 全研究仿真'),
    ):
        add('trajectory_sims_'+key, 'simulation_counts.'+key, 'Actual simulations: '+label, TRAJECTORY)
    return defs


def register_available_claims(registry, root=ROOT):
    """Called by 23; never register absent result files or duplicate IDs."""
    root = Path(root)
    if not (root / DIAGNOSIS).is_file():
        return
    trajectory = _read(root, TRAJECTORY) if (root / TRAJECTORY).is_file() else None
    if trajectory is not None:
        _validate(_read(root, DIAGNOSIS), trajectory)
    existing = {c['id']: c for c in registry['claims']}
    for definition in claim_definitions(trajectory):
        if definition['id'] in existing:
            existing[definition['id']].update(definition)
        else:
            registry['claims'].append(definition)


def _summary(d, p, chinese=False, detailed=False, relative='docs/'):
    spec = p['protocol']['specification']
    primary = spec['primary_candidate']
    r, monitor = p['evaluation'][primary], p['evaluation']['monitor']
    f = d['fixed_path_feasibility']
    status = 'PASS' if p['acceptance']['passed'] else 'FAIL'
    failed = ', '.join(p['acceptance']['failed']) or ('无' if chinese else 'none')
    scales = ', '.join(f'{s:g}' for s in spec['candidates']['scales'])
    counts = p['simulation_counts']
    if chinese:
        lines = [f"### 多步联合风险：预注册新实验 {status}", '',
            f"唯一主要候选为`{primary}`；状态为`{p['deployment']['status']}`。"
            f"在{r['n_plants']}个新独立测试对象上，{r['trajectory_harm']['events']}条轨迹出现有害执行，"
            f"风险的单侧95%精确上界为{r['trajectory_harm']['upper']:.6f}，首步执行率单侧95%下界为{r['first_stage_execution']['lower']:.6f}。"
            f"主要候选/配对monitor的最终mean J为{r['final_cost']['mean']:.6f}/{monitor['final_cost']['mean']:.6f}，"
            f"p90 J为{r['final_cost']['p90']:.6f}/{monitor['final_cost']['p90']:.6f}，"
            f"实际运行仿真数为{r['simulation_counts']['operating']}/{monitor['simulation_counts']['operating']}。未通过项：{failed}。", '',
            '旧v1失败结果保留。旧测试已经用于事后诊断，不能再作新方案的独立验证；本轮只用新测试验收事先指定的主要候选，其他组不按测试成绩选优上线。'
            '本轮同时改变训练轨迹、数据量、标准化和风险初态特征语义，是整体方案比较，不是单因素因果实验。', '',
            f"旧固定路径诊断发现{f['mandatory_harm_plants']}/{f['n']}株保留monitor最优必须经过有害步。"
            '这证明旧记录中仅截断、不改提案的门控无法同时满足原风险与零松弛均值条件；不证明所有新策略都不可能。'
            '替代联合动作可改变路径，但是否成功由本轮真实验收决定。', '',
            f"见[旧失败诊断]({relative}ROLLOUT_DIAGNOSIS.md)、[新完整研究]({relative}TRAJECTORY_RISK.md)及其JSON/原始分片。"
            '通用Python/C/MATLAB部署默认保持原样；即使通过，也只支持注册的研究运行器、模拟分布和时域。']
    else:
        lines = [f'### Multistep joint risk: new preregistered study {status}', '',
            f"The sole primary candidate is `{primary}`; status is `{p['deployment']['status']}`. "
            f"On {r['n_plants']} new independent test plants, {r['trajectory_harm']['events']} trajectories had a harmful execution. "
            f"The exact one-sided 95% risk upper bound is {r['trajectory_harm']['upper']:.6f}; the first-execution lower bound is {r['first_stage_execution']['lower']:.6f}. "
            f"Primary/matched-monitor final mean J is {r['final_cost']['mean']:.6f}/{monitor['final_cost']['mean']:.6f}, "
            f"p90 J is {r['final_cost']['p90']:.6f}/{monitor['final_cost']['p90']:.6f}, "
            f"and actual operating simulations are {r['simulation_counts']['operating']}/{monitor['simulation_counts']['operating']}. Failed criteria: {failed}.", '',
            'The v1 failure is preserved. Old tests have been used for retrospective diagnosis and cannot independently validate the new design. '
            'Only the primary candidate fixed before data is assessed for acceptance on the new test; explanatory arms cannot be selected for deployment after testing. '
            'The new comparison changes training trajectories, data volume, scaling and initial risk-feature semantics together; it is not a single-factor causal experiment.', '',
            f"On the recorded old paths, preserving the monitor optimum requires a harmful transition for {f['mandatory_harm_plants']}/{f['n']} plants. "
            'Thus a gate that only truncates those paths cannot meet both the original risk and zero-slack mean criteria. '
            'This is a finite-record diagnosis, not an impossibility theorem for all new policies. Alternative joint actions can change paths; their success is decided by the measured new acceptance.', '',
            f'See the [old failure diagnosis]({relative}ROLLOUT_DIAGNOSIS.md), [full new study]({relative}TRAJECTORY_RISK.md), and their JSON/raw shards. '
            'General Python/C/MATLAB deployment defaults remain unchanged. Even a pass supports only the registered research runner, simulated population and horizon.']
    if not detailed:
        return '\n'.join(lines)
    if chinese:
        lines += ['', f"风险头使用多轮训练；仅风险输入初态prev_dJ置零，提案头输入不变。每步先从完整联合动作尺度[{scales}]中按冻结风险模型选候选，再对已选动作作CP；只接受{{非劣}}，拒绝即停，不因集合内容重新挑动作。",
            f"目标逐步到达数为{spec['calibration']['target_reached']}，每步初始对象上限{spec['calibration']['initial_cap_per_stage']}。只按冻结前缀的到达条件继续采样，不看目标标签/分数决定是否补样；配额不足完整集合回退。",
            '训练与温度拟合可有同株相关行；这些行不当作独立校准样本。逐步校准使用新独立对象，最终测试另行独立。覆盖保证对校准与新抽样取边际；不等于每个固定校准文件的条件保证、获准动作风险比例界或闭环代价收益。', '',
            '| 组 | 有害轨迹/对象 | 风险上界 | 首步执行下界 | mean J | p90 J | 实际运行仿真 |',
            '| :--- | ---: | ---: | ---: | ---: | ---: | ---: |']
    else:
        lines += ['', f'The risk head is trained on multiple stages. Initial prev_dJ is zeroed only in risk inputs; proposal inputs remain unchanged. At each stage the frozen risk model first selects a complete joint action at a scale in [{scales}]. CP assesses only that selected action: only {{noninferior}} executes, and rejection stops without selecting again from the sets.',
            f"The per-stage reached target is {spec['calibration']['target_reached']}, capped at {spec['calibration']['initial_cap_per_stage']} initial plants. Sampling continues only according to reaching the frozen prefix, never according to target labels/scores; quota shortfall uses the full set.",
            'Training and temperature fitting may contain dependent rows within a plant; these are not independent calibration observations. Each calibration stage uses fresh independent plants, followed by a separate new test. Coverage averages over calibration and a fresh draw. It is not conditional on every fitted calibration file, a risk fraction among accepted actions, or a closed-loop performance benefit.', '',
            '| arm | harmed/total plants | risk upper | first-execution lower | mean J | p90 J | actual operating simulations |',
            '| :--- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name in spec['evaluation']['arms']:
        row = p['evaluation'][name]
        lines.append(f"| `{name}` | {row['trajectory_harm']['events']}/{row['n_plants']} | {row['trajectory_harm']['upper']:.6f} | {row['first_stage_execution']['lower']:.6f} | {row['final_cost']['mean']:.6f} | {row['final_cost']['p90']:.6f} | {row['simulation_counts']['operating']} |")
    if chinese:
        lines += ['', f"全研究实际仿真{counts['total']}次：训练/温度/开发{counts['training_total']}，逐步校准{counts['calibration_total']}，最终评估{counts['evaluation_total']}。表内运行计数与另行计账的离线诊断分开。",
            '有害指即时J严格上升，不等于失稳或最终返回参数恶化；返回值只取实际执行历史最优。风险和首步活动率的单侧95%界分别计算，不构成联合95%置信。改变模拟分布、噪声、起点、时域、动作选择或恢复规则后，需要新校准与新验证。']
    else:
        lines += ['', f"Actual study simulations: {counts['total']} total; {counts['training_total']} training/temperature/development, {counts['calibration_total']} stage calibration, {counts['evaluation_total']} final evaluation. Table operating counts exclude separately charged offline diagnostics.",
            'Harm is a strict immediate increase in J, not instability or degradation of returned parameters; returns use only actually executed historical best observations. The separate one-sided 95% risk/activity limits are not joint 95% confidence. Changed populations, noise, starts, horizon, action selection or recovery require new calibration and validation.']
    return '\n'.join(lines)


def rendered_sections(diagnosis, trajectory):
    """Pure renderer: relative document -> [(independent marker key, body)]."""
    _validate(diagnosis, trajectory)
    result = {
        'README.md': [('en', _summary(diagnosis, trajectory))],
        'README.zh-CN.md': [('zh', _summary(diagnosis, trajectory, chinese=True))],
    }
    for name in ('docs/ARCHITECTURE.md', 'docs/TRANSFER.md'):
        result[name] = [(key, _summary(diagnosis, trajectory, chinese=zh, detailed=True, relative=''))
                        for key, zh in (('en', False), ('zh', True))]
    return result


def _block(key, body):
    return f'<!-- {MARKER}:{key}:start -->\n{body}\n<!-- {MARKER}:{key}:end -->'


def _pattern(key):
    return re.compile(r'<!-- '+re.escape(MARKER+':'+key)+r':start -->.*?<!-- '
                      +re.escape(MARKER+':'+key)+r':end -->', re.S)


def update_document(text, name, sections):
    """Replace only owned blocks; preserve v1 failure prose and other agents."""
    for key, body in sections:
        pattern = _pattern(key)
        block = _block(key, body)
        count = len(pattern.findall(text))
        if count > 1:
            raise ValueError(f'{name}: duplicate {key} generated blocks')
        if count:
            text = pattern.sub(lambda _: block, text)
        elif name.startswith('README'):
            anchor = '<!-- joint-risk-rollout:end -->'
            if text.count(anchor) != 1:
                raise ValueError(f'{name}: expected one preserved v1 evidence anchor')
            text = text.replace(anchor, anchor+'\n\n'+block, 1)
        else:
            anchor = '## English\n' if key == 'en' else '## 简体中文\n'
            if text.count(anchor) != 1:
                raise ValueError(f'{name}: missing unique language section')
            text = text.replace(anchor, anchor+'\n'+block+'\n', 1)
    return text


def sync_documents(root=ROOT):
    root = Path(root)
    sections = rendered_sections(_read(root, DIAGNOSIS), _read(root, TRAJECTORY))
    for name, blocks in sections.items():
        path = root/name
        old = path.read_text(encoding='utf-8')
        updated = update_document(old, name, blocks)
        if old != updated:
            path.write_text(updated, encoding='utf-8')


def check_generated_sections(root=ROOT):
    """Read-only full-block/registration check; return [] on success (16 API)."""
    root = Path(root)
    errors = []
    try:
        trajectory = _read(root, TRAJECTORY)
        expected = rendered_sections(_read(root, DIAGNOSIS), trajectory)
        for name, sections in expected.items():
            text = (root/name).read_text(encoding='utf-8')
            for key, body in sections:
                if _pattern(key).findall(text) != [_block(key, body)]:
                    errors.append(f'{name}: stale/missing/duplicate {MARKER}:{key} block')
        claims = _read(root, 'docs/claims.json')['claims']
        for definition in claim_definitions(trajectory):
            found = [c for c in claims if c['id'] == definition['id']]
            if len(found) != 1 or any(found[0].get(k) != v for k, v in definition.items()):
                errors.append(f"claims: missing/stale/duplicate source definition {definition['id']}")
    except (KeyError, ValueError, OSError, TypeError) as exc:
        errors.append(f'{type(exc).__name__}: {exc}')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check complete generated blocks without writes')
    args = parser.parse_args()
    if not args.check:
        # Refuse to touch any document until both real final inputs validate.
        _validate(_read(ROOT, DIAGNOSIS), _read(ROOT, TRAJECTORY))
        spec = importlib.util.spec_from_file_location('reference_docs', ROOT/'scripts/23_sync_reference_docs.py')
        reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reference)
        reference.main()  # registers sources, emits CLAIMS, and calls sync_documents
    errors = check_generated_sections()
    for error in errors:
        print(error)
    print('Trajectory summaries: '+('FAIL' if errors else 'PASS'))
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()
