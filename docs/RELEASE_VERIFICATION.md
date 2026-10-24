# Release verification / 发布验证

[English](#english) · [简体中文](#简体中文)

## English

644 passed; 0 skipped; coverage 83.45%; 158 claims checks.

v0.10.0 provides a checked C decision chain and reusable frozen calibration shell, with a trained non-PID denoising transfer experiment. The primary acquisition used 76683 objective evaluations; acceptance is `negative_stop`. All three trained seeds failed to establish the preregistered stable benefit over the baselines. Fresh original-record evidence checks passed under the documented arithmetic assumptions. This does not establish policy superiority, recover bitwise replay, prove the causal history of training, or make current-CPU actions equivalent to the original trajectories. The raw report's verification_status remains a producer statement.

Original strict 46/48 replay passed on the original machine but failed on the hosted CPU; both failures and the predefined runtime diagnostic arms are preserved. A local strict pass is not a cross-CPU pass. The separate 52 audit certifies recorded evidence conditionally and uses independently checked recorded probabilities to reconstruct the original action chain. Its scope and numerical assumptions are linked below.

All retained local receipts, including failures, are listed by kind. These are audit evaluations of recorded candidates, separate from the 76683 prospective evaluations, and are not independent new samples.

| audit kind | passing / failed runs | passing / failed objective evaluations |
| :--- | ---: | ---: |
| `strict_nonpid` | 3 / 0 | 230049 / 0 |
| `recorded_transfer` | 2 / 0 | 153366 / 0 |
| `recorded_recalibration` | 2 / 0 | 0 / 0 |

The earlier hosted failed audit separately consumed 33745 objective evaluations in [run 40070330365](https://github.com/lijiawei255/jev-tune/actions/runs/40070330365). Its receipt file was not exported; the original failure log and explicit accounting JSON are preserved. This cost is not hidden in local receipts or acquisition. Final hosted CI must pass before publication; these local results alone are not hosted acceptance.

Recalibration adds 0 objective evaluations and 0 gradient steps. Its total host wall time is 5.0894591999986005 seconds; per-size measured fit timings in milliseconds follow. These exclude label acquisition and target-device execution.

```json
[
  {
    "seed": 101,
    "n_per_split": 16,
    "timing_statistics_ms": {
      "temperature_fit_ms": {
        "median": 4.512600000452949,
        "p99": 5.80412999879627,
        "min": 3.8088000001152977,
        "max": 5.865899998752866
      },
      "conformal_fit_ms": {
        "median": 0.08820000039122533,
        "p99": 0.1351799999611103,
        "min": 0.06799999937356915,
        "max": 0.14069999997445848
      },
      "total_fit_ms": {
        "median": 4.601499998898362,
        "p99": 5.912909998914984,
        "min": 3.8812999991932884,
        "max": 5.960999998933403
      }
    }
  },
  {
    "seed": 101,
    "n_per_split": 32,
    "timing_statistics_ms": {
      "temperature_fit_ms": {
        "median": 5.077400001027854,
        "p99": 6.9254199997885735,
        "min": 4.238499999701162,
        "max": 7.0845999998709885
      },
      "conformal_fit_ms": {
        "median": 0.09839999984251335,
        "p99": 0.2250400000775698,
        "min": 0.07189999996626284,
        "max": 0.25149999964924064
      },
      "total_fit_ms": {
        "median": 5.174100000658655,
        "p99": 7.074680000914668,
        "min": 4.31639999987965,
        "max": 7.247900000947993
      }
    }
  },
  {
    "seed": 101,
    "n_per_split": 64,
    "timing_statistics_ms": {
      "temperature_fit_ms": {
        "median": 5.647500000122818,
        "p99": 6.6766600000846665,
        "min": 4.833300001337193,
        "max": 6.8620000001828885
      },
      "conformal_fit_ms": {
        "median": 0.10470000052009709,
        "p99": 0.19937999968533396,
        "min": 0.08859999979904387,
        "max": 0.22979999994277023
      },
      "total_fit_ms": {
        "median": 5.744300000515068,
        "p99": 6.873369999630085,
        "min": 4.924499999106047,
        "max": 7.091800000125659
      }
    }
  },
  {
    "seed": 202,
    "n_per_split": 16,
    "timing_statistics_ms": {
      "temperature_fit_ms": {
        "median": 4.669800000556279,
        "p99": 5.7993700000224635,
        "min": 3.804199999649427,
        "max": 5.886400000235881
      },
      "conformal_fit_ms": {
        "median": 0.0928999997995561,
        "p99": 0.28075999980501365,
        "min": 0.07499999992433004,
        "max": 0.2815999996528262
      },
      "total_fit_ms": {
        "median": 4.769900000610505,
        "p99": 6.034100000215403,
        "min": 3.883900000801077,
        "max": 6.165200000395998
      }
    }
  },
  {
    "seed": 202,
    "n_per_split": 32,
    "timing_statistics_ms": {
      "temperature_fit_ms": {
        "median": 5.053099999713595,
        "p99": 5.55921000050148,
        "min": 4.208900001685834,
        "max": 5.58180000007269
      },
      "conformal_fit_ms": {
        "median": 0.09800000043469481,
        "p99": 0.23167999988800142,
        "min": 0.07199999890872277,
        "max": 0.25939999977708794
      },
      "total_fit_ms": {
        "median": 5.1615000011224765,
        "p99": 5.660359999819775,
        "min": 4.280900000594556,
        "max": 5.678899999111309
      }
    }
  },
  {
    "seed": 202,
    "n_per_split": 64,
    "timing_statistics_ms": {
      "temperature_fit_ms": {
        "median": 5.478999999468215,
        "p99": 7.469489998948119,
        "min": 4.525800000919844,
        "max": 7.682399998884648
      },
      "conformal_fit_ms": {
        "median": 0.1083999995898921,
        "p99": 0.21681999969587187,
        "min": 0.08189999971364159,
        "max": 0.2550999997765757
      },
      "total_fit_ms": {
        "median": 5.574999999225838,
        "p99": 7.5917999993180265,
        "min": 4.6232999993662816,
        "max": 7.80779999877268
      }
    }
  },
  {
    "seed": 303,
    "n_per_split": 16,
    "timing_statistics_ms": {
      "temperature_fit_ms": {
        "median": 4.534699999567238,
        "p99": 5.5508999997982755,
        "min": 3.80829999994603,
        "max": 5.599199999778648
      },
      "conformal_fit_ms": {
        "median": 0.09189999946102034,
        "p99": 0.16371000001527133,
        "min": 0.07050000021990854,
        "max": 0.17010000010486692
      },
      "total_fit_ms": {
        "median": 4.637199999706354,
        "p99": 5.676480000875017,
        "min": 3.8800999991508434,
        "max": 5.705700001271907
      }
    }
  },
  {
    "seed": 303,
    "n_per_split": 32,
    "timing_statistics_ms": {
      "temperature_fit_ms": {
        "median": 4.825899999559624,
        "p99": 6.034460000410036,
        "min": 4.15659999998752,
        "max": 6.114800000432297
      },
      "conformal_fit_ms": {
        "median": 0.09409999984200113,
        "p99": 0.11939999967580661,
        "min": 0.07229999937408138,
        "max": 0.11939999967580661
      },
      "total_fit_ms": {
        "median": 4.92119999944407,
        "p99": 6.150830000478891,
        "min": 4.228899999361602,
        "max": 6.234200000108103
      }
    }
  },
  {
    "seed": 303,
    "n_per_split": 64,
    "timing_statistics_ms": {
      "temperature_fit_ms": {
        "median": 5.385000000387663,
        "p99": 6.2766000006377,
        "min": 4.683500001192442,
        "max": 6.303600001047016
      },
      "conformal_fit_ms": {
        "median": 0.1038999998854706,
        "p99": 0.4685300002165601,
        "min": 0.08309999975608662,
        "max": 0.5951000002824003
      },
      "total_fit_ms": {
        "median": 5.484799999976531,
        "p99": 6.586310000056983,
        "min": 4.7921999994287034,
        "max": 6.658700000116369
      }
    }
  }
]
```

Complex risk research remains paused and risk-head deployment disabled. Host measurements are not target-board timing or safety guarantees. Existing v0.8.0/v0.9.0 research and failed conclusions remain preserved.

[Non-PID transfer](NONPID_TRANSFER.md) · [Recalibration](RECALIBRATION.md) · [Numerical reproducibility](NUMERICAL_REPRODUCIBILITY.md) · [Safety shell](SAFETY_SHELL.md) · [Compute](COMPUTE.md) · [Verification](../research/results/release_verification.json)

## 简体中文

644 passed; 0 skipped; coverage 83.45%; 158 claims checks.

v0.10.0提供经过输入和逐层输出检查的C决策整链，以及冻结模型的复用校准壳，并完成新训练的非PID去噪迁移实验。主实验实际目标评估76683次，验收为`negative_stop`；三个训练种子都没有建立优于基线的预注册稳定收益。新claims通过的是具有明确算术假设的原记录证据核验，不说明策略更优，不恢复逐位重放，不证明训练历史的因果真实性，也不承诺当前CPU的动作等价于原轨迹。原始报告verification_status仍是生产侧状态。

原46/48严格复现在原机通过、在托管CPU失败；原失败及预先固定的运行时诊断两臂完整保留。本机严格通过不等于跨CPU通过。独立52审计在算术假设下验证原记录，并使用独立检查过的原概率重建原动作链；范围和数值前提见下方链接。

所有本地成功和失败receipt按kind分别列于上表，与76683次前瞻主实验分开，不构成独立新样本。较早托管失败审计在[run 40070330365](https://github.com/lijiawei255/jev-tune/actions/runs/40070330365)实际执行33745次目标函数；当时没有导出receipt文件，原失败日志及单独计账JSON继续保留，不混入本地receipt或采集成本。最终托管CI通过后才可发布，本地结果本身不能代替托管验收。

再校准额外目标评估0次、梯度步骤0次，宿主总耗时5.0894591999986005秒；各规模实测拟合时间见上方JSON，排除标签采集和目标板执行。复杂风险研究继续暂停，风险头部署关闭，宿主测试不提供目标板时限或安全保证。v0.8.0/v0.9.0历史研究与失败结论继续保留。

[Non-PID transfer](NONPID_TRANSFER.md) · [Recalibration](RECALIBRATION.md) · [Numerical reproducibility](NUMERICAL_REPRODUCIBILITY.md) · [Safety shell](SAFETY_SHELL.md) · [Compute](COMPUTE.md) · [Verification](../research/results/release_verification.json)
