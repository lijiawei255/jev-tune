# Downloads and reproduction / 分发与复现

[English](#english) · [简体中文](#简体中文)

## English

### Reuse the framework

Download the [v0.10.1 source ZIP](https://github.com/lijiawei255/jev-tune/archive/refs/tags/v0.10.1.zip).
It contains the complete source, tests, bilingual documentation, C99/MATLAB bridges,
formal PID weights and the six small non-PID model/calibration JSON files in their
original locations. It excludes the other experimental records under
`research/results/`; no runtime needs to download those records merely to use the
shell or the shipped models. Existing demo/setup commands remain unchanged.
`scripts/61_check_distribution.py` checks a real `git archive` ZIP, every included
source blob, all retained formal weights, and the data-to-attachment mapping.
The source ZIP has a 5,000,000-byte acceptance budget; the final measured size is
reported in the Release verification evidence.

No files are deleted from Git, no history is rewritten, and no old tag or Release
is changed. `export-ignore` affects source archives, not `git clone`. A plain clone
still downloads research data. A shallow clone alone still checks out the current
large records. For an editable framework checkout without fetching research blobs:

```sh
git clone --filter=blob:none --sparse --branch v0.10.1 https://github.com/lijiawei255/jev-tune.git jev-tune-framework
cd jev-tune-framework
git sparse-checkout set .github assets c docs examples matlab models scripts src tests research/protocols research/distribution
git sparse-checkout add research/results/nonpid_transfer
```

The final `add` also fetches the non-PID raw/report files because cone-mode sparse
checkout selects whole directories; omit it for the smallest clone and use the PID
weights or your own model. The source ZIP is the recommended complete, small
framework download with all formal weights. Partial-clone size depends on Git and
server behavior, and is not the source-ZIP size guarantee. See the official
[clone](https://git-scm.com/docs/git-clone) and
[sparse checkout](https://git-scm.com/docs/git-sparse-checkout) documentation.

### Obtain experimental evidence only when needed

The [committed manifest](../research/distribution/research_data_v0101.json) pins
fixed Release URLs, whole-archive SHA-256/size and every member's relative path,
SHA-256/size. `historical` contains earlier risk trajectories; `current` contains
non-PID raw data and calibration arrays; `evidence` contains the remaining reports,
measurements and provenance. `pid` reuses the unchanged v0.10.0 synthetic-data ZIP.
All three new research bundles preserve the original v0.10.0 Git-blob bytes;
formal non-PID weights also have recoverable copies in `evidence`.

From an extracted source ZIP or matching checkout:

```sh
python scripts/59_research_data.py --fetch all
python scripts/59_research_data.py --check all
# Offline: place the pinned ZIP attachments in a separate directory first.
python scripts/59_research_data.py --fetch all --from-dir downloaded-attachments
```

Replace `all` with `historical`, `current`, `evidence` or `pid` for one group.
The restorer verifies all required selected bundles and every member before
installing any new data. It rejects unsafe paths, links, extra/duplicate/case-colliding entries,
corruption and pre-existing different files. Identical existing files are reused.
Each file is installed atomically; installation failure rolls back every new file
installed by this invocation. Pre-existing files remain. No existing file is overwritten.
Metadata-only LICENSE/NOTICE copies in bundles are checked but never replace the
checkout's current notices. The committed manifest is the integrity trust root;
hashes do not establish the causal history of data collection or provide a signature.

Data restoration uses exact original Git-blob bytes, including line endings.
New attributes disable text conversion for these records. If an older checkout
converted JSON line endings, restoration rejects that different file; use the new
release in a new directory instead of forcing an overwrite. The frozen evidence,
original failure results and scientific tolerances are unchanged.

### Complete verification

Full scientific verification needs the data **and real Git history** for historical
producer sources. Restoring attachments into a source ZIP does not create that
history. Missing evidence fails explicitly; it is never counted as a skipped pass.
Install the documented Python/development dependencies, then use a new directory:

```sh
python scripts/60_reproduce_release.py --destination jev-tune-full-verification --verify
```

This clones the fixed official release with full history, restores any missing
data, runs the complete `tests` suite with coverage and JUnit, and runs the complete
claims check. It reuses the current Python environment; it does not prove a clean
dependency installation. Existing destination/report files are refused. Reports,
logs and actual extra verification costs are retained under the new checkout's
`.local-audit/`. Partial test selection from `PYTEST_*` environment variables is
removed. Every registered claim ID and both newly executed recorded-evidence
receipts are required. A failure remains a failure. This verifies the documented
conditional original-record evidence, not the earlier failed strict cross-CPU
temperature refit or equivalent future physical trajectories.

### Data provenance and privacy boundary

The raw-data review successfully parsed all 330 tracked compressed JSON files,
checking 1,925,949 string values and all field names, and loaded all seven tracked
NPZ files with `allow_pickle=False`: 1,662 numeric/boolean arrays, no object or text
arrays. The scan found no listed email, credential/patient/name field, student-ID,
personal absolute-path or motor-valve benchmark/reference/reference indicators in that raw population.
The generating code uses seeded synthetic plants/signals. This is a bounded scan
and provenance review, not a legal certification or proof that arbitrary numeric
data can never identify a person.

Original measurement/provenance JSON and verification logs can contain the local
username, temporary directories, Python/MATLAB/library paths and host information.
These remain in the optional evidence attachment and retained Git records; they
are not anonymized or runtime path dependencies. The private benchmark,
geometry and teaching documents are not distributed in the current source tree
or new attachments. Historical Git commits remain outside that current-tree claim.
See [OPEN_SOURCE](OPEN_SOURCE.md) and [NOTICE](../NOTICE.md) for rights boundaries.

## 简体中文

### 复用框架

下载[v0.10.1源码ZIP](https://github.com/lijiawei255/jev-tune/archive/refs/tags/v0.10.1.zip)。
它保留完整代码、测试、中英文文档、C99/MATLAB桥、正式PID权重，以及原目录中的六份小型
非PID模型/校准JSON；`research/results/`下其他实验记录从默认源码包排除。使用外壳及正式
模型不需要先下载这些记录，现有演示与安装命令继续适用。
`scripts/61_check_distribution.py`验证真实`git archive` ZIP、每个源码blob、正式权重及
数据到附件的映射。源码ZIP验收预算为5,000,000字节，最终实测大小见Release验证证据。

没有从Git删除文件、重写历史、修改旧tag或旧Release。`export-ignore`只影响源码压缩包，
普通`git clone`仍会下载研究数据；仅加`--depth 1`也仍会检出当前大型记录。需要可编辑的
框架检出且避免获取研究blob时，可以使用：

```sh
git clone --filter=blob:none --sparse --branch v0.10.1 https://github.com/lijiawei255/jev-tune.git jev-tune-framework
cd jev-tune-framework
git sparse-checkout set .github assets c docs examples matlab models scripts src tests research/protocols research/distribution
git sparse-checkout add research/results/nonpid_transfer
```

最后一行因cone模式按整个目录选择，也会获取非PID raw/report；最小克隆可省略该行，使用
PID权重或自己的模型。推荐源码ZIP：其中全部正式权重齐全且包小。部分克隆实际体积依赖
Git与服务器行为，不属于源码ZIP体积保证。参见官方[clone](https://git-scm.com/docs/git-clone)
及[sparse checkout](https://git-scm.com/docs/git-sparse-checkout)说明。

### 按需获取实验记录

[提交的清单](../research/distribution/research_data_v0101.json)固定Release地址、整包SHA-256/
大小，以及每个成员的相对路径、SHA-256和大小。`historical`为早期风险轨迹；`current`为非PID
原始数据和校准数组；`evidence`为其余报告、测量及来源记录；`pid`复用未改动的v0.10.0合成
数据ZIP。三个新研究附件保留原v0.10.0 Git blob字节；`evidence`也含正式非PID权重的恢复副本。

在解压的源码ZIP或对应检出根目录运行：

```sh
python scripts/59_research_data.py --fetch all
python scripts/59_research_data.py --check all
# 离线：先将固定版本的ZIP附件放到独立目录。
python scripts/59_research_data.py --fetch all --from-dir downloaded-attachments
```

`all`可替换为`historical`、`current`、`evidence`或`pid`。本次选中且需要恢复的所有附件在安装前
先验证整包及全部成员；拒绝危险路径、链接、多余/重复/大小写冲突成员、损坏包和现存不同文件，
同内容则复用。每个文件原子安装，安装失败撤回本次调用新建的全部文件，既有文件保留且不覆盖。
附件内仅作元数据的LICENSE/NOTICE会核验但不替换当前声明。完整性信任起点是提交的清单，
哈希不是签名，也不证明数据采集过程的因果真实性。

恢复要求精确原Git blob字节，包括换行。新属性对这些记录关闭文本转换；旧检出若转换了JSON
换行，会被明确拒绝覆盖，应在新目录使用新发布。冻结证据、原失败结论及科学容差均不改变。

### 完整验证

完整科学核验同时需要数据和真实Git历史，用于读取历史生产源码。仅向源码ZIP恢复附件不能
补出历史；缺证据会明确失败，不计为跳过后通过。安装文档所列Python/开发依赖后，指定新目录：

```sh
python scripts/60_reproduce_release.py --destination jev-tune-full-verification --verify
```

脚本完整克隆固定官方版本、恢复缺失数据，执行全部`tests`、覆盖率/JUnit及完整claims检查。
它复用当前Python环境，不证明全新依赖安装；拒绝既有目标目录或报告。日志、报告及实际新增
核验成本保存在新检出的`.local-audit/`。清除`PYTEST_*`选测环境变量，要求全部注册claims ID
及本次新执行的主/补充证据收据；失败如实保留。它核验已有明确边界的条件性原记录证据，
不将早先严格跨CPU温度重拟合失败或未来物理轨迹等价改称通过。

### 数据来源与隐私边界

原始数据审查成功解析全部330份tracked压缩JSON，检查1,925,949个字符串值及全部字段名；
七份tracked NPZ用`allow_pickle=False`实际载入，共1,662个数值/布尔数组，无对象或文本数组。
该原始数据群未命中所列邮箱、凭证/患者/姓名字段、学号、个人绝对路径或其他识别标记；生成链使用固定随机种子的合成对象/信号。这是有范围的扫描及来源审查，
并非法律认证，也不能证明任意数值数据永远无法关联个人。

原测量/来源JSON及验证日志可能含本机用户名、临时目录、Python/MATLAB/运行库路径和宿主
信息，保留在按需证据附件与Git记录中，没有匿名化；这些不是运行路径依赖。当前源码树及
新附件不分发私有基准模型、几何或教学文档，历史Git提交不在这一当前树声明范围内。
权利边界见[OPEN_SOURCE](OPEN_SOURCE.md)及[NOTICE](../NOTICE.md)。
