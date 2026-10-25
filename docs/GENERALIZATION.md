# Generalization / 泛化

[English](#english) · [简体中文](#简体中文)

## English

The v0.9 practical-budget study uses a separate fixed non-oracle start and new parameter instances of these known scenarios; see [PRACTICAL_BUDGET](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/PRACTICAL_BUDGET.md). It does not replace this frozen oracle-prior table. Scenario jitter multiplies the numerator and one denominator coefficient by `10**U(-0.3,0.3)` and delay by `U(0.8,1.2)`, not merely ±20% gain. Failed and divergent starts remain included.


Ten out-of-zoo scenarios, four deterministic jitters each. Head and CMA-ES have a maximum 20-run budget including the start; one-shot methods have their own actual costs. Analytic Ku/Tu is oracle prior information.

| scenario | head | Z-N | relay | CMA-ES | ratio | within 5% |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| dead_time | 0.804 | 1.055 | 2.077 | 0.760 | 1.058 | 1/4 |
| double_integrator | 3.131 | 9.036 | 3.965 | 3.049 | 1.027 | 4/4 |
| unstable_pole | 26.043 | 26.620 | 50.000 | 26.037 | 1.000 | 4/4 |
| inverted_pendulum | 50.000 | 50.000 | 50.000 | 50.000 | 1.000 | 3/4 |
| sharp_resonance | 7.384 | 8.133 | 7.269 | 8.133 | 1.016 | 4/4 |
| noisy_sensor | 1.417 | 2.828 | 1.578 | 2.412 | 0.898 | 4/4 |
| valve_dead_zone | 2.236 | 2.237 | 0.990 | 2.226 | 2.258 | 2/4 |
| flexible_arm | 7.756 | 8.497 | 7.649 | 8.497 | 1.014 | 4/4 |
| inverse_response | 1.243 | 1.428 | 5.468 | 0.801 | 1.552 | 1/4 |
| hydraulic | 1.138 | 2.339 | 4.299 | 1.678 | 0.678 | 4/4 |

Within 5% of the best classical result on 31/40 plants; median ratio 1.014908. Ties at divergent cost count in this comparison and do not mean a usable controller. Dead band, inverse response and unstable starts remain failures.

Reproduce: `python scripts/08_generalize.py`. See [`research/results/generalization.json`](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1) and its manifest.

## 简体中文

v0.9实用预算研究使用单独固定的非oracle起点，以及这些已知场景的新参数实例，见[PRACTICAL_BUDGET](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/PRACTICAL_BUDGET.md)，不替换本页冻结的oracle先验表。场景扰动将分子及一个分母系数分别乘以`10**U(-0.3,0.3)`，延时乘以`U(0.8,1.2)`，并非增益仅±20%。失败及发散起点均保留。


十个分布外场景，每个四组确定性扰动。head与CMA-ES均最多20次，包含起点；一次性方法列自身实际用量。解析Ku/Tu属于oracle先验。

| scenario | head | Z-N | relay | CMA-ES | ratio | within 5% |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| dead_time | 0.804 | 1.055 | 2.077 | 0.760 | 1.058 | 1/4 |
| double_integrator | 3.131 | 9.036 | 3.965 | 3.049 | 1.027 | 4/4 |
| unstable_pole | 26.043 | 26.620 | 50.000 | 26.037 | 1.000 | 4/4 |
| inverted_pendulum | 50.000 | 50.000 | 50.000 | 50.000 | 1.000 | 3/4 |
| sharp_resonance | 7.384 | 8.133 | 7.269 | 8.133 | 1.016 | 4/4 |
| noisy_sensor | 1.417 | 2.828 | 1.578 | 2.412 | 0.898 | 4/4 |
| valve_dead_zone | 2.236 | 2.237 | 0.990 | 2.226 | 2.258 | 2/4 |
| flexible_arm | 7.756 | 8.497 | 7.649 | 8.497 | 1.014 | 4/4 |
| inverse_response | 1.243 | 1.428 | 5.468 | 0.801 | 1.552 | 1/4 |
| hydraulic | 1.138 | 2.339 | 4.299 | 1.678 | 0.678 | 4/4 |

40株中31株处于最强传统方法的5%以内，中位比值1.014908。发散代价上的并列也计入比较，不代表控制器可用；死区、反向响应与不稳定起点仍有失败。

复现：`python scripts/08_generalize.py`，产物及manifest见[`research/results/generalization.json`](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1)。
