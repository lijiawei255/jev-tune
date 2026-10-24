# Downloads and reproduction / 分发与复现

[English](#english) · [简体中文](#简体中文)

## English

### Local candidate and publication status

The v0.10.1 distribution change is currently a **local phase-1 candidate**. The
remote repository and existing public tags/Releases have not been changed in this
phase. The clone instructions below describe the candidate after an approved
remote transition; they do not claim that today's remote is already small.
Phase 2 scans history and proposes a cleanup plan; any redaction/removal needs
user approval. This is not completed anonymization or privacy certification.

### Reuse the framework

The candidate removes experimental payloads from reachable Git history. A new
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

The [history mapping](../research/distribution/history_rewrite_v0101.json) records
the original 83 commits and candidate identities. Author/committer metadata,
dates, messages, encoding and ordered parent/merge relationships are preserved.
Changed trees give their commits new identities. The initial signed commit is
retained byte-for-byte with its original identity and signature; this does not
preserve the identities or signatures of modified commits. The current removed
roster contains 443 experimental records; the six formal JSON files remain in
Git. Earlier names and versions are covered by the historical-data index.

`scripts/61_check_distribution.py` checks reachable source history, a real
`git archive` ZIP, included source bytes, formal weights and attachment mapping.
It distinguishes optional missing data from verified restored payloads. Exact
archive sizes, hashes and verification outcomes belong to machine reports;
source file counts do not establish download size.

### Restore the latest experimental evidence

The [data manifest](../research/distribution/research_data_v0101.json) pins fixed
Release URLs, whole-archive SHA-256/size and every member's path, SHA-256/size.
It covers 449 research files and four synthetic PID NPZ files. The six formal JSON
files also have recovery copies in `evidence`; identical source copies are reused.

| Group | Contents |
| :--- | :--- |
| `historical` | Earlier risk trajectories |
| `current` | Non-PID raw records and calibration arrays |
| `evidence` | Reports, measurements and provenance records |
| `pid` | The unchanged, pinned v0.10.0 synthetic-data ZIP |

Existing archive and member pins remain unchanged. From the repository root:

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
Restoration preserves original bytes and line endings. Hashes establish file
identity relative to the committed manifest, not training-process causality or
completeness of the original acquisition ledger.

### Historical sources and older data versions

Frozen verification reads selected original producer sources. Before pytest or
claims, restore the pinned
[historical source capsule](../research/distribution/historical_sources_v0101.json):

```sh
python scripts/history_sources.py --root . --restore-pinned
# Offline: this directory must also contain the pinned source capsule.
python scripts/history_sources.py --root . --restore-pinned --from-dir downloaded-attachments
```

The capsule contains selected source blobs, original commit metadata and complete
trees for five original commits and 33 selected source paths, without experimental
data payloads. Verified objects are imported without changing refs, tags or HEAD.
The promisor pack permits required source/tree queries; it is **not the complete
old Git history**. Verification disables lazy fetching and Git replacement objects.

The [historical-data index](../research/distribution/historical_data_v0101.json)
maps original commit/path/blob identities to the unchanged latest-data bundles or
`historical_data_variants_v0.10.1.zip`. Restore an older commit's records to a new
directory outside the checkout:

```sh
python scripts/64_restore_historical_data.py --commit ORIGINAL_COMMIT_SHA --destination ../jev-historical-records --from-dir downloaded-attachments
```

This verifies original blob identities without inserting data into Git. Omit
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
and the complete claims check. The official-version command applies after approved
publication; local phase-1 acceptance explicitly supplies local `--source` and
`--ref`. It reuses the current Python environment, not a clean dependency install.
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

### Privacy and rights boundary

Moving records out of Git is distribution work, not anonymization. Original
measurement/provenance records and logs can contain host information and local
paths; their bytes remain in optional attachments. The pending privacy review
must assess retained source/history, metadata and attachments separately.
No complete privacy cleanup is claimed. Private models, geometry and teaching
materials are excluded from the intended public payload; see
[OPEN_SOURCE](OPEN_SOURCE.md) and [NOTICE](../NOTICE.md) for bounded rights and
provenance statements. The original v0.10.0 inventory remains an unchanged
artifact binding, separate from new history/distribution evidence.

## 简体中文

### 本地候选与发布状态

v0.10.1分发调整目前仅为**本地阶段一候选**。本阶段尚未修改远端仓库、既有公开tag或
Release。下方普通克隆命令描述经批准切换后的候选方案，不表示当前远端已经缩小。
阶段二自动扫描历史并提出清理方案；任何脱敏/移除须经用户批准，不能称为已匿名化或通过隐私认证。

### 复用框架

候选方案从可达Git历史移出实验数据，新获取仓库只需普通克隆，无需部分克隆或稀疏参数：

```sh
git clone https://github.com/lijiawei255/jev-tune.git
cd jev-tune
```

克隆及源码ZIP保留完整实现、测试、中英文文档、C99/MATLAB桥、`models/`中的正式PID产物，
以及`research/results/nonpid_transfer/`内六份正式非PID模型/校准JSON。使用外壳与正式
模型不需要研究数据。其余实验记录及历史blob版本按需从固定Release附件恢复，安装不能
擅自重写用户既有检出。

[历史映射](../research/distribution/history_rewrite_v0101.json)记录原83个提交与候选身份，
保留作者/提交者元数据、日期、消息、编码和有序父节点/合并关系；树变化的提交获得新身份。
初始签名提交逐字节保留，原SHA及签名不变；不表示其他被修改提交仍保留原SHA或签名。
当前路径清单移出443份实验记录，六份正式JSON继续留在Git，更早异名和版本由历史数据
索引覆盖。

`scripts/61_check_distribution.py`检查可达源码历史、真实`git archive` ZIP、所含源码字节、
正式权重及附件映射，并区分“缺少可选数据”与“已核验恢复的数据”。精确压缩包大小、哈希
及验收结论以机器报告为准，不从源码文件数推断下载体积。

### 恢复最新实验记录

[数据清单](../research/distribution/research_data_v0101.json)固定Release地址、整包SHA-256/
大小及每个成员的路径、SHA-256/大小，覆盖449份研究文件和四份合成PID NPZ。六份正式
JSON在`evidence`中也有恢复副本，现存源码副本完全相同时直接复用。

| 分组 | 内容 |
| :--- | :--- |
| `historical` | 早期风险轨迹 |
| `current` | 非PID原始记录及校准数组 |
| `evidence` | 报告、测量和来源记录 |
| `pid` | 未改动且固定哈希的v0.10.0合成数据ZIP |

原整包和成员pin保持不变。在仓库根目录运行：

```sh
python scripts/59_research_data.py --fetch all
python scripts/59_research_data.py --check all
# 离线：先把固定附件放在另一目录。
python scripts/59_research_data.py --fetch all --from-dir downloaded-attachments
```

可将`all`换成单个分组名。所需的全部选中附件及成员先核验，再安装任何新数据；拒绝
危险路径、链接、未知/重复/大小写冲突成员、损坏包及现存不同内容文件。相同文件复用，
既有文件不覆盖；安装失败撤回本次新建文件。附件LICENSE/NOTICE元数据仅核对，不替换
当前声明。恢复保留原字节及换行；哈希证明相对于提交清单的文件身份，不证明训练因果
过程或原始采集账本完整性。

### 历史源码与更早的数据版本

冻结核验需要选定的原生产源码。运行pytest或claims前，恢复固定的
[历史源码胶囊](../research/distribution/historical_sources_v0101.json)：

```sh
python scripts/history_sources.py --root . --restore-pinned
# 离线：同一目录还需包含固定源码胶囊。
python scripts/history_sources.py --root . --restore-pinned --from-dir downloaded-attachments
```

胶囊含五个原提交、33条选定源码路径所需的源码blob、原提交元数据及完整tree，不含实验
数据载荷。恢复器导入已核验Git对象，不改变refs、tag或HEAD。形成的promisor pack允许
所需源码/tree查询，**不等于完整旧Git历史**。核验禁用惰性拉取和Git replacement对象。

[历史数据索引](../research/distribution/historical_data_v0101.json)将原提交/路径/blob身份
映射到未改动的最新数据包或`historical_data_variants_v0.10.1.zip`。可把某旧提交记录恢复
到检出之外的新目录：

```sh
python scripts/64_restore_historical_data.py --commit ORIGINAL_COMMIT_SHA --destination ../jev-historical-records --from-dir downloaded-attachments
```

此操作验证原blob身份，不向Git插入数据；省略`--from-dir`从固定Release地址下载。
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
JUnit和完整claims检查。该固定发布命令适用于经批准发布后；本地阶段一验收显式提供
本地`--source`及`--ref`。脚本复用现有Python环境，不证明全新依赖安装；拒绝既有目标目录
或报告。日志、收据和实际新增核验成本留在新检出的`.local-audit/`；清除`PYTEST_*`选测
设置，缺claims、跳过或失败不能计为通过。

手动核验时，先恢复数据，再恢复源码胶囊，随后运行`python -m pytest tests`与
`python scripts/16_check_claims.py --json`。源码ZIP没有Git仓库，仅恢复数据无法满足历史
源码检查。审计核验条件性原记录证据，不把保留的严格跨CPU失败改称通过，也不证明未来
物理轨迹等价。

### 隐私与权利边界

将记录移出Git是分发调整，不是匿名化。原测量/来源记录和日志可能含宿主信息与本地路径，
原字节仍保留在按需附件。阶段二扫描需分别检查保留源码/历史、元数据及附件；清理方案待批准，不能
宣称已经彻底清理。拟公开载荷排除私有模型、几何和教学材料；有范围的权利和来源说明见
[OPEN_SOURCE](OPEN_SOURCE.md)及[NOTICE](../NOTICE.md)。原v0.10.0清单仍只绑定原产物，
保持不变，独立于新的历史及分发证据。
