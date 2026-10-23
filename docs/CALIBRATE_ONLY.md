# Frozen-weight temperature and threshold adaptation

> [English](#english) · [简体中文](#简体中文)

## English

CP is disabled during collection and in all four arms; this diagnostic does not represent the shipped Temperature+CP policy. Deploying CP after a temperature change requires refitting qhat on independent calibration data; this experiment does not reuse old qhat or claim CP coverage.

All weights are frozen. 48 measured transitions from 8 simulated plants cost 56 simulations including initial responses; collection 0.973s, scalar fitting 8.111ms.
Calibration seed 101 and independent validation seed 202; each arm receives 20 experiments on 40 held-out plants.

| arm | T scale | tau | median J | p90 | coverage | harmful | ECE |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| base | 1.000 | 0.3500 | 2.2620 | 3.0795 | 0.9066 | 0.0610 | 0.2802 |
| temperature_only | 0.600 | 0.3500 | 2.2460 | 3.0792 | 0.9987 | 0.0725 | 0.2994 |
| threshold_only | 1.000 | 0.7322 | 2.2856 | 4.2648 | 0.6303 | 0.0063 | 0.3936 |
| combined | 0.600 | 0.9079 | 2.2856 | 4.1945 | 0.5408 | 0.0146 | 0.4554 |

Collection reuses production state history, accepted actions and the deterministic gate, with each response measured once. Threshold selection calls the runtime per-axis mask and uses the same joint coverage definition (at least one permitted axis). Temperature changes expectation decoding and variance shrinkage: frozen weights do not mean a frozen policy. NLL on source-policy outcomes is a surrogate and does not establish calibrated success for changed actions. Independent four-arm rollouts measure outcomes, not safety. ECE descriptively compares mean axis pmax with joint improvement. This single-scenario small-sample experiment does not prove real-device transfer, few-shot learning from scratch or universal gains; negative results are retained.

## 简体中文

本实验在采集及四个验证臂均关闭CP，不代表当前出厂的Temperature+CP策略。温度改变后若需部署CP，必须使用独立校准数据重新拟合qhat；这里不复用旧qhat，也不声称具有CP覆盖保证。

冻结所有权重；用8株模拟对象采集48个真实转移，实际56次仿真（包含初始测量）。采样0.973秒，标量拟合8.111毫秒。
校准seed101、独立验证seed202；在40株验证对象上，各臂预算20次。

| arm | T scale | tau | median J | p90 | coverage | harmful | ECE |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| base | 1.000 | 0.3500 | 2.2620 | 3.0795 | 0.9066 | 0.0610 | 0.2802 |
| temperature_only | 0.600 | 0.3500 | 2.2460 | 3.0792 | 0.9987 | 0.0725 | 0.2994 |
| threshold_only | 1.000 | 0.7322 | 2.2856 | 4.2648 | 0.6303 | 0.0063 | 0.3936 |
| combined | 0.600 | 0.9079 | 2.2856 | 4.1945 | 0.5408 | 0.0146 | 0.4554 |

采样复用生产运行器的历史特征、动作接受与安全门；每个响应只测一次。阈值选择直接调用运行时逐轴mask，coverage与验证同样按至少一轴获准计。温度会改变期望解码和方差缩步，因此权重冻结不等于策略冻结。拟合的NLL使用原策略动作结果作为代理目标，不能保证新动作的成功概率已校准；四臂独立验证用于测量结果而非保证安全。ECE以三轴平均pmax与整步改善作描述性比较。该单场景小样本实验不证明真机迁移、从零少样本学习或普遍改进，负结果必须保留。
