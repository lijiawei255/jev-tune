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


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_model(d):
    from jev_tune.risk import JointRiskModel
    return JointRiskModel(np.array(d['mean']), np.array(d['scale']), np.array(d['coefficient']),
                          d['intercept'], d['temperature'])


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    temporary.replace(path)


def probability_diagnostics(model, data):
    from sklearn.metrics import roc_auc_score
    x = np.asarray(data['features'], float).reshape(-1, 44)
    y = np.asarray(data['labels'], int)
    if not len(y):
        return {'n_rows': 0, 'harmful': 0, 'auroc': None, 'brier': None, 'nll': None}
    p = model.probabilities(x)
    return {'n_rows': len(y), 'harmful': int(y.sum()),
            'auroc': float(roc_auc_score(y, p[:,1])) if len(np.unique(y)) == 2 else None,
            'brier': float(np.mean((p[:,1]-y)**2)),
            'nll': float(-np.log(np.maximum(p[np.arange(len(y)),y], 1e-300)).mean())}


def _doc(p):
    spec = p['protocol']['specification']
    # Documentation only: the executed runner source is separately preserved.
    # Do not turn frozen numerical acceptance into an implementation guarantee.
    docs_module = _load_script('33_sync_trajectory_docs')
    validity_path = ROOT / 'research/results/trajectory_risk_validity.json'
    validity = json.loads(validity_path.read_text(encoding='utf-8')) if validity_path.is_file() else None
    lines = ['# Trajectory risk and alternative joint actions / 轨迹风险与替代联合动作', '',
             '[English](#english) · [简体中文](#简体中文)', '']
    for zh in (False, True):
        lines += ['## 简体中文' if zh else '## English', '',
            ('协议先于新数据冻结；旧测试仅作诊断，旧失败结果原样保留。新模型、动作尺度、样本量及风险预算均未按评估结果选参。唯一主要候选为trajectory_selected，其余组仅用于解释，不能测试后换组上线。'
             if zh else 'The protocol was frozen before new data. Old tests are retrospective diagnosis only and the old failure is preserved. No model, action scale, sample size or risk budget was selected from evaluation outcomes. The sole primary candidate is trajectory_selected; the other arms cannot be selected for deployment after testing.'), '',
            ('每步先在完整联合动作的固定尺度1、0.5、0.25中，用冻结风险模型选择最小预测有害概率的候选；平局按尺度顺序。然后仅对选中动作构造CP集合，只有{非劣}执行。拒绝即停止，不根据CP集合再挑候选。风险输入的初态prev_dJ置零，提案模型输入不改。'
             if zh else 'At each stage, the frozen risk model first selects the smallest predicted harmful probability among complete joint actions scaled by 1, 0.5 and 0.25, with stable scale-order ties. CP is then applied only to that selected action; only {noninferior} executes. Rejection stops, without choosing another candidate from its CP set. Initial prev_dJ is zeroed only for new risk inputs; proposal inputs are unchanged.'), '',
            ('新旧风险头比较同时改变训练轨迹、数据量、标准化和风险初态特征语义，因此不是单一特征修正的因果实验。固定行为尺度训练分布也不等于在线逐步选尺度分布。'
             if zh else 'The new-versus-old risk comparison changes trajectories, data volume, scaling and initial risk-feature semantics together; it is not a causal isolation of one feature repair. Fixed behavior-scale training is also different from online per-stage scale selection.'), '',
            '| 数据划分 | 独立对象 | 候选标签行 | 有害标签 |' if zh else '| split | independent plants | candidate label rows | harmful labels |',
            '| :--- | ---: | ---: | ---: |']
        for name, d in p['training']['datasets'].items():
            lines.append(f"| {name} | {d['n_plants']} | {d['n_rows']} | {d['harmful']} |")
        lines += ['', ('同一对象的多步/多候选行相关，只用于训练或描述统计，不能当独立校准对象。训练、温度、开发诊断、逐步校准及最终测试对象分离。开发组不参与任何搜索。'
            if zh else 'Rows from multiple stages/candidates of one plant are dependent and used for fitting or descriptive diagnostics, not counted as independent calibration plants. Training, temperature, development audit, stage calibration and final test cohorts are separated. The development audit performs no search.'), '',
            f"{'固定风险温度' if zh else 'Frozen risk temperature'}: {p['risk_model']['temperature']:.6f}.", '',
            '| 组 | 有害轨迹 / 测试数 | 名义风险95%上界 | 名义首步执行95%下界 | mean J | p90 J | 实际运行仿真 | 诊断仿真 |' if zh else '| arm | harmed trajectories / test plants | nominal risk 95% upper | nominal first execution 95% lower | mean J | p90 J | actual operating simulations | diagnostic simulations |',
            '| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for name, r in p['evaluation'].items():
            c = r['simulation_counts']
            lines.append(f"| {name} | {r['trajectory_harm']['events']}/{r['n_plants']} | {r['trajectory_harm']['upper']:.6f} | {r['first_stage_execution']['lower']:.6f} | {r['final_cost']['mean']:.6f} | {r['final_cost']['p90']:.6f} | {c['operating']} | {c['total']-c['operating']} |")
        lines += ['', f"{'主要候选的冻结数值判据' if zh else 'Primary frozen numerical criteria'}: **{'PASS' if p['acceptance']['passed'] else 'FAIL'}**; `{p['deployment']['status']}`.",
            f"{'未通过项' if zh else 'Failed criteria'}: {', '.join(p['acceptance']['failed']) or 'none'}.", '',
            docs_module.validity_note(p, validity, chinese=zh, relative=''), '',
            ('有害仍指一次即时J严格上升，不是最终参数恶化率或失稳率。两组返回各自真实执行历史最优。替代动作改变路径后，旧固定路径冲突的证明不直接适用于新策略；它也不意味着新策略必然通过。'
             if zh else 'Harm remains any strict immediate increase in J, not final-parameter degradation or instability. Each arm returns its actually executed historical best. Alternative actions change the path, so the old fixed-path conflict proof does not directly apply to the new policy; this does not imply that the new policy must pass.'), '',
            '| 组 | 步 | 初始对象 | 到达 / 用于拟合 | 秩 | qhat | 回退原因 |' if zh else '| arm | stage | initial plants | reached / fitted | rank | qhat | fallback reason |',
            '| :--- | ---: | ---: | ---: | ---: | ---: | :--- |']
        for name, arm in p['arms'].items():
            for s in arm['stages']:
                lines.append(f"| {name} | {s['stage']+1} | {s['n_initial']} | {s['n_observed_reached']}/{s['n_reached']} | {s['quantile_rank']} | {s['qhat']:.6f} | {s['fallback_reason'] or '-'} |")
        lines += ['', ('目标到达数为2000，每步最多20000个初始对象。按生成顺序收集，批次超额观测全部计账，仅按预先次序截取。配额不足返回完整集合是额外工程保守规则，与数学秩超过n不同。冻结前缀已有完整集合时后续结构不可达，直接记录零样本；不把一次零到达批次当作不可达证明。'
            if zh else 'The reached target is 2000, with at most 20000 initial plants per stage. Collection follows generation order; excess batch observations are fully charged and truncated only by predetermined order. Quota shortfall returns the full set as an additional engineering rule, distinct from mathematical rank exceeding n. A full set in the frozen prefix makes later stages structurally unreachable, recorded without wasteful simulation; one empty batch alone is not such proof.'), '',
            ('20步总预算0.10、每步alpha=0.005保持不变。CP定理需要逐步校准分数与冻结前缀下未来到达分数的交换性；本轮批次相关的机器映射尚未建立这一前提。轨迹事件的独立Bernoulli前提也未建立，因此所列单侧95%二项量只是名义计算，不能作为本实现已获精确CP/PAC保证的证据。即使未来闭合这些前提，CP仍对校准随机性取边际，不是每个固定校准文件的条件保证或获准子集风险比例界；两项单侧量也不构成联合95%。当前禁止部署，硬件、噪声变化、恢复及域外均未覆盖。'
             if zh else 'The 20-stage budget remains 0.10, with alpha=0.005 per stage. CP requires exchangeability of stage calibration scores and future reached scores under the frozen prefix; this premise is unestablished for the batch-dependent machine mapping in this run. Independent Bernoulli trajectory events are also unestablished. The reported one-sided 95% binomial quantities are therefore nominal calculations, not evidence of established exact CP/PAC guarantees for this implementation. Even if those premises are closed in future, CP averages over calibration randomness, rather than guaranteeing every fixed calibration file or the risk fraction among accepted actions; separate one-sided quantities are not joint 95% confidence. Deployment is prohibited; hardware, noise changes, recovery and domain shift remain uncovered.'), '',
            f"{'真实总仿真' if zh else 'Actual total simulations'}: {p['simulation_counts']['total']}; "
            f"{'训练/温度/开发' if zh else 'training/temperature/development'}: {p['simulation_counts']['training_total']}; "
            f"{'逐步校准' if zh else 'stage calibration'}: {p['simulation_counts']['calibration_total']}; "
            f"{'最终评估' if zh else 'final evaluation'}: {p['simulation_counts']['evaluation_total']}.", '',
            ('原始分片、SHA256、实际仿真与缓存命中见research/results/trajectory_risk.json及trajectory_risk_raw/。诊断观测不得自行更新运行历史；仅在同一动作后来实际采用时可复用确定性缓存。'
             if zh else 'Raw shards, SHA256, actual simulations and cache hits are recorded in research/results/trajectory_risk.json and trajectory_risk_raw/. Diagnostic observations cannot update operating history by themselves; an exact deterministic cached action may be reused only if subsequently actually adopted.'), '',
            '`python scripts/31_trajectory_risk.py --register-only` → `python scripts/31_trajectory_risk.py`', '',
            '`python scripts/32_verify_trajectory_risk.py`', '']
    return '\n'.join(lines)


def run_study(args):
    from jev_tune.decision import load_backend
    from jev_tune.primitives import calibrate_temperature
    from jev_tune.risk import JointRiskModel
    from jev_tune.sequential_risk import stage_calibration, summarize_rollout, acceptance_checks
    from jev_tune.trajectory_risk import run_trajectory_risk
    if not PROTOCOL.exists():
        raise SystemExit('Freeze and commit protocol before collection')
    protocol = json.loads(PROTOCOL.read_text(encoding='utf-8'))
    spec = protocol['specification']
    if spec != fixed_specification():
        raise SystemExit('Frozen protocol/configuration differs')
    calibration = json.loads((ROOT/'models/calibration.json').read_text(encoding='utf-8'))
    if (sha256(ROOT/'models/jev_head.pt') != spec['proposal']['checkpoint_sha256'] or
            calibration['choice_temperature'] != spec['proposal']['choice_temperature']):
        raise SystemExit('Frozen proposal checkpoint or temperatures changed')
    if RESULT.exists():
        raise SystemExit('Published result already exists; use verifier/render, never overwrite evaluation')
    progress_path = ROOT/'data/trajectory_risk/progress.json'
    if progress_path.exists():
        p = json.loads(progress_path.read_text(encoding='utf-8'))
        if p['protocol'] != protocol:
            raise SystemExit('Checkpoint belongs to a different protocol')
        # Resumption may add verifiers/docs, but cannot mix numerical runtimes.
        for filename, recorded in p['manifest']['file_sha256'].items():
            normalized = filename.replace('\\', '/')
            if not (normalized.startswith('src/jev_tune/') or normalized.endswith(
                    ('scripts/25_joint_risk.py', 'models/jev_head.pt', 'models/calibration.json'))):
                continue
            path = Path(filename)
            path = path if path.is_absolute() else ROOT/path
            raw_bytes = path.read_bytes()
            candidates = {hashlib.sha256(raw_bytes).hexdigest()}
            if path.suffix in ('.py', '.json'):
                lf = raw_bytes.replace(b'\r\n', b'\n')
                candidates.update(hashlib.sha256(b).hexdigest() for b in (lf, lf.replace(b'\n', b'\r\n')))
            if recorded not in candidates:
                raise SystemExit('Numerical dependency changed since collection: '+filename)
        import importlib.metadata
        for package, version in p['manifest']['packages'].items():
            if importlib.metadata.version(package) != version:
                raise SystemExit('Numerical package changed since collection: '+package)
    else:
        p = {'protocol': protocol, 'protocol_sha256': sha256(PROTOCOL),
             'protocol_canonical_sha256': canonical_hash(protocol), 'training': {'datasets': {}},
             'raw_files': [], 'arms': {}, 'evaluation': {}, 'evaluation_raw': {},
             'started_utc': datetime.now(timezone.utc).isoformat(),
             'manifest': manifest(args, files=[PROTOCOL, ROOT/'models/jev_head.pt', ROOT/'models/calibration.json'])}
    backend = load_backend(ROOT/'models')
    sampler = _load_script('25_joint_risk').independent_plants
    old = load_model(json.loads((ROOT/'research/results/joint_risk.json').read_text(encoding='utf-8'))['risk_model'])
    raw_by_path = {r['path']: r for r in p['raw_files']}
    if p['raw_files'] and 'runner_invocations' not in p:
        snapshot = ROOT/'research/protocols/trajectory_risk_sources/collection_runner.py'
        original_hash = next(v for k, v in p['manifest']['file_sha256'].items()
                             if k.replace('\\', '/') == 'scripts/31_trajectory_risk.py')
        if sha256(snapshot) != original_hash:
            raise SystemExit('Original executing runner snapshot does not match collection manifest')
        p['runner_invocations'] = [{'phase': 'training_calibration',
            'source_path': str(snapshot.relative_to(ROOT)).replace('\\', '/'),
            'source_sha256': original_hash, 'started_utc': p['started_utc'],
            'raw_files': [r['path'] for r in p['raw_files']]}]
    # Preserve the source of every invocation; code-documentation changes must
    # not erase the source that actually produced earlier numerical evidence.
    source_bytes = Path(__file__).read_bytes()
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    phase = ('full_study' if not p['raw_files'] and args.stop_after == 'evaluate' else
             'evaluation' if args.stop_after == 'evaluate' else 'training_calibration')
    snapshot = ROOT/'research/protocols/trajectory_risk_sources'/f'{phase}_{source_digest[:16]}.py'
    if snapshot.exists() and snapshot.read_bytes() != source_bytes:
        raise SystemExit('Executing runner snapshot differs from recorded content')
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(source_bytes)
    invocation = {'phase': phase, 'source_path': str(snapshot.relative_to(ROOT)).replace('\\', '/'),
        'source_sha256': source_digest, 'started_utc': datetime.now(timezone.utc).isoformat(),
        'raw_files': [], 'reused_raw_files': []}
    p.setdefault('runner_invocations', []).append(invocation)

    def checkpoint():
        write_json(progress_path, p)

    def shard(name, seed, n, kind, model, **kw):
        path = RAW_DIR/(name+'.json.gz')
        relative = str(path.relative_to(ROOT)).replace('\\', '/')
        metadata = {'protocol_canonical_sha256': p['protocol_canonical_sha256'], 'seed': seed,
                    'n_plants': n, 'kind': kind, 'arguments': kw,
                    'engine_sha256': sha256(ROOT/'src/jev_tune/trajectory_risk.py'),
                    'risk_model_sha256': None if model is None else canonical_hash(model.as_dict())}
        if path.exists():
            if relative in raw_by_path and sha256(path) != raw_by_path[relative]['sha256']:
                raise RuntimeError('Existing raw shard hash mismatch: '+relative)
            run = json.loads(gzip.decompress(path.read_bytes()))
            if run.get('study_metadata') != metadata:
                raise RuntimeError('Existing raw shard differs from frozen inputs: '+relative)
        else:
            plants = sampler(n, seed)
            run = run_trajectory_risk(backend, model, plants, **kw)
            run['study_metadata'] = metadata
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.tmp')
            temporary.write_bytes(gzip.compress(json.dumps(run, separators=(',', ':'), allow_nan=False).encode(), mtime=0))
            temporary.replace(path)
        if relative not in raw_by_path:
            entry = {'path': relative, 'sha256': sha256(path), 'kind': kind,
                     'n_plants': n, 'seed': seed, 'simulation_counts': run['simulation_counts'],
                     **{key: run[key] for key in ('mode', 'horizon', 'selector', 'feature_mode')}}
            p['raw_files'].append(entry)
            raw_by_path[relative] = entry
            if invocation is not None:
                invocation['raw_files'].append(relative)
        elif invocation is not None:
            invocation['reused_raw_files'].append(relative)
        return run, relative

    train_settings = spec['training']
    datasets = {}
    for split, settings in [('train', train_settings), ('temperature', train_settings['temperature']),
                            ('development', train_settings['development_audit'])]:
        run, path = shard(split, settings['seed'], settings['n_plants'], 'training', None,
                          mode='training', horizon=20, feature_mode='history_zero')
        data = run['collected']
        datasets[split] = data
        x = np.asarray(data['features'], float).reshape(-1, 44)
        y = np.asarray(data['labels'], int)
        npz_path = ROOT/'data/trajectory_risk'/f'{split}.npz'
        npz_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(npz_path, features=x, labels=y, plant_identity=np.asarray(data['plant_identity'], dtype=np.uint64),
                            stage=np.asarray(data['stage'], int))
        p['training']['datasets'][split] = {'n_plants': settings['n_plants'], 'n_rows': len(y),
            'harmful': int(y.sum()), 'seed': settings['seed'], 'raw_file': path,
            'npz_file': str(npz_path.relative_to(ROOT)).replace('\\', '/'), 'npz_sha256': sha256(npz_path),
            'simulation_counts': run['simulation_counts']}
        checkpoint()
        print(f"{split}: plants={settings['n_plants']} rows={len(y)} harmful={y.sum()} simulations={run['simulation_counts']['total']}", flush=True)
        del run
    if 'risk_model' not in p:
        model = JointRiskModel.fit(datasets['train']['features'], datasets['train']['labels'])
        td = datasets['temperature']
        model.temperature = calibrate_temperature(model.logits(td['features']), np.asarray(td['labels'], int))
        p['risk_model'] = model.as_dict()
        p['training']['model_frozen_utc'] = datetime.now(timezone.utc).isoformat()
        p['training']['model_canonical_sha256'] = canonical_hash(p['risk_model'])
        p['training']['diagnostics'] = {name: probability_diagnostics(model, d) for name, d in datasets.items()}
        checkpoint()
    model = load_model(p['risk_model'])
    del datasets
    if args.stop_after == 'train':
        return
    for arm_index, config in enumerate(spec['arms']):
        name = config['name']
        arm = p['arms'].setdefault(name, {'configuration': config, 'stages': [], 'qhats': []})
        risk = old if config['model'] == 'old' else model
        for stage in range(len(arm['stages']), 20):
            prefix = list(arm['qhats'])
            fit_refs, fit_x, fit_y, paths = [], [], [], []
            n_initial, n_observed = 0, 0
            unreachable = any(q >= 1 for q in prefix)
            cap = 512 if config['calibration'] == 'initial512' else spec['calibration']['initial_cap_per_stage']
            target = None if config['calibration'] == 'initial512' else spec['calibration']['target_reached']
            batch = 0
            while not unreachable and n_initial < cap and (target is None or len(fit_y) < target):
                n = min(512, cap-n_initial)
                seed = 900000000 + arm_index*1000000 + stage*1000 + batch
                run, path = shard(f'{name}_s{stage+1:02}_b{batch:03}', seed, n, 'calibration', risk,
                    mode='collect', horizon=20, selector=config['selector'], feature_mode=config['feature_mode'],
                    qhats=prefix, collect_step=stage, diagnostic=False)
                data = run['collected']
                # Explicit order, independent of target labels/scores.
                order = sorted(range(len(data['labels'])), key=lambda i: data['plant_index'][i])
                room = len(order) if target is None else target-len(fit_y)
                for index in order[:room]:
                    fit_x.append(data['features'][index]); fit_y.append(data['labels'][index])
                    fit_refs.append({'path': path, 'collected_index': index})
                n_initial += n; n_observed += len(order); paths.append(path); batch += 1
                checkpoint()
                print(f"cal {name} stage={stage+1:02} initial={n_initial} reached={len(fit_y)} observed={n_observed}", flush=True)
                del run
            x = np.asarray(fit_x, float).reshape(-1, 44)
            probabilities = risk.probabilities(x) if len(x) else np.empty((0, 2))
            q = stage_calibration(probabilities, np.asarray(fit_y, int), .005)
            quota_fallback = target is not None and len(fit_y) < target
            rank_fallback = q['all_labels_fallback']
            if quota_fallback:
                q['qhat'] = 1.
            reason = ('unreachable_frozen_prefix' if unreachable else 'quota_shortfall' if quota_fallback
                      else 'finite_sample_rank' if rank_fallback else None)
            q.update(stage=stage, n_initial=n_initial, n_observed_reached=n_observed,
                prefix_qhats=prefix, rank_fallback=rank_fallback, quota_fallback=quota_fallback,
                fallback_reason=reason, fit_refs=fit_refs, raw_files=paths)
            arm['stages'].append(q); arm['qhats'].append(q['qhat']); checkpoint()
            print(f"FROZEN {name} stage={stage+1:02} q={q['qhat']:.12f} n={q['n_reached']} reason={reason}", flush=True)
    if args.stop_after == 'calibrate':
        return
    eval_spec = spec['evaluation']
    for name in eval_spec['arms']:
        if name in p['evaluation']:
            continue
        if name == 'monitor':
            risk, kwargs = old, {'mode': 'monitor', 'selector': 'full_only', 'feature_mode': 'legacy', 'qhats': [1.]*20}
        else:
            a = p['arms'][name]; c = a['configuration']
            risk = old if c['model'] == 'old' else model
            kwargs = {'mode': 'gated', 'selector': c['selector'], 'feature_mode': c['feature_mode'], 'qhats': a['qhats']}
        run, path = shard('evaluation_'+name, eval_spec['seed'], eval_spec['n_plants'], 'evaluation', risk,
                          horizon=20, diagnostic=True, **kwargs)
        p['evaluation'][name] = summarize_rollout(run)
        p['evaluation_raw'][name] = path
        checkpoint()
        print('EVALUATION '+name+' '+json.dumps(p['evaluation'][name], separators=(',', ':')), flush=True)
        del run
    p['simulation_counts'] = {
        key+'_total': sum(r['simulation_counts']['total'] for r in p['raw_files'] if r['kind'] == key)
        for key in ('training', 'calibration', 'evaluation')}
    p['simulation_counts']['total'] = sum(p['simulation_counts'].values())
    # The independently implemented verifier must accept the evidence before publication.
    verifier = _load_script('32_verify_trajectory_risk')
    p['integrity'] = verifier.verify_payload(p)
    if not all(p['integrity'].values()):
        checkpoint()
        raise RuntimeError('Independent evidence verification failed: '+str(p['integrity']))
    primary = spec['primary_candidate']
    p['acceptance'] = acceptance_checks(p['evaluation']['monitor'], p['evaluation'][primary], True)
    p['deployment'] = {'enabled': p['acceptance']['passed'],
        'status': 'validated_research_scope_only' if p['acceptance']['passed'] else 'research_only',
        'primary_candidate': primary, 'generic_python_c_matlab_enabled': False,
        'failed_criteria': p['acceptance']['failed'], 'scope': spec['scope']}
    p['completed_utc'] = datetime.now(timezone.utc).isoformat()
    write_json(RESULT, p)
    DOC.write_text(_doc(p), encoding='utf-8')
    checkpoint()
    print(json.dumps({'acceptance': p['acceptance'], 'deployment': p['deployment'], 'simulation_counts': p['simulation_counts']}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--register-only', action='store_true')
    parser.add_argument('--render-only', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--stop-after', choices=['train', 'calibrate', 'evaluate'], default='evaluate')
    args = parser.parse_args()
    if args.register_only:
        register()
    elif args.render_only:
        rendered = _doc(json.loads(RESULT.read_text(encoding='utf-8')))
        if args.check:
            if DOC.read_text(encoding='utf-8') != rendered:
                raise SystemExit('TRAJECTORY_RISK.md differs from generated evidence')
        else:
            DOC.write_text(rendered, encoding='utf-8')
    else:
        run_study(args)


if __name__ == '__main__':
    main()
