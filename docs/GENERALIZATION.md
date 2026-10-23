# Generalization / 泛化

[English](#english) · [简体中文](#简体中文)

## English

Ten out-of-zoo scenarios, four deterministic jitters each. Head and CMA-ES have a maximum 20-run budget including the start; one-shot methods have their own actual costs. Analytic Ku/Tu is oracle prior information.

| scenario | head | Z-N | relay | CMA-ES | ratio | within 5% |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| dead_time | 0.886 | 1.055 | 2.077 | 0.760 | 1.166 | 0/4 |
| double_integrator | 3.254 | 9.036 | 3.965 | 3.049 | 1.067 | 1/4 |
| unstable_pole | 26.043 | 26.620 | 50.000 | 26.037 | 1.000 | 4/4 |
| inverted_pendulum | 50.000 | 50.000 | 50.000 | 50.000 | 1.000 | 3/4 |
| sharp_resonance | 7.384 | 8.133 | 7.269 | 8.133 | 1.016 | 4/4 |
| noisy_sensor | 1.400 | 2.828 | 1.578 | 2.412 | 0.887 | 4/4 |
| valve_dead_zone | 2.237 | 2.237 | 0.990 | 2.226 | 2.259 | 1/4 |
| flexible_arm | 7.756 | 8.497 | 7.649 | 8.497 | 1.014 | 4/4 |
| inverse_response | 1.239 | 1.428 | 5.468 | 0.801 | 1.547 | 1/4 |
| hydraulic | 1.178 | 2.339 | 4.299 | 1.678 | 0.702 | 4/4 |

Within 5% of the best classical result on 26/40 plants; median ratio 1.014908. Ties at divergent cost count in this comparison and do not mean a usable controller. Dead band, inverse response and unstable starts remain failures.

Reproduce: `python scripts/08_generalize.py`. See `research/results/generalization.json` and its manifest.

## 简体中文

十个分布外场景，每个四组确定性扰动。head与CMA-ES均最多20次，包含起点；一次性方法列自身实际用量。解析Ku/Tu属于oracle先验。

| scenario | head | Z-N | relay | CMA-ES | ratio | within 5% |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| dead_time | 0.886 | 1.055 | 2.077 | 0.760 | 1.166 | 0/4 |
| double_integrator | 3.254 | 9.036 | 3.965 | 3.049 | 1.067 | 1/4 |
| unstable_pole | 26.043 | 26.620 | 50.000 | 26.037 | 1.000 | 4/4 |
| inverted_pendulum | 50.000 | 50.000 | 50.000 | 50.000 | 1.000 | 3/4 |
| sharp_resonance | 7.384 | 8.133 | 7.269 | 8.133 | 1.016 | 4/4 |
| noisy_sensor | 1.400 | 2.828 | 1.578 | 2.412 | 0.887 | 4/4 |
| valve_dead_zone | 2.237 | 2.237 | 0.990 | 2.226 | 2.259 | 1/4 |
| flexible_arm | 7.756 | 8.497 | 7.649 | 8.497 | 1.014 | 4/4 |
| inverse_response | 1.239 | 1.428 | 5.468 | 0.801 | 1.547 | 1/4 |
| hydraulic | 1.178 | 2.339 | 4.299 | 1.678 | 0.702 | 4/4 |

40株中26株处于最强传统方法的5%以内，中位比值1.014908。发散代价上的并列也计入比较，不代表控制器可用；死区、反向响应与不稳定起点仍有失败。

复现：`python scripts/08_generalize.py`，产物及manifest见`research/results/generalization.json`。
