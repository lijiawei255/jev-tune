# ARCHITECTURE

[English](#english) · [简体中文](#简体中文)

## English

<!-- trajectory-risk-v2:en:start -->
### Multistep joint risk: new preregistered study FAIL

The sole primary candidate is `trajectory_selected`; status is `research_only`. On 1024 new independent test plants, 8 trajectories had a harmful execution. The nominal one-sided 95% binomial risk upper bound is 0.014052; the nominal first-execution lower bound is 0.559971. Implementation assumptions are audited below. Primary/matched-monitor final mean J is 2.158651/1.357796, p90 J is 3.149694/2.294926, and actual operating simulations are 2770/21504. Failed criteria: final mean cost noninferiority (`empirical_mean_cost_noninferior`); final p90 cost noninferiority (`empirical_p90_cost_noninferior`). Final mean and p90 are compared with monitor with zero slack; reducing harmful exploration alone does not pass the complete acceptance.

The v1 failure is preserved. Old tests have been used for retrospective diagnosis and cannot independently validate the new design. Only the primary candidate fixed before data is assessed for acceptance on the new test; explanatory arms cannot be selected for deployment after testing. The new comparison changes training trajectories, data volume, scaling and initial risk-feature semantics together; it is not a single-factor causal experiment.

On the recorded old paths, preserving the monitor optimum requires a harmful transition for 700/1024 plants. Thus a gate that only truncates those paths cannot meet both the original risk and zero-slack mean criteria. This is a finite-record diagnosis, not an impossibility theorem for all new policies. Alternative joint actions can change paths; their success is decided by the measured new acceptance.

See the [old failure diagnosis](ROLLOUT_DIAGNOSIS.md), [full new study](TRAJECTORY_RISK.md), and their JSON/raw shards. General Python/C/MATLAB deployment defaults remain unchanged. Passing numerical criteria alone cannot bypass the separate implementation-validity audit or expand the registered runner, population and horizon.

**Additional implementation-validity audit: NOT ESTABLISHED; deployment_allowed=false.** Frozen numerical criteria and this audit are separate. Observed dependence on batch shape/row position leaves a canonical per-object mapping, calibration/test CP-score exchangeability, and independence of trajectory events unestablished in this run. The CP and one-sided 95% binomial quantities are therefore nominal calculations, not established exact CP/PAC guarantees for this machine implementation. A generic exchangeability disclaimer does not close this gap. This is an additional failure beyond the frozen numerical acceptance; deployment remains prohibited. A fixed inference mapping, fresh calibration and new prospective validation are required. See the [implementation-validity audit](../research/results/trajectory_risk_validity.json).

Pairing fixes initial plants and observations; it does not require bitwise-identical cross-arm proposals or histories under different active batch layouts. Each arm retains its own actual actions, strict zero-tolerance labels, CP sets and history accounting; no new acceptance tolerance is fitted to test differences. [Pairing diagnosis](../research/results/trajectory_risk_pairing_diagnosis.json). Across full-action comparisons, 24/5348 matched proposal rows differ exactly; the largest recorded base_step difference is 7.28422891e-08. These dependent rows are not independent observations, and later state differences cannot all be attributed to one inference-rounding event. The [Fixed-input batch diagnosis](../research/results/batch_inference_diagnosis.json) charges 1 additional diagnostic simulations. Repeating identical inputs at different batch shapes/row positions gives a maximum base_step difference of 1.24583552e-07. This is a post-hoc numerical mechanism check, not reconstruction of the full original cohort or new independent acceptance; recorded actions and boundaries remain unchanged.

The risk head is trained on multiple stages. Initial prev_dJ is zeroed only in risk inputs; proposal inputs remain unchanged. At each stage the frozen risk model first selects a complete joint action at a scale in [1, 0.5, 0.25]. CP assesses only that selected action: only {noninferior} executes, and rejection stops without selecting again from the sets.
For reached-quota arms, the per-stage target is 2000, capped at 20000 initial plants; the fixed-initial-sample control separately records actual reached counts. Sampling continues only according to reaching the frozen prefix, never according to target labels/scores; quota shortfall uses the full set.
Training and temperature fitting may contain dependent rows within a plant; these are not independent calibration observations. Calibration stages and the final test draw fresh plants, but independent draws alone do not remove batch-dependent execution mappings. CP marginal coverage applies only after exchangeability and the other premises are established; it is still not conditional on every fitted calibration file, a risk fraction among accepted actions, or a closed-loop performance benefit.

| arm | harmed/total plants | nominal risk upper | nominal first-execution lower | mean J | p90 J | actual operating simulations |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `monitor` | 983/1024 | 0.969528 | 0.997079 | 1.357796 | 2.294926 | 21504 |
| `old_initial512` | 0/1024 | 0.002921 | 0.148060 | 2.544516 | 3.657641 | 1195 |
| `old_reached2000` | 5/1024 | 0.010239 | 0.465069 | 2.317541 | 3.409565 | 1888 |
| `trajectory_full` | 6/1024 | 0.011532 | 0.574731 | 2.146460 | 3.150350 | 2265 |
| `trajectory_selected` | 8/1024 | 0.014052 | 0.559971 | 2.158651 | 3.149694 | 2770 |

Actual study simulations: 513508 total; 93666 training/temperature/development, 386124 stage calibration, 33718 final evaluation. Table operating counts exclude separately charged offline diagnostics.
Harm is a strict immediate increase in J, not instability or degradation of returned parameters; returns use only actually executed historical best observations. The separate nominal one-sided 95% risk/activity quantities are not joint 95% confidence; their individual implementation assumptions are also unestablished in this run. Changed populations, noise, starts, horizon, action selection or recovery require new calibration and validation.
<!-- trajectory-risk-v2:en:end -->

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
family was frozen after training and re-evaluated during the earlier correctness
repairs. It is not a prospective or untouched-after-publication study. See
[BENCHMARK](BENCHMARK.md), [ABLATION](ABLATION.md), [ABSTENTION](ABSTENTION.md),
[COMPUTE](COMPUTE.md), [CLAIMS](CLAIMS.md) for current generated evidence.

## 简体中文

<!-- trajectory-risk-v2:zh:start -->
### 多步联合风险：预注册新实验 FAIL

唯一主要候选为`trajectory_selected`；状态为`research_only`。在1024个新独立测试对象上，8条轨迹出现有害执行，风险的名义单侧95%二项上界为0.014052，首步执行率名义下界为0.559971；本轮实现的统计前提另见下文。主要候选/配对monitor的最终mean J为2.158651/1.357796，p90 J为3.149694/2.294926，实际运行仿真数为2770/21504。未通过项：最终平均代价非劣 (`empirical_mean_cost_noninferior`); 最终p90代价非劣 (`empirical_p90_cost_noninferior`)。最终mean与p90均按零松弛要求和monitor比较；仅减少有害探索事件不足以通过全部验收。

旧v1失败结果保留。旧测试已经用于事后诊断，不能再作新方案的独立验证；本轮只用新测试验收事先指定的主要候选，其他组不按测试成绩选优上线。本轮同时改变训练轨迹、数据量、标准化和风险初态特征语义，是整体方案比较，不是单因素因果实验。

旧固定路径诊断发现700/1024株保留monitor最优必须经过有害步。这证明旧记录中仅截断、不改提案的门控无法同时满足原风险与零松弛均值条件；不证明所有新策略都不可能。替代联合动作可改变路径，但是否成功由本轮真实验收决定。

见[旧失败诊断](ROLLOUT_DIAGNOSIS.md)、[新完整研究](TRAJECTORY_RISK.md)及其JSON/原始分片。通用Python/C/MATLAB部署默认保持原样；即使数值判据通过，也不能绕过独立实现有效性审计或扩展注册的运行器、模拟分布和时域。

**额外的实现有效性审计：未建立；deployment_allowed=false。** 冻结数值判据与这一审计分开报告。本轮批次形状/行位置引起的输出依赖，使逐对象固定映射、校准/测试CP分数交换性及轨迹事件独立性均未建立。因此表内CP及单侧95%二项量只作名义计算，不能宣称本机器实现已获得精确CP/PAC保证；仅写一般交换性假设不足以弥补这一缺口。这是原数值验收之外的额外失败，继续禁止部署；需固定推理映射、重新校准和新的前瞻验证。 见[实现有效性审计](../research/results/trajectory_risk_validity.json)。

配对指相同初始对象与观测，不要求活跃批次不同的跨组提案/轨迹逐位相同。每组仍按自身真实动作、严格零容差标签、CP集合与历史计账；不从测试差异拟合新的验收容差。 [配对数值诊断](../research/results/trajectory_risk_pairing_diagnosis.json)。 完整动作对照合计24/5348个配对提案行不逐位相等，最大记录base_step差为7.28422891e-08；这些相关行不是独立样本，后续状态差异不能全部归因为一次推理舍入。 [固定输入批次诊断](../research/results/batch_inference_diagnosis.json)另计1次诊断仿真；相同输入复制到不同批次/行位置时，base_step最大差为1.24583552e-07。这是事后数值机制检查，未重建原完整批次，不是新的独立验收，未改动原始动作或边界。

风险头使用多轮训练；仅风险输入初态prev_dJ置零，提案头输入不变。每步先从完整联合动作尺度[1, 0.5, 0.25]中按冻结风险模型选候选，再对已选动作作CP；只接受{非劣}，拒绝即停，不因集合内容重新挑动作。
采用到达配额的组，目标逐步到达数为2000，每步初始对象上限20000；固定初始样本对照另按协议记录实际到达数。只按冻结前缀的到达条件继续采样，不看目标标签/分数决定是否补样；配额不足完整集合回退。
训练与温度拟合可有同株相关行；这些行不当作独立校准样本。逐步校准与最终测试分别抽取新对象，但独立抽对象本身不能消除批次相关的执行映射。只有交换性等前提建立后，CP边际覆盖定理才适用；它仍不等于每个固定校准文件的条件保证、获准动作风险比例界或闭环代价收益。

| 组 | 有害轨迹/对象 | 名义风险上界 | 名义首步执行下界 | mean J | p90 J | 实际运行仿真 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `monitor` | 983/1024 | 0.969528 | 0.997079 | 1.357796 | 2.294926 | 21504 |
| `old_initial512` | 0/1024 | 0.002921 | 0.148060 | 2.544516 | 3.657641 | 1195 |
| `old_reached2000` | 5/1024 | 0.010239 | 0.465069 | 2.317541 | 3.409565 | 1888 |
| `trajectory_full` | 6/1024 | 0.011532 | 0.574731 | 2.146460 | 3.150350 | 2265 |
| `trajectory_selected` | 8/1024 | 0.014052 | 0.559971 | 2.158651 | 3.149694 | 2770 |

全研究实际仿真513508次：训练/温度/开发93666，逐步校准386124，最终评估33718。表内运行计数与另行计账的离线诊断分开。
有害指即时J严格上升，不等于失稳或最终返回参数恶化；返回值只取实际执行历史最优。风险和首步活动率的名义单侧95%量分别计算，不构成联合95%置信；本轮实现的各自统计前提也尚未闭合。改变模拟分布、噪声、起点、时域、动作选择或恢复规则后，需要新校准与新验证。
<!-- trajectory-risk-v2:zh:end -->

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

two_mass参与过设计，属于验证数据。固定网格thermal_deadtime在训练后冻结，此前正确性修复后重新评测，
不是预注册或发布后从未接触的测试。当前证据见[BENCHMARK](BENCHMARK.md)、[ABLATION](ABLATION.md)、
[ABSTENTION](ABSTENTION.md)、[COMPUTE](COMPUTE.md)与[CLAIMS](CLAIMS.md)。
