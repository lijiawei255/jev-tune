"""Inventory the latest public tree; package only pinned synthetic PID data."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = "research/results/open_source_inventory_v0100.json"
DOC = "docs/OPEN_SOURCE.md"
TRAIN = "data/expert_train.npz"


def read(root, name):
    return json.loads((root / name).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def formal_bytes(path):
    data = Path(path).read_bytes()
    return data.replace(b"\r\n", b"\n") if Path(path).suffix == ".json" else data


def formal_paths(root):
    tracked = subprocess.check_output(["git", "ls-files", "models"], cwd=root, text=True).splitlines()
    assert len(tracked) == 7, "Expected seven formal tracked model artifacts"
    nonpid = sorted(p.relative_to(root).as_posix() for pattern in ("model_*.json", "calibration_*.json") for p in (root / "research/results/nonpid_transfer").glob(pattern))
    assert len(nonpid) == 6, "Expected six non-PID model/calibration artifacts"
    return sorted(tracked + nonpid)


def pins(root):
    artifacts = read(root, "models/calibration.json")["artifacts"]
    result = {TRAIN: artifacts["training_data_sha256"]}
    for entry in artifacts["calibration_data_files"].values():
        name = entry["path"].replace("\\", "/")
        assert name in {"data/calibration/temperature_fit.npz", "data/calibration/cp_fit.npz", "data/calibration/empirical_eval.npz"}
        result[name] = entry["sha256"]
    assert len(result) == 4
    return result


def scan(root):
    names = sorted(set(subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard"], cwd=root, text=True).splitlines()))
    for name in names:
        low = name.lower().replace("\\", "/")
        assert Path(low).suffix not in {".slx", ".mdl", ".stl", ".pdf", ".docx"}, "Forbidden private/source artifact: " + name
        assert not any(part in low for part in ("matlab/engine/", "mathworks/engine/", "matlabengine", "extern/engines/python")), "Vendored engine: " + name
    return names


def schema(path):
    with np.load(path, allow_pickle=False) as data:
        return {key: {"shape": list(data[key].shape), "dtype": str(data[key].dtype)} for key in sorted(data.files)}


def validate_data(root, inventory, required=False):
    expected = pins(root)
    assert {row["path"]: row["sha256"] for row in inventory["datasets"]} == expected, "Inventory/calibration pins differ"
    for row in inventory["datasets"]:
        path = root / row["path"]
        if not path.is_file():
            assert not required, "Required release data missing: " + row["path"]
            continue
        assert digest(path) == row["sha256"], "Data hash changed: " + row["path"]
        assert path.stat().st_size == row["size_bytes"] and schema(path) == row["schema"], "Data schema/size changed: " + row["path"]


def build(root=ROOT):
    root = Path(root)
    names = scan(root)
    weights = formal_paths(root)
    datasets = []
    for name, expected in pins(root).items():
        path = root / name
        assert path.is_file(), "Required release data missing: " + name
        assert digest(path) == expected, "Data hash changed: " + name
        datasets.append({"path": name, "sha256": expected, "size_bytes": path.stat().st_size, "schema": schema(path)})
    return {"ok": True, "schema_version": 1, "version": "0.10.0", "scope": "Latest working source tree/new release only; no claim of Git history cleansing",
            "hash_scope": "NPZ/binary weights byte-exact; formal JSON hash and size normalize CRLF to LF for Git checkout portability; no new collection-cost claims",
            "datasets": datasets, "formal_weights": [{"path": name, "sha256": hashlib.sha256(formal_bytes(root / name)).hexdigest(), "size_bytes": len(formal_bytes(root / name))} for name in weights],
            "excluded": ["Ignored value_net and specialized weights without a release provenance binding", "External benchmark models, geometry, private documents and vendored MathWorks engine", "Git history is outside this inventory"],
            "scan_scope": "git ls-files -co --exclude-standard; latest tree, not ignored files or history",
            "limitations": ["Final NPZ hashes do not prove training-process causality or a complete original per-evaluation acquisition log", "Benchmark development feedback influenced zoo design and was not independent external evaluation", "Risk parameters remain embedded in public research JSON"]}


def render(inventory):
    rows = "\n".join(f"| `{r['path']}` | {r['size_bytes']} | `{r['sha256']}` |" for r in inventory["datasets"])
    table = "| Data / 数据 | Bytes / 字节 | SHA-256 |\n| :--- | ---: | :--- |\n" + rows
    download = "https://github.com/lijiawei255/jev-tune/releases/download/v0.10.0/pid_synthetic_data_v0.10.0.zip"
    mapping = "| Component / 内容 | Distribution / 分发 |\n| :--- | :--- |\n| Formal PID model artifacts and non-PID models | Git: seven models files plus six non-PID JSON artifacts |\n| Generated demo model | `matlab/make_demo_model.m`; generate locally, no private SLX included |\n| Complete implementation and tests | `src/`, `matlab/`, `scripts/`, `tests/` |\n| Research records and earlier versions | Pinned Release data bundles; [latest-data manifest](../research/distribution/research_data_v0101.json) and [historical-data index](../research/distribution/historical_data_v0101.json) |\n| Selected producer sources | [Historical source capsule](../research/distribution/historical_sources_v0101.json); source/tree objects, not complete old history |\n" + f"| Pinned synthetic PID data | Release-only [pid_synthetic_data_v0.10.0.zip]({download}); four relative NPZ paths |"
    mapping_zh = "| 内容 | 分发方式 |\n| :--- | :--- |\n| 正式PID模型产物与非PID模型 | Git内7份正式模型产物（含元数据和校准）及6份非PID模型/校准JSON |\n| 生成的演示模型 | 本地运行matlab/make_demo_model.m，不附私有SLX |\n| 完整实现与测试 | src/、matlab/、scripts/、tests/ |\n| 研究记录及更早版本 | 固定Release数据附件；[最新数据清单](../research/distribution/research_data_v0101.json)与[历史数据索引](../research/distribution/historical_data_v0101.json) |\n| 选定生产源码 | [历史源码胶囊](../research/distribution/historical_sources_v0101.json)，提供源码/tree对象，不等于完整旧历史 |\n" + f"| 已固定hash的合成PID数据 | Release附件[pid_synthetic_data_v0.10.0.zip]({download})，含4份保持相对路径的NPZ |"
    extraction = """```sh
python -m zipfile -e pid_synthetic_data_v0.10.0.zip .
python scripts/50_open_source_inventory.py --check
```"""
    discovery = """```matlab
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
```"""
    return (
        "# Open-source inventory / 开源清单\n\n[English](#english) · [简体中文](#简体中文)\n\n## English\n\n"
        "The v0.10.0 artifact inventory records the model and data bindings; current distribution manifests identify sanitized metadata derivatives. "
        "A normal clone includes the formal trained weights, complete implementation and tests. "
        "The ignored synthetic PID datasets are distributed separately; the data ZIP includes LICENSE, NOTICE.md and the machine inventory. "
        "Without these NPZ files, --check still validates pins and any locally present files. Packaging requires all four exact files.\n\n"
        "The v0.10.1 distribution keeps complete source and formal weights, including the six non-PID JSON artifacts, in Git and source ZIPs. "
        "An ordinary clone needs no sparse/partial flags; experimental records and earlier data versions are restored from pinned Release attachments. "
        "Public manifests bind the distributed bytes and distinguish unchanged original scientific objects from sanitized metadata derivatives. "
        "The [history mapping](../research/distribution/history_rewrite_v0101.json) describes the history transition; "
        "original commit identities and signatures are not a blanket guarantee. Publication and reproduction acceptance require the actual pinned "
        "assets and verification receipts described in [DISTRIBUTION](DISTRIBUTION.md).\n\n"
        "Runtime reuse needs no research-data download. Before pytest or claims, run `python scripts/59_research_data.py --fetch all`, then "
        "`python scripts/history_sources.py --root . --restore-pinned`; both support `--from-dir` for offline pinned assets. "
        "The source capsule imports selected original scientific source/tree objects without changing refs, not the complete old history. "
        "Old script-42 maintenance commands are not promised to work directly; current script-44/16 frozen verification uses the required restored evidence. "
        "Use script 60 for a new verification checkout. See [distribution, reproduction and privacy boundaries](DISTRIBUTION.md).\n\n"
        + mapping + "\n\n" + table + "\n\n"
        "### Obtain the synthetic PID data\n\n"
        f"Download [pid_synthetic_data_v0.10.0.zip]({download}). From the repository root, "
        "extract it there, preserving the archived `data/...` paths; do not flatten the archive into one directory.\n\n"
        + extraction + "\n\n"
        "Final NPZ hashes establish final-file identity, not causal proof of the training process or a complete original per-evaluation acquisition log. "
        "Benchmark development feedback influenced zoo design and is not independent external evaluation. No new acquisition-cost numbers are inferred. "
        "Risk parameters remain in public research JSON. Ignored value_net/specialized weights without provenance bindings are excluded; "
        "private models/geometry/private documents and vendored MathWorks engines are prohibited in the latest source tree.\n\n"
        "### Regenerate the public discovery animation\n\n"
        "The current `assets/discover.gif` is a graph of the project's generated gains demo. "
        "Run the MATLAB block from the repository root to build that model and obtain fresh graph/discovery JSON, "
        "then run the Python renderer from the same root. This executes discovery probes and records their actual evidence. "
        "It uses project source and standard MATLAB/Simulink blocks under the user's MathWorks licence; "
        "reproduction uses the generated model and requires no external benchmark files.\n\n"
        + discovery + "\n\n"
        "The historical response figures (`tuning.gif`, `before_after.png`, `convergence.png`) are the project's own plots "
        "of earlier motor-valve benchmark measurements; they use a different model from the current discovery animation. "
        "Their historical objective and timing caveats still apply; regenerating an image does not rerun or validate that experiment.\n\n"
        "## 简体中文\n\n"
        "v0.10.0产物清单记录模型和数据绑定，当前分发清单标明脱敏元数据派生件。普通clone包含正式训练权重、完整实现与测试；"
        "被忽略的合成PID数据通过独立附件提供，ZIP内含LICENSE、NOTICE.md与机器清单。缺少NPZ时仍可运行--check，"
        "核对校准pin，存在本地文件则额外校验；打包必须四文件全部逐字节匹配。\n\n"
        "v0.10.1分发在Git和源码ZIP中保留完整源码及正式权重（含六份非PID模型/校准JSON）。普通克隆无需稀疏/部分克隆参数，"
        "实验记录及更早数据版本按需从固定Release附件恢复。公开清单绑定分发字节，区分未改动的原始科学对象与脱敏元数据派生件。"
        "[历史映射](../research/distribution/history_rewrite_v0101.json)说明历史切换，不笼统承诺保留原提交身份或签名。"
        "发布与复现验收以[DISTRIBUTION](DISTRIBUTION.md)所述的真实固定附件和核验收据为准。\n\n"
        "运行复用无需研究数据。pytest或claims前先运行`python scripts/59_research_data.py --fetch all`，再运行"
        "`python scripts/history_sources.py --root . --restore-pinned`；两者均支持`--from-dir`离线固定附件。源码胶囊导入选定原始科学源码/tree对象，"
        "不改变refs，也不等于完整旧历史；旧42维护命令不保证直接可用，当前44/16冻结核验使用恢复后的所需证据。"
        "新目录完整核验使用60脚本，详见[分发、复现与隐私边界](DISTRIBUTION.md)。\n\n"
        + mapping_zh + "\n\n" + table + "\n\n"
        "### 获取合成PID数据\n\n"
        f"下载[pid_synthetic_data_v0.10.0.zip]({download})后，在源码仓库根目录执行解压，"
        "保留附件中的`data/...`相对目录，不要将所有文件平铺到同一目录。\n\n"
        + extraction + "\n\n"
        "NPZ最终hash只证明文件身份，不证明训练过程因果关系或完整原始逐次采集日志。基准模型开发反馈影响了zoo设计，"
        "不属于独立外部测试；不推断新的采集成本。风险参数保留在公开研究JSON中。缺来源绑定的ignored value_net/specialized"
        "权重不发布；当前源码树禁止私有模型、几何、私有文档与第三方MathWorks engine源码。\n\n"
        "### 再生成公开发现动画\n\n"
        "当前`assets/discover.gif`展示本项目自主生成的gains演示模型图。"
        "从仓库根目录在MATLAB执行下面代码生成模型及新的graph/discovery JSON，再从同一根目录运行Python绘图脚本。"
        "这一过程会执行发现探测并记录真实证据；只使用项目源码及用户MathWorks许可证下的标准MATLAB/Simulink模块，"
        "复现使用生成模型，无需外部基准模型文件。\n\n"
        + discovery + "\n\n"
        "历史响应图（`tuning.gif`、`before_after.png`、`convergence.png`）是本项目对早期电机阀门验证床测量结果的自主绘图，"
        "它与当前发现动画使用不同模型。其历史目标函数与计时范围限制继续有效；重新生成图片不等于重跑或验收旧实验。\n"
    )


def check(root=ROOT):
    root = Path(root)
    scan(root)
    inventory = read(root, INVENTORY)
    assert inventory.get("ok") is True and inventory["version"] == "0.10.0"
    validate_data(root, inventory)
    assert [r["path"] for r in inventory["formal_weights"]] == formal_paths(root), "Formal artifact set changed"
    for row in inventory["formal_weights"]:
        path = root / row["path"]
        assert path.is_file() and hashlib.sha256(formal_bytes(path)).hexdigest() == row["sha256"] and len(formal_bytes(path)) == row["size_bytes"], "Formal artifact changed: " + row["path"]
    assert (root / DOC).read_text(encoding="utf-8") == render(inventory), "Stale open-source documentation"
    return inventory


def package(out, root=ROOT):
    root = Path(root)
    inventory = check(root)
    validate_data(root, inventory, required=True)
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    target = out / "pid_synthetic_data_v0.10.0.zip"
    paths = [r["path"] for r in inventory["datasets"]] + ["LICENSE", "NOTICE.md", INVENTORY]
    assert all((root / p).is_file() for p in paths), "LICENSE/NOTICE.md/inventory missing"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in paths:
            bundle.write(root / name, name)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument("--write", action="store_true")
    flags.add_argument("--check", action="store_true")
    flags.add_argument("--package", type=Path, metavar="OUTPUT_DIR")
    args = parser.parse_args()
    if args.write:
        inventory = build()
        (ROOT / INVENTORY).write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (ROOT / DOC).write_text(render(inventory), encoding="utf-8")
    elif args.check:
        check()
    else:
        package(args.package)
    print(json.dumps({"ok": True, "scope": "latest tree only"}))

if __name__ == "__main__":
    main()
