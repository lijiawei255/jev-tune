# Numerical reproducibility boundary / 数值复现边界

[English](#english) · [简体中文](#简体中文)

## English

The original strict cross-CPU refit **failed**. The retained [hosted failure](../research/results/calibration_runtime_ci_failure_v0100.json) and [full log](../research/results/calibration_runtime_sources/windows_failure_log.txt) are evidence of that failure, not a passing replay. The original `45`, `46`, `48`, model files, fit algorithm and their tolerances remain unchanged. The predefined AVX2 diagnostic also failed; no further ISA setting was selected to obtain a pass. Git history is retained.

The original CPU is Intel i9-13950HX; the hosted CPU is AMD EPYC 9V45. Recorded package versions agree, which does not imply identical elementary operations. The archived default and predefined ISA arms have identical arrays. On the compared original/hosted initial-state arrays, maximum absolute differences are generated below:

| logits | temperature | CP threshold | initial-state decoded step |
| ---: | ---: | ---: | ---: |
| 2.6645352591003757e-15 | 8.8824321675673445e-08 | 6.7894915245503284e-09 | 1.0269195577228274e-08 |

Changed complete CP options in the compared calibration populations: 0; changed test options: 0. These are observations on the archived cases, not a guarantee for unseen boundary cases. Continuous steps differ. Neither complete closed-loop trajectory equivalence nor identical outcomes on another CPU follows from unchanged CP sets. The deeper source of the first differing MLP operation was not captured; OpenBLAS architecture names alone do not explain a PyTorch forward pass.

The replacement automatic evidence obligation is explicitly post-incident: [52](../scripts/52_verify_recorded_transfer.py) independently validates the **recorded original-machine evidence**, with Decimal interval forward/softmax checks, a loss-based temperature certificate, exact CP ranks and recorded sets, complete action-to-measurement links and independently rerun objectives. It does not claim to reproduce every original floating branch, prove training causality, or certify the new backend's rollout. Its explicit binary64 and faithful elementary-function assumptions are recorded in the [audit library](../scripts/calibration_numeric_audit.py). Original strict failures remain separate results; a passing evidence audit never renames them as passes.

Across numerical backends, verify the inference and action mapping again. If recalibration is needed, use independent temperature/CP labels and verify the resulting policy; recalibration alone does not recover identical actions or extend coverage to reached states. Published fit timings remain observations on the original host. The non-PID `negative_stop` decision, sample counts, thresholds, acquisition costs and negative policy result are unchanged.

Recompute this descriptive comparison with `python scripts/54_compare_calibration_runtimes.py`; run the recorded-evidence audit with `python scripts/52_verify_recorded_transfer.py --check`. The former executes no objectives. Every latter objective replay is separately receipted, including failures; it is verification work on the same samples. The earlier hosted failure consumed the count retained in its JSON; its receipt file was not exported, so the log is the available source. [Runtime protocol](../research/protocols/calibration_runtime_v0100.json) documents the failed predefined diagnostic; the separate recorded-evidence protocol freezes the new audit obligations before their full execution.

## 简体中文

原严格跨CPU重新拟合检查**失败**。[托管失败记录](../research/results/calibration_runtime_ci_failure_v0100.json)与[完整日志](../research/results/calibration_runtime_sources/windows_failure_log.txt)保留的是失败证据。原`45`、`46`、`48`、模型、拟合算法和容差全部不变；预先指定的AVX2诊断也失败，没有继续寻找能通过的ISA设置。Git历史按用户要求保留。

原CPU为Intel i9-13950HX，托管CPU为AMD EPYC 9V45。软件版本相同不等于底层运算逐位相同；归档的默认与预定ISA组数组逐位一致。原机与托管初态数组的最大绝对差异如下，由脚本生成：

| logits | temperature | CP threshold | initial-state decoded step |
| ---: | ---: | ---: | ---: |
| 2.6645352591003757e-15 | 8.8824321675673445e-08 | 6.7894915245503284e-09 | 1.0269195577228274e-08 |

比较中校准总体的完整CP选项变化0个，测试选项变化0个。这只描述归档样本，不保证未见边界样本；连续动作确有差异，集合相同不能推出完整闭环轨迹或异机结果相同。未保存首个产生差异的MLP逐层运算，不能仅凭OpenBLAS架构名解释PyTorch前向差异。

自动证据检查改为明确标记的事后义务：[52](../scripts/52_verify_recorded_transfer.py)通过Decimal区间前向/概率核查、基于目标值的温度证书、严格CP分位秩与记录集合、完整动作到实测候选链及独立目标重放，核验**原机记录证据**。它不声称原浮点分支在异机一致，不证明训练因果真实性，也不认证新后端的整段运行。binary64和基本函数faithful舍入假设见[数值库](../scripts/calibration_numeric_audit.py)。原严格失败始终单列；证据审计通过也不能把失败改称通过。

跨数值后端必须重新验证推理及动作映射；如需重标定，使用独立温度/CP标签，并重新验证产生的策略。重标定本身不能恢复相同动作，也不能把覆盖边界扩展至到达状态。拟合耗时仍是原宿主的观测；非PID的`negative_stop`、样本量、阈值、采集成本和策略负结果全部保留。

用`python scripts/54_compare_calibration_runtimes.py`重算描述性比较，用`python scripts/52_verify_recorded_transfer.py --check`审计记录证据。前者不调用目标函数；后者每次重放都单独保存含失败的计账凭据，不构成新增独立样本。早先托管失败消耗的次数保存在其JSON内；当时未导出receipt文件，可用证据为完整日志。[数值运行协议](../research/protocols/calibration_runtime_v0100.json)记录失败的预定诊断，另有记录证据协议在完整执行新审计前冻结新义务。
