# Rollout failure diagnosis / 多轮实验失败归因

[English](#english) · [简体中文](#简体中文)

## English

This is a post-hoc recomputation of published raw traces. No new simulation, fitting, tuning or test replacement is performed; original results and acceptance remain intact. All numbers use public raw traces and the v1 risk model, without an untracked training NPZ.

Every harmful label uses strict J_after > J_before with zero tolerance; noninferior means J_after ≤ J_before. A trajectory harm event is at least one actually executed joint action increasing cost, not instability or degradation of the final returned parameters.

| stage | reached n | rank | q | actual noninferior / harmful |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 512 | 511 | 0.994453120322 | 482 / 30 |
| 2 | 245 | 245 | 0.999988548670 | 227 / 18 |
| 3 | 56 | 57 | 1.000000000000 | 55 / 1 |
| 4 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 5 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 6 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 7 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 8 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 9 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 10 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 11 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 12 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 13 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 14 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 15 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 16 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 17 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 18 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 19 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 20 | 0 | 1 | 1.000000000000 | 0 / 0 |

Stage 2 already has 245 samples; its extreme q is not an insufficient-sample fallback. The maximum score comes from an actually noninferior case, plant_index=358: J 5.437280028→5.081413604, p(harmful)=0.999988548670. A shared LAC threshold expands to include this true label and also puts both labels into other sets. With q>0.5 and only {noninferior} admitted, p(harmful) must be below 1-q, approximately 1.14513304886e-05.

| stage | harmful-case p(harmful) median / minimum | noninferior-case p(harmful) median |
| ---: | ---: | ---: |
| 1 | 0.258446 / 0.003066 | 0.005185 |
| 2 | 0.024856 / 0.000279 | 0.000328 |
| 3 | 0.446130 / 0.446130 | 0.672458 |

These are calibration plants under the actual gated prefix, not later monitor states. The tails contain both underestimated harmful actions and overestimated noninferior actions. Calibration-set admission counts are retrospective, not independent validation.

| rejection stage | rejected | noninferior / harmful | contribution to cohort mean gap | share of total gap |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 506 | 460 / 46 | 0.619815 | 61.6080% |
| 2 | 416 | 382 / 34 | 0.358117 | 35.5959% |
| 3 | 102 | 102 / 0 | 0.028130 | 2.7961% |

The first two stages account for most of the final cost gap. This groups observed paired differences by rejection stage; it is not causal mediation. All stage-3 rejected proposals were noninferior in diagnostic measurements, which does not authorize changing the frozen q.

Exactly zero model coefficients: 7.
`log_Kp/Kp_zn, log_Kd/Kd_zn, prev_dlog_Kp, prev_dlog_Ki, prev_dlog_Kd, iter_frac, log_Ku/Kp`

These inputs contribute nothing to this linear risk head. Public scaler means/scales can be checked, but scale=1 alone does not prove zero training variance; unread training ranges are not inferred. The training protocol covers one initial analytic-ZN state per plant.

prev_dJ: fitted mean=-0.517598; scale=0.270362; coefficient=1.445288.
The formula is clip((previous_J-current_J)/5,-3,3). Initially previous_J=0, so it encodes -current_J/5; later it encodes the previous measured improvement. The formula is checked against individual raw transitions.

| calibration stage | prev_dJ median | standardized median | median contribution to scaled harmful logit |
| ---: | ---: | ---: | ---: |
| 1 | -0.505081 | 0.046299 | 0.068123 |
| 2 | 0.069871 | 2.172896 | 3.197164 |
| 3 | 0.018140 | 1.981557 | 2.915632 |

These describe feature and model-computation shifts; they do not establish that one feature independently caused the final performance gap.

At alpha=0.005 per stage, avoiding rank>n needs at least 199 independent reached samples; n=199–398 still uses the maximum score. Adequate sample size does not ensure a small q or useful admission. Stage 3's old reach rate is 0.109375: the minimum needs 143 further reached samples, approximately 1307.4 new initial plants under the old prefix; collecting 512 reached from scratch needs approximately 4681.1 initial plants. These are neither guaranteed budgets nor actual simulation counts.

Fixed-path acceptance conflict: all 1024 gated operating histories are verified monitor prefixes, and returned cost is the measured history minimum. Every best_gated≥best_monitor, so mathematical zero-slack mean noninferiority requires equality plant by plant. For 700 plants, monitor's best is strictly below every pre-first-harm cost. Retaining those optima requires harmful execution on at least 68.359375% of plants, incompatible with the 10% trajectory-risk upper bound.

Even allowing the loose cap of 102 harmed plants, the mean gap is at least 6.26694770202e-06. A conservative bound for two binary64 mean computations is 6.11037859039e-12, leaving margin 6.26694159164e-06>0. Mean rounding cannot hide the conflict; this is not a bound on physical simulation error.

This conclusion concerns this finite deterministic cohort, the same starts/horizon, and accept-whole-action-or-stop gates. It is not a population theorem or an impossibility result for different action paths. Risk-head retraining and more calibration alone cannot make these fixed paths pass both original criteria. Changing the action path is necessary to escape this restriction, not sufficient for success; the actual executed joint action then needs new calibration and independent evaluation.

Future work should train on development data covering multi-round states and actual joint actions, then freeze the model, temperature, proposal and budgets. Use independent new plants at each calibration stage under its frozen prefix, with preregistered reached quotas. Continue sampling based only on reach counts, never target labels, scores or q; retain the full set if the preregistered cap is insufficient. Recalibrate after model/prefix changes and use a fresh final holdout. Coverage does not imply execution rate, closed-loop cost improvement or physical safety; this report selects no parameters from the old test.

`python scripts/30_rollout_diagnosis.py`

`python scripts/30_rollout_diagnosis.py --check`

## 简体中文

本报告对已发布原始轨迹做事后复算。没有新仿真、重新训练、调参或更换测试集；旧结果和原验收结论保持不变。所有数值来自公开原始轨迹及v1风险模型，不依赖未跟踪的训练NPZ。

所有有害标签均为严格J_after > J_before，零容差；非劣为J_after ≤ J_before。轨迹有害事件表示至少一次实际执行的联合动作使代价上升，不是失稳或最终返回参数恶化。

| 阶段 | 到达 n | 秩 | q | 实际非劣 / 有害 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 512 | 511 | 0.994453120322 | 482 / 30 |
| 2 | 245 | 245 | 0.999988548670 | 227 / 18 |
| 3 | 56 | 57 | 1.000000000000 | 55 / 1 |
| 4 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 5 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 6 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 7 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 8 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 9 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 10 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 11 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 12 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 13 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 14 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 15 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 16 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 17 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 18 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 19 | 0 | 1 | 1.000000000000 | 0 / 0 |
| 20 | 0 | 1 | 1.000000000000 | 0 / 0 |

第2步已有245个样本，极端q并非样本不足回退。决定最大分数的是实际非劣样本plant_index=358：J 5.437280028→5.081413604，p(harmful)=0.999988548670。共同LAC阈值为包含这个真实标签而增大，也让其他样本更容易同时包含两标签；当q>0.5且只允许{非劣}，需p(harmful)<1-q，约1.14513304886e-05。

| 阶段 | 有害样本p(harmful)中位数 / 最小值 | 非劣样本p(harmful)中位数 |
| ---: | ---: | ---: |
| 1 | 0.258446 / 0.003066 | 0.005185 |
| 2 | 0.024856 / 0.000279 | 0.000328 |
| 3 | 0.446130 / 0.446130 | 0.672458 |

这些数值来自实际门控前缀下的校准对象，不是monitor后期状态；分数尾部同时存在有害动作低估和非劣动作高估。校准集接纳计数仅为回看，不是独立验证。

| 拒绝阶段 | 拒绝数 | 其中非劣 / 有害 | 全体均值差贡献 | 总差份额 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 506 | 460 / 46 | 0.619815 | 61.6080% |
| 2 | 416 | 382 / 34 | 0.358117 | 35.5959% |
| 3 | 102 | 102 / 0 | 0.028130 | 2.7961% |

前两步占大部分最终代价差；这只是按实际拒绝阶段对配对差值分组，不是反事实因果比例。第三步102个拒绝动作在诊断测量中均非劣，也不能据此修改已冻结的q。

模型恰为零的系数数: 7.
`log_Kp/Kp_zn, log_Kd/Kd_zn, prev_dlog_Kp, prev_dlog_Ki, prev_dlog_Kd, iter_frac, log_Ku/Kp`

这些输入对当前线性风险头没有贡献。公开scaler的mean/scale可核对，但scale=1本身不能证明训练方差为零；本报告不推断未读取的训练范围。初态训练协议仅覆盖每株一个解析ZN状态。

prev_dJ：拟合均值=-0.517598；scale=0.270362；系数=1.445288。
其公式是clip((previous_J-current_J)/5,-3,3)。初态previous_J=0，因此编码为-current_J/5；后续则编码真实上一轮改善。原始轨迹已逐项核验公式。

| 校准阶段 | prev_dJ中位数 | 标准化中位数 | 温度缩放后有害logit贡献中位数 |
| ---: | ---: | ---: | ---: |
| 1 | -0.505081 | 0.046299 | 0.068123 |
| 2 | 0.069871 | 2.172896 | 3.197164 |
| 3 | 0.018140 | 1.981557 | 2.915632 |

这些是特征与模型运算的迁移证据，不证明某一个特征独立造成最终性能差。

每步alpha=0.005时，避免秩超过n至少需199个独立reached样本；n=199–398仍取最大分数。样本足够不代表q小或有效接纳。第3步旧到达率为0.109375：补足最低数量需再收143个reached，按旧前缀预计1307.4个新增初始植物；重新收满512个reached预计4681.1个初始植物。它们不是保证预算，也不是实际仿真次数。

固定路径验收冲突：已验证全部1024株gated操作历史是monitor前缀，返回代价为各自实测历史最小值。因此每株best_gated≥best_monitor，数学上的均值零松弛要求逐株相等。其中700株的monitor最优严格低于首次有害动作之前的所有代价；保持这些最优至少要让68.359375%对象执行有害步，不能满足10%轨迹风险上界。

即使宽松允许102株发生有害事件，均值损失仍至少6.26694770202e-06；两次binary64均值计算的保守舍入误差界为6.11037859039e-12，余量6.26694159164e-06>0。这排除了均值舍入掩盖冲突；未把数值舍入界当物理仿真误差界。

该结论仅针对这批确定性轨迹、相同起点/时域、整动作执行或拒绝即停，不是总体定理或对其他动作路径的不可能性证明。只重训风险头及补样无法让这些固定路径同时通过原两项验收。改变动作路径是突破此限制的必要条件而非充分条件，改变后必须对实际执行联合动作重新校准和独立评估。

后续研究应先在开发数据上训练多轮状态与实际联合动作风险，再冻结模型、温度、提案和预算。逐步使用独立新植物，按冻结前缀收满预注册reached配额；续采只看到达计数，不看目标标签、分数或q。达到预注册上限仍不足就保留完整集合。模型或前缀更新后重新校准，最终评估使用新保留集。覆盖不等于接纳率、闭环代价改善或物理安全；本页结果不用于从旧测试集选参。

`python scripts/30_rollout_diagnosis.py`

`python scripts/30_rollout_diagnosis.py --check`
