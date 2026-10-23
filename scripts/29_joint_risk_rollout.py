"""Frozen fresh-cohort calibration and a held-out finite-horizon control study."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import time

import numpy as np

from _experiment_protocol import manifest, sha256
from jev_tune.risk import JointRiskModel
from jev_tune.sequential_risk import stage_calibration, summarize_rollout, acceptance_checks

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT/'research/protocols/joint_risk_rollout_v1.json'
RESULT = ROOT/'research/results/joint_risk_rollout.json'
RAW = ROOT/'research/results/joint_risk_rollout_raw.json.gz'
DOC = ROOT/'docs/JOINT_RISK_ROLLOUT.md'


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def fixed_specification():
    initial = json.loads((ROOT/'research/results/joint_risk.json').read_text(encoding='utf-8'))
    return {
        'name':'joint_action_risk_fresh_cohort_rollout_v1', 'version':1,
        'frozen_risk_model_sha256':canonical_hash(initial['risk_model']),
        'frozen_proposal':initial['protocol']['specification']['proposal'],
        'calibration_file_sha256':sha256(ROOT/'models/calibration.json'),
        'horizon':20, 'trajectory_alpha':.10, 'alpha_per_stage':[.005]*20,
        'calibration':{'n_initial_per_stage':512,'seeds':list(range(82701,82721)),
            'sampling':'Fresh independent plant cohort for each stage, under frozen earlier thresholds; only reached changed proposals enter that stage calibration.',
            'score':'1-p(actual zero-tolerance paired-cost label)',
            'rank':'ceil((n_reached+1)*(1-alpha_t))',
            'insufficient_sample':'q=1 (bounded-score infinity equivalent); both labels; hold',
            'model_temperature':'Reuse frozen v1 model and temperature; no fitting or outcome-based selection.'},
        'evaluation':{'n_plants':1024,'seed':82801,'paired':['monitor','gated'],
            'fixed_sample':True,'peek_or_optional_stopping':False,
            'diagnostic_rejected_measurement':True},
        'scope':{'families':initial['protocol']['specification']['families'],
            'family_sampling':'IID uniform mixture', 'initial_gains':'analytic ZN clipped to [1e-4,1e3]',
            'objective':'step', 'horizon_seconds':10.,'reference':1.,'measurement_noise_sigma':0.,
            'candidate':'complete bounded Temp Only vector, expectation=true, shrinkage=1',
            'unchanged_action':'stop without simulation',
            'risk_rejection':'stop without operating simulation; optional diagnostic cannot affect state or best',
            'safety_veto':'stop on the existing divergence/cost safety predicate; no recovery or rollback actions',
            'return':'best actually executed measurement including initial gains',
            'not_covered':['initial measurement safety','prior identification','rollback/recovery actions',
                           'shifted domains','physical safety','MATLAB/C deployments']},
        'harm_definitions':{'harmful':'J_after > J_before; zero tolerance',
            'harmful_gt_2pct':'J_after > 1.02*J_before; explicitly named legacy secondary metric',
            'trajectory_event':'at least one actually executed changed proposal is harmful',
            'coverage_denominator':'reached changed proposals with measured labels, including rejected diagnostics; never padded stops'},
        'accounting':{'operating':'initial + executed',
            'diagnostic':'rejected + calibration target',
            'total':'operating + diagnostic; all real plant-runs counted once',
            'reuse':'no repeated identical parameter simulation in deterministic rollout'},
        'acceptance':{'confidence_one_sided':.95,'trajectory_risk_upper_max':.10,
            'first_stage_execution_lower_min':.50,
            'first_stage_denominator':'all 1024 test plants, including pre-proposal stops',
            'empirical_mean_cost':'gated <= matched monitor, zero slack',
            'empirical_p90_cost':'gated <= matched monitor, zero slack',
            'operating_simulations':'gated <= matched monitor', 'integrity_required':True,
            'interpretation':'Separate one-sided 95% binomial bounds; mean/p90 are empirical engineering gates, not population noninferiority theorems.',
            'failure':'remain research-only; no alpha, threshold or model adjustment from test outcomes'},
    }


def load_frozen_model():
    d=json.loads((ROOT/'research/results/joint_risk.json').read_text(encoding='utf-8'))['risk_model']
    return JointRiskModel(np.array(d['mean']),np.array(d['scale']),np.array(d['coefficient']),d['intercept'],d['temperature'])


def protocol_matches(registered, expected):
    """Git may convert text EOLs; permit that conversion, no content changes."""
    registered,expected=dict(registered),dict(expected)
    recorded_hash=registered.pop('calibration_file_sha256')
    expected.pop('calibration_file_sha256')
    data=(ROOT/'models/calibration.json').read_bytes().replace(b'\r\n',b'\n')
    candidates={hashlib.sha256(data).hexdigest(),hashlib.sha256(data.replace(b'\n',b'\r\n')).hexdigest()}
    return recorded_hash in candidates and registered==expected


def _doc(p):
    spec=p['protocol']['specification']; ev=p['evaluation']; acc=p['acceptance']
    lines=['# Joint-action risk in multi-round control / 多轮调参联合动作风险','',
           '[English](#english) · [简体中文](#简体中文)','']
    for zh in (False,True):
        lines += ['## 简体中文' if zh else '## English','',
            ('本页完全由冻结协议和真实实验JSON生成。既有风险模型、温度和提案策略未调参；先冻结并提交协议，再采集新的逐步校准批次，最后运行一次固定样本评估。'
             if zh else 'Generated from the frozen protocol and actual experiment JSON. Existing risk weights, temperature and proposal policy were not tuned. The protocol was frozen and committed before fresh stage calibration, followed by one fixed-size evaluation.'),'',
            (f"最多{spec['horizon']}次联合提案，整段预算{spec['trajectory_alpha']:.2f}，每步alpha={spec['alpha_per_stage'][0]:.3f}。每步从{spec['calibration']['n_initial_per_stage']}个新对象开始，只有实际到达该步且产生不同增益的对象进入校准。最终同批{spec['evaluation']['n_plants']}个独立新对象分别真实运行monitor与gated。"
             if zh else f"At most {spec['horizon']} joint proposals; trajectory budget {spec['trajectory_alpha']:.2f}; alpha per stage {spec['alpha_per_stage'][0]:.3f}. Each stage starts with {spec['calibration']['n_initial_per_stage']} fresh plants; only reached changed proposals enter calibration. Both monitor and gated are actually rolled out on the same {spec['evaluation']['n_plants']} independent test plants."),'',
            ('两组均为限定的研究控制器：六族均匀混合、解析ZN初态、10秒无测量噪声阶跃；安全门触发或动作不变时停止，不执行额外回滚。monitor是相同研究控制器的无风险门控对照，不等同于生产回滚控制器。'
             if zh else 'Both arms are scoped research controllers: uniform six-family mixture, analytic ZN start, a 10-second noiseless step response. A safety veto or unchanged action stops the plant; no recovery action is executed. Monitor is the matched ungated research controller, not the production rollback controller.'),'',
            '| 指标 | monitor | gated |' if zh else '| metric | monitor | gated |','| :--- | ---: | ---: |']
        fields=[('整轨迹有害对象数' if zh else 'plants with any harmful execution',lambda r:r['trajectory_harm']['events']),
                ('整轨迹有害率单侧95%上界' if zh else 'trajectory harm one-sided 95% upper bound',lambda r:f"{r['trajectory_harm']['upper']:.6f}"),
                ('第一步执行率单侧95%下界' if zh else 'first-stage execution one-sided 95% lower bound',lambda r:f"{r['first_stage_execution']['lower']:.6f}"),
                ('实际执行提案数' if zh else 'executed proposals',lambda r:r['n_executed']),
                ('有害执行数（零容差）' if zh else 'harmful executions (zero tolerance)',lambda r:r['n_harmful']),
                ('有害执行数（旧口径>2%）' if zh else 'harmful executions (legacy >2%)',lambda r:r['n_harmful_gt_2pct'])]
        for key in ('mean','median','p90'):
            fields.append((f'final J {key}',lambda r,key=key:f"{r['final_cost'][key]:.6f}"))
        for key in ('operating','diagnostic_rejected','total'):
            fields.append((f'simulations: {key}',lambda r,key=key:r['simulation_counts'][key]))
        for name,fn in fields:
            lines.append(f"| {name} | {fn(ev['monitor'])} | {fn(ev['gated'])} |")
        lines += ['',('零容差轨迹事件表示探索期间至少一次J上升；两组最终均返回各自已执行历史的实测最优参数。该事件率不是失稳率，也不是最终参数恶化率。monitor中的影子集合覆盖仅为诊断，其后续状态分布不同于门控前缀，不能将该数字当作已证明的monitor轨迹覆盖。'
            if zh else 'A zero-tolerance trajectory event means at least one cost increase during exploration. Both arms return the measured best parameters from their executed history. This event rate is neither an instability rate nor final-parameter degradation. Shadow-set coverage on monitor is diagnostic only: its later states differ from the gated prefix, so it is not a certified coverage claim for monitor trajectories.')]
        lines += ['',('| 步 | 到达样本 n | 秩 | qhat | 全集合回退 |' if zh else '| stage | reached n | rank | qhat | full-set fallback |'),
                  '| ---: | ---: | ---: | ---: | :--- |']
        for s in p['stages']:
            lines.append(f"| {s['stage']+1} | {s['n_reached']} | {s['quantile_rank']} | {s['qhat']:.6f} | {s['all_labels_fallback']} |")
        lines += ['',f"{'验收' if zh else 'Acceptance'}: **{'PASS' if acc['passed'] else 'FAIL'}**.",
            f"{'未通过项' if zh else 'Failed criteria'}: {', '.join(acc['failed']) or 'none'}.",
            f"{'启用状态' if zh else 'Enablement'}: `{p['deployment']['status']}`.",'',
            ('只有每一步在冻结前缀下的校准样本与未来到达样本交换性成立，才可逐步使用CP边际保证并由联合界得到有害执行概率<=sum(alpha_t)。同一轨迹内各步不要求独立；每步使用新对象批次，不能复用旧未门控轨迹。初始测量、回滚、域外和物理安全不在此界内。有限样本秩超过n或n=0时q=1保留两标签并Hold，不降低覆盖目标。'
             if zh else 'Stagewise CP and the union bound give harmful execution probability <=sum(alpha_t) only when stage calibration and future reached samples are exchangeable under the frozen prefix. Steps within one trajectory need not be independent; each calibration stage uses a new cohort, not reused ungated trajectories. Initial measurements, recovery, domain shift and physical safety are outside this bound. If the finite-sample rank exceeds n, including n=0, q=1 retains both labels and holds without relaxing coverage.'),'',
            ('单侧二项上界是对最终固定策略的独立验收，不等同于CP对校准随机性取平均的边际保证。两个95%界分别解释，不称联合95%。代价均值/p90是本次测试的经验门槛。失败不得通过重新选alpha、样本数、阈值或温度补救；没有反复查看后过线即停。'
             if zh else 'The one-sided binomial upper bound independently audits the final fixed policy; it differs from CP marginal coverage averaged over calibration randomness. The two 95% bounds are separate, not joint 95% confidence. Mean/p90 criteria are empirical test gates. Failure is not repaired by selecting new alpha, sample size, thresholds or temperature from evaluation outcomes; there is no optional stopping.'),'',
            (f"实际总仿真{p['simulation_counts']['total']}次，其中逐步校准{p['simulation_counts']['calibration_total']}次、两组最终评估{p['simulation_counts']['evaluation_total']}次。被拒绝提案的诊断测量不能更新状态、历史最优或操作预算，但计入总成本。完整轨迹保存在{p['raw_file']}，SHA-256 {p['raw_sha256']}。"
             if zh else f"Actual plant-runs total {p['simulation_counts']['total']}: stage calibration {p['simulation_counts']['calibration_total']}, final evaluation arms {p['simulation_counts']['evaluation_total']}. Rejected diagnostic measurements cannot update state, best gains or operating budget, but are charged to total cost. Full traces: {p['raw_file']}, SHA-256 {p['raw_sha256']}."),'',
            ('首次采集使用下列命令；已发布产物的完整确定性复现使用`--reproduce`，逐字节核对原始轨迹且不覆盖原始验收。'
             if zh else 'Use the commands below for first collection. For a full deterministic reproduction of published artifacts, add `--reproduce`; it verifies raw traces byte-for-byte without replacing the original acceptance.'),'',
            '`python scripts/29_joint_risk_rollout.py --register-only` → `python scripts/29_joint_risk_rollout.py`','',
            '`python scripts/29_joint_risk_rollout.py --render-only --check`','']
    return '\n'.join(lines)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--register-only',action='store_true')
    ap.add_argument('--render-only',action='store_true')
    ap.add_argument('--check',action='store_true')
    ap.add_argument('--reproduce',action='store_true',help='rerun fixed protocol and compare existing raw traces without replacing evidence')
    args=ap.parse_args()
    if args.render_only:
        text=_doc(json.loads(RESULT.read_text(encoding='utf-8')))
        if args.check:
            if DOC.read_text(encoding='utf-8') != text:
                raise SystemExit('JOINT_RISK_ROLLOUT.md differs from JSON')
        else:
            DOC.write_text(text,encoding='utf-8')
        return
    specification=fixed_specification()
    if args.register_only:
        if PROTOCOL.exists():
            if not protocol_matches(json.loads(PROTOCOL.read_text(encoding='utf-8'))['specification'],specification):
                raise SystemExit('Refusing to replace frozen protocol')
        else:
            PROTOCOL.write_text(json.dumps({'registered_utc':datetime.now(timezone.utc).isoformat(),
                'specification':specification},indent=2)+'\n',encoding='utf-8')
        print(f'Frozen {PROTOCOL}; no experimental data collected')
        return
    if not PROTOCOL.exists():
        raise SystemExit('Register protocol before collecting any study data')
    protocol=json.loads(PROTOCOL.read_text(encoding='utf-8'))
    if not protocol_matches(protocol['specification'],specification):
        raise SystemExit('Code/model configuration differs from frozen protocol')
    original=json.loads(RESULT.read_text(encoding='utf-8')) if args.reproduce and RESULT.exists() else None
    if args.reproduce and (original is None or not RAW.exists()):
        raise SystemExit('Reproduction requires the original result and raw trace')
    if not args.reproduce and (RESULT.exists() or RAW.exists()):
        raise SystemExit('Study output already exists. Preserve it; no outcome-driven reruns.')
    from jev_tune.decision import load_backend
    from jev_tune.joint_rollout import run_joint_rollout
    initial_spec=importlib.util.spec_from_file_location('initial_joint_risk',ROOT/'scripts/25_joint_risk.py')
    initial_module=importlib.util.module_from_spec(initial_spec);initial_spec.loader.exec_module(initial_module)
    backend=load_backend(ROOT/'models');model=load_frozen_model()
    qhats=[];stages=[];raw={'calibration':[],'evaluation':{}}
    start=time.perf_counter()
    for t,seed in enumerate(specification['calibration']['seeds']):
        plants=initial_module.independent_plants(specification['calibration']['n_initial_per_stage'],seed)
        result=run_joint_rollout(backend,model,plants,qhats,horizon=20,mode='collect',collect_step=t,diagnostic=False)
        data=result['collected'];x=np.asarray(data['features'],float).reshape(-1,44)
        probabilities=model.probabilities(x) if len(x) else np.empty((0,2))
        stage=stage_calibration(probabilities,data['labels'],specification['alpha_per_stage'][t])
        stage.update(stage=t,seed=seed,n_initial=plants.n,prefix_qhats=list(qhats),
            collected_sha256=canonical_hash(data),simulation_counts=result['simulation_counts'])
        qhats.append(stage['qhat']);stages.append(stage);raw['calibration'].append(result)
        print(f"stage {t+1:02}: reached={stage['n_reached']} rank={stage['quantile_rank']} q={stage['qhat']:.8f} total_sim={result['simulation_counts']['total']}",flush=True)
    plants=initial_module.independent_plants(specification['evaluation']['n_plants'],specification['evaluation']['seed'])
    for mode in ('monitor','gated'):
        raw['evaluation'][mode]=run_joint_rollout(backend,model,plants,qhats,horizon=20,mode=mode,diagnostic=True)
        print(f"evaluation {mode}: {raw['evaluation'][mode]['simulation_counts']}",flush=True)
    evaluation={mode:summarize_rollout(r) for mode,r in raw['evaluation'].items()}
    integrity=check_integrity(raw,qhats,stages)
    acceptance=acceptance_checks(evaluation['monitor'],evaluation['gated'],all(integrity.values()))
    # Enablement applies only to this exact scoped research runner, never generic runtimes.
    deployment={'enabled':acceptance['passed'],
        'status':'validated_research_scope_only' if acceptance['passed'] else 'research_only',
        'scope':specification['scope'],'generic_python_c_matlab_enabled':False,
        'failed_criteria':acceptance['failed']}
    raw_bytes=json.dumps(raw,separators=(',',':'),allow_nan=False).encode()
    if args.reproduce:
        if gzip.decompress(RAW.read_bytes()) != raw_bytes or original['qhats'] != qhats or original['acceptance'] != acceptance:
            raise SystemExit('Fixed-protocol reproduction differs; original evidence preserved')
        print('Full fixed-protocol reproduction matches the original raw traces and acceptance; original evidence preserved.',flush=True)
        return
    RAW.write_bytes(gzip.compress(raw_bytes,mtime=0))
    calibration_total=sum(r['simulation_counts']['total'] for r in raw['calibration'])
    evaluation_total=sum(r['simulation_counts']['total'] for r in raw['evaluation'].values())
    payload={'protocol':protocol,'protocol_sha256':sha256(PROTOCOL),
        'risk_model_sha256':specification['frozen_risk_model_sha256'],
        'stages':stages,'qhats':qhats,'union_bound':math.fsum(specification['alpha_per_stage']),
        'evaluation':evaluation,'integrity':integrity,'acceptance':acceptance,'deployment':deployment,
        'raw_file':str(RAW.relative_to(ROOT)).replace('\\','/'),'raw_sha256':sha256(RAW),
        'simulation_counts':{'calibration_total':calibration_total,'evaluation_total':evaluation_total,
                             'total':calibration_total+evaluation_total},
        'elapsed_s':time.perf_counter()-start,
        'manifest':manifest(args,files=[PROTOCOL,'models/jev_head.pt','models/calibration.json','research/results/joint_risk.json'])}
    RESULT.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    DOC.write_text(_doc(payload),encoding='utf-8')
    print(json.dumps({'acceptance':acceptance,'evaluation':evaluation},indent=2),flush=True)


def check_integrity(raw,qhats,stages):
    checks={'actual_simulation_accounting':True,'finite_observations':True,
            'harmful_execution_subset_miscoverage':True,'whole_vector_only':True,
            'no_duplicate_stage_per_plant':True,'frozen_prefix':True}
    all_runs=raw['calibration']+list(raw['evaluation'].values())
    for result in all_runs:
        c=result['simulation_counts']
        checks['actual_simulation_accounting'] &= c['operating']==c['operating_initial']+c['executed'] and c['total']==c['operating']+c['diagnostic_rejected']+c['diagnostic_collected']
        pairs=[]
        for r in result['transitions']:
            pairs.append((r['plant_index'],r['stage']))
            if r['measured']:
                checks['finite_observations'] &= r['observed_finite']
            if r['executed'] and r['prediction_set'] is not None and result['mode']=='gated':
                checks['whole_vector_only'] &= r['prediction_set']==[True,False]
                if r['observed_finite'] and r['cost_after']>r['cost_before']:
                    checks['harmful_execution_subset_miscoverage'] &= not r['prediction_set'][1]
        checks['no_duplicate_stage_per_plant'] &= len(pairs)==len(set(pairs))
    for t,stage in enumerate(stages):
        checks['frozen_prefix'] &= stage['prefix_qhats']==qhats[:t]
    return {k:bool(v) for k,v in checks.items()}


if __name__=='__main__':
    main()
