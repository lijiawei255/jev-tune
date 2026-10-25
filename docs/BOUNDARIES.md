# Boundaries, negative results and disclaimers / 边界、负结果与免责声明

[English](#english) · [简体中文](#简体中文)

These statements were the first screen of the v0.10.2 README. They are kept
verbatim; the scripts and data they cite are frozen at tag `v0.10.2-archive`
([ARCHIVE](ARCHIVE.md)). Hold costs are quantified in [TRADEOFFS](TRADEOFFS.md).

## English

**Scope: a decomposable Calibrated Decision & Safety Shell with a PID testbed.** A new non-PID offline denoising task includes three genuinely trained models and independent testing; policy-benefit acceptance is `negative_stop`. At budget20, learned mean MSE spans 0.01555577–0.01582834, versus simplex 0.01423997. Stable benefit was not established; this policy investigation stops. Prospective acquisition used 76683 objective calls; standalone training/calibration labels cost 27345 per model. Negative raw evidence, frozen protocols and reproduction remain available; complex risk research stays paused.

Using 16, 32 or 64 labeled states in EACH independent temperature/CP split (32, 64 or 128 total), the nine host fit-time medians span 4.601500–5.744300 ms. Label acquisition, inference, communication and device execution are excluded. This does not validate cross-day, VLA, clinical or target-board operation. The non-PID study did not replace the PID model or default policy; this release separately hardens C/MATLAB input and numeric handling. The C99 checked entry rejects invalid states/temperatures/policies and numeric failures, clears stale actions and holds every axis. Default CP retains complete monitor sets; explicit hard_hold can veto before actuation. Post-measurement rollback is domain-owned recovery, not a physical-safety proof.

Numerical replay scope: the original strict 46/48 checks passed on the original machine and failed across CPUs; those failures remain preserved. A local pass is not a cross-CPU pass. The separate 52 audit checks original-record evidence under explicit arithmetic assumptions and reconstructs its action chain from independently checked recorded probabilities. It does not recover bitwise replay, prove the causal history of training, or promise equivalent actions or trajectories across CPUs. The diagnostic step delta applies both archived logits/T inputs to the original comparison machine's decoder; it is not a difference between actions actually executed on two machines. Strict recomputation of 54's derived floating summaries also failed in the default hosted environment. New 57/58 preserve and independently audit post-incident observations from both default environments; they do not turn 54's failure into a pass or establish future backend identity.

See [shell and transfer boundaries](SAFETY_SHELL.md), [complete non-PID evidence](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/NONPID_TRANSFER.md), [small-sample recalibration](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/RECALIBRATION.md), [numerical reproducibility and evidence boundaries](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/NUMERICAL_REPRODUCIBILITY.md), [post-incident observation audit](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/RUNTIME_OBSERVATIONS.md), and [host resources](COMPUTE.md).

**Distribution:** ordinary `git clone https://github.com/lijiawei255/jev-tune.git`
retains the complete implementation, tests, documentation, formal PID artifacts and six non-PID
model/calibration JSON files. Research records are restored from pinned Release attachments only
when needed; runtime reuse needs no research-data download. No sparse-clone flags are required.
Then read [`AGENTS.md`](../AGENTS.md). The optional motor-valve model and recorded results are available
through `python scripts/65_restore_benchmark.py`; see its [pinned manifest](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/research/distribution/motor_valve_benchmark_v0101.json).
Before pytest or claims, restore data with `python scripts/59_research_data.py --fetch all`,
then historical sources with `python scripts/history_sources.py --root . --restore-pinned`.
Public manifests distinguish unchanged original scientific objects from sanitized metadata
derivatives. For a new verification checkout use script 60; publication acceptance requires the
actual pinned assets and verification receipts. See [distribution, history mapping and reproduction](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/DISTRIBUTION.md).


**Current mainline: real-model adaptation, applicability boundaries and simulation-budget value.**
Deeper joint-risk research is paused. Its failed acceptance, raw trajectories, frozen protocols and reproduction scripts remain available; the risk head stays in research mode and is not enabled in production. Complete CP sets and their existing coverage boundaries remain unchanged.
On the current checkout, use `python scripts/44_verify_historical_research.py --check` to verify the frozen research against an isolated historical source view. Original study commands remain available on v0.8.0; they must not silently substitute today's repaired runtime for their recorded sources.

The practical audit prioritizes controller equivalence, unambiguous measurements, time-based costs, truthful failure status and complete simulation accounting. See [MODEL_ADAPTATION](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/MODEL_ADAPTATION.md) and [PRACTICAL_BUDGET](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/PRACTICAL_BUDGET.md). Generated Simulink fixtures validate adapter behavior; they do not establish performance on an unseen external model or physical hardware.

Earlier MATLAB cost figures, traces and animations below are historical: the corrected time-grid integration changes that objective. They are retained as records, not current performance measurements.
Cross-job model/sweep caching is disabled to preserve each source model and configuration; historical warm-job throughput tables do not describe the current implementation.



**PID autotuning with typed probabilistic decisions and explicit abstention.**
The numeric head uses one CPU forward pass. Complete CP sets are monitored independently of actuation.
Hard Hold is an explicit comparison policy; unchanged deterministic trials stop without repeated simulation.

> **Jev-inspired, not affiliated.** It uses the *Jev interface* — the three typed
> primitives `choice` / `score` / `noul` with calibrated probabilities — not the
> hosted Jev model or Laya's 421 M text encoder. The runtime policy is a 200 KB
> numeric head trained in this repo; Laya is only mentioned as a text baseline
> that was never wired in. This project is **not affiliated with, endorsed by, or
> sponsored by TypeSafe AI**. What is borrowed and what is not:
> [`docs/JEV_MAPPING.md`](JEV_MAPPING.md).


See [Temperature + Split CP](CONFORMAL.md) for the independent calibration results and precise coverage limits. Historical CP hard-hold costs are worse than the temperature-only control; default monitor preserves the temperature-only proposal; neither a label-coverage theorem nor a hold certifies closed-loop safety.

**Joint-action risk rollout acceptance: not passed.** On 1024 independent test plants under the frozen protocol, 2 gated trajectories contained a harmful execution; the nominal exact-binomial one-sided 95% upper quantity is 0.006135. Gated/matched-monitor final mean J is 2.303682/1.297619, and p90 is 3.416603/2.314045. The nominal one-sided 95% lower quantity for first-stage execution is 0.479684; its preregistered minimum is 0.50. See [JOINT_RISK_ROLLOUT](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/JOINT_RISK_ROLLOUT.md) for every criterion, independent stage calibration, raw trajectories and scope. This preserves the v1 numerical record; calculating binomial quantities does not itself establish independence of implemented trajectory events. This does not enable a joint-risk gate by default in general Python, C or MATLAB deployment; failed criteria are not hidden by retuning thresholds.

### Multistep joint risk: new preregistered study FAIL

The sole primary candidate is `trajectory_selected`; status is `research_only`. On 1024 new independent test plants, 8 trajectories had a harmful execution. The nominal one-sided 95% binomial risk upper bound is 0.014052; the nominal first-execution lower bound is 0.559971. Implementation assumptions are audited below. Primary/matched-monitor final mean J is 2.158651/1.357796, p90 J is 3.149694/2.294926, and actual operating simulations are 2770/21504. Failed criteria: final mean cost noninferiority (`empirical_mean_cost_noninferior`); final p90 cost noninferiority (`empirical_p90_cost_noninferior`). Final mean and p90 are compared with monitor with zero slack; reducing harmful exploration alone does not pass the complete acceptance.

The v1 failure is preserved. Old tests have been used for retrospective diagnosis and cannot independently validate the new design. Only the primary candidate fixed before data is assessed for acceptance on the new test; explanatory arms cannot be selected for deployment after testing. The new comparison changes training trajectories, data volume, scaling and initial risk-feature semantics together; it is not a single-factor causal experiment.

On the recorded old paths, preserving the monitor optimum requires a harmful transition for 700/1024 plants. Thus a gate that only truncates those paths cannot meet both the original risk and zero-slack mean criteria. This is a finite-record diagnosis, not an impossibility theorem for all new policies. Alternative joint actions can change paths; their success is decided by the measured new acceptance.

See the [old failure diagnosis](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/ROLLOUT_DIAGNOSIS.md), [full new study](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/TRAJECTORY_RISK.md), and their JSON/raw shards. General Python/C/MATLAB deployment defaults remain unchanged. Passing numerical criteria alone cannot bypass the separate implementation-validity audit or expand the registered runner, population and horizon.

**Additional implementation-validity audit: NOT ESTABLISHED; deployment_allowed=false.** Frozen numerical criteria and this audit are separate. Observed dependence on batch shape/row position leaves a canonical per-object mapping, calibration/test CP-score exchangeability, and independence of trajectory events unestablished in this run. The CP and one-sided 95% binomial quantities are therefore nominal calculations, not established exact CP/PAC guarantees for this machine implementation. A generic exchangeability disclaimer does not close this gap. This is an additional failure beyond the frozen numerical acceptance; deployment remains prohibited. A fixed inference mapping, fresh calibration and new prospective validation are required. See the [implementation-validity audit](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1).

Pairing fixes initial plants and observations; it does not require bitwise-identical cross-arm proposals or histories under different active batch layouts. Each arm retains its own actual actions, strict zero-tolerance labels, CP sets and history accounting; no new acceptance tolerance is fitted to test differences. Strict scientific-evidence reconstruction and exact canonical-record replay are verified within the recorded reference environment; Python/C99 runtime portability does not imply bitwise reproduction of study trajectories across platforms. See the [release verification scope](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/RELEASE_VERIFICATION.md). [Pairing diagnosis](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1). The [Fixed-input batch diagnosis](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1) charges 1 additional diagnostic simulations. Repeating identical inputs at different batch shapes/row positions gives a maximum base_step difference of 1.24583552e-07. This is a post-hoc numerical mechanism check, not reconstruction of the full original cohort or new independent acceptance; recorded actions and boundaries remain unchanged.

## 简体中文

以下内容原为v0.10.2 README首屏，原文保留；所引脚本与数据冻结在`v0.10.2-archive`标签。

**定位：以PID为验证床的可拆解 Calibrated Decision & Safety Shell。** 新增非PID离线去噪标定完成三个模型的真实训练与独立测试，策略收益验收为`negative_stop`；预算20时三模型平均MSE为0.01555577–0.01582834，simplex为0.01423997，没有稳定收益，停止本轮策略深化。前瞻采集实际76683次，单模型离线训练/校准标注成本27345次；原始负结果、冻结协议和复现入口保留，复杂风险研究仍暂停。

每个独立温度/CP分区分别16、32、64个标注状态（合计32、64、128）时，九项组合的宿主纯拟合中位耗时范围为4.601500–5.744300 ms。标签采集、推理、通信和设备执行不在该拟合计时内；这不证明跨天、VLA、临床或目标板有效性。非PID研究没有替换PID模型或默认策略；本版本另外加固了C/MATLAB输入与数值处理。C99 checked入口拒绝非法状态/温度/策略及数值失败，清空旧动作并全轴保持。默认CP仍为完整集合monitor，显式hard_hold可事前否决；测后rollback是领域恢复提案，并非物理安全证明。

数值复现范围：原46/48在原机严格通过、跨CPU严格失败的结果完整保留；本机通过不等于跨CPU通过。独立52核验的是受明确算术假设限制的原记录证据，使用独立检查过的原概率重建动作链，不恢复逐位重放，不证明训练历史的因果真实性，不承诺不同CPU的动作或轨迹等价。数值诊断中的step差异，是原比较机器对两端归档logits/T的统一解码差异，不是两台机器实际输出动作之差。54的派生浮点汇总在默认托管环境也未能严格重算；新57/58保存默认两端的事后观察并独立核验，不把54失败改称通过，不保证未来后端逐位一致。

见[外壳与迁移边界](SAFETY_SHELL.md)、[完整非PID证据](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/NONPID_TRANSFER.md)、[少样本重标定](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/RECALIBRATION.md)、[数值复现与证据边界](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/NUMERICAL_REPRODUCIBILITY.md)、[事后观察与独立数值核验](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/RUNTIME_OBSERVATIONS.md)、[宿主资源指标](COMPUTE.md)。

**分发：**普通`git clone https://github.com/lijiawei255/jev-tune.git`保留完整代码、测试、
文档、正式PID产物及六份非PID模型/校准JSON。研究记录按需从固定Release附件恢复，
运行复用不需要研究数据，无需稀疏克隆参数。随后读取[`AGENTS.md`](../AGENTS.md)。
可选电机阀门模型与记录结果通过`python scripts/65_restore_benchmark.py`恢复，见
[固定清单](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/research/distribution/motor_valve_benchmark_v0101.json)。
运行pytest或claims前，先执行`python scripts/59_research_data.py --fetch all`恢复数据，
再执行`python scripts/history_sources.py --root . --restore-pinned`恢复历史源码。公开清单
区分未改动的原始科学对象与脱敏元数据派生件。新目录完整验证使用60脚本；发布验收以
真实固定附件与核验收据为准。详见[分发、历史映射及复现](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/DISTRIBUTION.md)。


**当前主线：真实模型适配、适用边界与仿真预算收益。**
暂停深化联合风险研究，保留未通过验收的结论、原始轨迹、冻结协议及复现脚本；风险头继续保留研究模式，不进入生产默认路径。完整CP集合及既有覆盖边界保持不变。
当前检出用`python scripts/44_verify_historical_research.py --check`在隔离的历史源码视图中核验冻结研究。原研究命令保留在v0.8.0，不能偷偷用今天修复后的运行时代替原记录源码。

实用审查优先保证控制器转换等价、测量对象明确、代价按真实时间计算、失败状态准确，以及仿真计账完整。见[MODEL_ADAPTATION](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/MODEL_ADAPTATION.md)和[PRACTICAL_BUDGET](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/PRACTICAL_BUDGET.md)。生成的Simulink回归模型用于验证适配器行为，不证明未见外部模型或硬件上的调参效果。

下方旧MATLAB代价、轨迹及动画为历史记录：按实际时间网格积分的修正已改变目标，旧记录不代表当前性能测量。
为保留各任务原件及配置语义，跨任务模型与扫描缓存已停用；历史热启动吞吐表不代表当前实现。


> **受Jev启发，与TypeSafe AI无隶属、背书或赞助关系。** 本项目使用自己训练的数值头，不含Jev/Laya权重或API。[English](../README.md)


独立校准结果及覆盖边界见[温度与分裂CP](CONFORMAL.md)。旧CP硬保持代价逊于温度单独校准；默认monitor保留温度单独校准的提案；标签覆盖定理或保持动作均不证明闭环安全。

**联合动作风险的多轮验收：未通过。** 冻结协议在1024个独立测试对象上，门控策略有2条轨迹至少一次有害执行；名义单侧95%精确二项上界量为0.006135。门控/配对monitor对照的最终平均J为2.303682/1.297619，p90为3.416603/2.314045。首步执行率的名义单侧95%下界为0.479684，预注册最低要求为0.50。全部判据、逐步独立校准、原始轨迹与适用范围见[联合风险多轮研究](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/JOINT_RISK_ROLLOUT.md)。这是保留的v1数值记录；计算二项量不单独证明机器实现的事件独立性。此结果不把联合风险门默认接入通用Python、C或MATLAB部署；失败判据不会通过改阈值掩盖。

### 多步联合风险：预注册新实验 FAIL

唯一主要候选为`trajectory_selected`；状态为`research_only`。在1024个新独立测试对象上，8条轨迹出现有害执行，风险的名义单侧95%二项上界为0.014052，首步执行率名义下界为0.559971；本轮实现的统计前提另见下文。主要候选/配对monitor的最终mean J为2.158651/1.357796，p90 J为3.149694/2.294926，实际运行仿真数为2770/21504。未通过项：最终平均代价非劣 (`empirical_mean_cost_noninferior`); 最终p90代价非劣 (`empirical_p90_cost_noninferior`)。最终mean与p90均按零松弛要求和monitor比较；仅减少有害探索事件不足以通过全部验收。

旧v1失败结果保留。旧测试已经用于事后诊断，不能再作新方案的独立验证；本轮只用新测试验收事先指定的主要候选，其他组不按测试成绩选优上线。本轮同时改变训练轨迹、数据量、标准化和风险初态特征语义，是整体方案比较，不是单因素因果实验。

旧固定路径诊断发现700/1024株保留monitor最优必须经过有害步。这证明旧记录中仅截断、不改提案的门控无法同时满足原风险与零松弛均值条件；不证明所有新策略都不可能。替代联合动作可改变路径，但是否成功由本轮真实验收决定。

见[旧失败诊断](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/ROLLOUT_DIAGNOSIS.md)、[新完整研究](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/TRAJECTORY_RISK.md)及其JSON/原始分片。通用Python/C/MATLAB部署默认保持原样；即使数值判据通过，也不能绕过独立实现有效性审计或扩展注册的运行器、模拟分布和时域。

**额外的实现有效性审计：未建立；deployment_allowed=false。** 冻结数值判据与这一审计分开报告。本轮批次形状/行位置引起的输出依赖，使逐对象固定映射、校准/测试CP分数交换性及轨迹事件独立性均未建立。因此表内CP及单侧95%二项量只作名义计算，不能宣称本机器实现已获得精确CP/PAC保证；仅写一般交换性假设不足以弥补这一缺口。这是原数值验收之外的额外失败，继续禁止部署；需固定推理映射、重新校准和新的前瞻验证。 见[实现有效性审计](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1)。

配对指相同初始对象与观测，不要求活跃批次不同的跨组提案/轨迹逐位相同。每组仍按自身真实动作、严格零容差标签、CP集合与历史计账；不从测试差异拟合新的验收容差。严格科学证据重建及规范化记录的精确重放，验证范围限于记录的参考环境；Python/C99运行时的跨平台支持不意味着研究轨迹可跨平台逐位复现。见[发布验证范围](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/RELEASE_VERIFICATION.md)。 [配对数值诊断](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1)。 [固定输入批次诊断](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1)另计1次诊断仿真；相同输入复制到不同批次/行位置时，base_step最大差为1.24583552e-07。这是事后数值机制检查，未重建原完整批次，不是新的独立验收，未改动原始动作或边界。
