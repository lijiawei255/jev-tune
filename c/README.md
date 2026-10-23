# C99 inference reference / C99 推理参考

> [English](#english) · [简体中文](#简体中文)

## English

This directory implements inference and PID feature assembly, not training or
plant simulation. It uses fixed-size arrays, standard C99/libm and no third-party
inference library. The core source has no dynamic allocation or mutable static
state. This does not claim that the linked C runtime uses no heap.

### Build and verify

From the repository root:

```sh
python -m pytest tests/test_portability.py -q
python scripts/18_export_c.py --verify
make -C c check
```

The exporter regenerates weights and fixtures from Python. Pytest also validates
**committed** fixture probabilities/decisions against the current checkpoint and
calibration without first regenerating them. It compiles a deliberately corrupt
NaN/Inf variants and requires failure. `--verify` runs three standalone C harnesses.

With MATLAB available, pytest also exercises the actual decoder and a temporary
Simulink model's first-iteration rollback and cumulative escalation history.
Regenerate the versioned MATLAB parity report with
`test_portability('research/results/matlab_parity.json')` after adding `matlab/`
to the MATLAB path. It records all 24 actual outputs, per-head error maxima and
checkpoint, configuration, source-vector and exported-weight hashes.

| File | Contract |
| :--- | :--- |
| `jev_head.h`, `jev_head.c` | forward, probabilities, decoder, abstention, rollback predicate, gain update, features/resampling |
| `jev_head_weights.h` | generated float32 weights; do not edit |
| `jev_config.h` | generated default temperatures, conformal quantiles/policy and checkpoint SHA-256 |
| `test_vectors.json` | schema version 3: checkpoint hash, vocabulary/deltas, temperatures, conformal configuration, legacy thresholds, bounds, shrink, all outputs and policy cases |
| `test_vectors.h`, `test_features.h`, `test_policy.h` | generated C representations of that JSON |
| `test_forward.c` | all Choice/Score/Noul logits/probabilities, proposed/step, conformal sets/sizes, held/escalate/reason |
| `test_features.c` | 20 features, 2×64 curves, resampling |
| `test_policy.c` | threshold boundaries, partial holds, confident no-change, Noul veto, early-stop, rollback and gain limits |

The current fixture suite contains 24 model states, 6 feature cases, 3 resampling
cases, 17 policy cases, 6 rollback cases and 3 gain-update cases. Comparisons reject
non-finite expected or actual values. A model passing numeric fixtures does not
prove correct handling of every possible fault or operating environment.

### Calling the default decoder

```c
#include "jev_head.h"
#include "jev_config.h"
/* Assemble a finite, validated state s and measured cost in the caller. */
jev_logits logits;
jev_probs probabilities;
jev_action action;
jev_policy policy = {JEV_DEFAULT_POLICY[0], JEV_DEFAULT_POLICY[1],
                     JEV_DEFAULT_POLICY[2]};
jev_conformal cp = {JEV_DEFAULT_CP_ENABLED,
                    {JEV_DEFAULT_CP_QHAT[0], JEV_DEFAULT_CP_QHAT[1],
                     JEV_DEFAULT_CP_QHAT[2]}, JEV_DEFAULT_CP_K_MAX};
int escalations = 0;
jev_forward(&s, &logits);
jev_answer(&logits, JEV_DEFAULT_TEMPERATURE, &probabilities);
jev_decode(&probabilities, &action);
jev_abstain(&action, &probabilities, &policy, &escalations);
jev_apply_conformal(&action, &probabilities, &cp, &escalations);
```

`axis_held[a]` means the policy vetoed axis `a`; `held` is true only if all axes
were vetoed. A confident ×1 choice has a zero step and is **not** abstention.
`reason` values match Python: 0 act, 1 legacy low confidence, 2 legacy escalation,
3 Noul veto, 4 empty conformal set, 5 set larger than `k_max`, 6 both positive
and negative gain steps in the set. Noul takes precedence over CP, then legacy
thresholds. An escalation is a flag for the caller, not an implemented supervisor.

The default is temperature scaling plus split-conformal prediction sets,
with alpha=0.10 and `k_max=3`. Membership uses `(1-p) <= qhat`, equivalent to
`p >= 1-qhat`, including equality. Empty, oversized or contradictory sets hold
that axis and flag escalation. `proposed` always uses the full calibrated
distribution; CP never truncates or renormalizes it. Default legacy p_max and
Noul thresholds are zero; explicit callers may still layer them on top.
`qhat` is binary64 even though model weights and activations are binary32:
rounding a near-one quantile to float32 can turn a small set into all options.

The calibration target is marginal coverage of teacher action labels per axis
under the split-conformal assumptions. It is not a bound on harmful steps,
closed-loop stability or shifted plants. `jev_gate_rollback` is a post-measurement predicate;
the caller owns recording the measured gain/cost, applying 0.6×best and testing
that new candidate. It does not certify stability or safety.

### Porting and resource limits

Numerical validation was run with TDM64 GCC 4.9.2 / Windows x64 and MATLAB R2024b;
CI builds with the Ubuntu host GCC. See [compute measurements](../docs/COMPUTE.md)
for host object sections, per-function stack estimates, latency and weight-only
quantization disagreements. Static RAM excludes stack and caller buffers. Object
sections are not a target-board linker map, and latency percentiles are not WCET.

The int8 experiment rounds/dequantizes weights and runs float32 kernels; it is
not an integer inference implementation. It changes hold masks on some states.
Do not infer its board speed, resource use or safety from argmax agreement.

A new port should record the JSON schema version and model SHA-256 and validate
all probability, action, telemetry and boundary cases. The vocabulary and its
variance normalization are part of the manifest. Revalidate when calibration or
policy changes. The code is not validated on any MCU, FPGA, robot or medical
device. Signal-validity checks, physical limits, interlocks and watchdogs belong
outside the network; see [transfer boundaries](../docs/TRANSFER.md).

Community ports can register language/platform, maintainer, fixture schema/model
hash and whether hardware was tested. There are no registered community ports.

## 简体中文

本目录实现推理与PID特征组装，不含训练和对象仿真。使用定长数组、标准C99/libm，
不依赖第三方推理框架。核心源码没有动态分配或可变静态状态；这不代表链接的C运行时
完全不用堆内存。

### 编译与验证

在仓库根目录运行上方三条命令。导出脚本从Python重新生成权重和测试向量；pytest还会
在**不先重新生成**的情况下，把已提交向量的概率和动作与当前checkpoint、校准比较，
并编译故意注入NaN/Inf的变体，要求它们必须失败。`--verify`运行三个独立C检查程序。

有MATLAB时，pytest还验证实际解码器，以及临时Simulink模型首轮回滚与累计升级历史。
将`matlab/`加入MATLAB路径后，运行
`test_portability('research/results/matlab_parity.json')`可再生版本化对齐报告，
其中包含24个实际输出、各头最大误差及checkpoint、配置、输入向量、导出权重的hash。

| 文件 | 内容 |
| :--- | :--- |
| `jev_head.h`、`jev_head.c` | 前向、概率、解码、弃权、回滚判据、增益更新、特征与重采样 |
| `jev_head_weights.h` | 生成的float32权重，不得手改 |
| `jev_config.h` | 生成的默认温度、conformal分位数/策略与checkpoint SHA-256 |
| `test_vectors.json` | schema v3：模型hash、词表/步长、温度、CP配置、旧阈值、限幅、缩步与全部期望输出/策略用例 |
| 三个测试`.h`文件 | 与JSON同源生成的C数组 |
| `test_forward.c` | Choice/Score/Noul各头logits/概率，以及proposed/step、CP集合/大小、held、escalate、reason |
| `test_features.c` | 20个特征、2×64曲线与重采样 |
| `test_policy.c` | 阈值边界、部分保持、主动不变、Noul否决、早停、回滚、增益限幅 |

当前有24个模型状态、6个特征用例、3个重采样用例、17个策略用例、6个回滚用例和3个
增益更新用例。期望值或实测值非有限都会失败；通过这些用例仍不等于覆盖所有故障与工况。

### 调用语义

调用顺序见英文部分代码。`axis_held[a]`表示策略否决第a轴；`held`仅在所有轴均被否决
时为真。高把握度主动选择×1时步长为0，但不是弃权。`reason`与Python一致：0执行、
1旧把握度阈值、2旧升级标志、3 Noul否决、4 CP集合为空、5集合超过k_max、6集合同时
包含正负增益步长。原因优先级为Noul、CP、旧阈值。升级只是供调用者处理的标志，没有上层接管器。

默认使用温度缩放加split-conformal集合，alpha=0.10、k_max=3。成员规则为
`(1-p) <= qhat`，数学上等价于`p >= 1-qhat`，含等号。空集合、过大集合或正负方向
冲突均保持该轴并标记升级。`proposed`仍由完整校准分布计算；CP不截断、不重新归一化。
旧p_max与Noul阈值默认均为0，显式调用者可叠加旧策略。模型权重和激活为binary32，
但qhat保留binary64：接近1的分位数若舍入成float32的1，会错误地将所有选项纳入集合。

校准目标是split-conformal假设下，每轴教师动作标签的边际覆盖率，不是有害动作、
闭环稳定性或分布变化对象上的安全界限。

`jev_gate_rollback`只提供测量后的回滚判据。调用者负责将已测增益与代价配对记录，执行
0.6倍历史最优增益并重新评估；该判据不证明闭环稳定或安全。

### 移植与资源边界

数值验证使用TDM64 GCC 4.9.2 / Windows x64及MATLAB R2024b，CI使用Ubuntu宿主GCC。
[算力文档](../docs/COMPUTE.md)记录宿主目标文件section、单函数栈估计、延迟及仅权重量化
误差。静态RAM不含栈和调用者缓冲区；宿主目标文件不等于目标板链接图，分位延迟不等于WCET。

int8实验将权重取整后反量化，仍使用float32内核，并会改变部分状态的保持掩码。它不是
整数推理实现，不能据其argmax一致率推断板端速度、资源或安全性。

新移植应记录JSON schema版本和模型SHA-256，对齐全部概率、动作、遥测与边界用例；
词表与方差归一化属于manifest，校准或策略变化后需重验。本实现未在任何MCU、FPGA、
机器人或医疗设备上验证。信号合法性、物理限幅、联锁和看门狗应位于网络之外，详见
[迁移边界](../docs/TRANSFER.md)。

社区移植可登记语言/平台、维护者、向量schema/模型hash及是否实测硬件；目前没有登记项目。
