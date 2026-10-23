# TRANSFER

[English](#english) · [简体中文](#简体中文)

## English

<!-- practical-mainline:en:start -->
**Current mainline: real-model adaptation, applicability boundaries and simulation-budget value.**
Deeper joint-risk research is paused. Its failed acceptance, raw trajectories, frozen protocols and reproduction scripts remain available; the risk head stays in research mode and is not enabled in production. Complete CP sets and their existing coverage boundaries remain unchanged.
On the current checkout, use `python scripts/44_verify_historical_research.py --check` to verify the frozen research against an isolated historical source view. Original study commands remain available on v0.8.0; they must not silently substitute today's repaired runtime for their recorded sources.

The practical audit prioritizes controller equivalence, unambiguous measurements, time-based costs, truthful failure status and complete simulation accounting. See [MODEL_ADAPTATION](MODEL_ADAPTATION.md) and [PRACTICAL_BUDGET](PRACTICAL_BUDGET.md). Generated Simulink fixtures validate adapter behavior; they do not establish performance on an unseen external model or physical hardware.

Earlier MATLAB cost figures, traces and animations below are historical: the corrected time-grid integration changes that objective. They are retained as records, not current performance measurements.
Cross-job model/sweep caching is disabled to preserve each source model and configuration; historical warm-job throughput tables do not describe the current implementation.
<!-- practical-mainline:en:end -->


<!-- trajectory-risk-v2:en:start -->
### Multistep joint risk: new preregistered study FAIL

The sole primary candidate is `trajectory_selected`; status is `research_only`. On 1024 new independent test plants, 8 trajectories had a harmful execution. The nominal one-sided 95% binomial risk upper bound is 0.014052; the nominal first-execution lower bound is 0.559971. Implementation assumptions are audited below. Primary/matched-monitor final mean J is 2.158651/1.357796, p90 J is 3.149694/2.294926, and actual operating simulations are 2770/21504. Failed criteria: final mean cost noninferiority (`empirical_mean_cost_noninferior`); final p90 cost noninferiority (`empirical_p90_cost_noninferior`). Final mean and p90 are compared with monitor with zero slack; reducing harmful exploration alone does not pass the complete acceptance.

The v1 failure is preserved. Old tests have been used for retrospective diagnosis and cannot independently validate the new design. Only the primary candidate fixed before data is assessed for acceptance on the new test; explanatory arms cannot be selected for deployment after testing. The new comparison changes training trajectories, data volume, scaling and initial risk-feature semantics together; it is not a single-factor causal experiment.

On the recorded old paths, preserving the monitor optimum requires a harmful transition for 700/1024 plants. Thus a gate that only truncates those paths cannot meet both the original risk and zero-slack mean criteria. This is a finite-record diagnosis, not an impossibility theorem for all new policies. Alternative joint actions can change paths; their success is decided by the measured new acceptance.

See the [old failure diagnosis](ROLLOUT_DIAGNOSIS.md), [full new study](TRAJECTORY_RISK.md), and their JSON/raw shards. General Python/C/MATLAB deployment defaults remain unchanged. Passing numerical criteria alone cannot bypass the separate implementation-validity audit or expand the registered runner, population and horizon.

**Additional implementation-validity audit: NOT ESTABLISHED; deployment_allowed=false.** Frozen numerical criteria and this audit are separate. Observed dependence on batch shape/row position leaves a canonical per-object mapping, calibration/test CP-score exchangeability, and independence of trajectory events unestablished in this run. The CP and one-sided 95% binomial quantities are therefore nominal calculations, not established exact CP/PAC guarantees for this machine implementation. A generic exchangeability disclaimer does not close this gap. This is an additional failure beyond the frozen numerical acceptance; deployment remains prohibited. A fixed inference mapping, fresh calibration and new prospective validation are required. See the [implementation-validity audit](../research/results/trajectory_risk_validity.json).

Pairing fixes initial plants and observations; it does not require bitwise-identical cross-arm proposals or histories under different active batch layouts. Each arm retains its own actual actions, strict zero-tolerance labels, CP sets and history accounting; no new acceptance tolerance is fitted to test differences. Strict scientific-evidence reconstruction and exact canonical-record replay are verified within the recorded reference environment; Python/C99 runtime portability does not imply bitwise reproduction of study trajectories across platforms. See the [release verification scope](RELEASE_VERIFICATION.md). [Pairing diagnosis](../research/results/trajectory_risk_pairing_diagnosis.json). Across full-action comparisons, 24/5348 matched proposal rows differ exactly; the largest recorded base_step difference is 7.28422891e-08. These dependent rows are not independent observations, and later state differences cannot all be attributed to one inference-rounding event. The [Fixed-input batch diagnosis](../research/results/batch_inference_diagnosis.json) charges 1 additional diagnostic simulations. Repeating identical inputs at different batch shapes/row positions gives a maximum base_step difference of 1.24583552e-07. This is a post-hoc numerical mechanism check, not reconstruction of the full original cohort or new independent acceptance; recorded actions and boundaries remain unchanged.

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

This repository supplies a reproducible PID testbed and reference components
for typed probabilities, temperature scaling, split conformal sets, independent optional axis-wise abstention and a
separate post-measurement fallback. It has not been evaluated on VLA, robots,
neuromodulation or medical devices. Full-loop portability requires new action
semantics, observations, objectives, data and verification.

| Component | Reuse boundary |
| :--- | :--- |
| Choice/Score/Noul and backend protocol | reusable data/interface pattern; numeric backend and question registry are PID-trained |
| `decide` without ActionSpace | ordered numeric Option.delta payloads, arbitrary axis count, caller-specified max_step |
| `decide` with PID ActionSpace | validates payloads against that single schema; mismatches raise ValueError |
| temperature/variance/abstention | reusable mathematics; fit labels and thresholds again for the new domain |
| evaluator/simulator/features/checkpoint | PID-specific three-axis implementation, not an injectable universal runner |
| rollback to 0.6×best | PID experiment heuristic, not a general safe recovery action |
| MATLAB/C inference | exported fixed PID network; retrain/re-export new schemas and verify numerical policies |

[The additive two-axis toy](../examples/linear_decoder_shell/README.md) exercises
non-PID names, distinct payloads and an external actuator. It validates the
numeric decoder interface only; it is not a trained second-domain controller.
Unordered actions such as hold/retreat/hand-back must use categorical selection:
averaging their payloads does not define a meaningful action.

For VLA research, scene descriptors could replace response features and a
separate envelope checker could veto actions. This repository provides no
vision encoder, navigation/manipulation results, perception-stack latency or
sim-to-real evidence. Ask first: can options be enumerated and bounded; where
can outcome labels be obtained without unsafe exploration; what independent
checker owns limits; what happens on repeated abstention; who receives an
escalation flag? A flag here has no external recipient or controller service.

For neuromodulation research, an offline state score and bounded parameter
proposal are only conceptual analogues. This repository supplies no physiology,
subject data, dose/stimulation protocol, clinical safety analysis or regulatory
work. Hardware/clinical hard limits, SQI, watchdogs, cooldown and escalation
cannot be delegated to this head. Risk can be asymmetric and multi-objective;
the symmetric PID decoder is not a recommended physiological policy.

Any port must define units, numeric versus categorical actions, labels and
sampling cost, temporal state, objective, tolerated error, quantisation, input
sanity and fault actions. Python rejects nonfinite inputs/logits, illegal
temperatures and invalid probabilities; this API check does not detect every
sensor fault or distribution shift. Holding prevents this proposal's change;
it does not prove the current parameters are stable. Repeated abstention must
be handled by a domain-owned state machine, with an independently validated
fallback rather than an assumed universal decay.

Training and adaptation are different costs. The backbone learns offline from
resettable simulations: 21 probes plus a combined trial per state, initial
measurements and rejection remeasurements. Real counters replace the old
22×states total-cost shorthand. Calibration-only freezes weights but still
needs labeled simulated transitions; T changes the continuous action as well
as confidence. Read [CALIBRATE_ONLY](CALIBRATE_ONLY.md) for T-only/tau-only/
combined arms and actual sampling cost. No small-sample-from-scratch or clinical
transfer claim follows. [tracking.json](../research/results/tracking.json) and
[SPECIALIZE](SPECIALIZE.md) include specialization failures.

two_mass is design/validation data; thermal_deadtime is a post-training frozen
family rerun during earlier repairs. Training-seed replication, full learning curves,
many-question scaling, broad hosted-model comparisons, mid-run regime changes
and target-board WCET remain unmeasured. Host float C inference and weight-only
fake-quantisation are not MCU/FPGA support or full integer kernels.

**Non-clinical, non-safety-critical:** research software, not certified or
validated for medical devices, human subjects, vehicles or industrial interlocks.
It must not make decisions in those settings. Nothing here is medical advice.
Cite the versioned software ([CITATION.cff](../CITATION.cff)) as an open testbed
with measured evidence, not a validated robot/clinical controller. Related
background includes Simplex runtime assurance, shielding and selective prediction;
those ideas do not confer their guarantees on this implementation.

## 简体中文

<!-- practical-mainline:zh:start -->
**当前主线：真实模型适配、适用边界与仿真预算收益。**
暂停深化联合风险研究，保留未通过验收的结论、原始轨迹、冻结协议及复现脚本；风险头继续保留研究模式，不进入生产默认路径。完整CP集合及既有覆盖边界保持不变。
当前检出用`python scripts/44_verify_historical_research.py --check`在隔离的历史源码视图中核验冻结研究。原研究命令保留在v0.8.0，不能偷偷用今天修复后的运行时代替原记录源码。

实用审查优先保证控制器转换等价、测量对象明确、代价按真实时间计算、失败状态准确，以及仿真计账完整。见[MODEL_ADAPTATION](MODEL_ADAPTATION.md)和[PRACTICAL_BUDGET](PRACTICAL_BUDGET.md)。生成的Simulink回归模型用于验证适配器行为，不证明未见外部模型或硬件上的调参效果。

下方旧MATLAB代价、轨迹及动画为历史记录：按实际时间网格积分的修正已改变目标，旧记录不代表当前性能测量。
为保留各任务原件及配置语义，跨任务模型与扫描缓存已停用；历史热启动吞吐表不代表当前实现。
<!-- practical-mainline:zh:end -->


<!-- trajectory-risk-v2:zh:start -->
### 多步联合风险：预注册新实验 FAIL

唯一主要候选为`trajectory_selected`；状态为`research_only`。在1024个新独立测试对象上，8条轨迹出现有害执行，风险的名义单侧95%二项上界为0.014052，首步执行率名义下界为0.559971；本轮实现的统计前提另见下文。主要候选/配对monitor的最终mean J为2.158651/1.357796，p90 J为3.149694/2.294926，实际运行仿真数为2770/21504。未通过项：最终平均代价非劣 (`empirical_mean_cost_noninferior`); 最终p90代价非劣 (`empirical_p90_cost_noninferior`)。最终mean与p90均按零松弛要求和monitor比较；仅减少有害探索事件不足以通过全部验收。

旧v1失败结果保留。旧测试已经用于事后诊断，不能再作新方案的独立验证；本轮只用新测试验收事先指定的主要候选，其他组不按测试成绩选优上线。本轮同时改变训练轨迹、数据量、标准化和风险初态特征语义，是整体方案比较，不是单因素因果实验。

旧固定路径诊断发现700/1024株保留monitor最优必须经过有害步。这证明旧记录中仅截断、不改提案的门控无法同时满足原风险与零松弛均值条件；不证明所有新策略都不可能。替代联合动作可改变路径，但是否成功由本轮真实验收决定。

见[旧失败诊断](ROLLOUT_DIAGNOSIS.md)、[新完整研究](TRAJECTORY_RISK.md)及其JSON/原始分片。通用Python/C/MATLAB部署默认保持原样；即使数值判据通过，也不能绕过独立实现有效性审计或扩展注册的运行器、模拟分布和时域。

**额外的实现有效性审计：未建立；deployment_allowed=false。** 冻结数值判据与这一审计分开报告。本轮批次形状/行位置引起的输出依赖，使逐对象固定映射、校准/测试CP分数交换性及轨迹事件独立性均未建立。因此表内CP及单侧95%二项量只作名义计算，不能宣称本机器实现已获得精确CP/PAC保证；仅写一般交换性假设不足以弥补这一缺口。这是原数值验收之外的额外失败，继续禁止部署；需固定推理映射、重新校准和新的前瞻验证。 见[实现有效性审计](../research/results/trajectory_risk_validity.json)。

配对指相同初始对象与观测，不要求活跃批次不同的跨组提案/轨迹逐位相同。每组仍按自身真实动作、严格零容差标签、CP集合与历史计账；不从测试差异拟合新的验收容差。严格科学证据重建及规范化记录的精确重放，验证范围限于记录的参考环境；Python/C99运行时的跨平台支持不意味着研究轨迹可跨平台逐位复现。见[发布验证范围](RELEASE_VERIFICATION.md)。 [配对数值诊断](../research/results/trajectory_risk_pairing_diagnosis.json)。 完整动作对照合计24/5348个配对提案行不逐位相等，最大记录base_step差为7.28422891e-08；这些相关行不是独立样本，后续状态差异不能全部归因为一次推理舍入。 [固定输入批次诊断](../research/results/batch_inference_diagnosis.json)另计1次诊断仿真；相同输入复制到不同批次/行位置时，base_step最大差为1.24583552e-07。这是事后数值机制检查，未重建原完整批次，不是新的独立验收，未改动原始动作或边界。

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

本仓库提供可复现PID试验场，以及类型化概率、温度缩放、完整CP集合、独立可选按轴弃权、独立事后回退的参考组件。
尚未在VLA、机器人、神经调控或医疗设备上评测。完整迁移需要重新设计动作、观测、目标、数据与验收。

| 组件 | 复用边界 |
| :--- | :--- |
| Choice/Score/Noul与后端协议 | 可复用数据/接口模式，具体数值后端和问题注册表基于PID训练 |
| 不传ActionSpace的decide | 有序数值Option.delta、任意轴数、调用方指定max_step |
| 显式PID ActionSpace | 载荷必须匹配唯一schema，否则抛ValueError |
| 温度/方差/弃权 | 数学函数可复用，标签和阈值需在新域重新拟合 |
| evaluator/仿真/特征/权重 | PID三轴实现，不是可注入的通用闭环框架 |
| 0.6×best回滚 | PID实验启发式，不是通用安全恢复动作 |
| MATLAB/C | 固定PID网络导出，新schema需重训重导出并验证策略 |

[两轴加法玩具示例](../examples/linear_decoder_shell/README.md)使用非PID名称、不同载荷与外部执行器，
只验证数值解码接口，不代表已训练第二领域控制器。“保持/退回/交还”等无序类别应采用独立类别选择，
不能对载荷求期望混合后当成有效动作。

VLA研究可借鉴“场景描述→小头→独立约束检查”的形态，但本仓库没有视觉编码器、导航/操作结果、
感知栈延迟或sim-to-real证据。移植前需回答：动作能否枚举和约束，结果标签从哪里安全获取，
谁独立执行硬限制，连续弃权如何处理，谁接收升级标记。本项目的标记没有外部接收服务。

神经调控中的离线状态评分和有界提案仅是概念映射。本仓库不提供生理数据、受试者数据、刺激协议、
临床安全分析或监管材料；硬限制、SQI、看门狗、冷却及升级不能交给此模型。
风险可能非对称且多目标，对称PID解码器不能直接作为生理控制策略。

任何移植均需定义单位、数值/类别动作、标签与采样成本、时序状态、目标、容错、量化、输入检查及故障动作。
Python拒绝非有限输入/logits、非法温度与概率，但这不检测所有传感器故障或域偏移。
保持仅阻止本次提案改变参数，不证明当前参数稳定；连续弃权由领域外壳处理，回退必须独立验证，
不能假设普适安全衰减规则。

离线预训练与适配成本不同。专家每状态有21个单轴及一个组合候选，另需初测和拒绝后的重测；
实际计数取代22×状态数的总成本简写。仅校准冻结权重，但仍需带标签模拟转移；T同时改变连续动作与置信度。
见[CALIBRATE_ONLY](CALIBRATE_ONLY.md)的T-only/tau-only/combined和实际采样账目。
不能据此宣称小样本从零训练或临床迁移成功。[tracking.json](../research/results/tracking.json)及
[SPECIALIZE](SPECIALIZE.md)保留专门化失败。

two_mass是设计/验证数据，thermal_deadtime是训练后冻结、此前修复后重测的族。
训练种子重复、完整学习曲线、多问题扩展、广泛托管模型对照、中途工况突变、目标板WCET仍未测。
宿主浮点C与仅权重量化敏感性实验不代表MCU/FPGA支持或全整数kernel。

**非临床、非安全关键：** 本软件仅供研究，未经医疗器械、人体、车辆或工业联锁认证或验证，
不得在这些场景执行决策，不构成医疗建议。引用[CITATION.cff](../CITATION.cff)对应的软件版本，
将其称为有测量证据的开放试验场，不称已验证机器人/临床控制器。Simplex、shielding、selective prediction
可作背景阅读，但这些思想的保证不会自动适用于本实现。


## Split conformal transfer boundary / 分裂CP迁移边界

The new default CP uses a frozen network and independent temperature-fit, CP-fit
and evaluation plants. Its finite-sample theorem concerns per-axis teacher-label
inclusion under exchangeability on initial states. It is not a joint-axis,
selected-action, adaptive-loop or safety guarantee. Changing T, weights, label
semantics or distribution requires independent recalibration and validation.
The third axis in the held-out finite sample is below the nominal level; no
threshold was reselected to conceal it. The actual numbers are generated in
[CONFORMAL](CONFORMAL.md), and comparative costs in [ABLATION](ABLATION.md).

新默认CP使用冻结网络和独立温度拟合/CP拟合/评估对象。有限样本定理针对初态交换性下的逐轴
专家标签包含率，不等于多轴联合、获准动作条件子集、自适应闭环或安全保证。改变T、权重、标签或分布后
需要独立重校准与验证。有限留出样本的第三轴低于名义水平，未重选阈值掩盖；实际数字由
[CONFORMAL](CONFORMAL.md)生成，代价对比见[ABLATION](ABLATION.md)。

The deployment default monitors complete CP sets without changing proposals.
This retains the original label-set inclusion statement on exchangeable inputs;
it adds no guarantee for states reached by a changed policy. No-action stopping
is for deterministic repeated trials, not a reason to stop physical monitoring.
[JOINT_RISK](JOINT_RISK.md) calibrates the actual joint proposal on fresh initial
states. Its unconditional harmful-execution bound is neither a conditional
accepted-action risk bound nor a trajectory guarantee. The risk head is a
research artifact, not silently enabled in Python/C/MATLAB deployment.

[JOINT_RISK_ROLLOUT](JOINT_RISK_ROLLOUT.md) is a separate finite-horizon study.
Each step receives a preregistered error budget and independent calibration
plants that reach it under the frozen prefix policy. Summing valid stepwise
bounds uses a union bound, not an assumption that steps within a plant are IID.
Stopped plants contribute no harmful-execution event; they are not fabricated
covered calibration examples. The numerical test calculation treats each complete
plant trajectory as one Bernoulli observation and reports a nominal exact-binomial
one-sided quantity. Independent input plants alone do not prove independent
implemented trajectory events when inference depends on the active batch context.
That premise and CP-score exchangeability require separate verification; the
current unresolved implementation gap is reported in [TRAJECTORY_RISK](TRAJECTORY_RISK.md).
This numerical criterion is distinct from a valid CP marginal theorem over
calibration and a fresh draw, whose implementation premises must also hold.

Passing frozen numerical criteria, if achieved, cannot replace that implementation
validity audit or expand the stated simulator population and controller.
MATLAB sweep-derived starts, new objectives, changed
noise, shifted families, hardware constraints and extra fallback actions require
new evidence. An endpoint cannot expand the scope by accepting arbitrary options
or trusting a saved `passed` flag without checking the bound artifacts. A scalar
cost noninferiority label does not certify transient constraints or physical safety.
Conversely, an exploration trajectory containing a cost increase does not imply
an unstable or worse returned controller: both arms return the measured best.
Event frequency, final performance and the amount of exploration are different
quantities and must be reported together.

部署默认仅监测完整集合而不修改提案。原标签包含性质在交换性输入上保留，但新策略访问的状态
不会自动继承保证。无动作停止适用于确定性重复试验，不意味着停止物理监测。
[JOINT_RISK](JOINT_RISK.md)用新初态样本校准实际联合提案；无条件有害执行概率界不等于
获准动作条件风险界，也不保证整段轨迹。风险头是研究产物，不默认接入Python/C/MATLAB部署。

[JOINT_RISK_ROLLOUT](JOINT_RISK_ROLLOUT.md)另行开展有限步研究。每步事先分配错误预算，
使用在已冻结前缀策略下到达该步的新独立对象校准。用并集界合成逐步概率界，不假设同一对象
轨迹内的各步是IID。停止对象不再产生有害执行事件，也不能伪填为已覆盖校准样本。
数值测试计算将每株完整轨迹视为一条Bernoulli观测，报告名义精确单侧二项量；
当推理依赖活跃批次上下文时，独立抽取对象不单独证明机器实现的轨迹事件独立。
该前提及CP分数交换性须另行验证，当前未闭合的实现缺口见[TRAJECTORY_RISK](TRAJECTORY_RISK.md)。
这个数值条件不同于对校准与新抽样取边际的有效CP定理，后者的实现前提同样必须成立。

即使通过冻结数值判据，也不能替代实现有效性审计或扩展列明的模拟分布与控制器。MATLAB扫描起点、新目标、噪声变化、
域外族、硬件约束及额外回退动作都需新证据。入口不能通过任意参数或只信任保存的passed标志
扩大适用范围，必须核对绑定产物。标量代价非劣标签不证明瞬态约束或物理安全。
反过来，探索轨迹中曾有代价上升也不意味着失稳或返回控制器恶化：两组都返回历史实测最优。
事件频率、最终性能和探索量是不同指标，必须共同报告。
