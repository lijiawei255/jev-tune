# Joint-action risk in multi-round control / 多轮调参联合动作风险

[English](#english) · [简体中文](#简体中文)

## English

Generated from the frozen protocol and actual experiment JSON. Existing risk weights, temperature and proposal policy were not tuned. The protocol was frozen and committed before fresh stage calibration, followed by one fixed-size evaluation.

At most 20 joint proposals; trajectory budget 0.10; alpha per stage 0.005. Each stage starts with 512 fresh plants; only reached changed proposals enter calibration. Both monitor and gated are actually rolled out on the same 1024 independent test plants.

Both arms are scoped research controllers: uniform six-family mixture, analytic ZN start, a 10-second noiseless step response. A safety veto or unchanged action stops the plant; no recovery action is executed. Monitor is the matched ungated research controller, not the production rollback controller.

| metric | monitor | gated |
| :--- | ---: | ---: |
| plants with any harmful execution | 994 | 2 |
| trajectory harm one-sided 95% upper bound | 0.978835 | 0.006135 |
| first-stage execution one-sided 95% lower bound | 0.997079 | 0.479684 |
| executed proposals | 20474 | 620 |
| harmful executions (zero tolerance) | 6495 | 2 |
| harmful executions (legacy >2%) | 2857 | 2 |
| final J mean | 1.297619 | 2.303682 |
| final J median | 1.310013 | 2.274618 |
| final J p90 | 2.314045 | 3.416603 |
| simulations: operating | 21498 | 1644 |
| simulations: diagnostic_rejected | 0 | 1024 |
| simulations: total | 21498 | 2668 |

| stage | reached n | rank | qhat | full-set fallback |
| ---: | ---: | ---: | ---: | :--- |
| 1 | 512 | 511 | 0.994453 | False |
| 2 | 245 | 245 | 0.999989 | False |
| 3 | 56 | 57 | 1.000000 | True |
| 4 | 0 | 1 | 1.000000 | True |
| 5 | 0 | 1 | 1.000000 | True |
| 6 | 0 | 1 | 1.000000 | True |
| 7 | 0 | 1 | 1.000000 | True |
| 8 | 0 | 1 | 1.000000 | True |
| 9 | 0 | 1 | 1.000000 | True |
| 10 | 0 | 1 | 1.000000 | True |
| 11 | 0 | 1 | 1.000000 | True |
| 12 | 0 | 1 | 1.000000 | True |
| 13 | 0 | 1 | 1.000000 | True |
| 14 | 0 | 1 | 1.000000 | True |
| 15 | 0 | 1 | 1.000000 | True |
| 16 | 0 | 1 | 1.000000 | True |
| 17 | 0 | 1 | 1.000000 | True |
| 18 | 0 | 1 | 1.000000 | True |
| 19 | 0 | 1 | 1.000000 | True |
| 20 | 0 | 1 | 1.000000 | True |

Acceptance: **FAIL**.
Failed criteria: first_stage_execution_lower, empirical_mean_cost_noninferior, empirical_p90_cost_noninferior.
Enablement: `research_only`.

Stagewise CP and the union bound give harmful execution probability <=sum(alpha_t) only when stage calibration and future reached samples are exchangeable under the frozen prefix. Steps within one trajectory need not be independent; each calibration stage uses a new cohort, not reused ungated trajectories. Initial measurements, recovery, domain shift and physical safety are outside this bound. If the finite-sample rank exceeds n, including n=0, q=1 retains both labels and holds without relaxing coverage.

The one-sided binomial upper bound independently audits the final fixed policy; it differs from CP marginal coverage averaged over calibration randomness. The two 95% bounds are separate, not joint 95% confidence. Mean/p90 criteria are empirical test gates. Failure is not repaired by selecting new alpha, sample size, thresholds or temperature from evaluation outcomes; there is no optional stopping.

Actual plant-runs total 40987: stage calibration 16821, final evaluation arms 24166. Rejected diagnostic measurements cannot update state, best gains or operating budget, but are charged to total cost. Full traces: research/results/joint_risk_rollout_raw.json.gz, SHA-256 4934bcac26b399628bcec2b5d57608b3d60b25a3bf94e308dbb348b23725c060.

`python scripts/29_joint_risk_rollout.py --register-only` → `python scripts/29_joint_risk_rollout.py`

`python scripts/29_joint_risk_rollout.py --render-only --check`

## 简体中文

本页完全由冻结协议和真实实验JSON生成。既有风险模型、温度和提案策略未调参；先冻结并提交协议，再采集新的逐步校准批次，最后运行一次固定样本评估。

最多20次联合提案，整段预算0.10，每步alpha=0.005。每步从512个新对象开始，只有实际到达该步且产生不同增益的对象进入校准。最终同批1024个独立新对象分别真实运行monitor与gated。

两组均为限定的研究控制器：六族均匀混合、解析ZN初态、10秒无测量噪声阶跃；安全门触发或动作不变时停止，不执行额外回滚。monitor是相同研究控制器的无风险门控对照，不等同于生产回滚控制器。

| 指标 | monitor | gated |
| :--- | ---: | ---: |
| 整轨迹有害对象数 | 994 | 2 |
| 整轨迹有害率单侧95%上界 | 0.978835 | 0.006135 |
| 第一步执行率单侧95%下界 | 0.997079 | 0.479684 |
| 实际执行提案数 | 20474 | 620 |
| 有害执行数（零容差） | 6495 | 2 |
| 有害执行数（旧口径>2%） | 2857 | 2 |
| final J mean | 1.297619 | 2.303682 |
| final J median | 1.310013 | 2.274618 |
| final J p90 | 2.314045 | 3.416603 |
| simulations: operating | 21498 | 1644 |
| simulations: diagnostic_rejected | 0 | 1024 |
| simulations: total | 21498 | 2668 |

| 步 | 到达样本 n | 秩 | qhat | 全集合回退 |
| ---: | ---: | ---: | ---: | :--- |
| 1 | 512 | 511 | 0.994453 | False |
| 2 | 245 | 245 | 0.999989 | False |
| 3 | 56 | 57 | 1.000000 | True |
| 4 | 0 | 1 | 1.000000 | True |
| 5 | 0 | 1 | 1.000000 | True |
| 6 | 0 | 1 | 1.000000 | True |
| 7 | 0 | 1 | 1.000000 | True |
| 8 | 0 | 1 | 1.000000 | True |
| 9 | 0 | 1 | 1.000000 | True |
| 10 | 0 | 1 | 1.000000 | True |
| 11 | 0 | 1 | 1.000000 | True |
| 12 | 0 | 1 | 1.000000 | True |
| 13 | 0 | 1 | 1.000000 | True |
| 14 | 0 | 1 | 1.000000 | True |
| 15 | 0 | 1 | 1.000000 | True |
| 16 | 0 | 1 | 1.000000 | True |
| 17 | 0 | 1 | 1.000000 | True |
| 18 | 0 | 1 | 1.000000 | True |
| 19 | 0 | 1 | 1.000000 | True |
| 20 | 0 | 1 | 1.000000 | True |

验收: **FAIL**.
未通过项: first_stage_execution_lower, empirical_mean_cost_noninferior, empirical_p90_cost_noninferior.
启用状态: `research_only`.

只有每一步在冻结前缀下的校准样本与未来到达样本交换性成立，才可逐步使用CP边际保证并由联合界得到有害执行概率<=sum(alpha_t)。同一轨迹内各步不要求独立；每步使用新对象批次，不能复用旧未门控轨迹。初始测量、回滚、域外和物理安全不在此界内。有限样本秩超过n或n=0时q=1保留两标签并Hold，不降低覆盖目标。

单侧二项上界是对最终固定策略的独立验收，不等同于CP对校准随机性取平均的边际保证。两个95%界分别解释，不称联合95%。代价均值/p90是本次测试的经验门槛。失败不得通过重新选alpha、样本数、阈值或温度补救；没有反复查看后过线即停。

实际总仿真40987次，其中逐步校准16821次、两组最终评估24166次。被拒绝提案的诊断测量不能更新状态、历史最优或操作预算，但计入总成本。完整轨迹保存在research/results/joint_risk_rollout_raw.json.gz，SHA-256 4934bcac26b399628bcec2b5d57608b3d60b25a3bf94e308dbb348b23725c060。

`python scripts/29_joint_risk_rollout.py --register-only` → `python scripts/29_joint_risk_rollout.py`

`python scripts/29_joint_risk_rollout.py --render-only --check`
