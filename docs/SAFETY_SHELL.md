# Calibrated Decision & Safety Shell / 校准决策与安全边界参考壳

[English](#english) · [简体中文](#简体中文)

## English

This project uses PID autotuning as a measured testbed for a separable
**Calibrated Decision & Safety Shell**: typed answers, peripheral calibration,
bounded numeric proposals, explicit refusal policies and independently recorded
fallbacks. The name describes software boundaries and observable decisions;
it does not establish physical safety or a universal controller. It uses the
Jev-inspired interface and this repository's trained models, with no Jev weights
or affiliation; see [JEV_MAPPING](JEV_MAPPING.md).

The reference is intended to make future VLA, closed-loop neuromodulation
research and embedded ports easier to inspect and test. Those are prospective
uses. The implemented non-PID transfer is an offline reference-denoising task,
with its own training, labels and additive actuator. It supplies evidence about
component reuse, not VLA perception, robot behavior, physiology or a clinical
system. Its actual acceptance, objective spend and failures are generated in
[NONPID_TRANSFER](NONPID_TRANSFER.md) and the
[primary JSON](../research/results/nonpid_transfer/report.json).

### Five implemented capabilities and their evidence

| Capability | Actual implementation and evidence | Boundary that remains with the new domain |
| :--- | :--- | :--- |
| Typed decision contract | [`Choice`, `Option`, `Score`, `Noul`, `Answer`](../src/jev_tune/primitives.py), the PID [`DecisionBackend`](../src/jev_tune/decision.py), and [primitive tests](../tests/test_primitives.py) carry distributions and named payloads on the execution path. | The shipped backend, question registry, features, score rubric and weights are PID-specific. Interface reuse does not transfer a learned representation or an outcome probability. |
| Frozen-model peripheral calibration | [`fit_frozen_calibration`](../src/jev_tune/calibration.py) fits per-axis temperatures and then independent split-CP thresholds from frozen logits and labeled sampling-unit IDs. [Calibration tests](../tests/test_frozen_calibration.py) check split separation, finite-sample endpoints and unchanged inputs. [RECALIBRATION](RECALIBRATION.md) supplies generated timings and small-sample diagnostics. | Valid labels, representative sampling, a fixed inference mapping and calibration/test exchangeability must be established. IDs and a supplied model hash alone do not prove those premises. |
| Bounded numeric decoding | [`decide`](../src/jev_tune/decode.py) consumes ordered `Option.delta` payloads, takes the full calibrated expectation, shrinks by vocabulary-normalized variance and clips the step. [Shell tests](../tests/test_shell_contract.py) hold the mean fixed while changing variance and actually exceed the clipping bound. | The caller defines units, coordinate normalization, numeric versus categorical semantics, actuator bounds and transition validity. The PID `apply_step` remains multiplicative and domain-specific. |
| Explicit refusal and separate fallback | `AbstainPolicy`, `ConformalPolicy` and `Decision` retain executed holds, proposed steps, complete CP sets and hypothetical veto reasons. [`evaluate_head`](../src/jev_tune/evaluate.py) records post-measurement rollback as a separate transition; [runtime accounting tests](../tests/test_runtime_accounting.py) and [shell tests](../tests/test_shell_contract.py) exercise the ordering and real call counts. | Holding a parameter does not establish that its present value is safe. The PID rollback rule is a testbed heuristic. A new domain owns safe-state selection, persistent-Hold handling and an independently validated supervisor. |
| Inspectable portability boundary | The C99 [`jev_decide_checked`](../c/jev_head.h) entry validates the fixed PID inference chain and clears actions on rejection. [Checked-shell tests](../tests/test_checked_shell.py), [portable vectors and tests](../tests/test_portability.py), [MATLAB parity evidence](../research/results/matlab_parity_v0100.json) and [runtime evidence](../research/results/matlab_runtime.json) cover specific host implementations. | Fixed PID exports are not generic new-domain firmware. STM32/FPGA work still needs a board implementation, numerical validation, resource measurements and target timing evidence. Host agreement is not hardware qualification. |

### What runs, and what each answer controls

The PID path is `state.build_state` → `NumericBackend.answer` or
`OnnxBackend.answer` → temperature-scaled typed answers → `decide` →
`apply_step` → simulation → measured-best tracking and optional rollback.
`load_backend` reads the checkpoint's calibration. The full PID evaluator,
simulator, objective and recovery rule are not an injectable universal runtime.
See [ARCHITECTURE](ARCHITECTURE.md) and [TRANSFER](TRANSFER.md).

- **Choice drives the numeric proposal.** A port may call
  `decide(answer, space=None, max_step=domain_cap, ...)` with its own ordered
  numeric payloads and axis names. `max_step` is in those payload units; the
  caller performs the additive or other validated actuation. Expectations must
  not average unordered actions such as retreat, grasp and hand-back.
- **Score does not directly drive `decide` actuation.** The PID evaluator can
  use the predicted quality band with Noul for explicitly enabled `early_stop`.
  Early stopping is off by default. The non-PID transfer does not use Score.
- **Noul needs a statement and an explicit policy.** The PID healthy-step head
  is not an independently validated joint-action safety probability.
  `AbstainPolicy.tau_noul` defaults to zero; an explicit positive threshold is
  required for its global pre-action veto. Merely constructing a Noul does not
  enable that veto. In the non-PID example, Noul states finite observation
  validity, not predicted physical safety.
- **CP monitors by default.** The calibrated complete set retains every option
  satisfying the score threshold, including ties. Monitor mode changes neither
  the full-distribution proposal nor the executed action. Explicit
  `mode="hard_hold"` vetoes empty, oversized or mixed-direction axis sets;
  `conformal_would_hold` and `conformal_reason` remain diagnostics in either
  mode. The checkpoint's CP path disables the implicit legacy pmax heuristic;
  callers may explicitly combine a separate `AbstainPolicy`.
- **Rollback follows an actual measurement.** The PID safety gate evaluates
  the measured cost and proposes its own recovery candidate. It does not turn
  a harmful measured trial into an unexecuted action. Recovery measurements,
  initial observations and final returned parameters remain separately counted.
  An escalation flag has no built-in human recipient or takeover controller.

Split CP's mathematical target here is marginal inclusion of the teacher's
label per axis under its sampling assumptions. It is not simultaneous coverage
of all axes, coverage conditional on passing a gate, coverage of adaptively
reached states, a harmful-action bound, stability or a performance guarantee.
Changing the model, quantization, population, inference mapping or action
selection can invalidate inherited calibration premises. The paused complex
joint-risk results and reproduction entry remain in
[TRAJECTORY_RISK](TRAJECTORY_RISK.md) and
[`44_verify_historical_research.py`](../scripts/44_verify_historical_research.py);
they are not enabled as a general runtime safety head.

### Peripheral recalibration after freezing the model

`fit_frozen_calibration` accepts temperature logits/labels and a disjoint CP
logit/label split, plus sampling-unit IDs and a model SHA-256. It supports an
arbitrary common axis/option schema. It has no model or weight access and
performs no neural gradient update. Temperature fitting is still numerical
optimization; it changes the probabilities and therefore can change an
expectation-decoded action. CP is fitted only after those temperatures freeze.
Neither a checkpoint hash nor unique IDs verify that recorded logits really
came from the claimed model; the caller must bind that provenance.

The small-sample benchmark, its raw clock observations and the distinction
between fitting and data collection are in [RECALIBRATION](RECALIBRATION.md) and
[recalibration_benchmark.json](../research/results/recalibration_benchmark.json).
Each reported sample count belongs to each of two independent fitting splits,
not a shared pool reused to fit both stages. Every fixed combination is reported;
test diagnostics do not select a sample count, model or threshold. The main
study's calibrated artifacts remain unchanged.

“Freeze at manufacture, recalibrate the periphery at the site” is a possible
research workflow only when valid target labels can be obtained and their
sampling is representative of the intended use. Peripheral fit time excludes
label acquisition, forward inference, communication and hardware execution.
The repository has not established cross-day validity or clinical efficacy.
Collecting several correlated windows from one session does not make them
independent calibration units. A change in setting requires its own protocol,
independent validation and failure policy.

### Embedded, VLA and neuromodulation responsibilities

For a C port, start from [`jev_decide_checked`](../c/jev_head.h), not the
unchecked low-level functions. With a non-NULL output, a rejected input,
enabled policy or nonfinite computation clears the entire action and
holds/escalates all axes so that an old command does not survive the failure.
Observe its pointer/non-overlap contract and check the return value before
actuation. It does not apply gains or supervise a physical actuator. Do not use
fast-math settings that invalidate its finite-value checks.

The core C source has fixed arrays, no `malloc`/`calloc`/`free`, and standard
C99/libm dependencies. This statement does not cover allocation inside a linked
runtime or certify stack limits. The exported network and feature builder are
fixed PID implementations. C is a bridge for an STM32 port; it is not a measured
STM32 binary or an FPGA/HLS design. There is no target-board WCET result or full
integer inference kernel. Host timing, object sizes, stack estimates and the
weight-only quantization sensitivity experiment retain their exact scope in
[COMPUTE](COMPUTE.md) and the [C reference guide](../c/README.md).

A VLA experiment needs its own visual encoder, temporal observations, learned
backend and action contract. Unordered action classes require categorical
selection; bounded continuous parameters may use numeric decoding only when
blending has a defined physical meaning. An independent physical checker and
domain-owned state machine must own limits, recovery, repeated Hold and
escalation. The denoising transfer supplies none of the visual, manipulation,
navigation or sim-to-real evidence needed for that system.

For closed-loop neuromodulation, the shell is only a non-clinical research
analogy. Signal-quality checks, independently enforced hard limits, watchdogs,
refractory/cooldown behavior, repeated-Hold strategy and escalation belong to a
domain-validated state machine. Neither Noul, CP nor retrospective rollback
provides those mechanisms or their validation. The repository provides no
treatment parameters, human-subject validation or clinically deployed
controller. Retaining a previous setting must never be assumed to be a validated
physiological safe state.

## 简体中文

本项目以PID自动整定为可实测验证床，提供可拆解的**Calibrated Decision & Safety
Shell（校准决策与安全边界参考壳）**：类型化回答、外围校准、有界数值建议、显式拒绝
策略和独立计账的回退。名称描述软件边界与可观察决策，不意味着已经证明物理安全或
实现通用控制器。项目借鉴Jev接口，使用本仓库训练的模型，不含Jev权重或隶属关系，
见[JEV_MAPPING](JEV_MAPPING.md)。

该参考架构面向未来VLA、闭环神经调控研究及嵌入式移植，帮助拆解、检查和测试组件。
这些是拟议使用方向。已实现的非PID迁移是带参考信号的离线去噪参数标定，另有训练、
标签和加法执行器。它验证组件复用，不构成视觉、机器人行为、生理机制或临床系统
证据。实际验收、目标调用开销与失败结论由[NONPID_TRANSFER](NONPID_TRANSFER.md)
及[主实验JSON](../research/results/nonpid_transfer/report.json)生成。

### 五项已实现能力及证据

| 能力 | 真实实现与证据 | 新领域仍需承担的边界 |
| :--- | :--- | :--- |
| 类型化决策契约 | [`Choice`、`Option`、`Score`、`Noul`、`Answer`](../src/jev_tune/primitives.py)、PID [`DecisionBackend`](../src/jev_tune/decision.py)与[基础类型测试](../tests/test_primitives.py)，在实际运行路径传递分布与具名载荷。 | 已有后端、问题注册、特征、质量分档与权重为PID专用；复用接口不等于迁移已学表征或结果概率。 |
| 冻结模型外围校准 | [`fit_frozen_calibration`](../src/jev_tune/calibration.py)从冻结logits和带采样单元ID的标签先拟合逐轴温度，再拟合独立Split CP；[校准测试](../tests/test_frozen_calibration.py)覆盖分区隔离、有限样本端点及输入不变。[RECALIBRATION](RECALIBRATION.md)生成实测耗时与小样本诊断。 | 需要有效标签、代表性采样、固定推理映射及校准/测试交换性；ID和提供的模型哈希本身不能证明这些前提。 |
| 有界数值解码 | [`decide`](../src/jev_tune/decode.py)读取有序`Option.delta`，按完整校准分布取期望，按词表方差归一化缩步，再限幅。[参考壳测试](../tests/test_shell_contract.py)固定非零均值仅改变方差，并真正触及限幅。 | 单位、坐标归一化、数值/类别动作语义、执行器边界及状态转移合法性由调用方定义；PID `apply_step`仍是专用乘法更新。 |
| 显式拒绝与独立回退 | `AbstainPolicy`、`ConformalPolicy`和`Decision`保留实际保持、建议步长、完整CP集合及假设否决原因；[`evaluate_head`](../src/jev_tune/evaluate.py)将测量后回滚记录为独立转移。[计账测试](../tests/test_runtime_accounting.py)及[参考壳测试](../tests/test_shell_contract.py)验证顺序和真实调用数。 | 保持参数不证明当前参数安全；PID回退是验证床启发式规则。新领域需要自行验证安全状态、连续Hold处理及独立监督器。 |
| 可检查的移植边界 | C99 [`jev_decide_checked`](../c/jev_head.h)检查固定PID推理链并在拒绝时清空动作。[检查入口测试](../tests/test_checked_shell.py)、[跨语言向量测试](../tests/test_portability.py)、[MATLAB对齐证据](../research/results/matlab_parity_v0100.json)及[运行时证据](../research/results/matlab_runtime.json)覆盖特定宿主实现。 | 固定PID导出物不是新领域通用固件；STM32/FPGA仍需板端实现、数值验证、资源测量和目标时序证据。宿主一致不等于硬件确认。 |

### 实际执行链与各类回答的作用

PID路径是`state.build_state`→`NumericBackend.answer`或`OnnxBackend.answer`→
温度缩放后的类型化回答→`decide`→`apply_step`→仿真→实测历史最优记录与可选回滚。
`load_backend`读取检查点校准；完整PID评测器、仿真器、目标与恢复规则不是可直接注入
任意领域的通用运行时。见[ARCHITECTURE](ARCHITECTURE.md)及[TRANSFER](TRANSFER.md)。

- **Choice驱动数值建议。**新领域可调用
  `decide(answer, space=None, max_step=domain_cap, ...)`，提供自己的有序数值载荷及轴名。
  `max_step`与载荷使用同一单位，由调用方执行加法或其他已验证更新。后退、抓取、
  交还控制等无序动作不能通过求数值期望混合。
- **Score不直接控制`decide`执行。**PID评测器仅在显式启用`early_stop`时将质量分档
  与Noul结合用于早停；默认关闭。非PID迁移不使用Score。
- **Noul需要明确陈述与显式策略。**PID健康动作头不是独立验证的联合动作安全概率。
  `AbstainPolicy.tau_noul`默认零，需要显式正阈值才会触发全局事前否决；仅构造Noul
  对象不会自动启用该机制。非PID示例的Noul表示观测有限有效，不预测物理安全。
- **CP默认监测。**完整校准集合按分数阈值纳入所有选项并保留等号边界，monitor不改
  完整分布建议或实际动作。显式`mode="hard_hold"`才否决空集、过宽或方向矛盾的轴；
  两种模式均保留`conformal_would_hold`及`conformal_reason`诊断。带CP的检查点路径
  关闭隐式旧pmax启发式；调用方仍可显式叠加独立`AbstainPolicy`。
- **回滚发生在真实测量之后。**PID门控根据实测代价提出自己的恢复候选，不会把已经
  执行的有害试验改写为未执行动作。恢复测量、初态观测和最终返回参数均单独计账。
  升级标志没有内置人工接收者或接管控制器。

此处Split CP的数学目标是在采样前提成立时逐轴包含teacher标签的边际覆盖，不包括
全部轴同时覆盖、通过门控后的条件覆盖、自适应到达状态覆盖、有害动作概率上界、
稳定性或性能保证。模型、量化、分布、推理映射或动作选择变化，均可能使旧校准前提
失效。暂停的复杂联合风险结果与复现入口保留于[TRAJECTORY_RISK](TRAJECTORY_RISK.md)
和[`44_verify_historical_research.py`](../scripts/44_verify_historical_research.py)，
未作为通用运行时安全头启用。

### 冻结模型后的外围重标定

`fit_frozen_calibration`接收温度拟合logits/标签、另一独立CP logits/标签分区、采样
单元ID和模型SHA-256，支持共同模式下任意轴数和选项数。函数不访问模型或权重，
不执行神经网络梯度更新；温度拟合仍是数值优化，会改变概率并可能改变期望解码动作。
温度固定后才拟合CP。检查点哈希或唯一ID也不能单独证明logits来自所声称模型；
该来源绑定由调用方负责。

小样本基准、原始时钟观测及拟合/采集成本区分见[RECALIBRATION](RECALIBRATION.md)
和[recalibration_benchmark.json](../research/results/recalibration_benchmark.json)。
每个样本量分别属于两个独立拟合分区，不是同一批样本同时拟合两阶段。所有预定组合
全部报告，不用测试诊断选择样本量、模型或阈值；主实验校准产物保持不变。

“出厂冻结、现场外围标定”仅是在能够获取有效目标域标签、且采样具有预期用途代表性
时可研究的流程。外围拟合计时不含标签采集、模型前向、通信与硬件执行；仓库未建立
跨天有效性或临床有效性。同一会话的多个相关窗口不会自动成为独立校准单元。场景
变化需要自己的协议、独立验证和失败策略。

### 嵌入式、VLA与神经调控的领域责任

C移植应从[`jev_decide_checked`](../c/jev_head.h)开始，而不是直接调用未检查的底层
函数。输出指针非空时，输入、启用策略或计算非有限等失败会清空完整动作并保持、
升级所有轴，防止旧命令残留。调用方须遵守指针与输入输出不重叠契约，并在执行前
检查返回值；该入口不更新增益，也不监督物理执行器。不得使用破坏有限值检查的
fast-math编译设置。

C核心采用定长数组，没有`malloc`/`calloc`/`free`，依赖标准C99/libm；这不覆盖链接
运行时内部的分配，也不确认峰值栈边界。导出网络和特征构造固定为PID实现。C是
STM32移植桥梁，不是已板测STM32二进制或FPGA/HLS设计；没有目标板WCET证据或全整数
推理内核。宿主耗时、目标文件大小、栈估计及仅权重量化敏感性实验的准确范围见
[COMPUTE](COMPUTE.md)与[C参考指南](../c/README.md)。

VLA实验需要自己的视觉编码器、时序观测、训练后端与动作契约。无序动作类别必须
采用类别选择；连续参数只有在混合存在明确物理含义时才适合数值解码。独立物理
检查器及领域状态机负责硬限制、恢复、连续Hold与升级。去噪迁移没有提供这一系统
所需的视觉、操作、导航或仿真到实物证据。

闭环神经调控方向仅作非临床研究示意。信号质量、独立硬上限、看门狗、不应期/冷却、
连续Hold策略与升级应由经过领域验证的状态机承担；Noul、CP和事后回滚均不能代替
这些机制或验证。仓库没有治疗参数、人体受试验证或已临床部署控制器；不能把保持
上一设置视为已经验证的生理安全状态。
