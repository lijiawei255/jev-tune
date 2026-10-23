# Frozen-weight temperature and threshold adaptation

> [English](#english) · [简体中文](#简体中文)

## English

CP is disabled during collection and in all four arms; this diagnostic does not represent the shipped Temperature+CP policy. Deploying CP after a temperature change requires refitting qhat on independent calibration data; this experiment does not reuse old qhat or claim CP coverage.

All weights are frozen. 48 measured transitions from 8 simulated plants cost 56 simulations including initial responses; collection 0.858s, scalar fitting 7.260ms.
Calibration seed 101 and independent validation seed 202; each arm receives 20 experiments on 40 held-out plants.

Canonical harm uses strict after > before with zero tolerance. The legacy after > 1.02 × before rate remains for comparison with v0.6. Both condition on measured policy decisions with at least one permitted axis, excluding rollbacks and terminal proposals; they are not unconditional joint-risk guarantees.

| arm | T scale | tau | median J | p90 | coverage | harm >0 | legacy harm >2% | ECE |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| base | 1.000 | 0.3500 | 2.2620 | 3.0795 | 1.0000 | 0.4843 | 0.0493 | 0.2874 |
| temperature_only | 0.600 | 0.3500 | 2.2465 | 3.0792 | 1.0000 | 0.5290 | 0.0742 | 0.3049 |
| threshold_only | 1.000 | 0.7322 | 2.2856 | 4.3151 | 1.0000 | 0.5819 | 0.0088 | 0.3406 |
| combined | 0.600 | 0.9079 | 2.2856 | 4.2001 | 1.0000 | 0.5635 | 0.0186 | 0.4599 |

Collection reuses production state history, accepted actions and the deterministic gate, with each response measured once. Threshold selection calls the runtime per-axis mask and uses the same joint coverage definition (at least one permitted axis). Temperature changes expectation decoding and variance shrinkage: frozen weights do not mean a frozen policy. NLL on source-policy outcomes is a surrogate and does not establish calibrated success for changed actions. Independent four-arm rollouts measure outcomes, not safety. ECE descriptively compares mean axis pmax with joint improvement. This single-scenario small-sample experiment does not prove real-device transfer, few-shot learning from scratch or universal gains; negative results are retained.

## 简体中文

本实验在采集及四个验证臂均关闭CP，不代表当前出厂的Temperature+CP策略。温度改变后若需部署CP，必须使用独立校准数据重新拟合qhat；这里不复用旧qhat，也不声称具有CP覆盖保证。

冻结所有权重；用8株模拟对象采集48个真实转移，实际56次仿真（包含初始测量）。采样0.858秒，标量拟合7.260毫秒。
校准seed101、独立验证seed202；在40株验证对象上，各臂预算20次。

主有害口径为严格after > before，零容差；另列旧口径after > 1.02 × before，供v0.6比较。两者均以至少一轴获准且实际测量的策略决策为分母，排除回滚和终止提案，不是无条件联合风险保证。

| arm | T scale | tau | median J | p90 | coverage | harm >0 | legacy harm >2% | ECE |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| base | 1.000 | 0.3500 | 2.2620 | 3.0795 | 1.0000 | 0.4843 | 0.0493 | 0.2874 |
| temperature_only | 0.600 | 0.3500 | 2.2465 | 3.0792 | 1.0000 | 0.5290 | 0.0742 | 0.3049 |
| threshold_only | 1.000 | 0.7322 | 2.2856 | 4.3151 | 1.0000 | 0.5819 | 0.0088 | 0.3406 |
| combined | 0.600 | 0.9079 | 2.2856 | 4.2001 | 1.0000 | 0.5635 | 0.0186 | 0.4599 |

采样复用生产运行器的历史特征、动作接受与安全门；每个响应只测一次。阈值选择直接调用运行时逐轴mask，coverage与验证同样按至少一轴获准计。温度会改变期望解码和方差缩步，因此权重冻结不等于策略冻结。拟合的NLL使用原策略动作结果作为代理目标，不能保证新动作的成功概率已校准；四臂独立验证用于测量结果而非保证安全。ECE以三轴平均pmax与整步改善作描述性比较。该单场景小样本实验不证明真机迁移、从零少样本学习或普遍改进，负结果必须保留。
