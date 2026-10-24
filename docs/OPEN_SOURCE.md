# Open-source inventory / 开源清单

[English](#english) · [简体中文](#简体中文)

## English

The unchanged v0.10.0 machine inventory binds its original artifacts, not the later history transition. A normal clone includes the formal trained weights, complete implementation and tests. The ignored synthetic PID datasets are distributed separately; the data ZIP includes LICENSE, NOTICE.md and the machine inventory. Without these NPZ files, --check still validates pins and any locally present files. Packaging requires all four exact files.

The local v0.10.1 candidate moves experimental payloads out of reachable Git history, so after approved publication an ordinary clone needs no sparse/partial flags. Complete source and formal weights, including the six non-PID JSON artifacts, remain in Git and source ZIPs. The latest 449 research files and four PID files are recoverable from pinned Release attachments without changing existing archive/member hashes; earlier blob versions have a separate historical-data index. The [history mapping](../research/distribution/history_rewrite_v0101.json) records the preserved original commit metadata and parent graph; changed trees have new commit identities, while the initial signed commit retains its original identity and signature. Current scope is local phase 1: the remote and public tags/Releases are unchanged, and the privacy scan follows phase 1; any cleanup needs user approval. Data externalization does not anonymize original records.

Runtime reuse needs no research-data download. Before pytest or claims, run `python scripts/59_research_data.py --fetch all`, then `python scripts/history_sources.py --root . --restore-pinned`; both support `--from-dir` for offline pinned assets. The source capsule imports selected original source/tree objects without changing refs, not the complete old history. Old script-42 maintenance commands are not promised to work directly; current script-44/16 frozen verification uses the required restored evidence. Use script 60 for a new verification checkout. See [distribution, reproduction and privacy boundaries](DISTRIBUTION.md).

| Component / 内容 | Distribution / 分发 |
| :--- | :--- |
| Formal PID model artifacts and non-PID models | Git: seven models files plus six non-PID JSON artifacts |
| Generated demo model | `matlab/make_demo_model.m`; generate locally, no private SLX included |
| Complete implementation and tests | `src/`, `matlab/`, `scripts/`, `tests/` |
| Research records and earlier versions | Pinned Release data bundles; [latest-data manifest](../research/distribution/research_data_v0101.json) and [historical-data index](../research/distribution/historical_data_v0101.json) |
| Selected original producer sources | [Historical source capsule](../research/distribution/historical_sources_v0101.json); source/tree objects, not complete old history |
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

未改动的v0.10.0机器清单绑定原产物，不是后续历史切换的证明。普通clone包含正式训练权重、完整实现与测试；被忽略的合成PID数据通过独立附件提供，ZIP内含LICENSE、NOTICE.md与机器清单。缺少NPZ时仍可运行--check，核对校准pin，存在本地文件则额外校验；打包必须四文件全部逐字节匹配。

本地v0.10.1候选从可达Git历史移出实验载荷，经批准发布后普通克隆无需稀疏/部分克隆参数；完整源码与正式权重（含六份非PID模型/校准JSON）继续保留在Git及源码ZIP。最新449份研究文件和四份PID文件按固定Release附件恢复，既有整包/成员哈希不变，更早blob版本由独立历史数据索引覆盖。[历史映射](../research/distribution/history_rewrite_v0101.json)记录保留的原提交元数据及父节点关系；树变化的提交获得新身份，初始签名提交保留原SHA及签名。当前仅本地阶段一，远端及公开tag/Release尚未改变，阶段一后自动扫描隐私，任何脱敏清理须另行批准；数据外置不等于匿名化。

运行复用无需研究数据。pytest或claims前先运行`python scripts/59_research_data.py --fetch all`，再运行`python scripts/history_sources.py --root . --restore-pinned`；两者均支持`--from-dir`离线固定附件。源码胶囊导入选定原源码/tree对象，不改变refs，也不等于完整旧历史；旧42维护命令不保证直接可用，当前44/16冻结核验使用恢复后的所需证据。新目录完整核验使用60脚本，详见[分发、复现与隐私边界](DISTRIBUTION.md)。

| 内容 | 分发方式 |
| :--- | :--- |
| 正式PID模型产物与非PID模型 | Git内7份正式模型产物（含元数据和校准）及6份非PID模型/校准JSON |
| 生成的演示模型 | 本地运行matlab/make_demo_model.m，不附私有SLX |
| 完整实现与测试 | src/、matlab/、scripts/、tests/ |
| 研究记录及更早版本 | 固定Release数据附件；[最新数据清单](../research/distribution/research_data_v0101.json)与[历史数据索引](../research/distribution/historical_data_v0101.json) |
| 选定原生产源码 | [历史源码胶囊](../research/distribution/historical_sources_v0101.json)，提供源码/tree对象，不等于完整旧历史 |
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
