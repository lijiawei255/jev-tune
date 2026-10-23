# TRANSFER

[English](#english) · [简体中文](#简体中文)

## English

This repository supplies a reproducible PID testbed and reference components
for typed probabilities, temperature scaling, split conformal sets, axis-wise abstention and a
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
family rerun after repairs. Training-seed replication, full learning curves,
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

本仓库提供可复现PID试验场，以及类型化概率、温度缩放、分裂CP集合、按轴弃权、独立事后回退的参考组件。
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

two_mass是设计/验证数据，thermal_deadtime是训练后冻结、本轮修复后重测的族。
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
