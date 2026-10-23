"""Render registered current evidence and its prose markers from artifacts.

This does not prove experiment design or validate arbitrary historical prose.
Use scripts/16_check_claims.py after generation to detect subsequent drift.
"""
from __future__ import annotations
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("claims_check", ROOT / "scripts/16_check_claims.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


ROLLOUT_CLAIMS = {
    'joint_rollout_n': ('evaluation.gated.n_plants', 'Independent rollout test plants / 独立轨迹测试对象数'),
    'joint_rollout_any_harm': ('evaluation.gated.trajectory_harm.events', 'Gated trajectories with any harmful execution / 门控轨迹至少一次有害执行数'),
    'joint_rollout_risk_upper': ('evaluation.gated.trajectory_harm.upper', 'Gated trajectory risk: nominal exact-binomial upper quantity / 门控轨迹风险名义精确二项上界量'),
    'joint_rollout_first_lower': ('evaluation.gated.first_stage_execution.lower', 'First-stage execution: nominal exact-binomial lower quantity / 首步执行率名义精确二项下界量'),
    'joint_rollout_monitor_mean': ('evaluation.monitor.final_cost.mean', 'Matched monitor final mean J / 配对监测对照最终平均J'),
    'joint_rollout_gated_mean': ('evaluation.gated.final_cost.mean', 'Joint-risk gate final mean J / 联合风险门最终平均J'),
    'joint_rollout_monitor_p90': ('evaluation.monitor.final_cost.p90', 'Matched monitor final p90 J / 配对监测对照最终p90 J'),
    'joint_rollout_gated_p90': ('evaluation.gated.final_cost.p90', 'Joint-risk gate final p90 J / 联合风险门最终p90 J'),
    'joint_rollout_monitor_sims': ('evaluation.monitor.simulation_counts.operating', 'Matched monitor operating simulations / 配对监测对照运行仿真数'),
    'joint_rollout_gated_sims': ('evaluation.gated.simulation_counts.operating', 'Joint-risk gate operating simulations / 联合风险门运行仿真数'),
    'joint_rollout_acceptance': ('acceptance.passed', 'All preregistered rollout criteria pass, 1=yes / 预注册轨迹验收全通过，1为是'),
}
ROLLOUT_README_IDS = {'joint_rollout_n', 'joint_rollout_any_harm', 'joint_rollout_risk_upper',
                      'joint_rollout_first_lower',
                      'joint_rollout_monitor_mean', 'joint_rollout_gated_mean',
                      'joint_rollout_monitor_p90', 'joint_rollout_gated_p90'}


def rollout_readme_section(payload, chinese=False):
    def mark(key):
        value = check.walk(payload, ROLLOUT_CLAIMS[key][0])
        fmt = '.0f' if key in {'joint_rollout_n', 'joint_rollout_any_harm'} else '.6f'
        return f"<!-- claim:{key} -->{check.render_value(value,fmt)}<!-- /claim -->"
    n, harmful, upper = (mark(key) for key in ('joint_rollout_n', 'joint_rollout_any_harm', 'joint_rollout_risk_upper'))
    gm, mm = (mark(key) for key in ('joint_rollout_gated_mean', 'joint_rollout_monitor_mean'))
    gp, mp = (mark(key) for key in ('joint_rollout_gated_p90', 'joint_rollout_monitor_p90'))
    lower = mark('joint_rollout_first_lower')
    required = payload['protocol']['specification']['acceptance']['first_stage_execution_lower_min']
    passed = payload['acceptance']['passed']
    if chinese:
        status = '通过' if passed else '未通过'
        body = (f"**联合动作风险的多轮验收：{status}。** 冻结协议在{n}个独立测试对象上，"
                f"门控策略有{harmful}条轨迹至少一次有害执行；名义单侧95%精确二项上界量为{upper}。"
                f"门控/配对monitor对照的最终平均J为{gm}/{mm}，p90为{gp}/{mp}。"
                f"首步执行率的名义单侧95%下界为{lower}，预注册最低要求为{required:.2f}。"
                "全部判据、逐步独立校准、原始轨迹与适用范围见[联合风险多轮研究](docs/JOINT_RISK_ROLLOUT.md)。"
                "这是保留的v1数值记录；计算二项量不单独证明机器实现的事件独立性。此结果不把联合风险门默认接入通用Python、C或MATLAB部署；失败判据不会通过改阈值掩盖。")
    else:
        status = 'passed' if passed else 'not passed'
        body = (f"**Joint-action risk rollout acceptance: {status}.** On {n} independent test plants under the frozen protocol, "
                f"{harmful} gated trajectories contained a harmful execution; the nominal exact-binomial one-sided 95% upper quantity is {upper}. "
                f"Gated/matched-monitor final mean J is {gm}/{mm}, and p90 is {gp}/{mp}. "
                f"The nominal one-sided 95% lower quantity for first-stage execution is {lower}; its preregistered minimum is {required:.2f}. "
                "See [JOINT_RISK_ROLLOUT](docs/JOINT_RISK_ROLLOUT.md) for every criterion, independent stage calibration, raw trajectories and scope. "
                "This preserves the v1 numerical record; calculating binomial quantities does not itself establish independence of implemented trajectory events. This does not enable a joint-risk gate by default in general Python, C or MATLAB deployment; failed criteria are not hidden by retuning thresholds.")
    return '<!-- joint-risk-rollout:start -->\n' + body + '\n<!-- joint-risk-rollout:end -->'


def conformal_document(write=True):
    blob=json.loads((ROOT/'models/calibration.json').read_text(encoding='utf-8'))
    cp=blob['split_conformal']
    def mark(key,value):
        return f"<!-- claim:{key} -->{check.render_value(value,'.6f')}<!-- /claim -->"
    header='| axis | Temperature | q_hat | empirical label coverage | average set size |\n| :--- | ---: | ---: | ---: | ---: |\n'
    rows=[]
    for i,axis in enumerate(('Kp','Ki','Kd')):
        rows.append('| '+axis+' | '+' | '.join([
            mark('temperature_'+axis,blob['choice_temperature'][i]),
            mark('cp_qhat_'+axis,cp['qhat_per_axis'][i]),
            mark('cp_coverage_'+axis,cp['evaluation']['coverage_per_axis'][i]),
            mark('cp_set_size_'+axis,cp['evaluation']['mean_set_size_per_axis'][i]),
        ])+' |')
    table=header+'\n'.join(rows)+'\n'
    ablation=json.loads((ROOT/'research/results/ablation.json').read_text(encoding='utf-8'))
    compare='| variant | mean of draw medians | p90 summary | rollbacks |\n| :--- | ---: | ---: | ---: |\n'
    for key,identifier in [('C0_MLP_regression','abl_regression_head'),('C1_uncalibrated','uncalibrated_median'),('C2_temperature_only','temperature_only_median'),('C3_temperature_CP','abl_typed_vs_regression'),('C4_CP_monitor','cp_monitor_median'),('C5_CP_hold_stop','cp_hold_stop_median')]:
        row=next(r for r in ablation['rows'] if r['variant']==key)
        compare+=f"| {key} | {mark(identifier,row['median_mean'])} | {row['p90_median']:.6f} | {row['rollbacks']} |\n"
    paired=ablation['paired_vs_temperature_only']['C3_temperature_CP']
    comparison=(compare+f"\nHistorical hard_hold minus Temp Only paired mean cost difference: {paired['mean_delta']:+.6f}; paired normal-approximation 95% CI (mean +/- 1.96 SE) [{paired['ci95'][0]:+.6f}, {paired['ci95'][1]:+.6f}]. These are measured differences, not a safety benefit.\n")
    body='''# Temperature + split conformal prediction / 温度与分裂共形预测

[English](#english) · [简体中文](#简体中文)

## English

The frozen checkpoint is calibrated on three disjoint, freshly simulated IID
plant samples, with one initial ZN state per plant: temperature fitting, CP
quantile fitting, and empirical evaluation. No evaluation label selects T,
q_hat, alpha or k_max. Dataset hashes, seeds and actual simulation counts are
in [calibration.json](../models/calibration.json); datasets are release assets.

For each axis, score s=1-p(teacher label) uses the temperature-scaled distribution.
q_hat is order statistic ceil((n+1)(1-alpha)); rank n+1 uses the bounded endpoint
1. The set C includes labels with p >= 1-q_hat (computed as 1-p <= q_hat to keep
floating-point ties). Default monitor mode records full sets and would-hold
reasons without changing the proposal. Explicit hard_hold mode vetoes empty,
large or opposing-direction sets; it remains a comparison policy. Proposals
retain the full probability expectation and variance shrink, without truncation
or renormalization to C. A numeric zero proposal is distinct from a veto;
even a singleton zero-label set does not force the full-distribution proposal to zero.

Default alpha and maximum set size are fixed configuration, not tuned to the
test costs. The old pmax threshold is a separate optional heuristic; the shipped
monitor path disables it. Deterministic no-action trials stop without another
simulation; repeated measurements require stop_on_no_action=False. Noul remains
an optional override, and rollback remains a
separate post-measurement rule. Python, MATLAB and C share policy test vectors.

'''+f"CP calibration n={cp['n_calibration']}, rank={cp['quantile_rank']}, alpha={cp['alpha']}, k_max={cp['k_max']}; independent evaluation n={cp['evaluation']['n_states']}.\n\n"+table+'''
The third axis's empirical result below the nominal level is reported as
observed. It is not repaired by reselecting q_hat. Under exchangeability and
independently fixed model/T, split CP has per-axis marginal teacher-label
inclusion at least 1-alpha over calibration and a fresh test draw. It does not
force a finite evaluation sample to reach that fraction. It does not establish
joint-axis, selected-action, multi-step, shifted-domain or closed-loop safety
coverage. In particular these calibration states are initial states, not
adaptive trajectories. Labels are a simulated expert's actions, not measured
stability or clinical outcomes. See the [primary tutorial](https://arxiv.org/abs/2107.07511).


```bash
python scripts/02_train.py --calibrate-only --alpha .10 --calibration-plants 512
python scripts/17_ablation.py
python scripts/20_abstention.py
python scripts/18_export_c.py --verify
python scripts/23_sync_reference_docs.py
python scripts/16_check_claims.py
```

Changing weights or T requires fresh CP fitting. Specialization and the small
calibration-only adaptation experiment explicitly disable CP, rather than reuse
an invalid guarantee. Current control costs and tails are in ABLATION/BENCHMARK;
prediction-set coverage is a different quantity from executed-action coverage.

The actual-action target is separate from these teacher labels.
[JOINT_RISK](JOINT_RISK.md) records the initial-state study;
[JOINT_RISK_ROLLOUT](JOINT_RISK_ROLLOUT.md) records a new finite-horizon protocol.
That protocol freezes the risk model and temperature, uses new independent
calibration plants at each step under the frozen prefix, and allocates a fixed
trajectory error budget across steps. It does not pool correlated states from
one trajectory as IID calibration examples. Only the complete assessed action
can be admitted; altered actions and rollback proposals do not inherit its label.
Insufficient reached calibration samples use the conservative all-label set.

A valid stepwise inclusion argument plus the union bound controls whether any
assessed action is executed harmfully within the registered horizon, over
calibration and fresh-trajectory randomness. The final test's nominal exact-binomial
one-sided quantity requires independent trajectory events for its coverage
interpretation; the numerical calculation alone does not establish that premise
in the machine implementation. The current batch-context validity gap is explicitly
documented in [TRAJECTORY_RISK](TRAJECTORY_RISK.md). Neither statement
is a bound on the harmful fraction conditional on acceptance, a requirement that
every finite test achieve nominal coverage, or a physical safety certificate.
The registered cost, activity and simulation-count criteria must also pass;
the results and the restricted deployment decision are reported without tuning
the protocol after seeing test outcomes.
Here a harmful event means a trial-cost increase with zero tolerance. It is not
an instability rate or the probability of returning worse gains: the returned
gains always come from measured operating history. Suppressing exploration by
stopping early can lower event frequency while worsening final cost.

## 简体中文

冻结权重后，使用三个新生成、互不相交的IID模拟对象样本：温度拟合、CP分位数拟合、
经验评估。每株仅取一个初始ZN状态；评估标签不参与T、q_hat、alpha或k_max选择。
种子、数据hash与真实仿真次数见[calibration.json](../models/calibration.json)，数据作为release附件提供。

逐轴使用温度缩放概率计算s=1-p(专家标签)，取ceil((n+1)(1-alpha))次序统计量；
rank=n+1时使用有界端点1。候选集p>=1-q_hat以数值等价的1-p<=q_hat实现，保留浮点边界。
默认monitor记录完整集合及would_hold原因，不修改提案；显式hard_hold保留空集、超过k_max或正负冲突时的逐轴否决作为对照。提案仍用完整概率分布的
期望与方差缩步，不将分布截断或归一化到候选集。数值零提案与弃权不同；即使集合只含零标签，
也不强制将完整分布的提案归零。

alpha与集合大小上限是固定配置，不按测试代价调参；默认monitor关闭旧pmax阈值；后者仍可显式组合。
确定性无动作试验停止重复仿真；需要重复观测时显式设stop_on_no_action=False。Noul是可选否决，事后回滚独立。Python/MATLAB/C共用策略测试向量。

'''+f"CP校准n={cp['n_calibration']}、rank={cp['quantile_rank']}、alpha={cp['alpha']}、k_max={cp['k_max']}；独立评估n={cp['evaluation']['n_states']}。\n\n"+table+'''
第三轴经验覆盖率低于名义水平，按实测保留，不重选q_hat凑数。在交换性且模型/T独立固定的条件下，
分裂CP保证对校准样本及新测试抽样取边际后的逐轴专家标签包含率至少1-alpha；不保证某次有限评估
样本恰好达到此比例，也不保证多轴联合、获准动作条件子集、自适应多步、域外或闭环安全覆盖。
此处校准分布是初态，不是自适应轨迹；专家动作标签也不是稳定性或临床结局。
理论出处见上方一手教程与讲义。改权重或T后需独立重拟CP；专门化和小样本温度适配实验显式关闭CP，
不沿用失效保证。控制代价及尾部风险见ABLATION/BENCHMARK，集合覆盖率与实际动作执行率分别报告。

实际动作的风险目标与上述专家标签分开。[JOINT_RISK](JOINT_RISK.md)记录初态研究，
[JOINT_RISK_ROLLOUT](JOINT_RISK_ROLLOUT.md)记录新的有限步协议：冻结风险模型与温度，
每步在固定前缀策略下用新独立对象校准，并在各步分配固定轨迹错误预算。
不能将同一轨迹内相关状态混成IID校准样本。只允许执行整组已评价动作；修改动作或另作回滚
不继承原标签保证。到达该步的校准样本不足时采用全标签集合保守保持。

在逐步包含关系与交换性成立时，通过并集界约束注册时域内任一已评价动作被有害执行的概率，
该界对校准与新轨迹抽样取边际。最终测试的名义精确单侧二项量只有在轨迹事件独立等前提成立时
才有相应覆盖解释；数值计算本身不建立机器实现的前提，当前批次上下文缺口见[TRAJECTORY_RISK](TRAJECTORY_RISK.md)。
两者均不等于获准子集中的条件有害率界，不要求每个有限测试样本恰达名义覆盖，更不是物理安全证书。
预注册的代价、活动率与仿真计数条件也须分别满足；按原协议报告结果与受限部署结论，
不在看到测试结果后改协议。
此处有害事件是零容差下的试验代价上升，不是失稳率或返回更差增益的概率：返回增益始终来自
真实操作历史中的最优测量。提前停止会减少探索，也可能在压低事件频率的同时损害最终代价。
'''
    body=body.replace('The third axis\'s empirical result', comparison+'\nThe third axis\'s empirical result')
    cp_row=next(r for r in ablation['rows'] if r['variant']=='C3_temperature_CP')
    t_row=next(r for r in ablation['rows'] if r['variant']=='C2_temperature_only')
    mean_relation='更高' if paired['mean_delta']>0 else ('更低' if paired['mean_delta']<0 else '相同')
    tail_relation='更高' if cp_row['p90_median']>t_row['p90_median'] else ('更低' if cp_row['p90_median']<t_row['p90_median'] else '相同')
    body=body.replace('第三轴经验覆盖率',comparison+f'\n配对均值差与区间来自原始JSON；旧hard_hold配对平均代价{mean_relation}，p90{tail_relation}，不把标签覆盖定理当作闭环性能收益。\n\n第三轴经验覆盖率')
    if write:
        (ROOT/'docs/CONFORMAL.md').write_text(body,encoding='utf-8')
    return body


def applicability_sections(robust):
    rows=[r for r in robust['rows'] if r['gate']]
    table='| group | n | start J | returned J | improved % | worse % | rollbacks | final diverged | search diverged |\n| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n'
    for r in rows:
        table+=f"| {r['group']} | {r['n']} | {r['start_median']:.3f} | {r['final_median']:.3f} | {r['improved_pct']:.1f} | {r['worse_pct']:.1f} | {r['rollbacks_total']} | {r['diverged']} | {r['diverged_during_search']} |\n"
    ood=next(r for r in rows if r['group']=='outofzoo')
    total=sum(r['n'] for r in rows)
    gate=sum(r['rollbacks_total'] for r in rows)
    paired=robust['paired_outofzoo_gate_effect']
    en=f"## 1. Returned cost versus search risk\n\n{table}\nAcross {total} plants, returned measured-best costs have worse_pct as listed above. This is bookkeeping, not a bound on trial costs or stability. OOD search divergence: {ood['diverged_during_search']}; final divergence: {ood['diverged']}. Total rollbacks: {gate}. Gate-on/off unchanged pairs: {paired['unchanged_plants']}/{ood['n']} at absolute tolerance {paired['comparison_atol']:g}.\n\nParameter bounds do not prove stability. A 0.6×best rollback proposal must be measured. Per-plant budget is {ood['budget_per_plant']}; original model files are copied. Source: `research/results/robustness.json`, reproduced by `python scripts/11_robustness.py`.\n\n"
    zh=f"## 1. 返回代价与搜索风险\n\n{table}\n{total}株返回实测最优值，其worse_pct如上表；这是记账性质，不约束试验过程代价或证明稳定性。分布外搜索发散{ood['diverged_during_search']}株，最终发散{ood['diverged']}株，总回滚{gate}次。门开关有{paired['unchanged_plants']}/{ood['n']}对在绝对容差{paired['comparison_atol']:g}下无实质差异。\n\n参数限幅不证明稳定性，0.6×best回滚提案仍需测量。逐株预算{ood['budget_per_plant']}，原模型先复制再整定。证据见`research/results/robustness.json`，复现用`python scripts/11_robustness.py`。\n\n"
    return en,zh


def evidence_documents():
    def marked(key, value):
        return f"<!-- claim:{key} -->{value:.3f}<!-- /claim -->"
    def read(name):
        return json.loads((ROOT / "research/results" / name).read_text(encoding="utf-8-sig"))
    latency = read("latency.json")
    validation, thermal = read("eval_heldout_120.json"), read("eval_thermal_deadtime_120.json")
    def method(blob, name):
        return next(r for r in blob["rows"] if r["method"] == name)
    vm, tm = method(validation, "jev_head"), method(thermal, "jev_head")
    def table(blob):
        text = "| method | median J | p90 J | maximum budget / one-shot actual |\n| :--- | ---: | ---: | ---: |\n"
        for r in blob["rows"]:
            text += f"| `{r['method']}` | {r['final_cost_median']:.3f} | {r['final_cost_p90']:.3f} | {r['budget']:g} |\n"
        return text
    for filename, chinese in [("README.md", False), ("README.zh-CN.md", True)]:
        path = ROOT / filename
        s = path.read_text(encoding="utf-8")
        # Replace the full lead, leaving its established affiliation notice.
        if not chinese:
            intro = ("**PID autotuning with typed probabilistic decisions and explicit abstention.**\n"
                     "The numeric head uses one CPU forward pass. Complete CP sets are monitored independently of actuation.\n"
                     "Hard Hold is an explicit comparison policy; unchanged deterministic trials stop without repeated simulation.\n\n")
            s = re.sub(r"\*\*PID autotuning (?:where|with).*?(?=> \*\*Jev-inspired)", intro, s, flags=re.S)
            s = re.sub(r"\| \*\*How fast\*\*.*", f"| **How fast** | ONNX forward {marked('decision_ms',latency['onnx_forward_ms'])} ms median; Python default typed/abstention path {marked('typed_decision_ms',latency['typed_decision_ms'])} ms median, {marked('typed_decision_p99_ms',latency['typed_decision_p99_ms'])} ms p99. Host timing, not WCET; see [COMPUTE](docs/COMPUTE.md). |", s)
            s = re.sub(r"\| \*\*How it generalises\*\*.*", f"| **How it generalises** | Historical validation median {vm['final_cost_median']:.3f}; frozen thermal median {tm['final_cost_median']:.3f}. Their baselines and oracle priors are shown below; the separate v0.9 fixed-start comparison is in [PRACTICAL_BUDGET](docs/PRACTICAL_BUDGET.md). |", s)
            s = re.sub(r"\*\*vs\. Bayesian optimisation.*?(?=\*\*Why not just)", "**Comparison with ordinary heads and optimizers.** Current matched-split regression/argmax controls are in [ABLATION](docs/ABLATION.md). One training checkpoint and three evaluation draws do not establish a general causal advantage of the type interface. The gate, calibrated thresholds and matched-coverage random hold are reported separately.\n\n", s, flags=re.S)
            s = re.sub(r"Measured on a family.*?(?=\n---)", "Specialization uses offline simulation and can also degrade held-out performance. Current measured artifacts and the withdrawn historical provenance explanation are documented in [SPECIALIZE](docs/SPECIALIZE.md).\n", s, flags=re.S)
            start = "**Validation family (" if "**Validation family (" in s else "**Validation family:"
            end = "**Historical Simulink model result (lab DC motor, old objective)**"
            body = "**Validation family: two_mass, 120 plants.** Historical benchmark used for design decisions. Iterative methods have a maximum budget of 20; one-shot methods report actual runs. The table's iterative counts are allocated caps, not measured calls after early stopping. All analytic-start methods share oracle Ku/Tu; sweep failures use a fixed non-oracle fallback.\n\n" + table(validation)
            body += "\n**Frozen thermal family: 120 fixed-grid plants.** Frozen after training and re-evaluated during earlier correctness repairs, without selecting a new checkpoint on it. This is not a preregistered prospective test.\n\n" + table(thermal)
            body += "\nThese frozen rows are separate from the v0.9 [practical budget study](docs/PRACTICAL_BUDGET.md), which reports actual calls and does not show uniform head superiority. Historical identify→pidtune rows retain their original implementation's failure limitations. See [BENCHMARK](docs/BENCHMARK.md) for accounting and [raw tables](research/results/benchmark_table_thermal_deadtime.md) for sweep recovery/fallback details.\n\n"
            s = s[:s.index(start)] + body + s[s.index(end):]
            s = s.replace("Two comparisons this project does not make.", "The following are two of the project's unmeasured comparisons.")
        else:
            intro = ("**PID调参：温度缩放、完整CP集合与独立执行策略。**\n数值头在CPU上一次前向；默认monitor保留集合而不否决动作，hard_hold作为显式对照，确定性参数不变时停止重复仿真。\n\n")
            s = re.sub(r'\*\*PID(?: 调参，每一次|调参：).*?(?=> \*\*受 Jev)', intro, s, flags=re.S)
            s = re.sub(r"\| \*\*多快\*\*.*", f"| **多快** | ONNX前向中位{marked('decision_ms',latency['onnx_forward_ms'])} ms；Python默认类型化/弃权路径中位{marked('typed_decision_ms',latency['typed_decision_ms'])} ms、p99 {marked('typed_decision_p99_ms',latency['typed_decision_p99_ms'])} ms。宿主时延不代表WCET，见[COMPUTE](docs/COMPUTE.md)。 |", s)
            s = re.sub(r"\| \*\*多能泛化\*\*.*", f"| **多能泛化** | 历史验证族中位{vm['final_cost_median']:.3f}；冻结热工族中位{tm['final_cost_median']:.3f}，对应基线与oracle先验见下表；独立的v0.9固定起点评测见[PRACTICAL_BUDGET](docs/PRACTICAL_BUDGET.md)。 |", s)
            s = re.sub(r"在没见过的对象族上实测.*?(?=\n---)", "专门化依赖离线仿真，也可能让留出性能变差。当前实测及撤回的历史归因见[SPECIALIZE](docs/SPECIALIZE.md)。\n", s, flags=re.S)
            start = "**验证族（120 个" if "**验证族（120 个" in s else "**验证族："
            end = "**历史Simulink模型结果（直流电机，旧目标）**"
            body = "**验证族：120个two_mass对象。** 参与过设计决策的历史基准。迭代方法最多20次，一次性方法列实际消耗；表内迭代次数是分配上限，不是提前停止后的实测次数。解析起点方法共享oracle Ku/Tu，扫描失败统一采用固定非oracle先验。\n\n" + table(validation)
            body += "\n**冻结热工族：120个固定网格对象。** 训练后冻结，此前正确性修复后重测，未据此选择新权重；不是预注册前瞻测试。\n\n" + table(thermal)
            body += "\n这些冻结行与v0.9[实用预算评测](docs/PRACTICAL_BUDGET.md)分开；后者列实际调用，也不证明head全面优于基线。历史辨识→pidtune行保留原实现的失败边界。计账规则见[BENCHMARK](docs/BENCHMARK.md)，扫描恢复/回退见[原始表](research/results/benchmark_table_thermal_deadtime.md)。\n\n"
            s = s[:s.index(start)] + body + s[s.index(end):]
            notice = "\n> **受Jev启发，与TypeSafe AI无隶属、背书或赞助关系。** 本项目使用自己训练的数值头，不含Jev/Laya权重或API。[English](README.md)\n"
            if notice.strip() not in s:
                s = s.replace("# jev-tune\n", "# jev-tune\n" + notice, 1)
        s = re.sub(r'\[!\[decision latency\].*?\n', '[![measured latency](https://img.shields.io/badge/latency-host%20measured-blue)](docs/COMPUTE.md)\n', s)
        rollout_path = ROOT / 'research/results/joint_risk_rollout.json'
        if rollout_path.is_file():
            section = rollout_readme_section(json.loads(rollout_path.read_text(encoding='utf-8')), chinese)
            if '<!-- joint-risk-rollout:start -->' in s:
                s = re.sub(r'<!-- joint-risk-rollout:start -->.*?<!-- joint-risk-rollout:end -->',
                           lambda _: section, s, flags=re.S)
            else:
                anchor = '## 15 秒看懂' if chinese else '## The 15-second version'
                s = s.replace(anchor, section+'\n\n'+anchor, 1)
        path.write_text(s, encoding="utf-8")

    # Replace both obsolete robustness tables with generated current evidence.
    robust = read("robustness.json")
    en_section,zh_section=applicability_sections(robust)
    p = ROOT / "docs/APPLICABILITY.md"
    s = p.read_text(encoding="utf-8")
    first = s.index("## 1.")
    end = s.index("## 2.")
    s = s[:first]+en_section+s[end:]
    heads=list(re.finditer(r'^## 1\..*$',s,re.M))
    if len(heads)!=2:
        raise ValueError('Expected English and Chinese applicability sections')
    a=heads[1].start(); b=s.index('## 2.',a)
    s=s[:a]+zh_section+s[b:]
    p.write_text(s,encoding='utf-8')

    gen=read('generalization.json')
    gt="| scenario | head | Z-N | relay | CMA-ES | ratio | within 5% |\n| :--- | ---: | ---: | ---: | ---: | ---: | ---: |\n"
    for r in gen['rows']:
        gt+=f"| {r['scenario']} | {r['jev_median']:.3f} | {r['zn_median']:.3f} | {r['relay_median']:.3f} | {r['cmaes_median']:.3f} | {r['ratio_vs_best_classical']:.3f} | {r['plants_beaten']} |\n"
    (ROOT/'docs/GENERALIZATION.md').write_text('# Generalization / 泛化\n\n[English](#english) · [简体中文](#简体中文)\n\n## English\n\nTen out-of-zoo scenarios, four deterministic jitters each. Head and CMA-ES have a maximum 20-run budget including the start; one-shot methods have their own actual costs. Analytic Ku/Tu is oracle prior information.\n\n'+gt+f"\nWithin 5% of the best classical result on {gen['plants_beaten']}/{gen['plants_total']} plants; median ratio {gen['median_ratio']:.6f}. Ties at divergent cost count in this comparison and do not mean a usable controller. Dead band, inverse response and unstable starts remain failures.\n\nReproduce: `python scripts/08_generalize.py`. See `research/results/generalization.json` and its manifest.\n\n## 简体中文\n\n十个分布外场景，每个四组确定性扰动。head与CMA-ES均最多20次，包含起点；一次性方法列自身实际用量。解析Ku/Tu属于oracle先验。\n\n"+gt+f"\n{gen['plants_total']}株中{gen['plants_beaten']}株处于最强传统方法的5%以内，中位比值{gen['median_ratio']:.6f}。发散代价上的并列也计入比较，不代表控制器可用；死区、反向响应与不稳定起点仍有失败。\n\n复现：`python scripts/08_generalize.py`，产物及manifest见`research/results/generalization.json`。\n",encoding='utf-8')

    # Preserve historical study pages with an unambiguous version boundary.
    for name in ('STEP1_RESULTS.md','PHASE0_RESEARCH_REPORT.md'):
        p=ROOT/'docs'/name; s=p.read_text(encoding='utf-8')
        note='> Historical study record (through v0.4.1). Its timing path excluded default abstention, and older benchmark/risk counts have been superseded by v0.5.0. Current results: [CLAIMS](CLAIMS.md), [BENCHMARK](BENCHMARK.md), [COMPUTE](COMPUTE.md).\n> 历史研究记录（截至v0.4.1）：当时时延不含默认显式弃权，旧基准/风险计数已由v0.5.0替代；当前结果见上述文档。\n\n'
        if note not in s:
            s=note+s
        p.write_text(s,encoding='utf-8')


def main():
    path = ROOT / "docs/claims.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    # The separate v2 generator owns complete prose blocks, not claim markers
    # inside them. Keep the original v1 failure section and registry intact.
    trajectory_spec = importlib.util.spec_from_file_location(
        'trajectory_docs', ROOT / 'scripts/33_sync_trajectory_docs.py')
    trajectory_docs = importlib.util.module_from_spec(trajectory_spec)
    trajectory_spec.loader.exec_module(trajectory_docs)
    trajectory_docs.register_available_claims(registry, ROOT)
    if (ROOT / 'research/results/joint_risk_rollout.json').is_file():
        existing = {claim['id']: claim for claim in registry['claims']}
        for identifier, (source_path, label) in ROLLOUT_CLAIMS.items():
            if identifier not in existing:
                registry['claims'].append({'id':identifier, 'label':label,
                    'source':'research/results/joint_risk_rollout.json', 'path':source_path,
                    'reproduce':'python scripts/29_joint_risk_rollout.py'})
            else:
                existing[identifier]['label'] = label
    conformal_document()
    registry["note"] = (
        "Registered current artifact values and explicitly linked prose only; not every number in historical documents. "
        "Iterative benchmarks have a maximum budget; one-shot methods list actual simulations. "
        "Manual claims are unverified by the checker and excluded from automatic passes."
    )
    en, zh = [], []
    for claim in registry["claims"]:
        claim["text"] = claim.get("label", f"Current registered {claim['id']}; see artifact and protocol")
        if claim.get("verified_by") == "manual":
            claim.pop("documents", None)
            value = "UNVERIFIED / 未自动复核"
        else:
            data_path = ROOT / claim["source"]
            if "regex" in claim:
                _, got, _ = check.evaluate(claim)
            else:
                data = json.loads(data_path.read_text(encoding="utf-8-sig"))
                got = check.walk(data, claim["path"])
                if "reduce" in claim:
                    rows = [r for r in got if all(r.get(k) == v for k, v in claim.get("where", {}).items())]
                    op, field = claim["reduce"].split(":")
                    got = sum(r[field] for r in rows) if op == "sum" else len(rows)
                if "all_equal" in claim:
                    field, want = claim["all_equal"]
                    got = int(all(r.get(field) == want for r in got))
            claim["value"] = None if got is None else float(got)
            claim["tol"] = 1e-9
            claim["documents"] = [{"file": "docs/CLAIMS.md", "format": ".6f"}]
            if claim["id"] in {"decision_ms", "typed_decision_ms", "typed_decision_p99_ms"}:
                claim["documents"] += [{"file": name, "format": ".3f"} for name in ("README.md", "README.zh-CN.md")]
            if claim['id'] in ROLLOUT_README_IDS:
                fmt = '.0f' if claim['id'] in {'joint_rollout_n', 'joint_rollout_any_harm'} else '.6f'
                claim['documents'] += [{'file':name, 'format':fmt} for name in ('README.md','README.zh-CN.md')]
            if claim["id"].startswith(("cp_qhat_", "cp_coverage_", "cp_set_size_", "temperature_")) or claim["id"] in {"abl_regression_head","uncalibrated_median","abl_typed_vs_regression","cp_monitor_median","cp_hold_stop_median"}:
                claim["documents"].append({"file": "docs/CONFORMAL.md", "format": ".6f"})
            value = f"<!-- claim:{claim['id']} -->{check.render_value(got,'.6f')}<!-- /claim -->"
        # Text describes a quantity, never embeds a stale rounded measurement.
        label = claim.get("label", claim["id"])
        row = f"| `{claim['id']}` | {label} | {value} | [{claim['source']}](../{claim['source']}) |"
        en.append(row)
        zh.append(row)
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    header = "| ID | Quantity / 指标 | Value / 数值 | Artifact / 产物 |\n| :--- | :--- | ---: | :--- |\n"
    text = """# Current evidence register / 当前证据注册表

[English](#english) · [简体中文](#简体中文)

## English

Generated by `python scripts/23_sync_reference_docs.py`. Values below are read
from the named artifacts. `python scripts/16_check_claims.py` independently
checks registered values and both language copies of their prose markers.
Manual evidence is reported as UNVERIFIED, never counted as an automatic pass.
This checks registered text, not every sentence in the repository, experimental
causality, clinical safety or target-board timing. Historical result pages are
versioned records; see BENCHMARK, ABLATION, ABSTENTION and CALIBRATE_ONLY for current protocols.

""" + header + "\n".join(en) + """

Unmeasured work includes training-seed replication, full data learning curves,
many-question scaling, broad hosted-model comparisons, mid-run domain shifts,
and physical robot/medical/MCU/FPGA validation. No success is inferred for them.

## 简体中文

由`python scripts/23_sync_reference_docs.py`从所列产物生成。
`python scripts/16_check_claims.py`独立核对注册值及中英文正文中的数值标记。
人工证据显示为UNVERIFIED，不计入自动通过。本检查只覆盖已注册正文，
不证明全仓每句描述、实验因果性、临床安全或目标板时序。历史结果页保留版本语境；
当前协议见BENCHMARK、ABLATION、ABSTENTION与CALIBRATE_ONLY。

""" + header + "\n".join(zh) + """

未测项目包括训练种子重复、完整数据学习曲线、多问题扩展、广泛托管模型对比、
运行中域变化及机器人、医疗、MCU/FPGA实物验证；不推断这些项目已成功。
"""
    (ROOT / "docs/CLAIMS.md").write_text(text, encoding="utf-8")
    evidence_documents()
    if (ROOT / trajectory_docs.TRAJECTORY).is_file():
        trajectory_docs.sync_documents(ROOT)


if __name__ == "__main__":
    main()
