"""Build v0.8 release assets and bilingual notes from completed evidence."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def archive(destination, paths):
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(paths):
            bundle.write(path, path.relative_to(ROOT).as_posix())


def trajectory_caches(study):
    """Recover optional caches from committed evidence, without simulating."""
    registered = {item['path']: item for item in study['raw_files']}
    paths = []
    for metadata in study['training']['datasets'].values():
        source = ROOT / metadata['raw_file']
        if hashlib.sha256(source.read_bytes()).hexdigest() != registered[metadata['raw_file']]['sha256']:
            raise ValueError('Training raw hash differs: ' + str(source))
        raw = json.loads(gzip.decompress(source.read_bytes()))
        data = raw['collected']
        arrays = {'features': np.asarray(data['features'], float).reshape(-1, 44),
                  'labels': np.asarray(data['labels'], int),
                  'plant_identity': np.asarray(data['plant_identity'], dtype=np.uint64),
                  'stage': np.asarray(data['stage'], int)}
        path = ROOT / metadata['npz_file']
        if path.exists():
            with np.load(path, allow_pickle=False) as cache:
                if set(cache.files) != set(arrays) or any(not np.array_equal(cache[k], v) for k, v in arrays.items()):
                    raise ValueError('Existing trajectory cache differs from raw: ' + str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, **arrays)
        paths.append(path)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.local-audit/release-v0.8.0')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    study = read('research/results/trajectory_risk.json')
    verification = read('research/results/release_verification.json')
    replay = read('research/results/trajectory_risk_reproduction.json')
    validity = read('research/results/trajectory_risk_validity.json')
    numerical = read('research/results/batch_inference_diagnosis.json')
    if verification['version'] != '0.8.0' or not verification['ok'] or not replay['equal']:
        raise SystemExit('Completed v0.8 verification and exact reproduction required')
    primary = study['protocol']['specification']['primary_candidate']
    candidate = study['evaluation'][primary]
    monitor = study['evaluation']['monitor']
    verdict = 'PASS' if study['acceptance']['passed'] else 'FAIL'
    failed = ', '.join(study['acceptance']['failed']) or 'none'
    tests = verification['pytest']
    passed = tests['tests'] - tests['skipped']
    data_zip = out / 'trajectory_risk_data_v0.8.0.zip'
    raw_zip = out / 'trajectory_risk_raw_v0.8.0.zip'
    data = trajectory_caches(study)
    archive(data_zip, data)
    archive(raw_zip, [ROOT / item['path'] for item in study['raw_files']])
    logs_zip = out / 'verification_logs_v0.8.0.zip'
    logs = [ROOT/'.local-audit'/name for name in (
        'v080_final_pytest.xml', 'v080_final_pytest.log', 'v080_final_claims.json',
        'v080_c99.log', 'v080_matlab_verification.log', 'v080_independent_evidence.log',
        'v080_reproduction.log', 'v080_batch_inference_diagnosis.log')]
    archive(logs_zip, logs)
    assets = [data_zip, raw_zip, logs_zip]
    source_paths = [
        'data/expert_train.npz', 'data/calibration/temperature_fit.npz',
        'data/calibration/cp_fit.npz', 'data/calibration/empirical_eval.npz',
        'models/calibration.json', 'research/protocols/trajectory_risk_v2.json',
        'research/results/rollout_diagnosis.json', 'research/results/trajectory_risk.json',
        'research/results/trajectory_risk_reproduction.json',
        'research/results/trajectory_risk_pairing_diagnosis.json',
        'research/results/trajectory_risk_validity.json',
        'research/results/batch_inference_diagnosis.json',
        'research/results/release_verification.json',
    ]
    for source in source_paths:
        path = ROOT / source
        target = out / path.name
        target.write_bytes(path.read_bytes())
        assets.append(target)
    status = study['deployment']['status']
    replay_total = replay['additional_simulation_counts']['total']
    numerical_total = numerical['additional_simulation_counts']['total']
    if study['deployment']['enabled'] and not validity['deployment_allowed']:
        raise SystemExit('Implementation validity does not allow deployment')
    notes = f'''# Prospective trajectory training and selected-action risk validation

[English](#english) · [简体中文](#简体中文)

## English

The v2 protocol was committed and pushed before new sampling. It fixes multi-round trajectory training, independent temperature fitting, independent reached-sample stage calibration, and complete joint-action selection before CP. A fresh paired test cohort evaluates five frozen arms. The primary candidate is `{primary}`; diagnostic arms cannot replace it after viewing results. The original failed study and raw trajectories remain byte-identical.

**Research enablement: {verdict}; `{status}`.** Failed numerical criteria: {failed}. Harmful trajectories: {candidate['trajectory_harm']['events']}/{candidate['n_plants']}, nominal one-sided 95% upper bound {candidate['trajectory_harm']['upper']:.6f}. Nominal first-stage execution lower bound: {candidate['first_stage_execution']['lower']:.6f}. Final mean J: monitor {monitor['final_cost']['mean']:.6f}, primary {candidate['final_cost']['mean']:.6f}; p90: {monitor['final_cost']['p90']:.6f} versus {candidate['final_cost']['p90']:.6f}. These are observed results; no post-test tuning or relaxed acceptance criteria were used. Generic Python/C99/MATLAB risk-head deployment remains disabled.

Full prediction sets and the preallocated 0.10 finite-horizon risk budget are retained. The selected complete action is calibrated after the frozen selector; rejection never triggers a candidate retry. Missing reached-sample quotas conservatively return both labels. **An additional implementation audit found coverage premises unestablished:** batch/row-dependent floating-point inference prevents inferring a common per-object numerical map, exchangeable calibration/test scores or independent trajectory events from frozen weights alone. The nominal CP/binomial quantities therefore do not establish an exact implementation-level guarantee. This finding adds a deployment prohibition without changing preregistered numerical criteria. Accepted-action conditional risk, recovery, domain shift and physical safety remain unproven.

The diagnosis explains the fixed-path truncation conflict in the previous acceptance test. Actual simulations: {study['simulation_counts']['total']} in the prospective study; {replay_total} additional simulations in the exact deterministic evaluation replay; {numerical_total} in the fixed-input numerical diagnosis. Replay and post-hoc diagnosis are charged separately and are not independent acceptance evidence. Raw trajectories, source snapshots and an independent verifier reconstruct selection, calibration, histories, labels, accounting and the failed acceptance decision.

Verification: {passed} pytest tests passed, {tests['skipped']} skipped; coverage {verification['coverage_percent']}%; {verification['automatic_document_checks']} automatic claims checks passed. Real MATLAB controller regressions and C99 parity were rerun. Earlier benchmark/ablation/generalization results are explicitly historical, preserved in the previous release verification record.

Extract both trajectory ZIPs at the repository root (their paths include `data/trajectory_risk/` and `research/results/trajectory_risk_raw/`). The fitted risk model is serialized inside `trajectory_risk.json`. Base data: place `expert_train.npz` in `data/`; the other three NPZ assets in `data/calibration/`. `SHA256SUMS.txt` covers all evidence/data attachments. See `docs/TRAJECTORY_RISK.md`, `docs/ROLLOUT_DIAGNOSIS.md`, and `docs/RELEASE_VERIFICATION.md` in the tagged source.

## 简体中文

v2协议在新采样前已提交并推送，冻结多轮轨迹训练、独立温度拟合、独立到达样本逐步校准，以及先选择完整联合动作再计算CP的规则。全新配对测试集验证五个固定方案；主候选固定为`{primary}`，不能看完结果后改选诊断组。原失败研究及原始轨迹保持逐字节不变。

**研究启用验收：{verdict}；`{status}`。** 未通过数值项：{failed}。有害轨迹{candidate['trajectory_harm']['events']}/{candidate['n_plants']}，名义单侧95%上界{candidate['trajectory_harm']['upper']:.6f}；名义首步执行率下界{candidate['first_stage_execution']['lower']:.6f}。最终平均J：monitor {monitor['final_cost']['mean']:.6f}、主方案{candidate['final_cost']['mean']:.6f}；p90分别为{monitor['final_cost']['p90']:.6f}、{candidate['final_cost']['p90']:.6f}。以上均为实际结果，没有测试后调参或放宽验收标准。通用Python/C99/MATLAB运行时仍不启用风险头。

完整预测集和预先分配的0.10整段风险预算保持不变。校准针对冻结选择器实际选出的完整动作；拒绝后不重试其他候选。到达样本不足时保守返回两个标签。**额外实施审计发现覆盖前提尚未建立：**批大小和行位置影响浮点推理，不能仅凭权重冻结推定每对象映射一致、校准与测试分数交换性或轨迹事件独立性。因此名义CP/二项统计量不构成机器实现的精确概率保证。该发现额外禁止部署，但不修改预注册数值标准；获准动作条件风险、恢复、域外和物理安全也未证明。

诊断文档说明原验收中固定路径截断的冲突。前瞻研究实际仿真{study['simulation_counts']['total']}次；逐字节一致的确定性评估重放另用{replay_total}次，固定输入数值诊断另用{numerical_total}次，均单独计账，不作为新增独立验收证据。原始轨迹、源码快照和独立验证器复核选择、校准、历史、标签、仿真账目和失败验收结论。

验证：pytest通过{passed}项、跳过{tests['skipped']}项，覆盖率{verification['coverage_percent']}%；自动claims检查{verification['automatic_document_checks']}项通过。MATLAB真实控制器回归及C99一致性重新运行。旧基准、消融和泛化结果明确保留为历史记录，见上一版本发布验证记录。

两个trajectory压缩包均解压到仓库根目录，内部已包含数据和原始轨迹路径。拟合风险模型保存在`trajectory_risk.json`。基础NPZ附件放置说明见英文部分；所有数据及证据附件摘要见`SHA256SUMS.txt`。详情见标签源码中的`docs/TRAJECTORY_RISK.md`、`docs/ROLLOUT_DIAGNOSIS.md`和`docs/RELEASE_VERIFICATION.md`。
'''
    (out / 'release_notes.md').write_text(notes, encoding='utf-8')
    sums = ''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n'
                   for path in assets)
    (out / 'SHA256SUMS.txt').write_text(sums, encoding='utf-8')
    print(json.dumps({'output': str(out), 'assets': [p.name for p in assets]}, indent=2))


if __name__ == '__main__':
    main()
