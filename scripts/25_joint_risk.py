"""Pre-registered one-state joint-action risk calibration; no deployment change."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from jev_tune.decision import load_backend
from jev_tune.decode import apply_step, decide
from jev_tune.metrics import cost_from_metrics
from jev_tune.plants import TRAIN_FAMILIES, sample_plants, simulate, ultimate_gain
from jev_tune.primitives import calibrate_temperature, fit_split_conformal
from jev_tune.risk import (JointRiskModel, joint_acceptance, paired_cost_labels,
                           risk_features, risk_report, select_joint_gains)
from jev_tune.state import build_state
from _experiment_protocol import manifest, sha256

SPLITS = {'train':72601,'temperature_fit':72602,'cp_fit':72603,'empirical_eval':72604}


def fixed_protocol(models):
    cal = json.loads((Path(models)/'calibration.json').read_text(encoding='utf-8'))
    return {
        'protocol_version':1,'name':'joint_action_risk_initial_state_v1',
        'n_per_split':512,'split_seeds':SPLITS,'families':list(TRAIN_FAMILIES),
        'sampling':'IID uniform family mixture; one initial analytic-ZN state per independent plant',
        'label':{'noninferior':0,'harmful':1,'rule':'J_proposal <= J_current', 'tolerance':0.0},
        'proposal':{'checkpoint_sha256':sha256(Path(models)/'jev_head.pt'),
            'choice_temperature':cal['choice_temperature'],'expectation':True,'shrinkage':1.0,
            'per_axis_conformal':False,'pmax_abstention':False,
            'gain_bounds':[1e-4,1e3],'action':'complete three-axis proposal, after production gain bounds'},
        'features':'20 state + 3 complete applied log10 steps + 21 temperature-scaled choice probabilities',
        'risk_model':{'standard_scaler_fit':'train only','classifier':'LogisticRegression',
            'C':1.0,'penalty':'l2','solver':'lbfgs','max_iter':2000,'tol':1e-4,
            'class_weight':None,'random_state':72601},
        'risk_temperature':{'fit_split':'temperature_fit','method':'existing calibrate_temperature NLL'},
        'conformal':{'fit_split':'cp_fit','alpha':0.10,'score':'1-p(actual paired-cost label)',
            'rank':'ceil((n+1)*(1-alpha))','accept':'set exactly {noninferior}',
            'otherwise':'hold complete current gains; no per-axis clipping'},
        'evaluation':{'split':'empirical_eval','no_parameter_selection':True,
            'measure_every_candidate':True,'expected_total_simulated_plant_runs':4096},
    }


def independent_plants(n,seed):
    rng = np.random.default_rng(seed)
    family = rng.choice(np.asarray(TRAIN_FAMILIES),size=n)
    return sample_plants(n,families=family.tolist(),seed=int(rng.integers(0,2**31-1)))


def collect_split(backend,n,seed):
    """Two actual plant-runs per independent initial state, including rejects."""
    plants = independent_plants(n,seed)
    ku,tu = ultimate_gain(plants)
    if not np.isfinite(ku).all() or not np.isfinite(tu).all() or (ku<=0).any() or (tu<=0).any():
        raise RuntimeError('pre-registered initial ZN population has invalid analytic priors')
    gzn = np.column_stack([.6*ku,1.2*ku/tu,.075*ku*tu])
    current = np.clip(gzn,1e-4,1e3)
    before = simulate(plants,current)
    j0 = cost_from_metrics(before['metrics'],y_curve=before['y_curve'])
    state,curves = build_state(before['metrics'],before['y_curve'],before['u_curve'],
                              current,gzn,ku,tu,cost=j0)
    answer = backend.answer(state,curves)
    decision = decide(answer,backend.space,use_expectation=True,shrinkage=1.,
                      abstain=None,conformal=None)
    proposed = apply_step(current,decision.step)
    actual_step = np.log10(proposed/current)
    probabilities = np.stack([c.probs for c in answer.choice],axis=1)
    after = simulate(plants,proposed)
    j1 = cost_from_metrics(after['metrics'],y_curve=after['y_curve'])
    arrays = {'plant_identity':plants.noise_seed,'state_features':state,'curves':curves,
        'current_gains':current,'proposed_gains':proposed,'commanded_step':decision.step,
        'applied_step':actual_step,'choice_probabilities':probabilities,
        'risk_features':risk_features(state,actual_step,probabilities),
        'current_cost':j0,'proposed_cost':j1,'labels':paired_cost_labels(j0,j1)}
    digest = hashlib.sha256()
    for name,x in sorted(arrays.items()):
        digest.update(name.encode());digest.update(str(x.dtype).encode())
        digest.update(str(x.shape).encode());digest.update(np.ascontiguousarray(x).tobytes())
    return arrays,{'seed':seed,'n_plants':n,'n_states':n,'one_state_per_plant':True,
        'array_sha256':digest.hexdigest(),'simulation_counts':{'current':n,'proposal':n,'total':2*n},
        'label_counts':{'noninferior':int((j1<=j0).sum()),'harmful':int((j1>j0).sum())},
        'family_counts':{str(f):plants.family.count(f) for f in sorted(set(plants.family))}}


def _doc(p):
    r=p['evaluation']; c=p['conformal']; md=p['risk_model']; n=r['n']
    lines=['# Joint-action risk: one initial-state research experiment','',
           '> [English](#english) · [简体中文](#简体中文)','']
    for zh in (False,True):
        lines += ['## 简体中文' if zh else '## English','',
          ('预先固定四个独立划分、每个512株对象、零容差标签和alpha=0.10；没有根据评估结果选参。完整三轴Temp Only提案保持不变，风险头只决定整组执行或整组保持。此研究不改变Python/C/MATLAB默认部署。'
           if zh else 'Four independent 512-plant splits, zero-tolerance labels and alpha=0.10 were fixed before collection. No parameter is selected from evaluation outcomes. The complete Temp Only proposal is unchanged; the risk head admits or holds the whole vector. This research does not change default Python/C/MATLAB deployment.'), '',
          '`train=72601; temperature_fit=72602; cp_fit=72603; empirical_eval=72604`','',
          ('目标是完整动作的实测J_proposal<=J_current，含等号，容差为0。44维特征为20个状态特征、3个实际联合步长、21个choice概率；StandardScaler和固定LogisticRegression只用train，温度只用temperature_fit，qhat只用cp_fit。'
           if zh else 'The target is measured J_proposal<=J_current for the full action, including equality, with tolerance zero. The 44 inputs are 20 state features, 3 applied joint steps and 21 choice probabilities. StandardScaler and fixed LogisticRegression use train only; temperature uses temperature_fit and qhat uses cp_fit.'), '',
          f"{'风险温度' if zh else 'Risk temperature'}={md['temperature']:.6f}; alpha={c['alpha']}; n_cal={c['n_calibration']}; rank={c['quantile_rank']}; qhat={c['qhat']:.6f}.",'',
          '| 指标 | 数值 |' if zh else '| metric | value |','| :--- | ---: |',
          f"| {'经验标签集合覆盖率' if zh else 'empirical label-set coverage'} | {r['label_coverage']:.6f} |",
          f"| {'平均集合大小' if zh else 'mean set size'} | {r['mean_set_size']:.6f} |",
          f"| {'获准数 / 全部' if zh else 'accepted / all'} | {r['n_accepted']} / {n} |",
          f"| {'执行率' if zh else 'execution rate'} | {r['execution_rate']:.6f} |",
          f"| {'有害执行数 / 全部' if zh else 'harmful executions / all'} | {r['harmful_execution_count']} / {n} |",
          f"| {'无条件有害执行率' if zh else 'unconditional harmful execution rate'} | {r['unconditional_harmful_execution_rate']:.6f} |",
          f"| {'获准动作中的条件有害率' if zh else 'conditional harmful rate among accepted'} | {r['conditional_harmful_rate'] if r['conditional_harmful_rate'] is not None else 'n/a'} |",
          f"| {'漏覆盖数' if zh else 'miscoverage count'} | {r['miscoverage_count']} |",
          f"| {'空集数' if zh else 'empty sets'} | {r['empty_set_count']} |",'',
          '| 同批对象实测代价 | 均值 J | 中位 J | p90 J |' if zh else '| cost measured on the same plants | mean J | median J | p90 J |',
          '| :--- | ---: | ---: | ---: |']
        for key in ('current_cost','always_propose_cost','selected_cost'):
            cost=r[key]
            lines.append(f"| {key} | {cost['mean']:.6f} | {cost['median']:.6f} | {cost['p90']:.6f} |")
        d=r['selected_minus_current']
        v=r['selected_vs_always_propose']
        lines += ['',(f"选择后相对当前代价的配对差：均值{d['mean']:+.6f}，中位数{d['median']:+.6f}；改善/不变/恶化={d['improved_count']}/{d['unchanged_count']}/{d['worse_count']}。"
          if zh else f"Selected minus current: paired mean {d['mean']:+.6f}; paired median {d['median']:+.6f}; improved/unchanged/worse = {d['improved_count']}/{d['unchanged_count']}/{d['worse_count']}."),'',
          ((f"相对总是执行完整提案，selected的均值J差{v['mean_J_difference']:+.6f}、中位J差{v['median_J_difference']:+.6f}、p90 J差{v['p90_J_difference']:+.6f}。这些是各汇总统计量之差；并非所有指标都改善。拒绝的动作中，{r['rejected_harmful_count']}个实际有害，{r['rejected_noninferior_count']}个实际非劣。")
           if zh else f"Selected minus always-propose summary differences: mean J {v['mean_J_difference']:+.6f}, median J {v['median_J_difference']:+.6f}, p90 J {v['p90_J_difference']:+.6f}. These are differences of the respective summary statistics; not every metric improves. The gate rejects {r['rejected_harmful_count']} actually harmful and {r['rejected_noninferior_count']} actually noninferior proposals."), '',
          ('只有集合恰为{非劣}才放行，空集、{有害}、{非劣,有害}都整组保持。因此“执行且有害”逐点包含于“真实标签未被集合覆盖”，本次集合包含关系已检查。交换性成立且模型/温度独立固定时，Split CP控制单次初态无条件有害执行概率；它不保证获准动作中的有害比例<=10%，不保证每个有限评估样本达到90%覆盖，也不保证多步闭环、域外、噪声变化或真机安全。'
           if zh else 'Only the exact set {noninferior} is admitted. Empty, {harmful}, and {noninferior,harmful} sets hold the whole vector. Thus harmful execution is pointwise a subset of label miscoverage; this inclusion is checked. Under exchangeability with model and temperature independently fixed, split CP bounds the one-initial-state unconditional probability of harmful execution. It does not bound the conditional harmful fraction among admitted actions by 10%, require every finite evaluation to reach 90% coverage, or ensure multi-step, shifted-domain, changed-noise or hardware safety.'), '',
          (f"采集实际仿真{p['simulation_counts']['total']}次：每个划分512次当前测量+512次完整提案测量，共四个划分。离线为所有候选取得真实标签，包含随后会被拒绝的提案；这些成本均计入。评估selected_cost在同一对实测代价中选择，不是另做一遍仿真；不使用min(Jcurrent,Jproposal)隐藏有害执行，也不据此声称部署效率。"
           if zh else f"Collection used {p['simulation_counts']['total']} actual plant-runs: 512 current and 512 full-proposal measurements in each of four splits. Offline labels include candidates the gate subsequently rejects, and all costs are counted. selected_cost selects from the same measured pair without an extra simulation; it does not take min(Jcurrent,Jproposal) to hide harmful execution or establish deployment efficiency."), '',
          ('原始配对代价、完整增益、集合及接纳决策位于`research/results/joint_risk.json`；协议位于`research/protocols/joint_risk_v1.json`。模型、数据及源代码hash记录于结果manifest。'
           if zh else 'Raw paired costs, complete gains, sets and admission decisions are in `research/results/joint_risk.json`; the fixed protocol is `research/protocols/joint_risk_v1.json`. Result provenance includes model, data and source hashes.'), '',
          '`python scripts/25_joint_risk.py --register-only` → `python scripts/25_joint_risk.py`','',
          '`python scripts/25_joint_risk.py --render-only --check`','']
    return '\n'.join(lines)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--models',default='models')
    ap.add_argument('--protocol',default='research/protocols/joint_risk_v1.json')
    ap.add_argument('--out',default='research/results/joint_risk.json')
    ap.add_argument('--doc',default='docs/JOINT_RISK.md')
    ap.add_argument('--data-dir',default='data/joint_risk')
    ap.add_argument('--register-only',action='store_true')
    ap.add_argument('--render-only',action='store_true')
    ap.add_argument('--check',action='store_true')
    args=ap.parse_args()
    if args.render_only:
        content=_doc(json.loads(Path(args.out).read_text(encoding='utf-8')))
        if args.check:
            if Path(args.doc).read_text(encoding='utf-8') != content:
                raise SystemExit('JOINT_RISK.md differs from its JSON render')
            print('[joint-risk] document matches JSON')
        else:
            Path(args.doc).write_text(content,encoding='utf-8')
        return
    path=Path(args.protocol); expected=fixed_protocol(args.models)
    if args.register_only:
        if path.exists():
            old=json.loads(path.read_text(encoding='utf-8'))
            if old['specification'] != expected:
                raise SystemExit('existing fixed protocol differs; refusing replacement')
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({'registered_utc':datetime.now(timezone.utc).isoformat(),
                'specification':expected},indent=2),encoding='utf-8')
        print(f'[joint-risk] fixed protocol saved: {path}; no data collected')
        return
    if not path.exists():
        raise SystemExit('register the fixed protocol before running the experiment')
    protocol=json.loads(path.read_text(encoding='utf-8'))
    if protocol['specification'] != expected:
        raise SystemExit('current proposal/configuration differs from the registered protocol')
    provenance=manifest(args,files=[path,Path(args.models)/'jev_head.pt',Path(args.models)/'calibration.json'])
    backend=load_backend(args.models); datasets={}; metadata={}
    Path(args.data_dir).mkdir(parents=True,exist_ok=True)
    for name,seed in SPLITS.items():
        start=time.perf_counter(); arrays,info=collect_split(backend,expected['n_per_split'],seed)
        for previous in datasets.values():
            if np.intersect1d(previous['plant_identity'],arrays['plant_identity']).size:
                raise RuntimeError('independent splits share a plant identity')
        file=Path(args.data_dir)/f'{name}.npz'
        np.savez_compressed(file,**arrays)
        info.update(data_file=str(file),file_sha256=sha256(file),wall_s=time.perf_counter()-start)
        datasets[name]=arrays;metadata[name]=info
        print(f"[joint-risk] {name}: {info['label_counts']}, actual sims={info['simulation_counts']['total']}",flush=True)
    model=JointRiskModel.fit(datasets['train']['risk_features'],datasets['train']['labels'])
    td=datasets['temperature_fit']
    model.temperature=calibrate_temperature(model.logits(td['risk_features']),td['labels'])
    cd=datasets['cp_fit']
    cp=fit_split_conformal(model.probabilities(cd['risk_features']),cd['labels'],alpha=.10)
    ed=datasets['empirical_eval']; probs=model.probabilities(ed['risk_features'])
    sets=cp.prediction_set(probs);accepted=joint_acceptance(sets)
    chosen_gains=select_joint_gains(ed['current_gains'],ed['proposed_gains'],sets)
    report=risk_report(probs,ed['labels'],sets,ed['current_cost'],ed['proposed_cost'])
    payload={'protocol':protocol,'protocol_sha256':sha256(path),
        'risk_model':model.as_dict(),'conformal':{'alpha':cp.alpha,'n_calibration':cp.n_calibration,
            'quantile_rank':cp.quantile_rank,'qhat':float(cp.qhat_per_axis),
            'cp_fit_diagnostics':cp.evaluate(model.probabilities(cd['risk_features']),cd['labels'])},
        'evaluation':report,'splits':metadata,
        'simulation_counts':{'total':sum(m['simulation_counts']['total'] for m in metadata.values()),
            'evaluation_current':len(ed['labels']),'evaluation_proposal':len(ed['labels']),
            'evaluation_selection_extra':0},
        'per_plant':{key:ed[key].tolist() for key in ['plant_identity','current_gains','proposed_gains','applied_step','current_cost','proposed_cost','labels']},
        'manifest':provenance,
        'scope':'one independent initial state; full fixed joint action; research only, not deployed'}
    payload['per_plant'].update(probabilities=probs.tolist(),prediction_set=sets.tolist(),
        accepted=accepted.tolist(),selected_gains=chosen_gains.tolist(),
        selected_cost=np.where(accepted,ed['proposed_cost'],ed['current_cost']).tolist())
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out).write_text(json.dumps(payload,indent=2),encoding='utf-8')
    Path(args.doc).write_text(_doc(payload),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':
    main()
