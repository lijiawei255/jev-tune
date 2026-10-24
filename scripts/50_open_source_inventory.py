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
            "excluded": ["Ignored value_net and specialized weights without a release provenance binding", "Private benchmarks, geometry, lecture documents and vendored MathWorks engine", "Git history is outside this inventory"],
            "scan_scope": "git ls-files -co --exclude-standard; latest tree, not ignored files or history",
            "limitations": ["Final NPZ hashes do not prove training-process causality or a complete original per-evaluation acquisition log", "benchmark development feedback influenced zoo design and was not independent external evaluation", "Risk parameters remain embedded in public research JSON"]}


def render(inventory):
    rows = "\n".join(f"| `{r['path']}` | {r['size_bytes']} | `{r['sha256']}` |" for r in inventory["datasets"])
    table = "| Data / 数据 | Bytes / 字节 | SHA-256 |\n| :--- | ---: | :--- |\n" + rows
    download = "https://github.com/lijiawei255/jev-tune/releases/download/v0.10.0/pid_synthetic_data_v0.10.0.zip"
    mapping = "| Component / 内容 | Distribution / 分发 |\n| :--- | :--- |\n| Formal PID model artifacts and non-PID models | Git: seven models files plus six non-PID JSON artifacts |\n| Generated demo model | `matlab/make_demo_model.m`; generate locally, no private SLX included |\n| Complete implementation and tests | `src/`, `matlab/`, `scripts/`, `tests/` |\n| Original public research trajectories | `research/results/`; prior release assets remain versioned |\n" + f"| Pinned synthetic PID data | Release-only [pid_synthetic_data_v0.10.0.zip]({download}); four relative NPZ paths |"
    mapping_zh = "| 内容 | 分发方式 |\n| :--- | :--- |\n| 正式PID模型产物与非PID模型 | Git内7份正式模型产物（含元数据和校准）及6份非PID模型/校准JSON |\n| 生成的演示模型 | 本地运行matlab/make_demo_model.m，不附私有SLX |\n| 完整实现与测试 | src/、matlab/、scripts/、tests/ |\n| 已公开研究原始轨迹 | research/results/及保留版本的历史release附件 |\n" + f"| 已固定hash的合成PID数据 | Release附件[pid_synthetic_data_v0.10.0.zip]({download})，含4份保持相对路径的NPZ |"
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
        "This inventories the latest source tree and v0.10.0 release, not Git history cleansing. "
        "A normal clone includes the formal trained weights, complete implementation and tests. "
        "The ignored synthetic PID datasets are distributed separately; the data ZIP includes LICENSE, NOTICE.md and the machine inventory. "
        "Without these NPZ files, --check still validates pins and any locally present files. Packaging requires all four exact files.\n\n"
        "Starting with v0.10.1, source ZIPs retain the complete implementation and all formal weights, including the six non-PID JSON artifacts, "
        "but omit the other experimental records. Those records are pinned Release attachments with automatic SHA-256 restoration; "
        "ordinary Git clones still contain them. This v0.10.0 inventory remains the original artifact binding. "
        "See [downloads, full reproduction and privacy boundaries](DISTRIBUTION.md). The source ZIP alone cannot run the complete scientific audit: "
        "restore evidence and obtain real historical Git objects with scripts/60_reproduce_release.py.\n\n"
        + mapping + "\n\n" + table + "\n\n"
        "### Obtain the synthetic PID data\n\n"
        f"Download [pid_synthetic_data_v0.10.0.zip]({download}). From the matching v0.10.0 repository root, "
        "extract it there, preserving the archived `data/...` paths; do not flatten the archive into one directory.\n\n"
        + extraction + "\n\n"
        "Final NPZ hashes establish final-file identity, not causal proof of the training process or a complete original per-evaluation acquisition log. "
        "benchmark development feedback influenced zoo design and is not independent external evaluation. No new acquisition-cost numbers are inferred. "
        "Risk parameters remain in public research JSON. Ignored value_net/specialized weights without provenance bindings are excluded; "
        "private models/geometry/lecture documents and vendored MathWorks engines are prohibited in the latest source tree.\n\n"
        "### Regenerate the public discovery animation\n\n"
        "The current `assets/discover.gif` is a graph of the project's generated gains demo, not a redraw of a benchmark. "
        "Run the MATLAB block from the repository root to build that model and obtain fresh graph/discovery JSON, "
        "then run the Python renderer from the same root. This executes discovery probes and records their actual evidence. "
        "It uses project source and standard MATLAB/Simulink blocks under the user's MathWorks licence; "
        "no benchmark, geometry or handout is required or redistributed.\n\n"
        + discovery + "\n\n"
        "The historical response figures (`tuning.gif`, `before_after.png`, `convergence.png`) are the project's own plots "
        "of earlier benchmark measurements, not original benchmark artwork or the current discovery model. "
        "Their historical objective and timing caveats still apply; regenerating an image does not rerun or validate that experiment.\n\n"
        "## 简体中文\n\n"
        "清单范围为当前源码树与v0.10.0发布，不声称清理Git历史。普通clone已包含正式训练权重、完整实现与测试；"
        "被忽略的合成PID数据通过独立附件提供，ZIP内含LICENSE、NOTICE.md与机器清单。缺少NPZ时仍可运行--check，"
        "核对校准pin，存在本地文件则额外校验；打包必须四文件全部逐字节匹配。\n\n"
        "从v0.10.1起，源码ZIP保留完整实现及全部正式权重（含六份非PID模型/校准JSON），其他实验记录通过固定哈希的Release附件"
        "按需恢复；普通Git克隆仍含原记录。本v0.10.0清单继续绑定原产物，不改旧证据。详见[分发、完整复现与隐私边界](DISTRIBUTION.md)。"
        "仅源码ZIP不能执行完整科学审计，须恢复证据并通过scripts/60_reproduce_release.py获取真实历史Git对象。\n\n"
        + mapping_zh + "\n\n" + table + "\n\n"
        "### 获取合成PID数据\n\n"
        f"下载[pid_synthetic_data_v0.10.0.zip]({download})后，在对应v0.10.0源码仓库根目录执行解压，"
        "保留附件中的`data/...`相对目录，不要将所有文件平铺到同一目录。\n\n"
        + extraction + "\n\n"
        "NPZ最终hash只证明文件身份，不证明训练过程因果关系或完整原始逐次采集日志。基准开发反馈影响了zoo设计，"
        "不属于独立外部测试；不推断新的采集成本。风险参数保留在公开研究JSON中。缺来源绑定的ignored value_net/specialized"
        "权重不发布；当前源码树禁止私有模型、几何、讲义文档与第三方MathWorks engine源码。\n\n"
        "### 再生成公开发现动画\n\n"
        "当前`assets/discover.gif`展示本项目自主生成的gains演示模型图，不是基准模型结构的重绘。"
        "从仓库根目录在MATLAB执行下面代码生成模型及新的graph/discovery JSON，再从同一根目录运行Python绘图脚本。"
        "这一过程会执行发现探测并记录真实证据；只使用项目源码及用户MathWorks许可证下的标准MATLAB/Simulink模块，"
        "不需要或分发基准原模型、几何或讲义。\n\n"
        + discovery + "\n\n"
        "历史响应图（`tuning.gif`、`before_after.png`、`convergence.png`）是本项目对早期基准验证床测量结果的自主绘图，"
        "并非基准原图，也不是当前发现动画所用模型。其历史目标函数与计时范围限制继续有效；重新生成图片不等于重跑或验收旧实验。\n"
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
