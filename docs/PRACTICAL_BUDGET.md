# Practical simulation budgets / 实用仿真预算

[English](#english) · [简体中文](#简体中文)

## English

This descriptive check keeps the existing model and runtime settings. It spends 7995 actual simulations against a preregistered maximum of 8192; each arm's initial measurement is included. The protocol was committed as `f6aafde` before execution. No training, parameter selection, reference optimization or additional verification simulations were performed.

All four methods start at PID gains `[0.6, 1.2, 0.075]`, use bounds `[0.0001, 1000]`, and reset the same simulator for a 10-second unit-step response. The head receives fixed assumed Ku=Tu=1, not an analytic oracle or a successful identification. Budgets 4, 8 and 20 are separate runs. CP is monitoring only. The cohorts contain 12 fresh two-mass draws, 12 seeded jitters of known thermal anchors and four fresh variants of each of ten existing out-of-zoo scenarios. These are known families, not a new independent family-level validation. Thermal T and delay each vary by ±10%; scenario numerator and one denominator coefficient each vary by a factor 10**U(-0.3,0.3), and delay by ±20%.

Lower returned J is better; compare it together with actual calls. Fewer calls alone is not success. A failed response follows `metrics.is_failed` (absolute final error >0.5, nonfinite error or sampled output magnitude >12); divergence uses the simulator cost sentinel J≥50. Failed starts, trials and returned controllers are retained. Returning the best measured point cannot prove safe exploration. Trial-worse-than-start counts and worst trial costs are also available per group in JSON; they are simulation diagnostics, not a trajectory-risk guarantee. The pooled mean weights each plant equally and the small scenario groups have only four plants.

| budget | method | mean / median / p90 J | actual calls mean (min–max) | final failed | trial divergence |
| ---: | :--- | ---: | ---: | ---: | ---: |
| 4 | cmaes | 8.381760 / 2.786286 / 15.882099 | 4.000 (4–4) | 22/64 | 10/64 |
| 4 | jev_head | 9.330184 / 2.351392 / 50.000000 | 3.703 (1–4) | 21/64 | 10/64 |
| 4 | simplex | 8.998029 / 3.036451 / 39.982001 | 4.000 (4–4) | 20/64 | 10/64 |
| 4 | vocab_hill | 8.618793 / 2.614199 / 39.725470 | 4.000 (4–4) | 19/64 | 10/64 |
| 8 | cmaes | 8.159355 / 2.542493 / 15.106381 | 8.000 (8–8) | 22/64 | 10/64 |
| 8 | jev_head | 8.257394 / 1.924203 / 39.965497 | 7.266 (1–8) | 19/64 | 10/64 |
| 8 | simplex | 8.651402 / 2.701620 / 39.982001 | 8.000 (8–8) | 19/64 | 10/64 |
| 8 | vocab_hill | 8.230496 / 2.274360 / 39.250037 | 8.000 (8–8) | 19/64 | 10/64 |
| 20 | cmaes | 7.366613 / 1.894782 / 12.902099 | 20.000 (20–20) | 17/64 | 10/64 |
| 20 | jev_head | 8.022816 / 1.843395 / 38.097492 | 17.953 (1–20) | 17/64 | 10/64 |
| 20 | simplex | 8.291111 / 2.404942 / 39.982001 | 20.000 (20–20) | 18/64 | 10/64 |
| 20 | vocab_hill | 7.047616 / 1.770341 / 11.168309 | 20.000 (20–20) | 17/64 | 10/64 |

| group, budget 20 | head J | hill J | CMA J | simplex J | head actual calls | head failed |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| dead_time (n=4) | 1.748101 | 1.549338 | 1.539012 | 1.546089 | 20.000 | 0/4 |
| double_integrator (n=4) | 4.624478 | 8.447126 | 10.113924 | 22.600240 | 20.000 | 0/4 |
| flexible_arm (n=4) | 7.632424 | 6.496813 | 6.571942 | 5.997240 | 20.000 | 4/4 |
| hydraulic (n=4) | 1.541970 | 1.093924 | 1.103566 | 1.023484 | 20.000 | 0/4 |
| inverse_response (n=4) | 5.746173 | 1.122418 | 4.090732 | 4.421046 | 20.000 | 2/4 |
| inverted_pendulum (n=4) | 50.000000 | 50.000000 | 50.000000 | 50.000000 | 1.000 | 4/4 |
| noisy_sensor (n=4) | 2.309496 | 2.093271 | 1.950216 | 1.958361 | 20.000 | 0/4 |
| sharp_resonance (n=4) | 7.291867 | 6.118430 | 6.214845 | 5.693872 | 20.000 | 4/4 |
| thermal_jitter (n=12) | 2.013557 | 2.242575 | 2.614794 | 2.509194 | 20.000 | 0/12 |
| two_mass (n=12) | 0.547965 | 0.681296 | 0.564300 | 0.619998 | 20.000 | 0/12 |
| unstable_pole (n=4) | 38.387301 | 25.878396 | 25.619372 | 28.799252 | 6.250 | 3/4 |
| valve_dead_zone (n=4) | 1.398672 | 1.190522 | 1.124918 | 1.230620 | 20.000 | 0/4 |

| budget | baseline | head − baseline mean J | head better / equal / worse | head − baseline mean calls |
| ---: | :--- | ---: | ---: | ---: |
| 4 | vocab_hill | 0.711391 | 33 / 9 / 22 | -0.297 |
| 4 | cmaes | 0.948424 | 31 / 8 / 25 | -0.297 |
| 4 | simplex | 0.332156 | 44 / 7 / 13 | -0.297 |
| 8 | vocab_hill | 0.026898 | 28 / 8 / 28 | -0.734 |
| 8 | cmaes | 0.098039 | 32 / 7 / 25 | -0.734 |
| 8 | simplex | -0.394008 | 29 / 6 / 29 | -0.734 |
| 20 | vocab_hill | 0.975200 | 25 / 6 / 33 | -2.047 |
| 20 | cmaes | 0.656202 | 22 / 7 / 35 | -2.047 |
| 20 | simplex | -0.268296 | 19 / 6 / 39 | -2.047 |

All cost differences are paired by object; negative head-minus-baseline J means lower head cost. Boundary-table J is the group mean. There is no significance test, superiority acceptance, deployment gate or CP/PAC guarantee. The fixed starting point may be poor and these numbers do not establish benefit with accurate user priors, a new objective, arbitrary Simulink models or hardware. Numerical batch layout and the reference environment are recorded; cross-platform bitwise trajectory reproduction is not claimed.

Sources: [protocol](../research/protocols/practical_budget_v090.json), [summary](../research/results/practical_budget.json), [complete measured ledger](../research/results/practical_budget_raw.json.gz). After freezing the protocol and code, `python scripts/39_practical_budget.py --run` writes new artifacts and refuses existing output. Use `--output-root <new-directory>` for a separate replay. `python scripts/39_practical_budget.py --check` validates protocol/source/model/raw hashes, all real-call and measured-best invariants, raw-derived summaries, and this bilingual document without running a simulation. No historical scientific result is overwritten.

## 简体中文

本描述性检查固定现有模型与运行设置，共实测7995次仿真，协议上限为8192次，每臂初测均在预算内。协议在执行前独立提交为`f6aafde`。没有训练、选参、参考优化或额外复测。

四种方法均从PID增益`[0.6, 1.2, 0.075]`出发，范围为`[0.0001, 1000]`，使用同一重置仿真器的10秒单位阶跃响应。head的Ku=Tu=1是固定假设，不来自解析真值或成功辨识。4、8、20次预算分别真实运行；CP仅监测。对象包括12个新双质量参数实例、12个已知热工锚点的固定种子扰动，以及十个既有域外场景各4个新变体。这些是已知族，不能称新的独立族级验证。热工T和延时分别±10%；场景分子及一个分母系数分别乘10**U(-0.3,0.3)，延时±20%。

返回代价J越低越好，必须与实际次数一起看，少调用本身不代表成功。失败响应沿用`metrics.is_failed`：末值绝对误差>0.5、非有限误差或采样输出幅值>12；发散沿用J≥50代价标志。差初态、失败试验和失败返回全部保留。返回实测最优不保证探索安全。JSON还按组列出试验比初态更差的株数及最差试验代价，属于仿真诊断而非轨迹风险保证。总体均值每株等权，每个域外场景仅4株。

| budget | method | mean / median / p90 J | actual calls mean (min–max) | final failed | trial divergence |
| ---: | :--- | ---: | ---: | ---: | ---: |
| 4 | cmaes | 8.381760 / 2.786286 / 15.882099 | 4.000 (4–4) | 22/64 | 10/64 |
| 4 | jev_head | 9.330184 / 2.351392 / 50.000000 | 3.703 (1–4) | 21/64 | 10/64 |
| 4 | simplex | 8.998029 / 3.036451 / 39.982001 | 4.000 (4–4) | 20/64 | 10/64 |
| 4 | vocab_hill | 8.618793 / 2.614199 / 39.725470 | 4.000 (4–4) | 19/64 | 10/64 |
| 8 | cmaes | 8.159355 / 2.542493 / 15.106381 | 8.000 (8–8) | 22/64 | 10/64 |
| 8 | jev_head | 8.257394 / 1.924203 / 39.965497 | 7.266 (1–8) | 19/64 | 10/64 |
| 8 | simplex | 8.651402 / 2.701620 / 39.982001 | 8.000 (8–8) | 19/64 | 10/64 |
| 8 | vocab_hill | 8.230496 / 2.274360 / 39.250037 | 8.000 (8–8) | 19/64 | 10/64 |
| 20 | cmaes | 7.366613 / 1.894782 / 12.902099 | 20.000 (20–20) | 17/64 | 10/64 |
| 20 | jev_head | 8.022816 / 1.843395 / 38.097492 | 17.953 (1–20) | 17/64 | 10/64 |
| 20 | simplex | 8.291111 / 2.404942 / 39.982001 | 20.000 (20–20) | 18/64 | 10/64 |
| 20 | vocab_hill | 7.047616 / 1.770341 / 11.168309 | 20.000 (20–20) | 17/64 | 10/64 |

| group, budget 20 | head J | hill J | CMA J | simplex J | head actual calls | head failed |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| dead_time (n=4) | 1.748101 | 1.549338 | 1.539012 | 1.546089 | 20.000 | 0/4 |
| double_integrator (n=4) | 4.624478 | 8.447126 | 10.113924 | 22.600240 | 20.000 | 0/4 |
| flexible_arm (n=4) | 7.632424 | 6.496813 | 6.571942 | 5.997240 | 20.000 | 4/4 |
| hydraulic (n=4) | 1.541970 | 1.093924 | 1.103566 | 1.023484 | 20.000 | 0/4 |
| inverse_response (n=4) | 5.746173 | 1.122418 | 4.090732 | 4.421046 | 20.000 | 2/4 |
| inverted_pendulum (n=4) | 50.000000 | 50.000000 | 50.000000 | 50.000000 | 1.000 | 4/4 |
| noisy_sensor (n=4) | 2.309496 | 2.093271 | 1.950216 | 1.958361 | 20.000 | 0/4 |
| sharp_resonance (n=4) | 7.291867 | 6.118430 | 6.214845 | 5.693872 | 20.000 | 4/4 |
| thermal_jitter (n=12) | 2.013557 | 2.242575 | 2.614794 | 2.509194 | 20.000 | 0/12 |
| two_mass (n=12) | 0.547965 | 0.681296 | 0.564300 | 0.619998 | 20.000 | 0/12 |
| unstable_pole (n=4) | 38.387301 | 25.878396 | 25.619372 | 28.799252 | 6.250 | 3/4 |
| valve_dead_zone (n=4) | 1.398672 | 1.190522 | 1.124918 | 1.230620 | 20.000 | 0/4 |

| budget | baseline | head − baseline mean J | head better / equal / worse | head − baseline mean calls |
| ---: | :--- | ---: | ---: | ---: |
| 4 | vocab_hill | 0.711391 | 33 / 9 / 22 | -0.297 |
| 4 | cmaes | 0.948424 | 31 / 8 / 25 | -0.297 |
| 4 | simplex | 0.332156 | 44 / 7 / 13 | -0.297 |
| 8 | vocab_hill | 0.026898 | 28 / 8 / 28 | -0.734 |
| 8 | cmaes | 0.098039 | 32 / 7 / 25 | -0.734 |
| 8 | simplex | -0.394008 | 29 / 6 / 29 | -0.734 |
| 20 | vocab_hill | 0.975200 | 25 / 6 / 33 | -2.047 |
| 20 | cmaes | 0.656202 | 22 / 7 / 35 | -2.047 |
| 20 | simplex | -0.268296 | 19 / 6 / 39 | -2.047 |

代价差按对象配对；head减基线J为负表示head代价更低。边界表列组内平均J。没有显著性检验、优越性验收、部署开关或CP/PAC保证。固定起点可能很差，结果不能外推到准确用户先验、新目标函数、任意Simulink模型或硬件。记录数值批布局和参考环境，不宣称跨平台逐位轨迹复现。

来源：[协议](../research/protocols/practical_budget_v090.json)、[汇总](../research/results/practical_budget.json)、[完整逐次实测账本](../research/results/practical_budget_raw.json.gz)。协议与代码冻结后运行`python scripts/39_practical_budget.py --run`，若输出已存在则拒绝覆盖；另用`--output-root <new-directory>`单独复现。`python scripts/39_practical_budget.py --check`不运行仿真，检查协议/源码/模型/原始账本hash、真实次数与返回实测最优约束、由原始账本重算的汇总及本双语文档。旧科学结果不覆盖。
