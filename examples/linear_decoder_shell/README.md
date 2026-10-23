# Numeric decoder port / 数值解码移植示例

[English](#english) · [简体中文](#简体中文)

## English

Run `PYTHONPATH=src python examples/linear_decoder_shell/run.py` from the repository.
Two named numeric Choices use different payloads, two axes and additive updates.
The result is `[0.6, 0.35]`. `Option.delta` is authoritative when `decide` receives
no PID `ActionSpace`; an explicit space instead requires matching payloads.
The example uses supplied distributions, not a trained non-PID controller.

Only ordered numeric actions can use expectation decoding. Distinct categorical
actions require a separate selection/actuation policy. The caller owns observation
quality, units, calibration labels, actuator bounds and fault handling. The PID
evaluator, checkpoint, features and rollback rule remain testbed-specific. Holding
a parameter does not certify stability. This example has no robot or medical use.

## 简体中文

在仓库根目录运行 `PYTHONPATH=src python examples/linear_decoder_shell/run.py`。
两个具名数值Choice使用不同载荷、两个轴和加法更新，结果为`[0.6, 0.35]`。
`decide`未传PID `ActionSpace`时以`Option.delta`为准；显式传入时要求载荷一致。
示例使用预先给定的分布，不代表已经训练了非PID控制器。

期望解码仅适用于有序数值动作；类别动作需要另设选择及执行策略。
调用方负责观测质量、单位、校准标签、执行器约束和故障处理。PID评测器、
权重、特征及回滚规则仍是试验场专用。保持参数不证明稳定性。本例未用于机器人或医疗。
