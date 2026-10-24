# Trained non-PID transfer example / 已训练的非PID迁移示例

[English](#english) · [简体中文](#简体中文)

## English

This example loads an existing two-axis denoising checkpoint and calibration,
then calls the frozen study's `rollout` on one recorded signal. It does not
train, select a checkpoint, change the primary experiment, or recompute the
study's acceptance. The reported acceptance is read from `report.json`, including
a negative result. One illustrative replay cannot overturn that result.

From the repository root, after installing the repository dependencies:

```bash
python examples/denoise_transfer/run.py --run --seed 101 --index 0 --budget 20
```

The default artifact directory is `research/results/nonpid_transfer`. It must
contain the completed study's `report.json`, `model_101.json` and
`calibration_101.json`; missing artifacts cause an explicit error rather than
automatic training. Use `--artifacts-dir <directory>` for an existing separate
reproduction. `--seed` selects a registered trained model, not a new signal
population. The signal split seed comes from the frozen protocol; `--index`
selects a recorded test object. `--budget` accepts only the registered operating
budgets. The primary budget remains the one in the protocol regardless of this
example's arguments. Source and selected artifact hashes are checked before
execution; inference uses a single object with shape `(1, 16)`.

Standard output is JSON. `additional_objective_evaluations` counts this invocation's
fresh filter attempts, including the initial point and failed attempts. Cached
requests do not execute the filter and are reported separately. These extra
measurements are deterministic reproduction work, not additional independent
test data; they are not silently added to or substituted for the original study
spend. The example writes no study artifacts. `returned_theta` and `returned_cost`
come from the best point actually measured in this replay. The study's current
status appears only under `study_acceptance_from_report`.

The two normalized parameters in `[0, 1]` map to local clipping multiplier
`k = 1 + 5 * theta[0]` and low-pass cutoff
`fc = .02 * (.35 / .02) ** theta[1]` cycles/sample. The task executes robust local
clipping followed by a noncausal second-order low-pass filter. A hidden clean
reference supplies the measured MSE. The policy receives that paid-for scalar
feedback and noisy/output/residual summaries, never clean samples or generating
parameters. This is synthetic offline reference calibration, not blind denoising,
an external-data result, a hardware controller, or transfer of the PID weights.

The example reuses `Choice/Option/Answer/Noul`, calibrated probabilities and the
numeric `decide` interface. Actuation is additive and domain-owned. CP is
monitoring only; the complex risk head remains paused. PID features, its
three-axis checkpoint, multiplicative actuation and rollback are not reused.
The optional `Score` primitive is unused here. Read the
[frozen protocol](../../research/protocols/nonpid_transfer_v0100.json) for the
independent splits, full acquisition budget, fixed baselines and stopping rule;
the full study's independent checker is `scripts/46_verify_nonpid_transfer.py`.

## 简体中文

本示例加载已有的二轴去噪检查点及校准文件，调用冻结研究的`rollout`，重放一个
已记录信号。不训练、不选优检查点、不改变主要实验，也不重新计算研究验收。
验收状态直接读取`report.json`，包括负面结论；单个演示不能推翻该结论。

安装仓库依赖后，从仓库根目录执行：

```bash
python examples/denoise_transfer/run.py --run --seed 101 --index 0 --budget 20
```

默认产物目录为`research/results/nonpid_transfer`，需要已完成研究生成的
`report.json`、`model_101.json`和`calibration_101.json`。产物缺失会明确失败，
不会自动训练。`--artifacts-dir <目录>`可读取另一次已有复现。
`--seed`选择已注册的训练模型，不是新信号总体；信号划分种子来自冻结协议，
`--index`选择已记录的测试对象。`--budget`仅接受已注册运行预算，示例参数不会
改变协议的主要验收预算。执行前核对源码及所选产物哈希，推理始终使用`(1, 16)`
单对象形状。

标准输出为JSON。`additional_objective_evaluations`统计本次新执行的滤波尝试，
包含初测和失败尝试；缓存命中不执行滤波，另列次数。额外测量属于确定性复现工作，
不是新的独立测试数据，不会偷偷并入或替换原研究支出。示例不写入研究产物。
`returned_theta`与`returned_cost`来自本次真实测过的最优点，研究当前是否通过
仅在`study_acceptance_from_report`中按原报告展示。

两个`[0, 1]`归一化参数分别映射为局部截断倍数`k = 1 + 5 * theta[0]`和
低通截止频率`fc = .02 * (.35 / .02) ** theta[1]`，单位为每采样周期数。
任务真实执行局部稳健截断与非因果二阶低通滤波，由隐藏clean参考计算实测MSE。
策略可读取付费取得的标量代价反馈及带噪信号、输出、残差摘要，不能读取clean
采样或生成参数。这是合成信号的离线有参考标定，不是盲去噪、外部数据验证、
硬件控制器或PID权重迁移。

本例复用`Choice/Option/Answer/Noul`、校准概率和数值`decide`接口，使用领域自有
的加法执行规则。CP仅监测，复杂风险头保持暂停；不复用PID特征、三轴检查点、
乘法动作或回滚，亦未使用可选的`Score`原语。
[冻结协议](../../research/protocols/nonpid_transfer_v0100.json)记录独立划分、
完整采集预算、固定基线与停止规则；完整研究独立核验入口为
`scripts/46_verify_nonpid_transfer.py`。
