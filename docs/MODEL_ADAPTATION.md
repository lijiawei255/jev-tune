# Model adaptation audit / 模型适配审查

[English](#english) · [简体中文](#简体中文)

## English

The joint-risk research branch is paused with its evidence intact. This audit fixes errors in the existing Simulink adapter and automation surface. It does not retrain the shipped policy or claim a new safety guarantee.

| Priority | Defect | Implemented contract |
| :--- | :--- | :--- |
| P1 | Ideal PID conversion changed the original controller before measuring its cost | Preserve the Simulink Ideal transfer function when converting to Parallel; verify pre/post conversion responses |
| P1 | A multi-element Scope Dataset silently selected its first signal | Reject ambiguous measurement data instead of evaluating a reference channel as the plant output |
| P1 | Variable-step sampling density changed the reported integral cost | Integrate against actual time and reject invalid time/signal data |
| P1 | An input file could coincide with the scratch model destination | Reject source/destination collisions before modifying files |
| P1 | Multi-loop CLI discarded explicit options; write-back failure could report success | Forward supported configuration, reject unsupported requests, and return failure when the requested output was not written |
| P1 | Partial worker responses could be deleted before successful parsing | Retry incomplete responses and publish queue files atomically |
| P2 | Discovery simulations and padded histories obscured actual cost | Include discovery in total attempts and report actual simulations separately from requested tuning budget |

Simulink Ideal uses `P * (1 + I/s + D*N*s/(s+N))`, so the corresponding Parallel gains are `[P, P*I, P*D]`. These are Simulink mask parameters, not `pidstd` time constants. [MathWorks controller definitions](https://www.mathworks.com/help/simulink/slref/pidcontroller.html).

Ideal conversion is restricted to internal coefficients and internal zero initial conditions, without reset, tracking, anti-windup or output/integrator limits; other configurations return `unsupported_pid_configuration`. For a multi-element Dataset, supply `measure_element` (and, when needed, `input_element`) as an index or unique signal name in `--config`; ambiguous selection defaults to `wide_signal`. A multi-loop request succeeds only when every loop succeeds. Partial results use `ok=false`, `partial_success=true`, `code=partial_failure` and may retain an output copy.

MATLAB integration metrics now use the recorded time grid. Historical MATLAB cost pages, traces and animations predate this correction and retain their historical numbers; they are not current reruns and must not be compared numerically with the corrected objective. Python fixed-grid benchmark metrics and the frozen CP studies are unchanged. This metric change also means old calibration data do not establish label coverage for arbitrary Simulink trajectories.

`iters` is the tuning-loop allowance, not a hard end-to-end simulation cap. Discovery, reference probing, ultimate-gain sweep, original-gain measurement and final verification can add work. `n_total_simulations` reports actual attempted simulations, including failed attempts; ledger components explain the overhead. A reused final observation is not charged as a fresh simulation. An early stop is not evidence of a better controller. Positive scalar step-response tasks are the supported objective; ambiguous channels and unsupported objectives require an explicit adapter rather than a guessed interpretation.

The generated fixtures exercise API behavior on the recorded MATLAB installation. They do not replace acceptance on a user's external plant. Before deployment, validate the selected feedback/output/reference, preserve the original model, compare its own gains using the same objective, and inspect both returned cost and trial failures. Returning the measured best does not bound intermediate trials or prove stability.

Reproduce the real regression with `PYTHONPATH=src python scripts/40_verify_model_adaptation.py`; verify saved evidence without MATLAB with `python scripts/40_verify_model_adaptation.py --check`. The JSON includes the original MATLAB log and source hashes. The following block is generated from `research/results/model_adaptation.json`:

```json
{
  "ok": true,
  "matlab_release": "2024b",
  "integration": {
    "uniform_iae_itae": [
      10,
      50
    ],
    "nonuniform_iae_itae": [
      10,
      50
    ],
    "max_difference": 0
  },
  "invalid_reference": "jev:ref",
  "invalid_time": "jev:invalid_signal",
  "dataset_rejection": "jev:wide_signal",
  "dataset_selected_response": [
    0,
    0,
    0
  ],
  "ideal": {
    "parameters": [
      2,
      4,
      0.5
    ],
    "parallel_gains": [
      2,
      8,
      1
    ],
    "max_trajectory_difference": 0,
    "samples": 3001,
    "simulations": 2
  },
  "ideal_nonzero_ic_rejection": "jev:unsupported_pid_configuration",
  "ideal_tracking_rejection": "jev:unsupported_pid_configuration",
  "path_rejections": {
    "tune": "jev:source_overwrite",
    "discover": "jev:source_overwrite",
    "doctor": "jev:source_overwrite",
    "writeback": "jev:source_overwrite"
  },
  "original_files_preserved": true,
  "auto_ledger": {
    "callback_count": 22,
    "reported_total": 22,
    "measurements": {
      "discovery_junction": 1,
      "discovery_controller_baseline": 1,
      "discovery_controller_perturbation": 3,
      "reference_probe": 0,
      "sweep": 14,
      "own_gain_probe": 1,
      "tuning": 1,
      "final_verification": 1
    },
    "discovery_total": 5,
    "recorded_measurements": 2
  },
  "ambiguous_scope": {
    "code": "wide_signal",
    "callback_count": 1,
    "reported_total": 1
  },
  "explicit_scope": {
    "final_J": 0.9195106157449489,
    "callback_count": 17,
    "reported_total": 17
  },
  "repeat_job": {
    "sweep_simulations": 14,
    "callback_count": 17,
    "reported_total": 17
  },
  "all_loops_ledger": {
    "callback_count": 52,
    "reported_total": 52,
    "measurements": {
      "initial_discovery": 6,
      "loop_discovery": 12,
      "tuning_jobs": 34
    },
    "n_tuned": 2,
    "n_loops": 2
  },
  "chain_path_rejections": {
    "iteration": {
      "code": "source_overwrite",
      "original_bytes_preserved": true,
      "callback_count": 6,
      "reported_total": 6
    },
    "discovery": {
      "code": "source_overwrite",
      "original_bytes_preserved": true,
      "callback_count": 6,
      "reported_total": 6
    },
    "tuning": {
      "code": "source_overwrite",
      "original_bytes_preserved": true,
      "callback_count": 6,
      "reported_total": 6
    }
  },
  "atomic_response_complete": true
}
```

For the separate fixed-budget study, `python scripts/43_verify_practical_budget.py` also checks the complete protocol cohort roster. It permits only original-hash-matching LF/CRLF differences in source/protocol/calibration text, records those paths, and keeps model weights and compressed raw evidence byte-exact. It does not regenerate trajectories or establish cross-platform bitwise simulation replay.

Historical research verification uses `python scripts/44_verify_historical_research.py --check`. The current baseline and adapter fixes differ from the original research source manifest. The verifier creates a physical temporary copy, restores only the explicitly archived historical files after checking their original hashes, and runs the unchanged study verifiers in an isolated subprocess. Current runtime code, old results and original acceptance remain unchanged; verification does not count as a new experiment or establish the missing coverage premises. Direct original commands require the historical v0.8.0 checkout.

## 简体中文

联合风险研究暂停，已有证据完整保留。本次修复既有Simulink适配器及自动化入口，不重训出厂策略，也不新增安全保证。

| 优先级 | 问题 | 修复后的约定 |
| :--- | :--- | :--- |
| P1 | Ideal PID转换在测量原始代价前改变控制器 | 按Simulink定义等价转换为Parallel，并对比转换前后响应 |
| P1 | 多元素Scope Dataset静默取第一个信号 | 拒绝含糊测量，避免把参考通道当作对象输出 |
| P1 | 可变步长的采样密度影响积分代价 | 根据实际时间积分，拒绝无效时间及信号数据 |
| P1 | 输入原件可能与工作副本目标重合 | 修改文件前拒绝源与目标路径冲突 |
| P1 | 多回路命令忽略显式选项，写回失败仍报成功 | 转发支持的配置，拒绝不支持请求，输出未写成时返回失败 |
| P1 | worker可能删除尚未解析成功的半写入结果 | 等待完整响应，队列文件采用原子发布 |
| P2 | 发现开销和补齐历史掩盖实耗 | 总仿真包含发现阶段，实际次数与请求预算分别报告 |

Simulink Ideal的表达式为`P * (1 + I/s + D*N*s/(s+N))`，对应Parallel增益为`[P, P*I, P*D]`。这里是Simulink掩码参数，不是`pidstd`时间常数。参见[MathWorks控制器定义](https://www.mathworks.com/help/simulink/slref/pidcontroller.html)。

Ideal转换仅限内部系数、内部零初态，且无reset、tracking、anti-windup及输出/积分器限制；其他配置返回`unsupported_pid_configuration`。多元素Dataset可在`--config`内用索引或唯一信号名指定`measure_element`，必要时也指定`input_element`；缺省选择不明确时返回`wide_signal`。多回路请求只有全部成功才成功，部分结果返回`ok=false`、`partial_success=true`和`code=partial_failure`，可能仍保留输出副本。

MATLAB积分指标现按记录的时间网格计算。历史MATLAB结果页、轨迹及动画保留修正前的原数字，不代表当前重跑，不可与修正后的目标直接比较。Python固定网格基准指标与冻结CP研究保持不变；指标变化也意味着旧校准数据不能为任意Simulink轨迹提供标签覆盖证据。

`iters`限制调参循环，不是端到端仿真硬上限。发现、参考探测、临界增益扫描、原增益测量和最终验证会增加开销。`n_total_simulations`记录实际尝试次数，包含失败尝试，分项账本解释额外开销；复用最终观测不算新仿真。提前停止本身不代表控制器更好。支持的目标为正向标量阶跃响应，含糊通道和其他目标需要明确适配，不能猜测含义。

生成模型只验证记录的MATLAB环境中的接口行为，不替代用户实际对象的验收。部署前仍需确认反馈、输出与参考，保留原件，在相同目标下测量原增益，并同时检查返回代价和搜索过程中的失败。返回实测最优不能约束中间试验或证明稳定性。

真实回归入口为`PYTHONPATH=src python scripts/40_verify_model_adaptation.py`；无MATLAB时可用`python scripts/40_verify_model_adaptation.py --check`验证保存的证据。JSON包含原始MATLAB日志及源码哈希。下列记录由`research/results/model_adaptation.json`生成：

```json
{
  "ok": true,
  "matlab_release": "2024b",
  "integration": {
    "uniform_iae_itae": [
      10,
      50
    ],
    "nonuniform_iae_itae": [
      10,
      50
    ],
    "max_difference": 0
  },
  "invalid_reference": "jev:ref",
  "invalid_time": "jev:invalid_signal",
  "dataset_rejection": "jev:wide_signal",
  "dataset_selected_response": [
    0,
    0,
    0
  ],
  "ideal": {
    "parameters": [
      2,
      4,
      0.5
    ],
    "parallel_gains": [
      2,
      8,
      1
    ],
    "max_trajectory_difference": 0,
    "samples": 3001,
    "simulations": 2
  },
  "ideal_nonzero_ic_rejection": "jev:unsupported_pid_configuration",
  "ideal_tracking_rejection": "jev:unsupported_pid_configuration",
  "path_rejections": {
    "tune": "jev:source_overwrite",
    "discover": "jev:source_overwrite",
    "doctor": "jev:source_overwrite",
    "writeback": "jev:source_overwrite"
  },
  "original_files_preserved": true,
  "auto_ledger": {
    "callback_count": 22,
    "reported_total": 22,
    "measurements": {
      "discovery_junction": 1,
      "discovery_controller_baseline": 1,
      "discovery_controller_perturbation": 3,
      "reference_probe": 0,
      "sweep": 14,
      "own_gain_probe": 1,
      "tuning": 1,
      "final_verification": 1
    },
    "discovery_total": 5,
    "recorded_measurements": 2
  },
  "ambiguous_scope": {
    "code": "wide_signal",
    "callback_count": 1,
    "reported_total": 1
  },
  "explicit_scope": {
    "final_J": 0.9195106157449489,
    "callback_count": 17,
    "reported_total": 17
  },
  "repeat_job": {
    "sweep_simulations": 14,
    "callback_count": 17,
    "reported_total": 17
  },
  "all_loops_ledger": {
    "callback_count": 52,
    "reported_total": 52,
    "measurements": {
      "initial_discovery": 6,
      "loop_discovery": 12,
      "tuning_jobs": 34
    },
    "n_tuned": 2,
    "n_loops": 2
  },
  "chain_path_rejections": {
    "iteration": {
      "code": "source_overwrite",
      "original_bytes_preserved": true,
      "callback_count": 6,
      "reported_total": 6
    },
    "discovery": {
      "code": "source_overwrite",
      "original_bytes_preserved": true,
      "callback_count": 6,
      "reported_total": 6
    },
    "tuning": {
      "code": "source_overwrite",
      "original_bytes_preserved": true,
      "callback_count": 6,
      "reported_total": 6
    }
  },
  "atomic_response_complete": true
}
```

独立固定预算研究可用`python scripts/43_verify_practical_budget.py`额外核对协议完整分组。它仅接受源码、协议及校准文本中可匹配原哈希的LF/CRLF差异，列出对应路径；模型权重和压缩原始证据仍逐字节核验。不重生成轨迹，也不建立跨平台仿真逐位重放保证。

历史研究核验入口为`python scripts/44_verify_historical_research.py --check`。当前基线及适配器修复已不同于原研究源码清单；核验器建立物理临时副本，只有明确归档的历史文件在匹配原哈希后才被恢复，并在隔离子进程中运行原研究检查器。当前运行时代码、旧结果和原验收规则不变；核验不计为新实验，也不补足尚未建立的覆盖前提。直接使用原命令需检出历史v0.8.0版本。
