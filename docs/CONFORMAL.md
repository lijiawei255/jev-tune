# Temperature + split conformal prediction / 温度与分裂共形预测

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

CP calibration n=512, rank=462, alpha=0.1, k_max=3; independent evaluation n=512.

| axis | Temperature | q_hat | empirical label coverage | average set size |
| :--- | ---: | ---: | ---: | ---: |
| Kp | <!-- claim:temperature_Kp -->1.891494<!-- /claim --> | <!-- claim:cp_qhat_Kp -->0.906791<!-- /claim --> | <!-- claim:cp_coverage_Kp -->0.919922<!-- /claim --> | <!-- claim:cp_set_size_Kp -->3.015625<!-- /claim --> |
| Ki | <!-- claim:temperature_Ki -->1.521889<!-- /claim --> | <!-- claim:cp_qhat_Ki -->0.876490<!-- /claim --> | <!-- claim:cp_coverage_Ki -->0.906250<!-- /claim --> | <!-- claim:cp_set_size_Ki -->1.906250<!-- /claim --> |
| Kd | <!-- claim:temperature_Kd -->1.502246<!-- /claim --> | <!-- claim:cp_qhat_Kd -->0.906878<!-- /claim --> | <!-- claim:cp_coverage_Kd -->0.882812<!-- /claim --> | <!-- claim:cp_set_size_Kd -->2.576172<!-- /claim --> |

| variant | mean of draw medians | p90 summary | rollbacks |
| :--- | ---: | ---: | ---: |
| C0_MLP_regression | <!-- claim:abl_regression_head -->0.455395<!-- /claim --> | 1.527834 | 0 |
| C1_uncalibrated | <!-- claim:uncalibrated_median -->0.435726<!-- /claim --> | 1.060245 | 0 |
| C2_temperature_only | <!-- claim:temperature_only_median -->0.453664<!-- /claim --> | 1.029825 | 0 |
| C3_temperature_CP | <!-- claim:abl_typed_vs_regression -->0.672046<!-- /claim --> | 1.309521 | 0 |
| C4_CP_monitor | <!-- claim:cp_monitor_median -->0.453664<!-- /claim --> | 1.029825 | 0 |
| C5_CP_hold_stop | <!-- claim:cp_hold_stop_median -->0.701220<!-- /claim --> | 1.353294 | 0 |

Historical hard_hold minus Temp Only paired mean cost difference: +0.240389; paired normal-approximation 95% CI (mean +/- 1.96 SE) [+0.194164, +0.286614]. These are measured differences, not a safety benefit.

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

CP校准n=512、rank=462、alpha=0.1、k_max=3；独立评估n=512。

| axis | Temperature | q_hat | empirical label coverage | average set size |
| :--- | ---: | ---: | ---: | ---: |
| Kp | <!-- claim:temperature_Kp -->1.891494<!-- /claim --> | <!-- claim:cp_qhat_Kp -->0.906791<!-- /claim --> | <!-- claim:cp_coverage_Kp -->0.919922<!-- /claim --> | <!-- claim:cp_set_size_Kp -->3.015625<!-- /claim --> |
| Ki | <!-- claim:temperature_Ki -->1.521889<!-- /claim --> | <!-- claim:cp_qhat_Ki -->0.876490<!-- /claim --> | <!-- claim:cp_coverage_Ki -->0.906250<!-- /claim --> | <!-- claim:cp_set_size_Ki -->1.906250<!-- /claim --> |
| Kd | <!-- claim:temperature_Kd -->1.502246<!-- /claim --> | <!-- claim:cp_qhat_Kd -->0.906878<!-- /claim --> | <!-- claim:cp_coverage_Kd -->0.882812<!-- /claim --> | <!-- claim:cp_set_size_Kd -->2.576172<!-- /claim --> |

| variant | mean of draw medians | p90 summary | rollbacks |
| :--- | ---: | ---: | ---: |
| C0_MLP_regression | <!-- claim:abl_regression_head -->0.455395<!-- /claim --> | 1.527834 | 0 |
| C1_uncalibrated | <!-- claim:uncalibrated_median -->0.435726<!-- /claim --> | 1.060245 | 0 |
| C2_temperature_only | <!-- claim:temperature_only_median -->0.453664<!-- /claim --> | 1.029825 | 0 |
| C3_temperature_CP | <!-- claim:abl_typed_vs_regression -->0.672046<!-- /claim --> | 1.309521 | 0 |
| C4_CP_monitor | <!-- claim:cp_monitor_median -->0.453664<!-- /claim --> | 1.029825 | 0 |
| C5_CP_hold_stop | <!-- claim:cp_hold_stop_median -->0.701220<!-- /claim --> | 1.353294 | 0 |

Historical hard_hold minus Temp Only paired mean cost difference: +0.240389; paired normal-approximation 95% CI (mean +/- 1.96 SE) [+0.194164, +0.286614]. These are measured differences, not a safety benefit.

配对均值差与区间来自原始JSON；旧hard_hold配对平均代价更高，p90更高，不把标签覆盖定理当作闭环性能收益。

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
