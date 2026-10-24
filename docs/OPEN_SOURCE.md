# Open-source inventory / 开源清单

[English](#english) · [简体中文](#简体中文)

## English

This inventories the latest source tree and v0.10.0 release, not Git history cleansing. A normal clone includes the formal trained weights, complete implementation and tests. The ignored synthetic PID datasets are distributed separately; the data ZIP includes LICENSE, NOTICE.md and the machine inventory. Without these NPZ files, --check still validates pins and any locally present files. Packaging requires all four exact files.

Starting with v0.10.1, source ZIPs retain the complete implementation and all formal weights, including the six non-PID JSON artifacts, but omit the other experimental records. Those records are pinned Release attachments with automatic SHA-256 restoration; ordinary Git clones still contain them. This v0.10.0 inventory remains the original artifact binding. See [downloads, full reproduction and privacy boundaries](DISTRIBUTION.md). The source ZIP alone cannot run the complete scientific audit: restore evidence and obtain real historical Git objects with scripts/60_reproduce_release.py.

| Component / 内容 | Distribution / 分发 |
| :--- | :--- |
| Formal PID model artifacts and non-PID models | Git: seven models files plus six non-PID JSON artifacts |
| Generated demo model | `matlab/make_demo_model.m`; generate locally, no private SLX included |
| Complete implementation and tests | `src/`, `matlab/`, `scripts/`, `tests/` |
| Original public research trajectories | `research/results/`; prior release assets remain versioned |
| Pinned synthetic PID data | Release-only [pid_synthetic_data_v0.10.0.zip](https://github.com/lijiawei255/jev-tune/releases/download/v0.10.0/pid_synthetic_data_v0.10.0.zip); four relative NPZ paths |

| Data / 数据 | Bytes / 字节 | SHA-256 |
| :--- | ---: | :--- |
| `data/expert_train.npz` | 20505545 | `0be698afd7443695637bfa7f9ead51b05b279c063b7e25c9b745a2c0efb855a4` |
| `data/calibration/temperature_fit.npz` | 245644 | `de618327a1737e80fa0db68fb7d7390af2459c913621164457e6de056c15dce8` |
| `data/calibration/cp_fit.npz` | 248321 | `74216c6dd8c93dd408df65e37183ba13ec089458605caa08b4cc1a1523b5356f` |
| `data/calibration/empirical_eval.npz` | 244739 | `757fc4a7c43bc871e06e1725077bd7795f995cec3367c571369c5b057e50c0e9` |

### Obtain the synthetic PID data

Download [pid_synthetic_data_v0.10.0.zip](https://github.com/lijiawei255/jev-tune/releases/download/v0.10.0/pid_synthetic_data_v0.10.0.zip). From the matching v0.10.0 repository root, extract it there, preserving the archived `data/...` paths; do not flatten the archive into one directory.

```sh
python -m zipfile -e pid_synthetic_data_v0.10.0.zip .
python scripts/50_open_source_inventory.py --check
```

Final NPZ hashes establish final-file identity, not causal proof of the training process or a complete original per-evaluation acquisition log. benchmark development feedback influenced zoo design and is not independent external evaluation. No new acquisition-cost numbers are inferred. Risk parameters remain in public research JSON. Ignored value_net/specialized weights without provenance bindings are excluded; private models/geometry/lecture documents and vendored MathWorks engines are prohibited in the latest source tree.

### Regenerate the public discovery animation

The current `assets/discover.gif` is a graph of the project's generated gains demo, not a redraw of a benchmark. Run the MATLAB block from the repository root to build that model and obtain fresh graph/discovery JSON, then run the Python renderer from the same root. This executes discovery probes and records their actual evidence. It uses project source and standard MATLAB/Simulink blocks under the user's MathWorks licence; no benchmark, geometry or handout is required or redistributed.

```matlab
addpath('matlab');
root = pwd;  % Run from the repository root.
folder = tempname;
mkdir(folder);
name = 'portable_reference_demo';
make_demo_model(folder, 'gains', struct('name', name));
modelpath = fullfile(folder, [name '.slx']);
jev_dump_graph(modelpath, fullfile(root, 'research', 'results', ...
    'demo_discovery_graph_v0100.json'));
D = jev_discover(modelpath, struct('probe', true, ...
    'work_dir', fullfile(folder, 'discovery')));
assert(D.ok, 'Generated-model discovery failed');
fid = fopen(fullfile(root, 'research', 'results', ...
    'demo_discovery_v0100.json'), 'w');
assert(fid >= 0, 'Cannot open discovery JSON output');
fwrite(fid, unicode2native(jsonencode(D), 'UTF-8'), 'uint8');
fclose(fid);
```

```sh
python scripts/15_make_discovery_gif.py
```

The historical response figures (`tuning.gif`, `before_after.png`, `convergence.png`) are the project's own plots of earlier benchmark measurements, not original benchmark artwork or the current discovery model. Their historical objective and timing caveats still apply; regenerating an image does not rerun or validate that experiment.

## 简体中文

清单范围为当前源码树与v0.10.0发布，不声称清理Git历史。普通clone已包含正式训练权重、完整实现与测试；被忽略的合成PID数据通过独立附件提供，ZIP内含LICENSE、NOTICE.md与机器清单。缺少NPZ时仍可运行--check，核对校准pin，存在本地文件则额外校验；打包必须四文件全部逐字节匹配。

从v0.10.1起，源码ZIP保留完整实现及全部正式权重（含六份非PID模型/校准JSON），其他实验记录通过固定哈希的Release附件按需恢复；普通Git克隆仍含原记录。本v0.10.0清单继续绑定原产物，不改旧证据。详见[分发、完整复现与隐私边界](DISTRIBUTION.md)。仅源码ZIP不能执行完整科学审计，须恢复证据并通过scripts/60_reproduce_release.py获取真实历史Git对象。

| 内容 | 分发方式 |
| :--- | :--- |
| 正式PID模型产物与非PID模型 | Git内7份正式模型产物（含元数据和校准）及6份非PID模型/校准JSON |
| 生成的演示模型 | 本地运行matlab/make_demo_model.m，不附私有SLX |
| 完整实现与测试 | src/、matlab/、scripts/、tests/ |
| 已公开研究原始轨迹 | research/results/及保留版本的历史release附件 |
| 已固定hash的合成PID数据 | Release附件[pid_synthetic_data_v0.10.0.zip](https://github.com/lijiawei255/jev-tune/releases/download/v0.10.0/pid_synthetic_data_v0.10.0.zip)，含4份保持相对路径的NPZ |

| Data / 数据 | Bytes / 字节 | SHA-256 |
| :--- | ---: | :--- |
| `data/expert_train.npz` | 20505545 | `0be698afd7443695637bfa7f9ead51b05b279c063b7e25c9b745a2c0efb855a4` |
| `data/calibration/temperature_fit.npz` | 245644 | `de618327a1737e80fa0db68fb7d7390af2459c913621164457e6de056c15dce8` |
| `data/calibration/cp_fit.npz` | 248321 | `74216c6dd8c93dd408df65e37183ba13ec089458605caa08b4cc1a1523b5356f` |
| `data/calibration/empirical_eval.npz` | 244739 | `757fc4a7c43bc871e06e1725077bd7795f995cec3367c571369c5b057e50c0e9` |

### 获取合成PID数据

下载[pid_synthetic_data_v0.10.0.zip](https://github.com/lijiawei255/jev-tune/releases/download/v0.10.0/pid_synthetic_data_v0.10.0.zip)后，在对应v0.10.0源码仓库根目录执行解压，保留附件中的`data/...`相对目录，不要将所有文件平铺到同一目录。

```sh
python -m zipfile -e pid_synthetic_data_v0.10.0.zip .
python scripts/50_open_source_inventory.py --check
```

NPZ最终hash只证明文件身份，不证明训练过程因果关系或完整原始逐次采集日志。基准开发反馈影响了zoo设计，不属于独立外部测试；不推断新的采集成本。风险参数保留在公开研究JSON中。缺来源绑定的ignored value_net/specialized权重不发布；当前源码树禁止私有模型、几何、讲义文档与第三方MathWorks engine源码。

### 再生成公开发现动画

当前`assets/discover.gif`展示本项目自主生成的gains演示模型图，不是基准模型结构的重绘。从仓库根目录在MATLAB执行下面代码生成模型及新的graph/discovery JSON，再从同一根目录运行Python绘图脚本。这一过程会执行发现探测并记录真实证据；只使用项目源码及用户MathWorks许可证下的标准MATLAB/Simulink模块，不需要或分发基准原模型、几何或讲义。

```matlab
addpath('matlab');
root = pwd;  % Run from the repository root.
folder = tempname;
mkdir(folder);
name = 'portable_reference_demo';
make_demo_model(folder, 'gains', struct('name', name));
modelpath = fullfile(folder, [name '.slx']);
jev_dump_graph(modelpath, fullfile(root, 'research', 'results', ...
    'demo_discovery_graph_v0100.json'));
D = jev_discover(modelpath, struct('probe', true, ...
    'work_dir', fullfile(folder, 'discovery')));
assert(D.ok, 'Generated-model discovery failed');
fid = fopen(fullfile(root, 'research', 'results', ...
    'demo_discovery_v0100.json'), 'w');
assert(fid >= 0, 'Cannot open discovery JSON output');
fwrite(fid, unicode2native(jsonencode(D), 'UTF-8'), 'uint8');
fclose(fid);
```

```sh
python scripts/15_make_discovery_gif.py
```

历史响应图（`tuning.gif`、`before_after.png`、`convergence.png`）是本项目对早期基准验证床测量结果的自主绘图，并非基准原图，也不是当前发现动画所用模型。其历史目标函数与计时范围限制继续有效；重新生成图片不等于重跑或验收旧实验。
