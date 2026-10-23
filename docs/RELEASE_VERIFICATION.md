# Release verification / 发布验证

[English](#english) · [简体中文](#简体中文)

## English

This page is generated from actual pytest JUnit output and the claims checker,
not from the intended number of tests. The baseline audit is a private local
record; this public record summarizes the repaired release.

187 passed; 0 skipped; 0 failures; coverage 75.03%; 88 automatic document checks.

Regression coverage includes CP monitor/hard_hold separation, terminal-proposal
telemetry, no-action stopping, joint-risk acceptance, unique transition accounting, partial holds,
independent rollbacks, measured best gain/cost pairs, real early-stop calls,
noise-invariant subsets, numeric faults, split-CP ranks/ties, independent
calibration, CP policy boundaries, NaN/Inf C mutants, MATLAB decoder and real
first-rollback/JSON-history paths. Benchmark, ablation, random-hold, calibration,
robustness, generalization, specialization and disturbance results were rerun.

The historical hard_hold policy does not improve current matched control costs.
The default monitor retains full sets and preserves the Temp Only proposal.
The joint-action risk experiment is independently calibrated and remains research-only;
see [JOINT_RISK](JOINT_RISK.md) and [CP_DIAGNOSIS](CP_DIAGNOSIS.md). The independent empirical
label coverage and its finite-sample scope are in [CONFORMAL](CONFORMAL.md).
Training-seed replication, robot/clinical/board testing and WCET remain outside
the demonstrated scope; they are not silently counted as passing experiments.
Historical study pages and paid hosted-model measurements remain versioned records.

Synthetic data assets are attached to v0.6.0. From a clone, download
`expert_train.npz` into `data/` and `temperature_fit.npz`, `cp_fit.npz`,
`empirical_eval.npz` into `data/calibration/`. Their hashes are in the calibration
and A0 cache manifests. The CP-fit data was not used to select T or weights.

See [release_verification.json](../research/results/release_verification.json)
for actual experiment subprocess outcomes/provenance. `23_sync_reference_docs.py` renders the current
numerical docs, and `16_check_claims.py` verifies registered text, both README
benchmark tables, and complete generated bilingual experiment/CP documents.
It does not reinterpret historical numbers as new experiments.

## 简体中文

本页由pytest实际JUnit输出与claims检查生成，不按计划测试数填表。原审计保留本地；
本公开记录概述修复版本。

187 passed; 0 skipped; 0 failures; coverage 75.03%; 88 automatic document checks.

回归覆盖CP监测/硬保持分离、终止提案遥测、无动作停止、联合风险整步获准、唯一转移记账、部分保持、独立回滚、实测最优增益/代价、早停真实次数、
噪声子集一致性、数值故障、CP分位次序/边界、独立校准、集合弃权、C NaN/Inf变体、
MATLAB解码及真实首回滚/JSON历史。基准、消融、匹配随机保持、校准、鲁棒性、泛化、
专门化与扰动研究均已重跑。旧hard_hold当前同条件代价没有改善；默认monitor保留完整集合和Temp Only提案。
联合动作风险独立校准并保持研究用途，见[JOINT_RISK](JOINT_RISK.md)及[CP_DIAGNOSIS](CP_DIAGNOSIS.md)。
独立经验标签覆盖及理论边界见
[CONFORMAL](CONFORMAL.md)。训练种子重复、机器人/临床/板测和WCET仍未验证，未计入通过。
历史研究页及付费托管模型测量保留版本语境，不冒充本次重测。

v0.6.0附件包含合成数据：将expert_train.npz放入data/，三个校准NPZ放入data/calibration/。
数据hash见校准与A0缓存manifest；CP拟合数据未参与T或权重选择。实际命令及来源见
[release_verification.json](../research/results/release_verification.json)。23脚本生成当前数字文档，
16检查注册正文、两种README基准表和完整双语实验/CP文档，不将历史数字重新解释为当前实验。
