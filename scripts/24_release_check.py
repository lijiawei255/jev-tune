"""Archive actual pytest/claims outcomes and render bilingual release evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import importlib.util
import os

from _experiment_protocol import manifest, sha256

ROOT=Path(__file__).resolve().parents[1]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--junit',required=True)
    ap.add_argument('--pytest-log',required=True)
    ap.add_argument('--out',default='research/results/release_verification.json')
    args=ap.parse_args()
    tree=ET.parse(args.junit)
    suites=list(tree.getroot().iter('testsuite'))
    totals={key:sum(int(s.attrib.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
    if not totals['tests'] or totals['failures'] or totals['errors']:
        raise SystemExit('pytest evidence has failures/errors or no tests')
    proc=subprocess.run([sys.executable,str(ROOT/'scripts/16_check_claims.py'),'--json'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',env=dict(os.environ,PYTHONIOENCODING='utf-8'))
    if proc.returncode:
        raise SystemExit(proc.stdout+proc.stderr)
    claims=json.loads(proc.stdout)
    if any(r['ok'] is not True for r in claims):
        raise SystemExit('release requires verified claims, without manual bypasses')
    log=Path(args.pytest_log).read_text(encoding='utf-8')
    coverage=re.search(r'Total coverage: ([\d.]+)%',log)
    reproduction=json.loads((ROOT/'research/results/reproduction.json').read_text(encoding='utf-8'))
    selection={'source':'research/results/reproduction.json','runs':[
        run for run in reproduction['runs'] if run['command'][1] in ('scripts/17_ablation.py','scripts/20_abstention.py')]}
    (ROOT/'research/results/selection_reproduction.json').write_text(json.dumps(selection,indent=2)+'\n',encoding='utf-8')
    rollout=json.loads((ROOT/'research/results/joint_risk_rollout.json').read_text(encoding='utf-8'))
    replay=json.loads((ROOT/'research/results/joint_risk_reproduction.json').read_text(encoding='utf-8'))
    if (replay['returncode'] or not replay['raw_bytes_identical']
        or replay['additional_independent_evidence']
        or replay['original_artifact_hashes']['summary'] != sha256(ROOT/'research/results/joint_risk_rollout.json')
        or replay['original_artifact_hashes']['raw'] != sha256(ROOT/rollout['raw_file'])):
        raise SystemExit('fixed-sample reproduction evidence does not match the prospective study')
    if not all(rollout['integrity'].values()):
        raise SystemExit('rollout evidence has integrity failures')
    payload={
        'ok':True,'pytest':totals,'coverage_percent':float(coverage[1]) if coverage else None,
        'automatic_document_checks':len(claims),'unverified_claims':0,
        'experiment_runs':reproduction,
        'selection_reruns':selection,
        'matlab_runtime':json.loads((ROOT/'research/results/matlab_runtime.json').read_text(encoding='utf-8'))['test_results'],
        'joint_risk_evaluation':json.loads((ROOT/'research/results/joint_risk.json').read_text(encoding='utf-8'))['evaluation'],
        'joint_risk_rollout':{'acceptance':rollout['acceptance'],'deployment':rollout['deployment'],
            'evaluation':rollout['evaluation'],'simulation_counts':rollout['simulation_counts'],
            'protocol_sha256':rollout['protocol_sha256'],'raw_sha256':rollout['raw_sha256']},
        'joint_risk_reproduction':replay,
        'preserved_calibration':'Existing independent teacher-label T/CP fits are unchanged; no threshold refitting on outcomes.',
        'manifest':manifest(args,files=[args.junit,args.pytest_log,'models/jev_head.pt','models/calibration.json']),
    }
    if any(r['returncode'] for r in payload['experiment_runs']['runs']):
        raise SystemExit('experiment subprocess failed')
    spec=importlib.util.spec_from_file_location('reproduce',ROOT/'scripts/28_reproduce.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    if [r['command'][1:] for r in payload['experiment_runs']['runs']] != module.COMMANDS:
        raise SystemExit('experiment execution record is incomplete')
    Path(args.out).write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    passed=totals['tests']-totals['skipped']
    stats=f"{passed} passed; {totals['skipped']} skipped; {totals['failures']} failures; coverage {payload['coverage_percent']}%; {len(claims)} automatic document checks."
    md='''# Release verification / 发布验证

[English](#english) · [简体中文](#简体中文)

## English

This page is generated from actual pytest JUnit output and the claims checker,
not from the intended number of tests. The baseline audit is a private local
record; this public record summarizes the repaired release.

'''+stats+'''

Regression coverage includes CP monitor/hard_hold separation, terminal-proposal
telemetry, no-action stopping, joint-risk acceptance, unique transition accounting, partial holds,
independent rollbacks, measured best gain/cost pairs, real early-stop calls,
noise-invariant subsets, numeric faults, split-CP ranks/ties, independent
calibration, CP policy boundaries, NaN/Inf C mutants, MATLAB decoder and real
first-rollback/JSON-history paths. Benchmark, ablation, random-hold, calibration,
robustness, generalization, specialization and disturbance results were rerun.

The historical hard_hold policy does not improve current matched control costs.
The default monitor retains full sets and preserves the Temp Only proposal.
The prospective multi-round joint-risk study passed the risk-upper-bound criterion
but failed the execution lower bound and final mean/p90 cost criteria. It remains
research-only. The finite-horizon guarantee concerns the scoped changed proposals,
not initial identification, recovery, shifted domains or physical safety.
The fixed samples were additionally replayed with `29_joint_risk_rollout.py --reproduce`;
raw traces matched byte-for-byte and the original acceptance was preserved.
The extra reproduction simulations are separately recorded in
`research/results/joint_risk_reproduction.json`; they add no independent statistical evidence.
See [JOINT_RISK_ROLLOUT](JOINT_RISK_ROLLOUT.md), [JOINT_RISK](JOINT_RISK.md)
and [CP_DIAGNOSIS](CP_DIAGNOSIS.md). The independent empirical
label coverage and its finite-sample scope are in [CONFORMAL](CONFORMAL.md).
Training-seed replication, robot/clinical/board testing and WCET remain outside
the demonstrated scope; they are not silently counted as passing experiments.
Historical study pages and paid hosted-model measurements remain versioned records.

Synthetic data assets are attached to v0.7.0. From a clone, download
`expert_train.npz` into `data/` and `temperature_fit.npz`, `cp_fit.npz`,
`empirical_eval.npz` into `data/calibration/`. Their hashes are in the calibration
and A0 cache manifests. The CP-fit data was not used to select T or weights.

See [release_verification.json](../research/results/release_verification.json)
for actual experiment subprocess outcomes/provenance. `23_sync_reference_docs.py` renders the current
numerical docs, and `16_check_claims.py` verifies registered text, both README
benchmark tables, and complete generated bilingual experiment/CP documents.
It does not reinterpret historical numbers as new experiments.

## 简体中文

本页由pytest实际JUnit输出与claims检查生成，不按计划测试数填表。原审计保留本地；
本公开记录概述修复版本。

'''+stats+'''

回归覆盖CP监测/硬保持分离、终止提案遥测、无动作停止、联合风险整步获准、唯一转移记账、部分保持、独立回滚、实测最优增益/代价、早停真实次数、
噪声子集一致性、数值故障、CP分位次序/边界、独立校准、集合弃权、C NaN/Inf变体、
MATLAB解码及真实首回滚/JSON历史。基准、消融、匹配随机保持、校准、鲁棒性、泛化、
专门化与扰动研究均已重跑。旧hard_hold当前同条件代价没有改善；默认monitor保留完整集合和Temp Only提案。
前瞻多轮联合风险研究通过风险上界条件，但执行率下界与最终均值/p90代价未通过，保持研究用途。
整段界只覆盖限定协议中的实际改变参数提案，不含初始辨识、回退、域外或物理安全。
另用29脚本的--reproduce完整重放固定样本，原始轨迹逐字节相同，原验收未覆盖。
额外复现仿真单列于research/results/joint_risk_reproduction.json，不算新增独立统计证据。
见[JOINT_RISK_ROLLOUT](JOINT_RISK_ROLLOUT.md)、[JOINT_RISK](JOINT_RISK.md)及[CP_DIAGNOSIS](CP_DIAGNOSIS.md)。
独立经验标签覆盖及理论边界见
[CONFORMAL](CONFORMAL.md)。训练种子重复、机器人/临床/板测和WCET仍未验证，未计入通过。
历史研究页及付费托管模型测量保留版本语境，不冒充本次重测。

v0.7.0附件包含合成数据：将expert_train.npz放入data/，三个校准NPZ放入data/calibration/。
数据hash见校准与A0缓存manifest；CP拟合数据未参与T或权重选择。实际命令及来源见
[release_verification.json](../research/results/release_verification.json)。23脚本生成当前数字文档，
16检查注册正文、两种README基准表和完整双语实验/CP文档，不将历史数字重新解释为当前实验。
'''
    (ROOT/'docs/RELEASE_VERIFICATION.md').write_text(md,encoding='utf-8')
    print(stats)


if __name__=='__main__':
    main()
