# Open-source inventory / 开源清单

[English](#english) · [简体中文](#简体中文)

## English

The v0.10.0 artifact inventory records the model and data bindings; current distribution manifests identify sanitized metadata derivatives. A normal clone includes the formal trained weights, complete implementation and tests. The ignored synthetic PID datasets are distributed separately; the data ZIP includes LICENSE, NOTICE.md and the machine inventory. Without these NPZ files, --check still validates pins and any locally present files. Packaging requires all four exact files.

The v0.10.1 distribution keeps complete source and formal weights, including the six non-PID JSON artifacts, in Git and source ZIPs. An ordinary clone needs no sparse/partial flags; experimental records and earlier data versions are restored from pinned Release attachments. Public manifests bind the distributed bytes and distinguish unchanged original scientific objects from sanitized metadata derivatives. The [history mapping](../research/distribution/history_rewrite_v0101.json) describes the history transition; original commit identities and signatures are not a blanket guarantee. Publication and reproduction acceptance require the actual pinned assets and verification receipts described in [DISTRIBUTION](DISTRIBUTION.md).

Runtime reuse needs no research-data download. Before pytest or claims, run `python scripts/59_research_data.py --fetch all`, then `python scripts/history_sources.py --root . --restore-pinned`; both support `--from-dir` for offline pinned assets. The source capsule imports selected original scientific source/tree objects without changing refs, not the complete old history. Old script-42 maintenance commands are not promised to work directly; current script-44/16 frozen verification uses the required restored evidence. Use script 60 for a new verification checkout. See [distribution, reproduction and privacy boundaries](DISTRIBUTION.md).

| Component / 内容 | Distribution / 分发 |
| :--- | :--- |
| Formal PID model artifacts and non-PID models | Git: seven models files plus six non-PID JSON artifacts |
| Generated demo model | `matlab/make_demo_model.m`; generate locally, no private SLX included |
| Complete implementation and tests | `src/`, `matlab/`, `scripts/`, `tests/` |
| Research records and earlier versions | Pinned Release data bundles; [latest-data manifest](../research/distribution/research_data_v0101.json) and [historical-data index](../research/distribution/historical_data_v0101.json) |
| Selected producer sources | [Historical source capsule](../research/distribution/historical_sources_v0101.json); source/tree objects, not complete old history |
| Pinned synthetic PID data | Release-only [pid_synthetic_data_v0.10.0.zip](https://github.com/lijiawei255/jev-tune/releases/download/v0.10.0/pid_synthetic_data_v0.10.0.zip); four relative NPZ paths |

| Data / 数据 | Bytes / 字节 | SHA-256 |
| :--- | ---: | :--- |
| `data/expert_train.npz` | 20505545 | `0be698afd7443695637bfa7f9ead51b05b279c063b7e25c9b745a2c0efb855a4` |
| `data/calibration/temperature_fit.npz` | 245644 | `de618327a1737e80fa0db68fb7d7390af2459c913621164457e6de056c15dce8` |
| `data/calibration/cp_fit.npz` | 248321 | `74216c6dd8c93dd408df65e37183ba13ec089458605caa08b4cc1a1523b5356f` |
| `data/calibration/empirical_eval.npz` | 244739 | `757fc4a7c43bc871e06e1725077bd7795f995cec3367c571369c5b057e50c0e9` |

### Obtain the synthetic PID data

Download [pid_synthetic_data_v0.10.0.zip](https://github.com/lijiawei255/jev-tune/releases/download/v0.10.0/pid_synthetic_data_v0.10.0.zip). From the repository root, extract it there, preserving the archived `data/...` paths; do not flatten the archive into one directory.

```sh
python -m zipfile -e pid_synthetic_data_v0.10.0.zip .
python scripts/50_open_source_inventory.py --check
```

Final NPZ hashes establish final-file identity, not causal proof of the training process or a complete original per-evaluation acquisition log. Benchmark development feedback influenced zoo design and is not independent external evaluation. No new acquisition-cost numbers are inferred. Risk parameters remain in public research JSON. Ignored value_net/specialized weights without provenance bindings are excluded; private models/geometry/private documents and vendored MathWorks engines are prohibited in the latest source tree.

### Regenerate the public discovery animation

The current `assets/discover.gif` is a graph of the project's generated gains demo. Run the MATLAB block from the repository root to build that model and obtain fresh graph/discovery JSON, then run the Python renderer from the same root. This executes discovery probes and records their actual evidence. It uses project source and standard MATLAB/Simulink blocks under the user's MathWorks licence; reproduction uses the generated model and requires no external benchmark files.

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

The historical response figures (`tuning.gif`, `before_after.png`, `convergence.png`) are the project's own plots of earlier motor-valve benchmark measurements; they use a different model from the current discovery animation. Their historical objective and timing caveats still apply; regenerating an image does not rerun or validate that experiment.

## 简体中文

v0.10.0产物清单记录模型和数据绑定，当前分发清单标明脱敏元数据派生件。普通clone包含正式训练权重、完整实现与测试；被忽略的合成PID数据通过独立附件提供，ZIP内含LICENSE、NOTICE.md与机器清单。缺少NPZ时仍可运行--check，核对校准pin，存在本地文件则额外校验；打包必须四文件全部逐字节匹配。

v0.10.1分发在Git和源码ZIP中保留完整源码及正式权重（含六份非PID模型/校准JSON）。普通克隆无需稀疏/部分克隆参数，实验记录及更早数据版本按需从固定Release附件恢复。公开清单绑定分发字节，区分未改动的原始科学对象与脱敏元数据派生件。[历史映射](../research/distribution/history_rewrite_v0101.json)说明历史切换，不笼统承诺保留原提交身份或签名。发布与复现验收以[DISTRIBUTION](DISTRIBUTION.md)所述的真实固定附件和核验收据为准。

运行复用无需研究数据。pytest或claims前先运行`python scripts/59_research_data.py --fetch all`，再运行`python scripts/history_sources.py --root . --restore-pinned`；两者均支持`--from-dir`离线固定附件。源码胶囊导入选定原始科学源码/tree对象，不改变refs，也不等于完整旧历史；旧42维护命令不保证直接可用，当前44/16冻结核验使用恢复后的所需证据。新目录完整核验使用60脚本，详见[分发、复现与隐私边界](DISTRIBUTION.md)。

| 内容 | 分发方式 |
| :--- | :--- |
| 正式PID模型产物与非PID模型 | Git内7份正式模型产物（含元数据和校准）及6份非PID模型/校准JSON |
| 生成的演示模型 | 本地运行matlab/make_demo_model.m，不附私有SLX |
| 完整实现与测试 | src/、matlab/、scripts/、tests/ |
| 研究记录及更早版本 | 固定Release数据附件；[最新数据清单](../research/distribution/research_data_v0101.json)与[历史数据索引](../research/distribution/historical_data_v0101.json) |
| 选定生产源码 | [历史源码胶囊](../research/distribution/historical_sources_v0101.json)，提供源码/tree对象，不等于完整旧历史 |
| 已固定hash的合成PID数据 | Release附件[pid_synthetic_data_v0.10.0.zip](https://github.com/lijiawei255/jev-tune/releases/download/v0.10.0/pid_synthetic_data_v0.10.0.zip)，含4份保持相对路径的NPZ |

| Data / 数据 | Bytes / 字节 | SHA-256 |
| :--- | ---: | :--- |
| `data/expert_train.npz` | 20505545 | `0be698afd7443695637bfa7f9ead51b05b279c063b7e25c9b745a2c0efb855a4` |
| `data/calibration/temperature_fit.npz` | 245644 | `de618327a1737e80fa0db68fb7d7390af2459c913621164457e6de056c15dce8` |
| `data/calibration/cp_fit.npz` | 248321 | `74216c6dd8c93dd408df65e37183ba13ec089458605caa08b4cc1a1523b5356f` |
| `data/calibration/empirical_eval.npz` | 244739 | `757fc4a7c43bc871e06e1725077bd7795f995cec3367c571369c5b057e50c0e9` |

### 获取合成PID数据

下载[pid_synthetic_data_v0.10.0.zip](https://github.com/lijiawei255/jev-tune/releases/download/v0.10.0/pid_synthetic_data_v0.10.0.zip)后，在源码仓库根目录执行解压，保留附件中的`data/...`相对目录，不要将所有文件平铺到同一目录。

```sh
python -m zipfile -e pid_synthetic_data_v0.10.0.zip .
python scripts/50_open_source_inventory.py --check
```

NPZ最终hash只证明文件身份，不证明训练过程因果关系或完整原始逐次采集日志。基准模型开发反馈影响了zoo设计，不属于独立外部测试；不推断新的采集成本。风险参数保留在公开研究JSON中。缺来源绑定的ignored value_net/specialized权重不发布；当前源码树禁止私有模型、几何、私有文档与第三方MathWorks engine源码。

### 再生成公开发现动画

当前`assets/discover.gif`展示本项目自主生成的gains演示模型图。从仓库根目录在MATLAB执行下面代码生成模型及新的graph/discovery JSON，再从同一根目录运行Python绘图脚本。这一过程会执行发现探测并记录真实证据；只使用项目源码及用户MathWorks许可证下的标准MATLAB/Simulink模块，复现使用生成模型，无需外部基准模型文件。

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

历史响应图（`tuning.gif`、`before_after.png`、`convergence.png`）是本项目对早期电机阀门验证床测量结果的自主绘图，它与当前发现动画使用不同模型。其历史目标函数与计时范围限制继续有效；重新生成图片不等于重跑或验收旧实验。
