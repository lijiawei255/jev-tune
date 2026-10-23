# Trajectory risk and alternative joint actions / 轨迹风险与替代联合动作

[English](#english) · [简体中文](#简体中文)

## English

The protocol was frozen before new data. Old tests are retrospective diagnosis only and the old failure is preserved. No model, action scale, sample size or risk budget was selected from evaluation outcomes. The sole primary candidate is trajectory_selected; the other arms cannot be selected for deployment after testing.

At each stage, the frozen risk model first selects the smallest predicted harmful probability among complete joint actions scaled by 1, 0.5 and 0.25, with stable scale-order ties. CP is then applied only to that selected action; only {noninferior} executes. Rejection stops, without choosing another candidate from its CP set. Initial prev_dJ is zeroed only for new risk inputs; proposal inputs are unchanged.

The new-versus-old risk comparison changes trajectories, data volume, scaling and initial risk-feature semantics together; it is not a causal isolation of one feature repair. Fixed behavior-scale training is also different from online per-stage scale selection.

| split | independent plants | candidate label rows | harmful labels |
| :--- | ---: | ---: | ---: |
| train | 1024 | 61440 | 13214 |
| temperature | 256 | 15360 | 3034 |
| development | 256 | 15330 | 3439 |

Rows from multiple stages/candidates of one plant are dependent and used for fitting or descriptive diagnostics, not counted as independent calibration plants. Training, temperature, development audit, stage calibration and final test cohorts are separated. The development audit performs no search.

Frozen risk temperature: 0.970665.

| arm | harmed trajectories / test plants | nominal risk 95% upper | nominal first execution 95% lower | mean J | p90 J | actual operating simulations | diagnostic simulations |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| monitor | 983/1024 | 0.969528 | 0.997079 | 1.357796 | 2.294926 | 21504 | 0 |
| old_initial512 | 0/1024 | 0.002921 | 0.148060 | 2.544516 | 3.657641 | 1195 | 1024 |
| old_reached2000 | 5/1024 | 0.010239 | 0.465069 | 2.317541 | 3.409565 | 1888 | 1024 |
| trajectory_full | 6/1024 | 0.011532 | 0.574731 | 2.146460 | 3.150350 | 2265 | 1024 |
| trajectory_selected | 8/1024 | 0.014052 | 0.559971 | 2.158651 | 3.149694 | 2770 | 1024 |

Primary frozen numerical criteria: **FAIL**; `research_only`.
Failed criteria: empirical_mean_cost_noninferior, empirical_p90_cost_noninferior.

**Additional implementation-validity audit: NOT ESTABLISHED; deployment_allowed=false.** Frozen numerical criteria and this audit are separate. Observed dependence on batch shape/row position leaves a canonical per-object mapping, calibration/test CP-score exchangeability, and independence of trajectory events unestablished in this run. The CP and one-sided 95% binomial quantities are therefore nominal calculations, not established exact CP/PAC guarantees for this machine implementation. A generic exchangeability disclaimer does not close this gap. This is an additional failure beyond the frozen numerical acceptance; deployment remains prohibited. A fixed inference mapping, fresh calibration and new prospective validation are required. See the [implementation-validity audit](../research/results/trajectory_risk_validity.json).

Harm remains any strict immediate increase in J, not final-parameter degradation or instability. Each arm returns its actually executed historical best. Alternative actions change the path, so the old fixed-path conflict proof does not directly apply to the new policy; this does not imply that the new policy must pass.

| arm | stage | initial plants | reached / fitted | rank | qhat | fallback reason |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| old_initial512 | 1 | 512 | 512/512 | 511 | 0.999002 | - |
| old_initial512 | 2 | 512 | 95/95 | 96 | 1.000000 | finite_sample_rank |
| old_initial512 | 3 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 4 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 5 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 6 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 7 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 8 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 9 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 10 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 11 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 12 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 13 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 14 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 15 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 16 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 17 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 18 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 19 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 20 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 1 | 2048 | 2048/2000 | 1991 | 0.994235 | - |
| old_reached2000 | 2 | 4096 | 2084/2000 | 1991 | 0.999117 | - |
| old_reached2000 | 3 | 7168 | 2069/2000 | 1991 | 0.998820 | - |
| old_reached2000 | 4 | 20000 | 1937/1937 | 1929 | 1.000000 | quota_shortfall |
| old_reached2000 | 5 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 6 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 7 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 8 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 9 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 10 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 11 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 12 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 13 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 14 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 15 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 16 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 17 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 18 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 19 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 20 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 1 | 2048 | 2048/2000 | 1991 | 0.963312 | - |
| trajectory_full | 2 | 3584 | 2179/2000 | 1991 | 0.937754 | - |
| trajectory_full | 3 | 7680 | 2150/2000 | 1991 | 0.963965 | - |
| trajectory_full | 4 | 12288 | 2006/2000 | 1991 | 0.956024 | - |
| trajectory_full | 5 | 17408 | 2025/2000 | 1991 | 0.952644 | - |
| trajectory_full | 6 | 20000 | 1563/1563 | 1557 | 1.000000 | quota_shortfall |
| trajectory_full | 7 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 8 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 9 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 10 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 11 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 12 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 13 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 14 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 15 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 16 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 17 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 18 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 19 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 20 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 1 | 2048 | 2048/2000 | 1991 | 0.964909 | - |
| trajectory_selected | 2 | 3584 | 2158/2000 | 1991 | 0.927509 | - |
| trajectory_selected | 3 | 4096 | 2051/2000 | 1991 | 0.944189 | - |
| trajectory_selected | 4 | 7680 | 2104/2000 | 1991 | 0.951104 | - |
| trajectory_selected | 5 | 11264 | 2085/2000 | 1991 | 0.953491 | - |
| trajectory_selected | 6 | 15872 | 2005/2000 | 1991 | 0.959310 | - |
| trajectory_selected | 7 | 20000 | 1634/1634 | 1627 | 1.000000 | quota_shortfall |
| trajectory_selected | 8 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 9 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 10 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 11 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 12 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 13 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 14 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 15 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 16 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 17 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 18 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 19 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 20 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |

The reached target is 2000, with at most 20000 initial plants per stage. Collection follows generation order; excess batch observations are fully charged and truncated only by predetermined order. Quota shortfall returns the full set as an additional engineering rule, distinct from mathematical rank exceeding n. A full set in the frozen prefix makes later stages structurally unreachable, recorded without wasteful simulation; one empty batch alone is not such proof.

The 20-stage budget remains 0.10, with alpha=0.005 per stage. CP requires exchangeability of stage calibration scores and future reached scores under the frozen prefix; this premise is unestablished for the batch-dependent machine mapping in this run. Independent Bernoulli trajectory events are also unestablished. The reported one-sided 95% binomial quantities are therefore nominal calculations, not evidence of established exact CP/PAC guarantees for this implementation. Even if those premises are closed in future, CP averages over calibration randomness, rather than guaranteeing every fixed calibration file or the risk fraction among accepted actions; separate one-sided quantities are not joint 95% confidence. Deployment is prohibited; hardware, noise changes, recovery and domain shift remain uncovered.

Actual total simulations: 513508; training/temperature/development: 93666; stage calibration: 386124; final evaluation: 33718.

Raw shards, SHA256, actual simulations and cache hits are recorded in research/results/trajectory_risk.json and trajectory_risk_raw/. Diagnostic observations cannot update operating history by themselves; an exact deterministic cached action may be reused only if subsequently actually adopted.

`python scripts/31_trajectory_risk.py --register-only` → `python scripts/31_trajectory_risk.py`

`python scripts/32_verify_trajectory_risk.py`

## 简体中文

协议先于新数据冻结；旧测试仅作诊断，旧失败结果原样保留。新模型、动作尺度、样本量及风险预算均未按评估结果选参。唯一主要候选为trajectory_selected，其余组仅用于解释，不能测试后换组上线。

每步先在完整联合动作的固定尺度1、0.5、0.25中，用冻结风险模型选择最小预测有害概率的候选；平局按尺度顺序。然后仅对选中动作构造CP集合，只有{非劣}执行。拒绝即停止，不根据CP集合再挑候选。风险输入的初态prev_dJ置零，提案模型输入不改。

新旧风险头比较同时改变训练轨迹、数据量、标准化和风险初态特征语义，因此不是单一特征修正的因果实验。固定行为尺度训练分布也不等于在线逐步选尺度分布。

| 数据划分 | 独立对象 | 候选标签行 | 有害标签 |
| :--- | ---: | ---: | ---: |
| train | 1024 | 61440 | 13214 |
| temperature | 256 | 15360 | 3034 |
| development | 256 | 15330 | 3439 |

同一对象的多步/多候选行相关，只用于训练或描述统计，不能当独立校准对象。训练、温度、开发诊断、逐步校准及最终测试对象分离。开发组不参与任何搜索。

固定风险温度: 0.970665.

| 组 | 有害轨迹 / 测试数 | 名义风险95%上界 | 名义首步执行95%下界 | mean J | p90 J | 实际运行仿真 | 诊断仿真 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| monitor | 983/1024 | 0.969528 | 0.997079 | 1.357796 | 2.294926 | 21504 | 0 |
| old_initial512 | 0/1024 | 0.002921 | 0.148060 | 2.544516 | 3.657641 | 1195 | 1024 |
| old_reached2000 | 5/1024 | 0.010239 | 0.465069 | 2.317541 | 3.409565 | 1888 | 1024 |
| trajectory_full | 6/1024 | 0.011532 | 0.574731 | 2.146460 | 3.150350 | 2265 | 1024 |
| trajectory_selected | 8/1024 | 0.014052 | 0.559971 | 2.158651 | 3.149694 | 2770 | 1024 |

主要候选的冻结数值判据: **FAIL**; `research_only`.
未通过项: empirical_mean_cost_noninferior, empirical_p90_cost_noninferior.

**额外的实现有效性审计：未建立；deployment_allowed=false。** 冻结数值判据与这一审计分开报告。本轮批次形状/行位置引起的输出依赖，使逐对象固定映射、校准/测试CP分数交换性及轨迹事件独立性均未建立。因此表内CP及单侧95%二项量只作名义计算，不能宣称本机器实现已获得精确CP/PAC保证；仅写一般交换性假设不足以弥补这一缺口。这是原数值验收之外的额外失败，继续禁止部署；需固定推理映射、重新校准和新的前瞻验证。 见[实现有效性审计](../research/results/trajectory_risk_validity.json)。

有害仍指一次即时J严格上升，不是最终参数恶化率或失稳率。两组返回各自真实执行历史最优。替代动作改变路径后，旧固定路径冲突的证明不直接适用于新策略；它也不意味着新策略必然通过。

| 组 | 步 | 初始对象 | 到达 / 用于拟合 | 秩 | qhat | 回退原因 |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| old_initial512 | 1 | 512 | 512/512 | 511 | 0.999002 | - |
| old_initial512 | 2 | 512 | 95/95 | 96 | 1.000000 | finite_sample_rank |
| old_initial512 | 3 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 4 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 5 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 6 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 7 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 8 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 9 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 10 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 11 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 12 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 13 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 14 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 15 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 16 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 17 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 18 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 19 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_initial512 | 20 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 1 | 2048 | 2048/2000 | 1991 | 0.994235 | - |
| old_reached2000 | 2 | 4096 | 2084/2000 | 1991 | 0.999117 | - |
| old_reached2000 | 3 | 7168 | 2069/2000 | 1991 | 0.998820 | - |
| old_reached2000 | 4 | 20000 | 1937/1937 | 1929 | 1.000000 | quota_shortfall |
| old_reached2000 | 5 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 6 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 7 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 8 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 9 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 10 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 11 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 12 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 13 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 14 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 15 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 16 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 17 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 18 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 19 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| old_reached2000 | 20 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 1 | 2048 | 2048/2000 | 1991 | 0.963312 | - |
| trajectory_full | 2 | 3584 | 2179/2000 | 1991 | 0.937754 | - |
| trajectory_full | 3 | 7680 | 2150/2000 | 1991 | 0.963965 | - |
| trajectory_full | 4 | 12288 | 2006/2000 | 1991 | 0.956024 | - |
| trajectory_full | 5 | 17408 | 2025/2000 | 1991 | 0.952644 | - |
| trajectory_full | 6 | 20000 | 1563/1563 | 1557 | 1.000000 | quota_shortfall |
| trajectory_full | 7 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 8 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 9 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 10 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 11 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 12 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 13 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 14 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 15 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 16 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 17 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 18 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 19 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_full | 20 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 1 | 2048 | 2048/2000 | 1991 | 0.964909 | - |
| trajectory_selected | 2 | 3584 | 2158/2000 | 1991 | 0.927509 | - |
| trajectory_selected | 3 | 4096 | 2051/2000 | 1991 | 0.944189 | - |
| trajectory_selected | 4 | 7680 | 2104/2000 | 1991 | 0.951104 | - |
| trajectory_selected | 5 | 11264 | 2085/2000 | 1991 | 0.953491 | - |
| trajectory_selected | 6 | 15872 | 2005/2000 | 1991 | 0.959310 | - |
| trajectory_selected | 7 | 20000 | 1634/1634 | 1627 | 1.000000 | quota_shortfall |
| trajectory_selected | 8 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 9 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 10 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 11 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 12 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 13 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 14 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 15 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 16 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 17 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 18 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 19 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |
| trajectory_selected | 20 | 0 | 0/0 | 1 | 1.000000 | unreachable_frozen_prefix |

目标到达数为2000，每步最多20000个初始对象。按生成顺序收集，批次超额观测全部计账，仅按预先次序截取。配额不足返回完整集合是额外工程保守规则，与数学秩超过n不同。冻结前缀已有完整集合时后续结构不可达，直接记录零样本；不把一次零到达批次当作不可达证明。

20步总预算0.10、每步alpha=0.005保持不变。CP定理需要逐步校准分数与冻结前缀下未来到达分数的交换性；本轮批次相关的机器映射尚未建立这一前提。轨迹事件的独立Bernoulli前提也未建立，因此所列单侧95%二项量只是名义计算，不能作为本实现已获精确CP/PAC保证的证据。即使未来闭合这些前提，CP仍对校准随机性取边际，不是每个固定校准文件的条件保证或获准子集风险比例界；两项单侧量也不构成联合95%。当前禁止部署，硬件、噪声变化、恢复及域外均未覆盖。

真实总仿真: 513508; 训练/温度/开发: 93666; 逐步校准: 386124; 最终评估: 33718.

原始分片、SHA256、实际仿真与缓存命中见research/results/trajectory_risk.json及trajectory_risk_raw/。诊断观测不得自行更新运行历史；仅在同一动作后来实际采用时可复用确定性缓存。

`python scripts/31_trajectory_risk.py --register-only` → `python scripts/31_trajectory_risk.py`

`python scripts/32_verify_trajectory_risk.py`
