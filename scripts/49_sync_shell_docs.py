"""Generate cross-domain shell summaries and claim bindings from saved evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REPORT = 'research/results/nonpid_transfer/report.json'
CALIBRATION = 'research/results/recalibration_benchmark.json'


def read(root, name):
    return json.loads((Path(root)/name).read_text(encoding='utf-8'))


def registered(root):
    report = read(root, REPORT)
    values = [('nonpid_actual_evaluations', 'accounting.actual_objective_evaluations',
               'Prospective non-PID objective evaluations / 非PID前瞻目标评价次数'),
              ('nonpid_offline_per_model', 'accounting.standalone_offline_per_model',
               'Standalone model training and calibration label cost / 单模型训练与校准标注成本'),
              ('nonpid_stable_benefit', 'acceptance.stable_empirical_policy_benefit',
               'All preregistered non-PID policy benefit criteria pass, 1=yes / 非PID策略收益验收，1为通过')]
    result = []
    for identifier, path, text in values:
        value = report
        for key in path.split('.'):
            value = value[key]
        result.append({'id':identifier, 'text':text, 'source':REPORT, 'path':path, 'value':float(value),
                       'tol':0, 'reproduce':'python scripts/45_nonpid_transfer.py --run',
                       'documents':[{'file':'docs/CLAIMS.md','format':'.0f'}]})
    return result


def block(root, zh=False, *, readme=False):
    report, calibration = read(root, REPORT), read(root, CALIBRATION)
    rows = [r for r in report['rows'] if r['budget'] == 20]
    heads = [r for r in rows if r['method'].startswith('typed_seed_')]
    simplex = next(r for r in rows if r['method'] == 'simplex')
    lo, hi = min(r['mean_final_MSE'] for r in heads), max(r['mean_final_MSE'] for r in heads)
    times = [r['timing_statistics_ms']['total_fit_ms']['median'] for r in calibration['rows']]
    prefix = 'docs/' if readme else ''
    status = report['acceptance']['status']
    if zh:
        prose = (f"**定位：以PID为验证床的可拆解 Calibrated Decision & Safety Shell。** "
                 f"新增非PID离线去噪标定完成三个模型的真实训练与独立测试，策略收益验收为`{status}`；"
                 f"预算20时三模型平均MSE为{lo:.8f}–{hi:.8f}，simplex为{simplex['mean_final_MSE']:.8f}，"
                 f"没有稳定收益，停止本轮策略深化。前瞻采集实际{report['accounting']['actual_objective_evaluations']}次，"
                 f"单模型离线训练/校准标注成本{report['accounting']['standalone_offline_per_model']}次；"
                 "原始负结果、冻结协议和复现入口保留，复杂风险研究仍暂停。\n\n"
                 f"每个独立温度/CP分区分别16、32、64个标注状态（合计32、64、128）时，"
                 f"九项组合的宿主纯拟合中位耗时范围为{min(times):.6f}–{max(times):.6f} ms。"
                 "标签采集、推理、通信和设备执行不在该拟合计时内；这不证明跨天、VLA、临床或目标板有效性。"
                 "非PID研究没有替换PID模型或默认策略；本版本另外加固了C/MATLAB输入与数值处理。"
                 "C99 checked入口拒绝非法状态/温度/策略及数值失败，清空旧动作并全轴保持。"
                 "默认CP仍为完整集合monitor，显式hard_hold可事前否决；测后rollback是领域恢复提案，并非物理安全证明。\n\n"
                 f"见[外壳与迁移边界]({prefix}SAFETY_SHELL.md)、[完整非PID证据]({prefix}NONPID_TRANSFER.md)、"
                 f"[少样本重标定]({prefix}RECALIBRATION.md)、[宿主资源指标]({prefix}COMPUTE.md)。")
    else:
        prose = (f"**Scope: a decomposable Calibrated Decision & Safety Shell with a PID testbed.** "
                 f"A new non-PID offline denoising task includes three genuinely trained models and independent testing; "
                 f"policy-benefit acceptance is `{status}`. At budget20, learned mean MSE spans {lo:.8f}–{hi:.8f}, "
                 f"versus simplex {simplex['mean_final_MSE']:.8f}. Stable benefit was not established; this policy investigation stops. "
                 f"Prospective acquisition used {report['accounting']['actual_objective_evaluations']} objective calls; standalone "
                 f"training/calibration labels cost {report['accounting']['standalone_offline_per_model']} per model. "
                 "Negative raw evidence, frozen protocols and reproduction remain available; complex risk research stays paused.\n\n"
                 f"Using 16, 32 or 64 labeled states in EACH independent temperature/CP split (32, 64 or 128 total), "
                 f"the nine host fit-time medians span {min(times):.6f}–{max(times):.6f} ms. "
                 "Label acquisition, inference, communication and device execution are excluded. This does not validate cross-day, "
                 "VLA, clinical or target-board operation. The non-PID study did not replace the PID model or default policy; "
                 "this release separately hardens C/MATLAB input and numeric handling. The C99 checked entry rejects invalid states/temperatures/policies and "
                 "numeric failures, clears stale actions and holds every axis. Default CP retains complete monitor sets; explicit "
                 "hard_hold can veto before actuation. Post-measurement rollback is domain-owned recovery, not a physical-safety proof.\n\n"
                 f"See [shell and transfer boundaries]({prefix}SAFETY_SHELL.md), [complete non-PID evidence]({prefix}NONPID_TRANSFER.md), "
                 f"[small-sample recalibration]({prefix}RECALIBRATION.md), and [host resources]({prefix}COMPUTE.md).")
    return prose


def insert(body, text, language, *, readme=False):
    start, end = f'<!-- transfer-shell:{language}:start -->', f'<!-- transfer-shell:{language}:end -->'
    section = start+'\n'+text+'\n'+end
    if readme:
        body = re.sub(re.escape(start)+r'.*?'+re.escape(end), '', body, flags=re.S)
        switch = '[English](README.md) · [简体中文](README.zh-CN.md)'
        body = body.replace(switch, '', 1)
        return switch+'\n\n'+section+'\n\n'+body.strip()+'\n'
    if start in body or end in body:
        if body.count(start) != 1 or body.count(end) != 1:
            raise ValueError('Broken shell markers')
        return re.sub(re.escape(start)+r'.*?'+re.escape(end), lambda _:section, body, flags=re.S)
    heading = '## 简体中文' if language == 'zh' else '## English'
    if heading not in body:
        raise ValueError('Missing bilingual heading')
    return body.replace(heading, heading+'\n\n'+section, 1)


def documents(root):
    result = {}
    for name, language in [('README.md','en'), ('README.zh-CN.md','zh')]:
        path = Path(root)/name
        result[name] = insert(path.read_text(encoding='utf-8'), block(root, language=='zh',readme=True), language,readme=True)
    for name in ('docs/ARCHITECTURE.md','docs/TRANSFER.md','docs/CLAIMS.md'):
        body = (Path(root)/name).read_text(encoding='utf-8')
        for language in ('en','zh'):
            body = insert(body, block(root, language=='zh'), language)
        result[name] = body
    claims_body = result['docs/CLAIMS.md']
    for language in ('en','zh'):
        start, end = f'<!-- transfer-values:{language}:start -->', f'<!-- transfer-values:{language}:end -->'
        lines = [f"* {c['text']}: <!-- claim:{c['id']} -->{c['value']:.0f}<!-- /claim -->" for c in registered(root)]
        section = start+'\n'+'\n'.join(lines)+'\n'+end
        if start in claims_body:
            claims_body = re.sub(re.escape(start)+r'.*?'+re.escape(end),lambda _:section,claims_body,flags=re.S)
        else:
            heading = '## 简体中文' if language=='zh' else '## English'
            claims_body = claims_body.replace(heading,heading+'\n\n'+section,1)
    result['docs/CLAIMS.md'] = claims_body
    # The general reference generator may also render these owned claims in
    # its bilingual tables. Every occurrence must use the registered document
    # format, not just the summary blocks this generator inserts above.
    for claim in registered(root):
        marker = rf"(<!-- claim:{re.escape(claim['id'])} -->).*?(<!-- /claim -->)"
        for document in claim['documents']:
            name = document['file']
            body = result.get(name)
            if body is None:
                body = (Path(root)/name).read_text(encoding='utf-8')
            rendered = format(float(claim['value']), document.get('format', '.3f'))
            result[name] = re.sub(marker, lambda match: match.group(1)+rendered+match.group(2),
                                  body, flags=re.S)
    return result


def sync(root=ROOT):
    root = Path(root)
    for name, content in documents(root).items():
        (root/name).write_text(content,encoding='utf-8')
    payload = read(root,'docs/claims.json')
    new = {c['id']:c for c in registered(root)}
    payload['claims'] = [c for c in payload['claims'] if c['id'] not in new]+list(new.values())
    (root/'docs/claims.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def check(root=ROOT):
    root = Path(root)
    for name, content in documents(root).items():
        assert (root/name).read_text(encoding='utf-8') == content, 'Stale shell summary: '+name
    observed = {c['id']:c for c in read(root,'docs/claims.json')['claims']}
    assert all(observed.get(c['id']) == c for c in registered(root)), 'Stale shell claim registration'
    assert (root/'docs/SAFETY_SHELL.md').is_file()
    return {'ok':True,'additional_verification_objective_evaluations':0}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if not args.check:
        sync()
    print(json.dumps(check()))
