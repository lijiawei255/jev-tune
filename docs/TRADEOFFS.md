# Hold trade-offs / 弃权取舍

[English](#english) · [简体中文](#简体中文)

## English

The split-CP veto can act before actuation (`hard_hold`) or only record what it
would have done (`monitor`). Both modes compute the same sets; they differ only
in whether the step is sent. The measured trade-off on the PID test bed:

| 48 held-out plants, budget 21, ONNX head | `monitor` | `hard_hold` |
| :--- | ---: | ---: |
| axes held before actuation | 0.0 % | 42.0 % |
| harmful measured steps (`after > before`) | 34.6 % | 24.0 % |
| mean simulations per plant | 21.0 | 9.1 |
| final cost, median | 1.123 | 1.908 |
| final cost, p90 | 2.231 | 2.409 |
| final cost, max | 2.577 | 3.832 |

What this does and does not show:

* `hard_hold` makes fewer harmful moves and spends fewer experiments, because a
  held plant whose gains stop changing ends early (`stop_on_no_action`).
* It **does not** buy tail cost here: p90 and max final cost are worse as well.
  The honest description is "fewer harmful actuations and experiments for a
  higher final cost", not "tail safety".
* Hence the split defaults: the PID evaluator and CLI monitor (final cost is the
  product there); `core.policy.ConformalPolicy` and `c/jev_config.h` default to
  `hard_hold` (an unvetted actuation is the costlier failure on a device).
* One seed and one plant draw; per-step harm is measured against the previous
  measured cost, not a physical-safety criterion. Neither mode is a safety bound.

Reproduce (about one minute on a laptop CPU):

```python
import numpy as np
from jev_tune.domains.pid.baselines import zn_gains
from jev_tune.domains.pid.decision import load_backend
from jev_tune.domains.pid.evaluate import evaluate_head
from jev_tune.domains.pid.plants import sample_plants, ultimate_gain

head = load_backend("models", kind="onnx")
plants = sample_plants(48, seed=3, heldout=True)
ku, tu = ultimate_gain(plants)
for mode in ("monitor", "hard_hold"):
    r = evaluate_head(head, plants, zn_gains(plants), ku, tu, budget=21, conformal=mode)
    d = r.decisions
    print(mode, d["axis_held"][d["decision_valid"]].mean(), d["harmful"][d["valid"]].mean(),
          r.actual_simulations.mean(), np.median(r.best_j), np.percentile(r.best_j, 90), r.best_j.max())
```

## 简体中文

split-CP否决既可在执行前生效（`hard_hold`），也可只记录（`monitor`）；两种模式计算的集合
完全相同，区别只在是否下发该步。PID实验场实测（48个留出对象、预算21、ONNX头）：执行前
保持轴比例0.0%/42.0%，有害测量步34.6%/24.0%，平均仿真次数21.0/9.1，最终代价中位数
1.123/1.908、p90 2.231/2.409、最大值2.577/3.832（前者monitor，后者hard_hold）。

结论：`hard_hold`减少有害执行与实验次数（保持后增益不再变化即提前结束），但本实验中
**并未改善尾部代价**，p90与最大值同样变差。准确表述是“以更高最终代价换取更少有害执行
与实验”，而不是“尾部安全”。因此默认值分开设置：PID评测器与CLI用monitor；通用壳
`ConformalPolicy`与`c/jev_config.h`默认`hard_hold`（设备上未经否决的执行代价更高）。
单一种子与单次抽样；逐步有害以前一次实测代价为基准，不是物理安全判据。复现代码见英文部分。
