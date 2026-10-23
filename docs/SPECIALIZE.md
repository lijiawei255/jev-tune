# SPECIALIZE

[English](#english) · [简体中文](#简体中文)

## English

Specialization is offline fine-tuning from pretrained weights using a resettable
simulator. It is a candidate experiment, not a guaranteed remedy for dead band,
inverse response, unstable starts or a mismatched objective. It is not on-device
learning from a few human/robot trials.

```bash
python scripts/10_specialize.py --scenario valve_dead_zone --name valve --plants 120 --report research/results/specialization.json
python scripts/10_specialize.py --spec plant.json --name myplant
python scripts/13_tracking_demo.py
```

Script 10 defaults: 48 total plants (36 training/12 held out), 12 rollout steps,
10 epochs and learning rate 5e-4. `--plants 120` gives 90/30, not the default.
Every rollout state uses 21 single-axis candidates and a combined trial, plus
initial/rejection simulations; actual expert counters expose the cost. The
evaluation budget is 20 per plant, with the same calibrated starting policy.
See the freshly generated `models/specialized/valve.json` locally and the
versioned [specialization result](../research/results/specialization.json).

Earlier releases quoted different valve numbers. The current family builder
uses its own seeded RNG; the assertion that all historical discrepancies came
from salted scenario hashes lacks a commit/data manifest and is withdrawn.
Historical numbers are not valid replacements for a rerun with a fixed protocol.

[tracking.json](../research/results/tracking.json) compares a step-trained policy
with a disturbance specialist using the disturbance objective. Improvement or
degradation must be read from that JSON; the script no longer presupposes a
positive result. The complete learning curve and training-seed replication are
unmeasured. [CALIBRATE_ONLY](CALIBRATE_ONLY.md) instead freezes network weights;
it still pays sampling cost and is not from-scratch learning.

## 简体中文

专门化是在可重置仿真器中，从预训练权重离线微调，是待验证实验，不保证修好死区、反向响应、
不稳定起点或目标不匹配，也不是用少量人体/机器人试验进行设备在线学习。

```bash
python scripts/10_specialize.py --scenario valve_dead_zone --name valve --plants 120 --report research/results/specialization.json
python scripts/10_specialize.py --spec plant.json --name myplant
python scripts/13_tracking_demo.py
```

脚本10默认总48株（36训练/12留出）、12步rollout、10 epochs、学习率5e-4。
`--plants 120`才是90/30。每状态有21个单轴和一个组合候选，另需初始/拒绝后的仿真，
实际专家计数明确成本。评测逐株预算20，使用相同校准起始策略。
本地输出为`models/specialized/valve.json`，版本化结果见[specialization.json](../research/results/specialization.json)。

旧版本曾引用不同阀门数字，当前族生成器使用自己的确定性RNG；将全部历史差异归因于scenario的
salted hash缺少commit/数据manifest支持，现撤回该解释。历史数字不能替代固定协议重跑。

[tracking.json](../research/results/tracking.json)使用扰动目标比较阶跃策略与扰动专家，改善或退化以JSON为准，
脚本不再预设正收益。完整学习曲线与训练种子重复仍未测。
[CALIBRATE_ONLY](CALIBRATE_ONLY.md)冻结网络权重，但仍需采样，不等于从零小样本训练。
