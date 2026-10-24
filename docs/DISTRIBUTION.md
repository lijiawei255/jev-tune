# Downloads and reproduction / 分发与复现

[English](#english) · [简体中文](#简体中文)

## English

### Distribution and publication acceptance

The v0.10.1 distribution separates experimental records from reachable source
history and applies the authorized text and environment-path cleanup. The public
manifests bind the distributed bytes and record historical identities and any
sanitized metadata derivatives. Scientific numeric outcomes, formal weights,
thresholds and frozen protocols retain their stated evidence scope.

The commands below describe this distribution. Publication acceptance requires
that the official tag and all pinned Release attachments exist and pass the
verification steps below. A local checkout or this document alone does not prove
that a remote transition has completed. Exact archive sizes, hashes and remote
verification outcomes belong to the release verification receipts.

### Reuse the framework

The distribution removes experimental payloads from reachable Git history. A new
ordinary clone needs no partial-clone or sparse-checkout flags:

```sh
git clone https://github.com/lijiawei255/jev-tune.git
cd jev-tune
```

The clone and source ZIP retain the complete implementation, tests, bilingual
documentation, C99/MATLAB bridges, formal PID artifacts in `models/`, and the six
non-PID model/calibration JSON files in `research/results/nonpid_transfer/`.
Runtime use of the shell and shipped models needs no research-data download.
Other experimental records and their older blob versions are restored from pinned
Release attachments when needed. Setup must not rewrite an existing user's checkout.

The [history mapping](../research/distribution/history_rewrite_v0101.json)
records original and distributed commit identities. Metadata and ordered parent
relationships are preserved where compatible with the authorized text cleanup;
changed commit messages or trees produce new identities. A retained original
signed commit preserves only its own original bytes and signature. Rewritten
commits do not inherit that signature. The manifests, rather than a blanket
identity claim, define which objects remain original.

`scripts/61_check_distribution.py` checks reachable source history, a real
`git archive` ZIP, included source bytes, formal weights and attachment mapping.
It distinguishes optional missing data from verified restored payloads. Exact
archive sizes, hashes and verification outcomes belong to machine reports;
source file counts do not establish download size.

### Optional motor-valve benchmark

The optional [motor-valve benchmark manifest](../research/distribution/motor_valve_benchmark_v0101.json)
pins a separate model bundle. Restore it only when you need this benchmark:

```sh
python scripts/65_restore_benchmark.py
```

The ignored `benchmarks/motor_valve/` directory receives one canonical sanitized
SLX model, its geometry and image, six unique recorded MAT results and the
model-equivalence proof. These are retained benchmark materials; sanitization does
not establish from-scratch authorship. The proof defines the model's behavioral
comparison scope. This bundle is separate from framework runtime dependencies and
from the scientific source capsule.

### Restore the latest experimental evidence

The [data manifest](../research/distribution/research_data_v0101.json) pins fixed
Release URLs, whole-archive SHA-256/size and every member's path, SHA-256/size.
It covers the listed research files and four synthetic PID NPZ files. The six
formal JSON files also have recovery copies in `evidence`; identical source copies
are reused. Numeric payloads are retained. Sanitized metadata derivatives have
new byte pins and explicit mappings to their original identities.

| Group | Contents |
| :--- | :--- |
| `historical` | Earlier risk trajectories |
| `current` | Non-PID raw records and calibration arrays |
| `evidence` | Reports, measurements and provenance records |
| `pid` | The pinned synthetic PID data files |

The committed manifest is authoritative for current archive and member pins.
From the repository root:

```sh
python scripts/59_research_data.py --fetch all
python scripts/59_research_data.py --check all
# Offline: use the pinned attachments downloaded to another directory.
python scripts/59_research_data.py --fetch all --from-dir downloaded-attachments
```

Replace `all` with a group name to restore only that group. All selected required
archives and members are verified before new data files are published. Unsafe
paths, links, unknown/duplicate/case-colliding entries, corruption and existing
different files are rejected. Identical files are reused; existing files are
never overwritten. A publication failure rolls back files created by that call.
Bundle LICENSE/NOTICE metadata is checked without replacing current notices.
Restoration preserves the distributed bytes and line endings. Hashes establish
file identity relative to the committed manifest. For metadata derivatives they
do not assert identity with the original unsanitized record. Neither kind of hash
proves training-process causality or completeness of the acquisition ledger.

The original research-preservation manifest remains byte-exact. Its approved
metadata derivatives are checked against separate original/current hashes,
canonical JSON hashes and unchanged numeric projections in the
[source proofs](../research/distribution/deidentified_source_proofs_v0101.json).
An original digest is never presented as the digest of altered public bytes.

### Historical sources and older data versions

Frozen verification reads selected original producer sources. Before pytest or
claims, restore the pinned
[historical source capsule](../research/distribution/historical_sources_v0101.json):

```sh
python scripts/history_sources.py --root . --restore-pinned
# Offline: this directory must also contain the pinned source capsule.
python scripts/history_sources.py --root . --restore-pinned --from-dir downloaded-attachments
```

The capsule contains the selected original scientific source blobs and required
commit/tree objects listed in its manifest. The selected original source paths
remain authentic; this is not a claim that every historical file is included or
that rewritten metadata are original bytes. Verified objects are imported without
changing refs, tags or HEAD. The promisor pack permits required source/tree
queries; it is **not the complete old Git history**. Verification disables lazy
fetching and Git replacement objects.

The frozen script-32 and script-34 sources retain their original bytes. During
those verifiers only, script 44 first runs each original hash predicate; its
metadata adapter accepts a failed comparison only for two explicitly bound
contexts: the trajectory protocol's old rollout result and the replay's original
trajectory result. It checks the original recorded/LF identities (including the
recorded LF/CRLF relationship), actual approved public derivative hashes,
canonical JSON and unchanged original numeric projections. Original raw-record,
model, threshold and numerical assertions still run; digest functions are not
changed. Receipts distinguish archival original hashes from actual public bytes.

The [historical-data index](../research/distribution/historical_data_v0101.json)
maps original commit/path/blob identities to the pinned latest-data bundles or
`historical_data_variants_v0.10.1.zip`. Restore an older commit's records to a new
directory outside the checkout:

```sh
python scripts/64_restore_historical_data.py --commit ORIGINAL_COMMIT_SHA --destination ../jev-historical-records --from-dir downloaded-attachments
```

This checks the indexed original or explicitly mapped derivative identities
without inserting data into Git. Omit
`--from-dir` for pinned Release downloads. It restores records, not a complete old
runnable environment. The old script-42 `--prepare` and `--check-baseline`
maintenance paths are not promised to work directly with the reduced historical
object set. Use the current script-44 frozen-research verifier and script-16 claims
entry point after restoring their required evidence.

### Complete verification in a new directory

Install the documented Python/development dependencies, then run:

```sh
python scripts/60_reproduce_release.py --destination jev-tune-full-verification --verify
# Offline: supply all data ZIPs and the source capsule in one directory.
python scripts/60_reproduce_release.py --destination jev-tune-offline-verification --verify --from-dir downloaded-attachments
```

The wrapper uses a new ordinary clone of the fixed official release, restores data
and historical source objects, then runs the complete tests with coverage/JUnit
and the complete claims check. Official-version verification requires the
published tag and pinned assets; local acceptance explicitly supplies local
`--source` and `--ref`. It reuses the current Python environment, not a clean dependency install.
Existing destinations/reports are refused. Logs, receipts and actual additional
verification costs remain under the new checkout's `.local-audit/`.
Partial `PYTEST_*` selection is removed; missing claims, skips or failed checks
cannot count as success.

For manual verification, restore data first, the source capsule second, then run
`python -m pytest tests` and `python scripts/16_check_claims.py --json`. A source
ZIP has no Git repository: restoring data alone cannot satisfy historical source
checks. This verifies conditional original-record evidence; preserved strict
cross-CPU failures remain failures, and future physical trajectory equivalence
is not established.

### Privacy, rights and source-proof boundary

The authorized cleanup removes identifying benchmark labels and private host-path
metadata from public distribution. Public author names and contact identities
remain intentional. Numeric measurements and failed outcomes are retained;
metadata substitutions are disclosed as derivatives. This is a bounded cleanup,
not a guarantee that every possible identifier has been detected.

External benchmark files are not distributed and no redistribution right over
them is asserted. [OPEN_SOURCE](OPEN_SOURCE.md) and [NOTICE](../NOTICE.md) describe
the payload and dependency licences. Original scientific source proofs remain
valid only for the selected unchanged objects bound by the source capsule;
sanitized prose or metadata cannot use an original hash as proof of byte identity.
The original v0.10.0 inventory binds its original artifacts separately from new
history and distribution evidence.

## 简体中文

### 分发与发布验收

v0.10.1分发从可达源码历史分离实验记录，并执行已授权的文字和环境路径清理。公开清单
绑定分发字节，记录历史身份及脱敏元数据派生件。科学数值结果、正式权重、阈值与冻结
协议保留其原有证据范围。

以下命令描述该分发方案。发布验收要求官方tag与全部固定Release附件真实存在，并通过
下述核验。本地检出或本文本身不能证明远端切换已经完成；精确压缩包大小、哈希及远端
核验结果以发布核验收据为准。

### 复用框架

分发方案从可达Git历史移出实验数据，新获取仓库只需普通克隆，无需部分克隆或稀疏参数：

```sh
git clone https://github.com/lijiawei255/jev-tune.git
cd jev-tune
```

克隆及源码ZIP保留完整实现、测试、中英文文档、C99/MATLAB桥、`models/`中的正式PID产物，
以及`research/results/nonpid_transfer/`内六份正式非PID模型/校准JSON。使用外壳与正式
模型不需要研究数据。其余实验记录及历史blob版本按需从固定Release附件恢复，安装不能
擅自重写用户既有检出。

[历史映射](../research/distribution/history_rewrite_v0101.json)记录原提交与分发提交身份。
元数据和有序父节点关系在与已授权文字清理兼容的范围内保留，消息或tree变化会产生新
身份。保留的原始签名提交仅保持其自身原字节与签名，重写提交不会继承该签名。哪些对象
仍为原件，以清单为准，不能笼统宣称所有身份不变。

`scripts/61_check_distribution.py`检查可达源码历史、真实`git archive` ZIP、所含源码字节、
正式权重及附件映射，并区分“缺少可选数据”与“已核验恢复的数据”。精确压缩包大小、哈希
及验收结论以机器报告为准，不从源码文件数推断下载体积。

### 可选电机阀门基准

[电机阀门基准清单](../research/distribution/motor_valve_benchmark_v0101.json)固定独立模型
附件。需要该基准时运行：

```sh
python scripts/65_restore_benchmark.py
```

被忽略的`benchmarks/motor_valve/`目录接收一个统一的脱敏SLX模型、配套几何及图片、
六份唯一的MAT记录结果和模型等价性证明。这些是保留的基准材料，脱敏不意味着从零
原创；模型行为比较范围以证明为准。该附件独立于框架运行依赖与科学源码胶囊。

### 恢复最新实验记录

[数据清单](../research/distribution/research_data_v0101.json)固定Release地址、整包SHA-256/
大小及每个成员的路径、SHA-256/大小，覆盖清单所列研究文件与四份合成PID NPZ。六份
正式JSON在`evidence`中也有恢复副本，现存源码副本完全相同时直接复用。数值载荷保留，
脱敏元数据派生件使用新字节pin，并明确映射原身份。

| 分组 | 内容 |
| :--- | :--- |
| `historical` | 早期风险轨迹 |
| `current` | 非PID原始记录及校准数组 |
| `evidence` | 报告、测量和来源记录 |
| `pid` | 固定哈希的合成PID数据文件 |

当前整包与成员pin以提交的清单为准。在仓库根目录运行：

```sh
python scripts/59_research_data.py --fetch all
python scripts/59_research_data.py --check all
# 离线：先把固定附件放在另一目录。
python scripts/59_research_data.py --fetch all --from-dir downloaded-attachments
```

可将`all`换成单个分组名。所需的全部选中附件及成员先核验，再安装任何新数据；拒绝
危险路径、链接、未知/重复/大小写冲突成员、损坏包及现存不同内容文件。相同文件复用，
既有文件不覆盖；安装失败撤回本次新建文件。附件LICENSE/NOTICE元数据仅核对，不替换
当前声明。恢复保留分发字节及换行；哈希证明相对于提交清单的文件身份，元数据派生件
的哈希不证明其与脱敏前原件逐字节相同。两类哈希都不证明训练因果过程或采集账本完整性。

原研究保存清单保持字节不变；其中获准脱敏的元数据，通过独立的原件/现件哈希、规范JSON
哈希及不变数值投影核验，详见[来源证明](../research/distribution/deidentified_source_proofs_v0101.json)。
原件摘要不会冒充改动后公开字节的摘要。

### 历史源码与更早的数据版本

冻结核验需要选定的原生产源码。运行pytest或claims前，恢复固定的
[历史源码胶囊](../research/distribution/historical_sources_v0101.json)：

```sh
python scripts/history_sources.py --root . --restore-pinned
# 离线：同一目录还需包含固定源码胶囊。
python scripts/history_sources.py --root . --restore-pinned --from-dir downloaded-attachments
```

胶囊包含清单列出的选定原始科学源码blob及所需commit/tree对象。选定原始源码路径
保持真实，但这不表示包含每个历史文件，也不表示改写元数据仍为原字节。恢复器导入
已核验Git对象，不改变refs、tag或HEAD。形成的promisor pack允许所需源码/tree查询，
**不等于完整旧Git历史**。核验禁用惰性拉取和Git replacement对象。

冻结32与34脚本保留原源码字节。44脚本仅在调用这两个核验器期间，先执行原哈希判断；
元数据适配器只对两个明确绑定的失败比较提供兼容：轨迹协议引用的旧rollout结果，以及
重放记录引用的原trajectory结果。门禁逐项检查原记录/LF身份（含记录的LF/CRLF关系）、
获准公开派生件的实际哈希、规范JSON与不变的原数值投影。原始raw记录、模型、阈值及
数值断言仍照常执行，不改摘要函数；收据分别记录归档原哈希与公开实际字节的哈希。

[历史数据索引](../research/distribution/historical_data_v0101.json)将原提交/路径/blob身份
映射到固定的最新数据包或`historical_data_variants_v0.10.1.zip`。可把某旧提交记录恢复
到检出之外的新目录：

```sh
python scripts/64_restore_historical_data.py --commit ORIGINAL_COMMIT_SHA --destination ../jev-historical-records --from-dir downloaded-attachments
```

此操作检查索引记录的原件或明确映射的派生件身份，不向Git插入数据；省略`--from-dir`从固定Release地址下载。
恢复的是记录，并非完整旧运行环境。不能保证旧42脚本的`--prepare`、`--check-baseline`
维护入口能直接使用精简后的历史对象集；恢复所需证据后使用当前44脚本冻结研究核验器
和16脚本claims入口。

### 在新目录完整验证

安装文档所列Python/开发依赖后运行：

```sh
python scripts/60_reproduce_release.py --destination jev-tune-full-verification --verify
# 离线：同一目录提供全部数据ZIP和源码胶囊。
python scripts/60_reproduce_release.py --destination jev-tune-offline-verification --verify --from-dir downloaded-attachments
```

脚本普通克隆固定官方版本到新目录，依次恢复数据及历史源码对象，再执行全部测试、覆盖率/
JUnit和完整claims检查。官方版本核验要求tag及固定附件已发布；本地验收显式提供
本地`--source`及`--ref`。脚本复用现有Python环境，不证明全新依赖安装；拒绝既有目标目录
或报告。日志、收据和实际新增核验成本留在新检出的`.local-audit/`；清除`PYTEST_*`选测
设置，缺claims、跳过或失败不能计为通过。

手动核验时，先恢复数据，再恢复源码胶囊，随后运行`python -m pytest tests`与
`python scripts/16_check_claims.py --json`。源码ZIP没有Git仓库，仅恢复数据无法满足历史
源码检查。审计核验条件性原记录证据，不把保留的严格跨CPU失败改称通过，也不证明未来
物理轨迹等价。

### 隐私、权利与源码证明边界

已授权清理从公开分发移除基准对象的识别标签与私有宿主路径元数据，公开作者姓名和
联系方式属于有意保留。数值测量与失败结果保留，元数据替换明确标为派生件。清理范围
有边界，不保证检出了所有可能标识。

外部基准文件不分发，也不主张其转发权。载荷与依赖许可见[OPEN_SOURCE](OPEN_SOURCE.md)
及[NOTICE](../NOTICE.md)。原始科学源码证明仅适用于源码胶囊绑定的选定未改动对象，
脱敏正文或元数据不能用原哈希证明字节身份。原v0.10.0清单独立绑定原产物，与新的历史
和分发证据分别说明。
