# ARCHITECTURE

[English](#english) · [简体中文](#简体中文)

## English

This is a PID testbed plus reusable numeric decision components. The full loop
is not domain-neutral: it owns three PID axes, multiplicative updates, response
features, a scalar step-response cost and a PID-specific rollback rule.

| Layer | Execution path | Contract |
| :--- | :--- | :--- |
| Observation | `state.build_state` | 20 features and 2×64 curve samples; PID-specific |
| Backend | `decision.NumericBackend` / `OnnxBackend` | one forward; fitted per-axis temperatures; typed Choice/Score/Noul |
| Decode | `decode.decide` | ordered numeric payload expectation, variance shrink, full CP monitoring; optional per-axis veto |
| Actuation | `decode.apply_step` | clipped multiplicative PID gain update |
| Measurement | `evaluate.evaluate_head` | one simulation per active plant; next response belongs to the actual applied parameters |
| Fallback | evaluator safety gate | after measured J > max(3×best+1,8), propose 0.6×best gains; at most four rollbacks |
| Return | running measured minimum | gains and J saved together, including the final measurement |

The runtime really asks typed backends for answers; types are not dead wrappers.
`load_backend` reads `models/calibration.json`; CLI/demo/MCP use this loader.
MATLAB and C use exported snapshots with the same temperatures and policy.
An export must be regenerated after checkpoint/calibration changes.

The default checkpoint uses temperature scaling plus complete split conformal
sets in `monitor` mode. Set construction is independent of actuation: the full
calibrated distribution drives expectation and variance shrink. `hard_hold`
explicitly restores the historical axis veto for empty, large or mixed sets.
`conformal_would_hold` and `conformal_reason` retain those diagnostics in both
modes; `held` and `reason` describe actual actuation. Legacy pmax thresholds are
optional and disabled by default. Noul and post-measurement rollback remain
separate overrides. The experimental joint-risk classifier evaluates the full
proposal, without per-axis masking; see [JOINT_RISK](JOINT_RISK.md).
The separate [joint-risk rollout study](JOINT_RISK_ROLLOUT.md) freezes that risk
model and temperature, then calibrates each candidate step on a fresh independent
plant batch under the already frozen prefix policy. It spends a fixed trajectory
risk budget across steps. Stop and no-action decisions have no synthetic next
measurement; rejected proposals are measured separately only for offline
diagnosis and never fed back into the executed trajectory. Its matched monitor
control uses the same stop rules. This research controller stops at the safety
threshold rather than issuing the production loop's uncalibrated rollback.
The study's release decision concerns only its registered simulator population,
initialization, objective and finite horizon. It does not turn on a joint-risk
gate in the general CLI, MCP, C or MATLAB runtime. A scope or proposal change
requires fresh calibration and validation.
The rollout's harmful-event label is any strictly positive trial-cost increase;
it does not mean instability or deterioration of the returned measured-best
controller. A low event rate obtained by stopping early is assessed together
with activity, final-cost and experiment-budget criteria.
See [CONFORMAL](CONFORMAL.md) for actual q_hat/empirical coverage and its scope:
per-axis marginal expert-label inclusion under exchangeability, not joint-axis,
adaptive-trajectory or closed-loop safety. Three independent plant-level splits
fit T, fit CP, and evaluate; a finite empirical sample may fall below nominal.

Each valid trace entry links measurement IDs, measured gains/costs, the applied
transition and its next observation. Rollback is a distinct event. Unmeasured
padding is excluded. Coverage reports permitted proposals, permitted axes and
nonzero actions separately. Mean axis pmax versus improvement ECE is a diagnostic,
not calibrated joint success probability. Expert-label ECE is a different target.

No-action stopping is on by default: unchanged gains in deterministic simulation
return the measured best without another trial. Use stop_on_no_action=False
when repeated observations are required. Plateau early stopping is separate and
off by default. When enabled, stopped plants leave the active
simulation set; actual_simulations counts calls per plant, including prior runs.
Plot history carries the last measured best forward without pretending to spend
more experiments. ValueNet/lookahead is opt-in, tested for execution, and not a
claimed gain; interval_refine is implemented but unused by the production loop.

Expert data uses 21 single-axis candidates plus a combined trial, an initial
measurement and any rejected-combination remeasurement. Real counters are returned
by `expert.generate`; 22 is the candidate count, not total cost per state.
The shipped checkpoint used a 90/10 split with seed 0. A0 now reuses that split;
the current study still has one trained checkpoint, not replicated training seeds.

`two_mass` is validation data used for design. The fixed-grid thermal_deadtime
family was frozen after training and has now been re-evaluated after correctness
repairs. It is not a prospective or untouched-after-publication study. See
[BENCHMARK](BENCHMARK.md), [ABLATION](ABLATION.md), [ABSTENTION](ABSTENTION.md),
[COMPUTE](COMPUTE.md), [CLAIMS](CLAIMS.md) for current generated evidence.

## 简体中文

本仓库是PID试验场与部分可复用数值决策组件。完整闭环仍固定三个PID轴、乘法更新、
响应特征、阶跃目标及PID回滚规则，不能只替换两个函数就成为领域中性框架。

| 层 | 执行路径 | 契约 |
| :--- | :--- | :--- |
| 观测 | `state.build_state` | PID专用20维特征与2×64曲线 |
| 后端 | `decision.NumericBackend` / `OnnxBackend` | 一次前向、每轴温度、Choice/Score/Noul类型输出 |
| 解码 | `decode.decide` | 有序数值载荷期望、方差缩步、完整CP监测与可选按轴否决 |
| 执行 | `decode.apply_step` | 有界PID增益乘法更新 |
| 测量 | `evaluate.evaluate_head` | 每个活跃对象一次仿真，观测对应实际执行参数 |
| 回退 | 独立确定性门 | 测得J > max(3×best+1,8)后提议0.6×best，最多四次回滚 |
| 返回 | 已测历史最优 | 增益与J同步保存，包含最后测量 |

类型层处于主执行路径。`load_backend`读取`models/calibration.json`，CLI/demo/MCP复用该加载器。
MATLAB和C使用导出的温度与策略快照；权重或校准变化后必须重新导出。

默认温度缩放后构建完整CP集合，采用monitor模式。集合构建与执行解耦：完整概率分布仍驱动期望与方差缩步。
hard_hold显式恢复空集、过宽或正负冲突的历史按轴否决。conformal_would_hold/conformal_reason保存独立诊断，
held/reason表示真实执行决策。旧pmax可显式组合、默认关闭；Noul与事后回滚独立。
实验性联合风险分类器评价完整proposal，不逐轴遮罩；见[JOINT_RISK](JOINT_RISK.md)。
独立的[联合风险多轮研究](JOINT_RISK_ROLLOUT.md)冻结该风险模型和温度，在已固定的前缀策略下，
逐候选步使用新独立对象批次校准，并在各步分配固定轨迹风险预算。停止与无动作不伪造下一次测量；
被拒绝提案仅作离线反事实诊断，其结果不反馈给执行轨迹。配对monitor对照使用相同停止规则。
该研究控制器在安全阈值处停止，不执行生产闭环中未经此风险头校准的回滚提案。
验收只涉及已注册的模拟对象分布、起点、目标与有限时域；不因此开启通用CLI、MCP、C或MATLAB
联合风险门。范围或候选策略改变后需要独立重校准与验证。
轨迹有害事件指探索试验中出现严格正的代价上升，不等于失稳或返回的历史实测最优控制器恶化。
通过提前停止得到的低事件率，必须和活动率、最终代价及实验预算一起验收。
实际q_hat与经验覆盖见[CONFORMAL](CONFORMAL.md)。
保证仅针对交换性条件下逐轴专家标签的边际包含率，不保证多轴联合、自适应轨迹或闭环安全。
温度拟合、CP拟合与评估分别使用独立对象样本；有限经验评估可低于名义水平。

每条有效日志关联测量ID、实测增益与代价、实际转移和下一观测；回滚单独归因，未测padding剔除。
覆盖率分别报告至少一轴获准、逐轴获准和实际非零动作。平均轴pmax与改善结果之间的ECE只是诊断，
不是联合成功概率校准；专家标签ECE是另一目标。

默认在确定性仿真中参数不变时停止重复试验，返回已测最优；需要重复观测时设置stop_on_no_action=False。
平台期早停是另一选项，默认关闭。启用时停止对象退出活跃仿真集合，actual_simulations记录含先验的逐株真实消耗；
绘图历史沿用最后最优值而不伪造实验。ValueNet/lookahead默认关闭，可选分支已验证可执行，
不宣传其收益；interval_refine已实现但不在生产路径。

专家数据每步含21个单轴候选、一个组合候选，还需初始测量及拒绝组合后的重测。
`expert.generate`返回实际计数，22是候选数，不是每状态全部成本。
出厂权重使用seed 0的90/10划分，A0现复用该划分；当前仍只有一组训练权重，未重复训练种子。

two_mass参与过设计，属于验证数据。固定网格thermal_deadtime在训练后冻结，本轮正确性修复后重新评测，
不是预注册或发布后从未接触的测试。当前证据见[BENCHMARK](BENCHMARK.md)、[ABLATION](ABLATION.md)、
[ABSTENTION](ABSTENTION.md)、[COMPUTE](COMPUTE.md)与[CLAIMS](CLAIMS.md)。
