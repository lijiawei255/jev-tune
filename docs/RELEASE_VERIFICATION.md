# Release verification / 发布验证

[English](#english) · [简体中文](#简体中文)

## English

278 passed; 0 skipped; coverage 77.8%; 140 automatic document checks.

Counts come from actual JUnit, pytest logs and claims recomputation. Software verification and research enablement are separate conclusions.

New study acceptance: **FAIL**; `research_only`.
Failed criteria: empirical_mean_cost_noninferior, empirical_p90_cost_noninferior.

Additional implementation validity audit: coverage premises are not established and deployment is prohibited. Batch/row-dependent floating-point inference leaves score exchangeability and trajectory-event independence unestablished; nominal CP/binomial quantities are not an exact probability guarantee for this implementation. This post-hoc audit does not revise frozen numerical acceptance.

Actual prospective study simulations: 513508.

Additional full evaluation replay simulations: 33718; additional numerical diagnosis simulations: 1; total: 547227.

This release runs trajectory training, independent temperature fitting, reached-sample stage calibration and five real closed-loop arms on a new fixed test cohort. Old data is diagnostic and old failure JSON/traces are preserved. Additional full evaluation replay is charged separately in the reproduction JSON below, adds no independent statistical evidence and does not replace acceptance.

Full pytest covers CP boundaries, action selection, cache/diagnostic isolation, evidence mutations and existing runtimes; real MATLAB controller regressions were rerun. Generic Python/C99/MATLAB policies do not automatically enable the research head. Earlier benchmark, ablation and generalization records are historical in release_verification_v070.json, not represented as newly rerun here.

Theoretical coverage requires the frozen noiseless six-family scope and assumptions including exchangeability; this implementation has not established those premises. Accepted-action conditional risk, domain shift, recovery and physical safety are also unproven. Data and SHA256 are attached to v0.8.0; NPZ caches regenerate from committed raw shards and claims do not depend on uncommitted local data.

[TRAJECTORY_RISK](TRAJECTORY_RISK.md) · [ROLLOUT_DIAGNOSIS](ROLLOUT_DIAGNOSIS.md) · [preserved v1](JOINT_RISK_ROLLOUT.md)

[release_verification.json](../research/results/release_verification.json) · [trajectory_risk_reproduction.json](../research/results/trajectory_risk_reproduction.json)
[trajectory_risk_validity.json](../research/results/trajectory_risk_validity.json) · [batch_inference_diagnosis.json](../research/results/batch_inference_diagnosis.json)

## 简体中文

278 passed; 0 skipped; coverage 77.8%; 140 automatic document checks.

数字来自本次实际JUnit、pytest日志和claims复算。软件检查与研究启用验收是不同结论。

新研究验收: **FAIL**; `research_only`.
未通过项: empirical_mean_cost_noninferior, empirical_p90_cost_noninferior.

额外实施有效性审计：覆盖前提尚未建立，禁止部署。批大小/行位置会改变浮点推理，校准与测试分数的交换性及轨迹事件独立性未闭合；名义CP/二项统计量不能作为机器实现的精确概率保证。该事后审计没有修改冻结数值验收。

前瞻研究实际仿真: 513508.

完整评估重放额外仿真: 33718; 数值诊断额外仿真: 1; 合计: 547227.

本次完成多轮训练、独立温度拟合、到达样本逐步校准及全新固定测试集五组真实闭环。旧数据仅诊断，旧失败JSON/原始轨迹保持不变。额外完整评估重放在下列reproduction JSON中单独计账，不是新增独立统计证据，不覆盖原验收。

完整pytest覆盖CP边界、动作选择、缓存/诊断隔离、证据变异及既有运行时；MATLAB真实控制器回归重新运行。通用Python/C99/MATLAB策略不自动启用研究头。历史基准、消融和泛化记录见release_verification_v070.json，不冒充本次重跑。

理论覆盖需要冻结的无噪声六族协议及交换性等条件，本次尚未证明实现满足这些条件，也不证明获准动作条件风险、域外、恢复或物理安全。数据及SHA256见v0.8.0附件；NPZ可从提交的原始分片再生，claims不依赖本地未提交数据。

[TRAJECTORY_RISK](TRAJECTORY_RISK.md) · [ROLLOUT_DIAGNOSIS](ROLLOUT_DIAGNOSIS.md) · [preserved v1](JOINT_RISK_ROLLOUT.md)

[release_verification.json](../research/results/release_verification.json) · [trajectory_risk_reproduction.json](../research/results/trajectory_risk_reproduction.json)
[trajectory_risk_validity.json](../research/results/trajectory_risk_validity.json) · [batch_inference_diagnosis.json](../research/results/batch_inference_diagnosis.json)
