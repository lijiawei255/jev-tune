# Research archive / 研究归档

[English](#english) · [简体中文](#简体中文)

## English

`main` carries the runtime shell, the PID test bed, the light instances, the C99
and MATLAB ports and their tests. Everything else from v0.10.2 is frozen,
unchanged, at the Git tag **`v0.10.2-archive`**:

* frozen protocols ([`research/protocols/`](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/research/protocols)), verifiers and release scripts
  (`scripts/00`, `00b`, `05`, `07`–`09`, `12`–`17`, `21`, `23`–`62`, `64`–`66`,
  `history_sources.py`, `calibration_numeric_audit.py`);
* negative and paused studies: non-PID denoising transfer (`negative_stop`),
  joint/trajectory risk, recalibration, calibration-runtime diagnosis, the
  cross-CPU numerical replay records and their documents;
* the research modules `risk.py`, `joint_rollout.py`, `trajectory_risk.py`,
  `sequential_risk.py`, the ablation control `models/ablation_a0.pt` and the
  non-PID example [`examples/denoise_transfer/`](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/examples/denoise_transfer).

Their data stay the hash-pinned attachments of the existing `v0.10.0` and
`v0.10.1` GitHub Releases, which the archived scripts already download and
verify. The `v0.11.0` Release carries the tag's source snapshot as
`jev-tune-v0.10.2-archive-source.zip`. The tag is the recoverable entry;
nothing is rewritten:

```bash
python scripts/archive.py            # opens .archive/v0.10.2-archive as a worktree
python scripts/archive.py --verify   # restores pinned data there and runs the claim verifier
```

Hashes recorded by the frozen studies refer to the files at the tag, so later
changes on `main` cannot invalidate them. Numbers quoted in `docs/` that come
from archived runs link to the tag or the Release.

## 简体中文

`main`保留运行时外壳、PID实验场、轻量实例、C99/MATLAB移植及其测试。v0.10.2的其余内容
原样冻结在Git标签**`v0.10.2-archive`**：冻结协议、核验与发布脚本、非PID去噪迁移
（`negative_stop`）、联合/轨迹风险、重标定、校准运行时诊断、跨CPU数值复现记录及对应文档、
研究模块、消融对照权重和[`examples/denoise_transfer/`](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/examples/denoise_transfer)。数据仍为既有`v0.10.0`、`v0.10.1` GitHub Release中按哈希固定的附件（归档脚本自行下载核验）；`v0.11.0` Release附带该标签源码快照`jev-tune-v0.10.2-archive-source.zip`。
`python scripts/archive.py`以worktree打开标签，`--verify`在其中恢复固定数据并运行claims核验。
冻结研究记录的哈希指向标签内文件，`main`后续修改不会使其失效。
