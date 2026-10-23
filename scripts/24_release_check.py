"""Archive actual pytest/claims outcomes and render bilingual release evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from _experiment_protocol import manifest

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
    proc=subprocess.run([sys.executable,str(ROOT/'scripts/16_check_claims.py'),'--json'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    if proc.returncode:
        raise SystemExit(proc.stdout+proc.stderr)
    claims=json.loads(proc.stdout)
    if any(r['ok'] is not True for r in claims):
        raise SystemExit('release requires verified claims, without manual bypasses')
    log=Path(args.pytest_log).read_text(encoding='utf-8')
    coverage=re.search(r'Total coverage: ([\d.]+)%',log)
    payload={
        'ok':True,'pytest':totals,'coverage_percent':float(coverage[1]) if coverage else None,
        'automatic_document_checks':len(claims),'unverified_claims':0,
        'commands':[
            'python scripts/02_train.py --calibrate-only --alpha .10 --calibration-plants 512',
            'python scripts/03_evaluate.py --plants 120 --budget 20',
            'python scripts/03_evaluate.py --family thermal_deadtime --plants 120 --budget 20',
            'python scripts/17_ablation.py','python scripts/20_abstention.py','python scripts/22_calibrate_only.py',
            'python scripts/08_generalize.py','python scripts/11_robustness.py','python scripts/12_make_race.py',
            'python scripts/10_specialize.py --scenario valve_dead_zone --plants 120 --name valve --report research/results/specialization.json',
            'python scripts/13_tracking_demo.py','python scripts/06_export_weights_mat.py','python scripts/18_export_c.py --verify',
            "MATLAB: addpath('matlab'); test_portability('research/results/matlab_parity.json'); test_tune_history(tempname)",
            'python scripts/04_export_onnx.py --reps 2000','python scripts/21_hardware.py',
            'python scripts/23_sync_reference_docs.py','python -m pytest --cov --cov-fail-under=66',
            'python scripts/16_check_claims.py',
        ],
        'manifest':manifest(args,files=[args.junit,args.pytest_log,'models/jev_head.pt','models/calibration.json']),
    }
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

Regression coverage includes unique transition accounting, partial holds,
independent rollbacks, measured best gain/cost pairs, real early-stop calls,
noise-invariant subsets, numeric faults, split-CP ranks/ties, independent
calibration, CP policy boundaries, NaN/Inf C mutants, MATLAB decoder and real
first-rollback/JSON-history paths. Benchmark, ablation, random-hold, calibration,
robustness, generalization, specialization and disturbance results were rerun.

CP does not improve the current matched control costs. The independent empirical
label coverage and its finite-sample scope are in [CONFORMAL](CONFORMAL.md).
Training-seed replication, robot/clinical/board testing and WCET remain outside
the demonstrated scope; they are not silently counted as passing experiments.
Historical study pages and paid hosted-model measurements remain versioned records.

Synthetic data assets are attached to v0.5.0. From a clone, download
`expert_train.npz` into `data/` and `temperature_fit.npz`, `cp_fit.npz`,
`empirical_eval.npz` into `data/calibration/`. Their hashes are in the calibration
and A0 cache manifests. The CP-fit data was not used to select T or weights.

See [release_verification.json](../research/results/release_verification.json)
for executed commands/provenance. `23_sync_reference_docs.py` renders the current
numerical docs, and `16_check_claims.py` verifies registered text, both README
benchmark tables, and complete generated bilingual experiment/CP documents.
It does not reinterpret historical numbers as new experiments.

## 简体中文

本页由pytest实际JUnit输出与claims检查生成，不按计划测试数填表。原审计保留本地；
本公开记录概述修复版本。

'''+stats+'''

回归覆盖唯一转移记账、部分保持、独立回滚、实测最优增益/代价、早停真实次数、
噪声子集一致性、数值故障、CP分位次序/边界、独立校准、集合弃权、C NaN/Inf变体、
MATLAB解码及真实首回滚/JSON历史。基准、消融、匹配随机保持、校准、鲁棒性、泛化、
专门化与扰动研究均已重跑。CP当前同条件代价没有改善；独立经验标签覆盖及理论边界见
[CONFORMAL](CONFORMAL.md)。训练种子重复、机器人/临床/板测和WCET仍未验证，未计入通过。
历史研究页及付费托管模型测量保留版本语境，不冒充本次重测。

v0.5.0附件包含合成数据：将expert_train.npz放入data/，三个校准NPZ放入data/calibration/。
数据hash见校准与A0缓存manifest；CP拟合数据未参与T或权重选择。实际命令及来源见
[release_verification.json](../research/results/release_verification.json)。23脚本生成当前数字文档，
16检查注册正文、两种README基准表和完整双语实验/CP文档，不将历史数字重新解释为当前实验。
'''
    (ROOT/'docs/RELEASE_VERIFICATION.md').write_text(md,encoding='utf-8')
    print(stats)


if __name__=='__main__':
    main()
