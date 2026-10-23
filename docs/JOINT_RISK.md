# Joint-action risk: one initial-state research experiment

> [English](#english) · [简体中文](#简体中文)

## English

Four independent 512-plant splits, zero-tolerance labels and alpha=0.10 were fixed before collection. No parameter is selected from evaluation outcomes. The complete Temp Only proposal is unchanged; the risk head admits or holds the whole vector. This research does not change default Python/C/MATLAB deployment.

`train=72601; temperature_fit=72602; cp_fit=72603; empirical_eval=72604`

The target is measured J_proposal<=J_current for the full action, including equality, with tolerance zero. The 44 inputs are 20 state features, 3 applied joint steps and 21 choice probabilities. StandardScaler and fixed LogisticRegression use train only; temperature uses temperature_fit and qhat uses cp_fit.

Risk temperature=0.982264; alpha=0.1; n_cal=512; rank=462; qhat=0.297073.

| metric | value |
| :--- | ---: |
| empirical label-set coverage | 0.921875 |
| mean set size | 0.949219 |
| accepted / all | 483 / 512 |
| execution rate | 0.943359 |
| harmful executions / all | 12 / 512 |
| unconditional harmful execution rate | 0.023438 |
| conditional harmful rate among accepted | 0.024844720496894408 |
| miscoverage count | 40 |
| empty sets | 26 |

| cost measured on the same plants | mean J | median J | p90 J |
| :--- | ---: | ---: | ---: |
| current_cost | 2.667070 | 2.587236 | 3.840215 |
| always_propose_cost | 2.205279 | 2.250860 | 3.121987 |
| selected_cost | 2.200082 | 2.253813 | 3.125058 |

Selected minus current: paired mean -0.466988; paired median -0.281424; improved/unchanged/worse = 451/49/12.

Selected minus always-propose summary differences: mean J -0.005197, median J +0.002953, p90 J +0.003071. These are differences of the respective summary statistics; not every metric improves. The gate rejects 16 actually harmful and 13 actually noninferior proposals.

Only the exact set {noninferior} is admitted. Empty, {harmful}, and {noninferior,harmful} sets hold the whole vector. Thus harmful execution is pointwise a subset of label miscoverage; this inclusion is checked. Under exchangeability with model and temperature independently fixed, split CP bounds the one-initial-state unconditional probability of harmful execution. It does not bound the conditional harmful fraction among admitted actions by 10%, require every finite evaluation to reach 90% coverage, or ensure multi-step, shifted-domain, changed-noise or hardware safety.

Collection used 4096 actual plant-runs: 512 current and 512 full-proposal measurements in each of four splits. Offline labels include candidates the gate subsequently rejects, and all costs are counted. selected_cost selects from the same measured pair without an extra simulation; it does not take min(Jcurrent,Jproposal) to hide harmful execution or establish deployment efficiency.

Raw paired costs, complete gains, sets and admission decisions are in `research/results/joint_risk.json`; the fixed protocol is `research/protocols/joint_risk_v1.json`. Result provenance includes model, data and source hashes.

`python scripts/25_joint_risk.py --register-only` → `python scripts/25_joint_risk.py`

`python scripts/25_joint_risk.py --render-only --check`

## 简体中文

预先固定四个独立划分、每个512株对象、零容差标签和alpha=0.10；没有根据评估结果选参。完整三轴Temp Only提案保持不变，风险头只决定整组执行或整组保持。此研究不改变Python/C/MATLAB默认部署。

`train=72601; temperature_fit=72602; cp_fit=72603; empirical_eval=72604`

目标是完整动作的实测J_proposal<=J_current，含等号，容差为0。44维特征为20个状态特征、3个实际联合步长、21个choice概率；StandardScaler和固定LogisticRegression只用train，温度只用temperature_fit，qhat只用cp_fit。

风险温度=0.982264; alpha=0.1; n_cal=512; rank=462; qhat=0.297073.

| 指标 | 数值 |
| :--- | ---: |
| 经验标签集合覆盖率 | 0.921875 |
| 平均集合大小 | 0.949219 |
| 获准数 / 全部 | 483 / 512 |
| 执行率 | 0.943359 |
| 有害执行数 / 全部 | 12 / 512 |
| 无条件有害执行率 | 0.023438 |
| 获准动作中的条件有害率 | 0.024844720496894408 |
| 漏覆盖数 | 40 |
| 空集数 | 26 |

| 同批对象实测代价 | 均值 J | 中位 J | p90 J |
| :--- | ---: | ---: | ---: |
| current_cost | 2.667070 | 2.587236 | 3.840215 |
| always_propose_cost | 2.205279 | 2.250860 | 3.121987 |
| selected_cost | 2.200082 | 2.253813 | 3.125058 |

选择后相对当前代价的配对差：均值-0.466988，中位数-0.281424；改善/不变/恶化=451/49/12。

相对总是执行完整提案，selected的均值J差-0.005197、中位J差+0.002953、p90 J差+0.003071。这些是各汇总统计量之差；并非所有指标都改善。拒绝的动作中，16个实际有害，13个实际非劣。

只有集合恰为{非劣}才放行，空集、{有害}、{非劣,有害}都整组保持。因此“执行且有害”逐点包含于“真实标签未被集合覆盖”，本次集合包含关系已检查。交换性成立且模型/温度独立固定时，Split CP控制单次初态无条件有害执行概率；它不保证获准动作中的有害比例<=10%，不保证每个有限评估样本达到90%覆盖，也不保证多步闭环、域外、噪声变化或真机安全。

采集实际仿真4096次：每个划分512次当前测量+512次完整提案测量，共四个划分。离线为所有候选取得真实标签，包含随后会被拒绝的提案；这些成本均计入。评估selected_cost在同一对实测代价中选择，不是另做一遍仿真；不使用min(Jcurrent,Jproposal)隐藏有害执行，也不据此声称部署效率。

原始配对代价、完整增益、集合及接纳决策位于`research/results/joint_risk.json`；协议位于`research/protocols/joint_risk_v1.json`。模型、数据及源代码hash记录于结果manifest。

`python scripts/25_joint_risk.py --register-only` → `python scripts/25_joint_risk.py`

`python scripts/25_joint_risk.py --render-only --check`
