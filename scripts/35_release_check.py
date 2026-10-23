"""Archive v0.8 test evidence without confusing software and research gates."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from _experiment_protocol import manifest

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--junit', required=True)
    ap.add_argument('--pytest-log', required=True)
    args = ap.parse_args()
    suites = list(ET.parse(args.junit).getroot().iter('testsuite'))
    totals = {k: sum(int(s.attrib.get(k, 0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    if not totals['tests'] or totals['failures'] or totals['errors']:
        raise SystemExit('Missing or failing actual pytest evidence')
    env = dict(os.environ, PYTHONPATH=str(ROOT/'src'), PYTHONIOENCODING='utf-8', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    def command(script, flag):
        p = subprocess.run([sys.executable, str(ROOT/'scripts'/script), flag], cwd=ROOT,
                           capture_output=True, text=True, encoding='utf-8', env=env)
        if p.returncode:
            raise SystemExit(p.stdout+p.stderr)
        return p.stdout
    claims_text = command('16_check_claims.py', '--json')
    claims = json.loads(claims_text)
    if any(r['ok'] is not True for r in claims):
        raise SystemExit('Failed or unverified claims')
    claims_log = ROOT/'.local-audit/v080_final_claims.json'
    claims_log.parent.mkdir(parents=True, exist_ok=True)
    claims_log.write_text(claims_text, encoding='utf-8')
    command('34_reproduce_trajectory_evaluation.py', '--check')
    command('38_cohort_portability.py', '--check')
    study = json.loads((ROOT/'research/results/trajectory_risk.json').read_text())
    replay = json.loads((ROOT/'research/results/trajectory_risk_reproduction.json').read_text())
    validity = json.loads((ROOT/'research/results/trajectory_risk_validity.json').read_text())
    numerical = json.loads((ROOT/'research/results/batch_inference_diagnosis.json').read_text())
    portability = json.loads((ROOT/'research/results/cohort_portability.json').read_text(encoding='utf-8'))
    if study['deployment']['enabled'] and not validity['deployment_allowed']:
        raise SystemExit('Unestablished validity cannot authorize deployment')
    coverage = re.search(r'Total coverage: ([\d.]+)%', Path(args.pytest_log).read_text(encoding='utf-8'))
    if not coverage:
        raise SystemExit('Actual coverage summary missing')
    dest = ROOT/'research/results/release_verification.json'
    historical = ROOT/'research/results/release_verification_v070.json'
    if not historical.exists():
        historical.write_bytes(dest.read_bytes())
    payload = {'version':'0.8.0', 'ok':True, 'pytest':totals, 'coverage_percent':float(coverage[1]),
        'automatic_document_checks':len(claims), 'unverified_claims':0,
        'previous_release_verification':'research/results/release_verification_v070.json',
        'matlab_runtime':json.loads((ROOT/'research/results/matlab_runtime.json').read_text())['test_results'],
        'trajectory_risk':{k:study[k] for k in ('acceptance','deployment','evaluation','simulation_counts','protocol_sha256')},
        'trajectory_risk_reproduction':replay, 'scientific_validity':validity,
        'cohort_portability':portability,
        'additional_numerical_diagnosis_simulations':numerical['additional_simulation_counts'],
        'all_current_study_and_reproduction_simulations':study['simulation_counts']['total']
            + replay['additional_simulation_counts']['total'] + numerical['additional_simulation_counts']['total'],
        'preserved_v1':study['protocol']['specification']['old_results'],
        'manifest':manifest(args, files=[args.junit,args.pytest_log,str(claims_log),'research/results/trajectory_risk.json',
            'research/results/trajectory_risk_reproduction.json','research/results/matlab_runtime.json',
            'research/results/trajectory_risk_validity.json','research/results/batch_inference_diagnosis.json',
            'research/results/cohort_portability.json'])}
    dest.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    stats = f"{totals['tests']-totals['skipped']} passed; {totals['skipped']} skipped; coverage {float(coverage[1])}%; {len(claims)} automatic document checks."
    lines = ['# Release verification / 发布验证','','[English](#english) · [简体中文](#简体中文)','']
    for zh in (False,True):
        lines += ['## 简体中文' if zh else '## English','',stats,'',
            ('数字来自本次实际JUnit、pytest日志和claims复算。软件检查与研究启用验收是不同结论。'
             if zh else 'Counts come from actual JUnit, pytest logs and claims recomputation. Software verification and research enablement are separate conclusions.'),'',
            ('严格科学证据重建及规范化JSON记录精确重放已在记录的Windows参考宿主验证。Linux即使固定相同Python/科学包版本，仍在训练对象身份哈希首关失败；初始增益通过原容差，但不替代身份校验，后续v2重建未获验证。该失败保存在cohort_portability.json。Windows托管CI是另一个实际受检环境；Linux Python/C99运行时支持不意味着研究轨迹跨平台逐位复现。'
             if zh else 'Strict scientific evidence reconstruction and exact canonical-JSON replay were verified on the recorded Windows reference host. Linux with matching Python/scientific package versions failed the first training-cohort identity-hash check; initial gains passed the original tolerance but cannot replace identity validation, and later v2 reconstruction was not established there. This failure is preserved in cohort_portability.json. Hosted Windows CI is a separate environment that must actually pass; Linux Python/C99 runtime support does not imply cross-platform bitwise scientific replay.'),'',
            f"{'新研究验收' if zh else 'New study acceptance'}: **{'PASS' if study['acceptance']['passed'] else 'FAIL'}**; `{study['deployment']['status']}`.",
            f"{'未通过项' if zh else 'Failed criteria'}: {', '.join(study['acceptance']['failed']) or 'none'}.",'',
            ('额外实施有效性审计：覆盖前提尚未建立，禁止部署。批大小/行位置会改变浮点推理，校准与测试分数的交换性及轨迹事件独立性未闭合；名义CP/二项统计量不能作为机器实现的精确概率保证。该事后审计没有修改冻结数值验收。'
             if zh else 'Additional implementation validity audit: coverage premises are not established and deployment is prohibited. Batch/row-dependent floating-point inference leaves score exchangeability and trajectory-event independence unestablished; nominal CP/binomial quantities are not an exact probability guarantee for this implementation. This post-hoc audit does not revise frozen numerical acceptance.'),'',
            f"{'前瞻研究实际仿真' if zh else 'Actual prospective study simulations'}: {study['simulation_counts']['total']}.",'',
            f"{'完整评估重放额外仿真' if zh else 'Additional full evaluation replay simulations'}: {replay['additional_simulation_counts']['total']}; {'数值诊断额外仿真' if zh else 'additional numerical diagnosis simulations'}: {numerical['additional_simulation_counts']['total']}; {'合计' if zh else 'total'}: {payload['all_current_study_and_reproduction_simulations']}.",'',
            ('本次完成多轮训练、独立温度拟合、到达样本逐步校准及全新固定测试集五组真实闭环。旧数据仅诊断，旧失败JSON/原始轨迹保持不变。额外完整评估重放在下列reproduction JSON中单独计账，不是新增独立统计证据，不覆盖原验收。'
             if zh else 'This release runs trajectory training, independent temperature fitting, reached-sample stage calibration and five real closed-loop arms on a new fixed test cohort. Old data is diagnostic and old failure JSON/traces are preserved. Additional full evaluation replay is charged separately in the reproduction JSON below, adds no independent statistical evidence and does not replace acceptance.'),'',
            ('完整pytest覆盖CP边界、动作选择、缓存/诊断隔离、证据变异及既有运行时；MATLAB真实控制器回归重新运行。通用Python/C99/MATLAB策略不自动启用研究头。历史基准、消融和泛化记录见release_verification_v070.json，不冒充本次重跑。'
             if zh else 'Full pytest covers CP boundaries, action selection, cache/diagnostic isolation, evidence mutations and existing runtimes; real MATLAB controller regressions were rerun. Generic Python/C99/MATLAB policies do not automatically enable the research head. Earlier benchmark, ablation and generalization records are historical in release_verification_v070.json, not represented as newly rerun here.'),'',
            ('理论覆盖需要冻结的无噪声六族协议及交换性等条件，本次尚未证明实现满足这些条件，也不证明获准动作条件风险、域外、恢复或物理安全。数据及SHA256见v0.8.0附件；NPZ可从提交的原始分片再生，claims不依赖本地未提交数据。'
             if zh else 'Theoretical coverage requires the frozen noiseless six-family scope and assumptions including exchangeability; this implementation has not established those premises. Accepted-action conditional risk, domain shift, recovery and physical safety are also unproven. Data and SHA256 are attached to v0.8.0; NPZ caches regenerate from committed raw shards and claims do not depend on uncommitted local data.'),'',
            '[TRAJECTORY_RISK](TRAJECTORY_RISK.md) · [ROLLOUT_DIAGNOSIS](ROLLOUT_DIAGNOSIS.md) · [preserved v1](JOINT_RISK_ROLLOUT.md)','',
            '[release_verification.json](../research/results/release_verification.json) · [trajectory_risk_reproduction.json](../research/results/trajectory_risk_reproduction.json)',
            '[trajectory_risk_validity.json](../research/results/trajectory_risk_validity.json) · [batch_inference_diagnosis.json](../research/results/batch_inference_diagnosis.json)','']
        lines += ['[cohort_portability.json](../research/results/cohort_portability.json)', '']
    (ROOT/'docs/RELEASE_VERIFICATION.md').write_text('\n'.join(lines),encoding='utf-8')
    print(stats)


if __name__ == '__main__':
    main()
