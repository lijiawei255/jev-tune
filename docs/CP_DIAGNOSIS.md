# CP mechanism diagnosis / CP机制诊断

[English](#english) · [简体中文](#简体中文)

## English

Frozen model, temperature, alpha and q_hat. Replay seed17 on 120 plants at maximum budget20. Historical hard_hold repeats are a diagnostic control; default monitor preserves full sets without vetoing axes. Stopping counts actual measurements, not padded history.

| policy | median J | actual simulations |
| :--- | ---: | ---: |
| Temp Only | 0.440964 | 2400 |
| hard_hold repeat (historical) | 0.727577 | 2400 |
| monitor | 0.440964 | 2400 |
| hard_hold_stop | 0.751176 | 1088 |

Historical hard_hold: 1193 full holds; 85 plants with at least5 final holds; median unique gains 7.
Frozen initial-state counterfactual: vetoed axes 451; improve >2% 138; harm >2% 47.

One-step simulated counterfactuals do not prove long-run safety. Teacher labels describe discrete single-axis argmins; actual proposals are continuous joint actions. Set coverage does not imply joint action improvement or safety. Initial-state calibration does not cover adaptive trajectories or shifted domains.

Reproduce / 复现: `python scripts/26_cp_diagnosis.py`; data / 数据: `research/results/cp_diagnosis.json`.

## 简体中文

冻结原模型、温度、alpha和q_hat；重放同一seed17的120株、最大预算20。旧hard_hold重复观测是诊断对照；默认monitor保留完整集合但不否决轴。停止模式只计实际测量，不把填充历史当新观测。

| policy | median J | actual simulations |
| :--- | ---: | ---: |
| Temp Only | 0.440964 | 2400 |
| hard_hold repeat (historical) | 0.727577 | 2400 |
| monitor | 0.440964 | 2400 |
| hard_hold_stop | 0.751176 | 1088 |

旧hard_hold: 全保持1193次；末段至少连续5次保持85株；不同参数组中位数7。
冻结初态反事实：被禁轴451个；改善超过2%有138个；恶化超过2%有47个。

专项反事实仅评价一次仿真提案，不证明长期安全。专家标签是单轴离散精确最优项，实际动作是三轴连续组合；集合覆盖不能自动转成联合动作改善或安全。初态校准不覆盖自适应轨迹及域外对象。

Reproduce / 复现: `python scripts/26_cp_diagnosis.py`; data / 数据: `research/results/cp_diagnosis.json`.
