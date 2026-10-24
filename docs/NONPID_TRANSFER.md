# Trained non-PID transfer / 非PID训练迁移

[English](#english) · [简体中文](#简体中文)

## English

Framework transfer is **PASS** after the independent evidence checker passes. Policy-value acceptance is **negative_stop**. The learned policy failed the frozen stable-benefit rule. The outcome is `negative_stop`: preserve all trained artifacts and evidence and stop policy/risk deepening on this test.

The protocol was frozen in `b4b8858`, with verification accounting clarified in `9cd159f` before acquisition. One prospective run trains the three fixed seeds on shared teacher data and tests every frozen arm on the same 256 new signals. Seeds are correlated model replicates, not 768 independent test objects. No architecture, checkpoint, threshold, task variant or acceptance criterion is selected from test results. Budget 8 is secondary; budget 20 alone determines policy-value acceptance. Every model must have mean MSE at most 0.95 times each baseline and p90 no greater than each baseline; this is an empirical stability rule, not a confidence guarantee or a significance test.

The task is synthetic, offline reference denoising calibration: adjust a local winsorization multiplier and a low-pass cutoff through two bounded additive coordinates. Each 192-sample noisy/reference pair is immutable and resettable. A full filter execution measures reference MSE. The clean signal and latent generator parameters are excluded from policy input, but reference MSE is supplied by the evaluator; this is not blind denoising or validation on external data. Filtering deliberately uses future samples. The initial normalized coordinates are `[0.5, 0.5]`; every operating arm includes that initial measurement in its budget, returns its best actually measured point, and receives no uncharged final optimization.

| budget | method | mean / median / p90 MSE | actual calls mean (min–max) |
| ---: | :--- | ---: | ---: |
| 8 | `coordinate_search` | 0.01648699 / 0.01299753 / 0.03325589 | 8.000000 (8–8) |
| 8 | `simplex` | 0.01564696 / 0.01233312 / 0.03089400 | 8.000000 (8–8) |
| 8 | `space_filling` | 0.01589837 / 0.01285487 / 0.03203129 | 8.000000 (8–8) |
| 8 | `typed_seed_101` | 0.01605888 / 0.01336950 / 0.03094641 | 8.000000 (8–8) |
| 8 | `typed_seed_202` | 0.01600915 / 0.01316406 / 0.03083002 | 8.000000 (8–8) |
| 8 | `typed_seed_303` | 0.01601969 / 0.01318240 / 0.03089533 | 8.000000 (8–8) |
| 20 | `coordinate_search` | 0.01524690 / 0.01228943 / 0.03075090 | 19.847656 (17–20) |
| 20 | `simplex` | 0.01423997 / 0.01161406 / 0.02962768 | 20.000000 (20–20) |
| 20 | `space_filling` | 0.01488830 / 0.01218638 / 0.03010520 | 20.000000 (20–20) |
| 20 | `typed_seed_101` | 0.01582834 / 0.01319646 / 0.03094641 | 19.925781 (12–20) |
| 20 | `typed_seed_202` | 0.01555577 / 0.01275519 / 0.03059184 | 19.968750 (12–20) |
| 20 | `typed_seed_303` | 0.01576981 / 0.01299860 / 0.03058048 | 19.984375 (17–20) |

| seed | baseline, primary budget 20 | mean rule | p90 rule |
| ---: | :--- | :--- | :--- |
| 101 | `coordinate_search` | FAIL | FAIL |
| 101 | `space_filling` | FAIL | FAIL |
| 101 | `simplex` | FAIL | FAIL |
| 202 | `coordinate_search` | FAIL | PASS |
| 202 | `space_filling` | FAIL | FAIL |
| 202 | `simplex` | FAIL | FAIL |
| 303 | `coordinate_search` | FAIL | PASS |
| 303 | `space_filling` | FAIL | FAIL |
| 303 | `simplex` | FAIL | FAIL |

Temperature scaling and split CP use distinct independent signal splits after weight fitting. Each fitted checkpoint is applied in the canonical `(1,16)` float64 CPU mapping on every calibration and operating inference. CP retains complete sets in monitor mode and never changes an action. Its 90% marginal teacher-label inclusion boundary is per axis on independent initial-state signals under this fixed generator and inference mapping. It does not cover both axes jointly, reached states, accepted-action risk, closed-loop safety or performance. Empirical test coverage is descriptive and never changes a threshold. Noul reports finite observation validity; it is not a trained harmful-action probability.

| seed | initial-state coverage, axes 0 / 1 | mean complete-set size, axes 0 / 1 |
| ---: | ---: | ---: |
| 101 | 0.929688 / 0.910156 | 1.929688 / 2.804688 |
| 202 | 0.921875 / 0.914062 | 2.027344 / 2.843750 |
| 303 | 0.925781 / 0.902344 | 1.929688 / 2.738281 |

Acquisition executed **76683** fresh objectives against the frozen maximum **83840**. Exact coordinate duplicates reuse only their own ledger; no cache is shared across splits, objects, arms or budgets. Shared teacher acquisition is physically charged once, and its complete training + temperature + CP cost is charged to every deployable model's standalone cost: **27345** objective evaluations. Offline test teacher labels are separate from operating calls and never fit a model. Model optimizer time is recorded separately from objective calls.

| phase | actual fresh objective evaluations |
| :--- | ---: |
| `train` | 17745 |
| `temperature` | 3200 |
| `conformal` | 6400 |
| `test` | 6400 |
| `operating` | 42938 |

| model seed | SGD steps | CPU seconds | wall seconds |
| ---: | ---: | ---: | ---: |
| 101 | 800 | 0.453125 | 0.474216 |
| 202 | 800 | 0.562500 | 0.568371 |
| 303 | 800 | 1.093750 | 1.146802 |

Cost versus task count is descriptive and uses actual operating calls. The break-even entry remains null when the learned method does not reduce operating calls. It does not assert equal quality merely because calls match or decrease.

| seed | baseline | call-only break-even tasks | learned / baseline calls after 100 tasks |
| ---: | :--- | ---: | ---: |
| 101 | `coordinate_search` | null | 29337.578125 / 1984.765625 |
| 101 | `space_filling` | 368438 | 29337.578125 / 2000.000000 |
| 101 | `simplex` | 368438 | 29337.578125 / 2000.000000 |
| 202 | `coordinate_search` | null | 29341.875000 / 1984.765625 |
| 202 | `space_filling` | 875040 | 29341.875000 / 2000.000000 |
| 202 | `simplex` | 875040 | 29341.875000 / 2000.000000 |
| 303 | `coordinate_search` | null | 29343.437500 / 1984.765625 |
| 303 | `space_filling` | 1750080 | 29343.437500 / 2000.000000 |
| 303 | `simplex` | 1750080 | 29343.437500 / 2000.000000 |

Reusable components are unchanged `Choice`/`Option`/`Answer`/`Noul`, softmax, temperature fitting, split CP and `decide` for ordered numeric payloads. The domain owns observations, teacher labels, this two-axis MLP, reference objective, additive actuation, ledger, baselines and acceptance. PID weights, three-axis features, multiplicative gain updates, PID rollback and complex joint-risk heads are not transferred. Score remains an optional unused primitive. Existing Python/C/MATLAB PID deployment is unchanged.

Sources: [frozen protocol](../research/protocols/nonpid_transfer_v0100.json), [summary](../research/results/nonpid_transfer/report.json), [raw measured records](../research/results/nonpid_transfer/raw.json.gz). `python scripts/45_nonpid_transfer.py --run` refuses existing outputs; use `--output-root <new-directory>` for a separate replay. `python scripts/46_verify_nonpid_transfer.py --check` independently reconstructs recorded objectives, labels, calibration, decisions, budgets and acceptance. Each audit reports and persists its additional deterministic filter executions separately; these are verification compute, not new independent data or prospective acquisition. Historical failed risk studies remain available unchanged.

## 简体中文

独立证据检查通过后，框架迁移验收为**PASS**；策略价值验收为**negative_stop**。学习策略未通过冻结的稳定收益规则，结论为`negative_stop`：保留全部训练产物与证据，停止利用本测试继续深化策略或风险头。

协议在`b4b8858`冻结，并在采集前由`9cd159f`明确复核计账。一次前瞻执行使用共享teacher数据训练三个固定种子，在同一批256个新信号上测试全部冻结方法。三个种子是相关模型重复，不是768个独立测试对象。没有用测试结果挑选架构、checkpoint、阈值、任务变体或验收条件。8次预算属于次要诊断，只有20次预算决定策略价值验收。每个种子的平均MSE都必须不高于每条基线的0.95倍，p90也不得高于每条基线；这属于经验稳定性规则，不是置信保证或显著性检验。

任务是合成的离线参考去噪标定，通过两个有界加法坐标调整局部截断倍数及低通截止频率。每个192点带噪/参考信号对固定且可重置，一次完整滤波执行计算参考MSE。策略输入没有干净波形及隐含生成参数，但评估器提供参考MSE，因此不能称盲去噪或外部数据验证；非因果滤波有意使用未来样本。所有方法都从归一化坐标`[0.5, 0.5]`起步，初测计入运行预算，只返回实际测过的最优点，没有免费末次优化。

| budget | method | mean / median / p90 MSE | actual calls mean (min–max) |
| ---: | :--- | ---: | ---: |
| 8 | `coordinate_search` | 0.01648699 / 0.01299753 / 0.03325589 | 8.000000 (8–8) |
| 8 | `simplex` | 0.01564696 / 0.01233312 / 0.03089400 | 8.000000 (8–8) |
| 8 | `space_filling` | 0.01589837 / 0.01285487 / 0.03203129 | 8.000000 (8–8) |
| 8 | `typed_seed_101` | 0.01605888 / 0.01336950 / 0.03094641 | 8.000000 (8–8) |
| 8 | `typed_seed_202` | 0.01600915 / 0.01316406 / 0.03083002 | 8.000000 (8–8) |
| 8 | `typed_seed_303` | 0.01601969 / 0.01318240 / 0.03089533 | 8.000000 (8–8) |
| 20 | `coordinate_search` | 0.01524690 / 0.01228943 / 0.03075090 | 19.847656 (17–20) |
| 20 | `simplex` | 0.01423997 / 0.01161406 / 0.02962768 | 20.000000 (20–20) |
| 20 | `space_filling` | 0.01488830 / 0.01218638 / 0.03010520 | 20.000000 (20–20) |
| 20 | `typed_seed_101` | 0.01582834 / 0.01319646 / 0.03094641 | 19.925781 (12–20) |
| 20 | `typed_seed_202` | 0.01555577 / 0.01275519 / 0.03059184 | 19.968750 (12–20) |
| 20 | `typed_seed_303` | 0.01576981 / 0.01299860 / 0.03058048 | 19.984375 (17–20) |

| seed | baseline, primary budget 20 | mean rule | p90 rule |
| ---: | :--- | :--- | :--- |
| 101 | `coordinate_search` | FAIL | FAIL |
| 101 | `space_filling` | FAIL | FAIL |
| 101 | `simplex` | FAIL | FAIL |
| 202 | `coordinate_search` | FAIL | PASS |
| 202 | `space_filling` | FAIL | FAIL |
| 202 | `simplex` | FAIL | FAIL |
| 303 | `coordinate_search` | FAIL | PASS |
| 303 | `space_filling` | FAIL | FAIL |
| 303 | `simplex` | FAIL | FAIL |

权重训练后，温度缩放与Split CP分别使用两个独立信号划分。所有校准和运行推理均使用固定checkpoint的`(1,16)` float64 CPU映射。CP在monitor模式保留完整集合，不改变动作。90%边际teacher标签包含边界仅针对固定生成器及推理映射下、独立初态信号的单轴标签；不保证联合双轴、到达状态、已接受动作风险、闭环安全或性能。测试经验覆盖率仅描述结果，不能用来修改阈值。Noul只表示观测是否有限，不是训练得到的有害动作概率。

| seed | initial-state coverage, axes 0 / 1 | mean complete-set size, axes 0 / 1 |
| ---: | ---: | ---: |
| 101 | 0.929688 / 0.910156 | 1.929688 / 2.804688 |
| 202 | 0.921875 / 0.914062 | 2.027344 / 2.843750 |
| 303 | 0.925781 / 0.902344 | 1.929688 / 2.738281 |

前瞻采集共真实执行**76683**次目标函数，冻结上限为**83840**次。完全相同的坐标只在自己的账本内复用，不跨划分、对象、方法或预算共享缓存。共享teacher采集物理上只计一次，同时每个可部署模型均独立承担完整训练、温度和CP采集成本：**27345**次目标函数。测试teacher标签单独计账，不用于拟合模型，不混入在线运行次数。优化器时间与目标调用次数分开报告。

| phase | actual fresh objective evaluations |
| :--- | ---: |
| `train` | 17745 |
| `temperature` | 3200 |
| `conformal` | 6400 |
| `test` | 6400 |
| `operating` | 42938 |

| model seed | SGD steps | CPU seconds | wall seconds |
| ---: | ---: | ---: | ---: |
| 101 | 800 | 0.453125 | 0.474216 |
| 202 | 800 | 0.562500 | 0.568371 |
| 303 | 800 | 1.093750 | 1.146802 |

随任务次数的成本比较采用实际运行次数，仅作描述。当学习方法没有减少运行调用时，收支平衡项保持null。调用相同或更少也不表示质量相同。

| seed | baseline | call-only break-even tasks | learned / baseline calls after 100 tasks |
| ---: | :--- | ---: | ---: |
| 101 | `coordinate_search` | null | 29337.578125 / 1984.765625 |
| 101 | `space_filling` | 368438 | 29337.578125 / 2000.000000 |
| 101 | `simplex` | 368438 | 29337.578125 / 2000.000000 |
| 202 | `coordinate_search` | null | 29341.875000 / 1984.765625 |
| 202 | `space_filling` | 875040 | 29341.875000 / 2000.000000 |
| 202 | `simplex` | 875040 | 29341.875000 / 2000.000000 |
| 303 | `coordinate_search` | null | 29343.437500 / 1984.765625 |
| 303 | `space_filling` | 1750080 | 29343.437500 / 2000.000000 |
| 303 | `simplex` | 1750080 | 29343.437500 / 2000.000000 |

复用边界为未改动的`Choice`/`Option`/`Answer`/`Noul`、softmax、温度拟合、Split CP，以及处理有序数值载荷的`decide`。新领域负责观测、teacher标签、双轴MLP、参考目标函数、加法执行器、账本、基线及验收。PID权重、三轴特征、乘法增益更新、PID回退与复杂联合风险头均未迁移；Score作为可选原语，本例未使用。既有Python/C/MATLAB PID部署不变。

来源：[冻结协议](../research/protocols/nonpid_transfer_v0100.json)、[汇总](../research/results/nonpid_transfer/report.json)、[原始实测记录](../research/results/nonpid_transfer/raw.json.gz)。`python scripts/45_nonpid_transfer.py --run`拒绝覆盖已有输出；使用`--output-root <new-directory>`单独复现。`python scripts/46_verify_nonpid_transfer.py --check`独立重建已记录目标、标签、校准、决策、预算和验收。每次复核单独报告并保存额外确定性滤波执行次数，属于复核算力，不是新增独立样本或前瞻采集。历史失败风险研究保持原样可用。
