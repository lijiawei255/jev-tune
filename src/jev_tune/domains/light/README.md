# Lightweight shell instances / 轻量壳实例

[English](#english) · [简体中文](#简体中文)

## English

Two pure-Python instances (numpy only) that reuse `jev_tune.core` unchanged:

| file | action type | shell layers exercised |
| :--- | :--- | :--- |
| `linear_shell.py` | ordered numeric (additive offsets) | expectation decode, variance shrink, p_max Hold, step cap |
| `vla_mask.py` | categorical tokens (VLA-style) | temperature fit, split-CP set, hard domain mask, Hold on empty/ambiguous/forbidden |

```bash
python -m jev_tune.domains.light.linear_shell   # {"state": [0.6, 0.35], ...}
python -m jev_tune.domains.light.vla_mask       # coverage, hold rate, forbidden-action rate
```

Both use supplied or synthetic distributions, not a trained controller or robot.
The caller owns observation quality, units, labels, actuator bounds and faults.
The frozen non-PID denoising study lives in the `v0.10.2-archive` tag
(`python scripts/archive.py`).

## 简体中文

两个只依赖numpy的纯Python实例，原样复用`jev_tune.core`：`linear_shell.py`演示有序数值动作
（期望解码、方差收缩、p_max弃权、步长上限）；`vla_mask.py`演示类别动作（温度拟合、
分裂共形集合、硬性领域掩码，集合为空/歧义/首选被禁止时Hold）。均使用给定或合成分布，
不代表已训练控制器或机器人。冻结的非PID去噪研究保存在`v0.10.2-archive`标签
（`python scripts/archive.py`）。
