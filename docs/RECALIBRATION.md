# Frozen peripheral recalibration / 冻结模型的外围重标定

[English](#english) · [简体中文](#简体中文)

## English

This descriptive benchmark fits temperature scaling and independent split CP on fixed logits from three trained non-PID artifacts. Each row uses n independent temperature label states and n independent CP label states, totaling 2n; each state has two teacher-axis labels. One warmup fit precedes 31 recorded fits. The primary study's 128/256 calibration remains unchanged; all nine model/sample-count combinations are reported without selection.

| model seed | n per split (total label states) | TS median / p99 ms | CP median / p99 ms | total median / p99 ms | test coverage per axis | mean set size per axis |
| ---: | ---: | ---: | ---: | ---: | :--- | :--- |
| 101 | 16 (32) | 4.512600 / 5.804130 | 0.088200 / 0.135180 | 4.601500 / 5.912910 | 0.992188, 0.976562 | 3.671875, 3.746094 |
| 101 | 32 (64) | 5.077400 / 6.925420 | 0.098400 / 0.225040 | 5.174100 / 7.074680 | 0.953125, 0.925781 | 2.250000, 3.000000 |
| 101 | 64 (128) | 5.647500 / 6.676660 | 0.104700 / 0.199380 | 5.744300 / 6.873370 | 0.937500, 0.917969 | 1.988281, 2.914062 |
| 202 | 16 (32) | 4.669800 / 5.799370 | 0.092900 / 0.280760 | 4.769900 / 6.034100 | 0.984375, 0.972656 | 3.429688, 3.664062 |
| 202 | 32 (64) | 5.053100 / 5.559210 | 0.098000 / 0.231680 | 5.161500 / 5.660360 | 0.921875, 0.964844 | 2.074219, 3.355469 |
| 202 | 64 (128) | 5.479000 / 7.469490 | 0.108400 / 0.216820 | 5.575000 / 7.591800 | 0.921875, 0.921875 | 2.078125, 2.914062 |
| 303 | 16 (32) | 4.534700 / 5.550900 | 0.091900 / 0.163710 | 4.637200 / 5.676480 | 0.980469, 0.980469 | 3.210938, 3.890625 |
| 303 | 32 (64) | 4.825900 / 6.034460 | 0.094100 / 0.119400 | 4.921200 / 6.150830 | 0.968750, 0.964844 | 2.910156, 3.429688 |
| 303 | 64 (128) | 5.385000 / 6.276600 | 0.103900 / 0.468530 | 5.484800 / 6.586310 | 0.937500, 0.941406 | 2.222656, 3.019531 |

The full timing samples, min/max and generated statistics are in [recalibration_benchmark.json](../research/results/recalibration_benchmark.json). Overall benchmark wall time is 5.089459 s, including loading and canonical single-object forward inference. Table fit times exclude label acquisition, model forward inference, communication and hardware execution. Frozen model-file hashes agree before and after. Additional objective/filter evaluations: 0; neural gradient steps: 0. Labels were already acquired and charged in the primary study; reusing them adds no new independent evidence.

Test diagnostics use the same independent 256 initial-state signals for every row. They never select n, a model or thresholds and never change primary acceptance or operating actions. CP retains complete sets in monitor mode. Its coverage boundary is per-axis teacher-label marginal inclusion under exchangeability, not joint-axis, conditional, reached-state, closed-loop safety or performance coverage. Unique disjoint IDs do not themselves prove exchangeability. Compact or useful sets with tens of labels are an empirical question.

These CPU fit measurements do not establish millisecond end-to-end adaptation, target-board deadlines, cross-day validity, domain-shift robustness, or clinical/hardware readiness. Label collection, reset feasibility and fresh-domain exchangeability remain caller responsibilities. Complex risk research remains paused.

Run `PYTHONPATH=src python scripts/48_recalibration_benchmark.py --check` to recompute fits, diagnostics, hashes and timing statistics. It preserves observed timing samples, performs no objective/filter calls, and does not demand that a new clock run reproduce old milliseconds. The original timing output cannot be overwritten; a new run requires another `--output` path.

## 简体中文

本描述性基准从三个已训练非PID模型的冻结logits拟合温度缩放与独立分裂CP。每行使用n个温度拟合标注状态和另n个CP标注状态，总计2n；每个状态含两个轴的teacher标签。先预热1次，再记录31次拟合。主实验128/256样本的校准保持原样，九个模型/样本量组合全部报告，不据测试结果选择。

| model seed | n per split (total label states) | TS median / p99 ms | CP median / p99 ms | total median / p99 ms | test coverage per axis | mean set size per axis |
| ---: | ---: | ---: | ---: | ---: | :--- | :--- |
| 101 | 16 (32) | 4.512600 / 5.804130 | 0.088200 / 0.135180 | 4.601500 / 5.912910 | 0.992188, 0.976562 | 3.671875, 3.746094 |
| 101 | 32 (64) | 5.077400 / 6.925420 | 0.098400 / 0.225040 | 5.174100 / 7.074680 | 0.953125, 0.925781 | 2.250000, 3.000000 |
| 101 | 64 (128) | 5.647500 / 6.676660 | 0.104700 / 0.199380 | 5.744300 / 6.873370 | 0.937500, 0.917969 | 1.988281, 2.914062 |
| 202 | 16 (32) | 4.669800 / 5.799370 | 0.092900 / 0.280760 | 4.769900 / 6.034100 | 0.984375, 0.972656 | 3.429688, 3.664062 |
| 202 | 32 (64) | 5.053100 / 5.559210 | 0.098000 / 0.231680 | 5.161500 / 5.660360 | 0.921875, 0.964844 | 2.074219, 3.355469 |
| 202 | 64 (128) | 5.479000 / 7.469490 | 0.108400 / 0.216820 | 5.575000 / 7.591800 | 0.921875, 0.921875 | 2.078125, 2.914062 |
| 303 | 16 (32) | 4.534700 / 5.550900 | 0.091900 / 0.163710 | 4.637200 / 5.676480 | 0.980469, 0.980469 | 3.210938, 3.890625 |
| 303 | 32 (64) | 4.825900 / 6.034460 | 0.094100 / 0.119400 | 4.921200 / 6.150830 | 0.968750, 0.964844 | 2.910156, 3.429688 |
| 303 | 64 (128) | 5.385000 / 6.276600 | 0.103900 / 0.468530 | 5.484800 / 6.586310 | 0.937500, 0.941406 | 2.222656, 3.019531 |

逐次原始计时、最小/最大值及统计均保存在[recalibration_benchmark.json](../research/results/recalibration_benchmark.json)。整个基准墙钟耗时5.089459秒，包含加载与固定单对象前向推理；表中拟合耗时不包含标签采集、模型推理、通信或硬件执行。模型文件执行前后哈希一致。额外目标/滤波调用0次，神经网络梯度更新0步。标签采集已经在主实验计账，复用标签不构成新增独立证据。

每行诊断使用同一批独立的256个初态测试信号，不用测试表现选择n、模型或阈值，不更改主实验验收或运行时动作。CP保留完整集合并仅监测；覆盖边界是在交换性前提下逐轴teacher标签的边际包含，不涵盖双轴联合、条件、闭环到达状态、闭环安全或性能。唯一且互斥的ID本身不能证明交换性。几十个标签能否得到紧凑且有用的集合，需要看真实数据。

CPU外围拟合计时不能证明毫秒级端到端适配、目标板截止时间、跨天有效性、域偏移稳健性或临床/硬件可用性。标签采集、可重置条件和新域交换性仍由调用方建立；复杂风险研究继续暂停。

运行`PYTHONPATH=src python scripts/48_recalibration_benchmark.py --check`重算拟合、诊断、哈希与计时统计。检查保留原始时钟观测，额外目标/滤波调用为零，不要求重新计时得到相同毫秒数。拒绝覆盖原始计时输出；新的计时运行必须指定另一个`--output`路径。
