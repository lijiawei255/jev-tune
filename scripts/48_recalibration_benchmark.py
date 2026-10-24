"""Time peripheral fits from frozen paid-for labels; never execute an objective."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import time

import numpy as np

from jev_tune.calibration import fit_frozen_calibration
from jev_tune.primitives import conformal_prediction_set, softmax

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "research/protocols/shell_recalibration_v0100.json"
PROTOCOL_SHA256 = "fc7c382558de069e7163837ddf8ca58fd7c00a08a1d06ea58966c83d00823573"
RESULT = "research/results/recalibration_benchmark.json"
DOC = "docs/RECALIBRATION.md"
PRIMARY = "research/results/nonpid_transfer"
SEEDS, SIZES, WARMUPS, REPETITIONS = (101, 202, 303), (16, 32, 64), 1, 31
SOURCES = [PROTOCOL, "scripts/48_recalibration_benchmark.py",
           "scripts/45_nonpid_transfer.py", "examples/denoise_transfer/task.py",
           "src/jev_tune/calibration.py", "src/jev_tune/primitives.py"]
TIMING_FIELDS = {"temperature": "temperature_fit_ms", "conformal": "conformal_fit_ms",
                 "total": "total_fit_ms"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    value = Path(path).read_bytes()
    if Path(path).suffix in {".py", ".json", ".md", ".txt", ".yml", ".toml"}:
        value = value.replace(b"\r\n", b"\n")
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def protocol(root=ROOT):
    require(digest(Path(root) / PROTOCOL) == PROTOCOL_SHA256, "frozen recalibration protocol changed")
    value = read(Path(root) / PROTOCOL)
    require(tuple(value["model_seeds"]) == SEEDS
            and tuple(value["samples_per_independent_split"]) == SIZES
            and value["timing"]["warmup_fits"] == WARMUPS
            and value["timing"]["recorded_repetitions"] == REPETITIONS,
            "benchmark constants differ from frozen protocol")
    return value


def verify_hashes(root, hashes):
    root = Path(root).resolve()
    for name, expected in hashes.items():
        path = (root / name).resolve()
        require(path.is_relative_to(root), "input path escapes repository")
        require(digest(path) == expected, "input/source content changed: " + name)


def timing_statistics(samples, *, expected_repetitions=REPETITIONS):
    require(len(samples) == expected_repetitions and expected_repetitions > 0,
            "incomplete timing repetitions")
    for sample in samples:
        require(set(sample) == set(TIMING_FIELDS), "timing fields differ")
        values = np.asarray(list(sample.values()), dtype=float)
        require(np.isfinite(values).all() and (values >= 0).all(), "invalid observed timing")
        require(np.isclose(sample["total"], sample["temperature"] + sample["conformal"],
                           rtol=1e-12, atol=1e-10), "timing stage totals differ")
    result = {}
    for source, target in TIMING_FIELDS.items():
        values = np.asarray([sample[source] for sample in samples])
        result[target] = {"median": float(np.median(values)), "p99": float(np.quantile(values, .99)),
                          "min": float(np.min(values)), "max": float(np.max(values))}
    return result


def diagnostics(logits, labels, fitted):
    probabilities = softmax(logits, temperature=np.asarray(fitted["temperatures"])[None, :, None])
    mask = conformal_prediction_set(probabilities, np.asarray(fitted["qhat_per_axis"]))
    labels = np.asarray(labels)
    require(labels.shape == probabilities.shape[:-1] and np.issubdtype(labels.dtype, np.integer),
            "test diagnostic labels must be integer indices")
    require(((labels >= 0) & (labels < probabilities.shape[-1])).all(), "test diagnostic label out of bounds")
    included = np.take_along_axis(mask, labels[..., None], axis=-1)[..., 0]
    sizes = mask.sum(axis=-1)
    return {"n_states": len(labels), "coverage_per_axis": included.mean(axis=0).tolist(),
            "mean_set_size_per_axis": sizes.mean(axis=0).tolist(),
            "empty_set_rate_per_axis": (sizes == 0).mean(axis=0).tolist(),
            "set_size_histogram_per_axis": np.stack([
                (sizes == k).sum(axis=0) for k in range(probabilities.shape[-1] + 1)], axis=-1).tolist()}


def benchmark_fit(payload, test_logits, test_labels, *, warmups=WARMUPS, repetitions=REPETITIONS):
    """Benchmark precomputed logits only; no model inference or label acquisition."""
    require(warmups >= 0 and repetitions > 0, "invalid benchmark repetition count")
    for _ in range(warmups):
        fit_frozen_calibration(**payload)
    timings, fitted = [], None
    for _ in range(repetitions):
        current = fit_frozen_calibration(**payload)
        timings.append(current.pop("fit_ms"))
        if fitted is not None:
            require(current == fitted, "frozen numerical fit changed across repetitions")
        fitted = current
    return {"calibration": fitted, "warmup_fits": warmups, "recorded_repetitions": repetitions,
            "timing_samples_ms": timings,
            "timing_statistics_ms": timing_statistics(timings, expected_repetitions=repetitions),
            "test_diagnostics": diagnostics(test_logits, test_labels, fitted)}


def _treeclose(left, right, context):
    if isinstance(right, dict):
        require(isinstance(left, dict) and set(left) == set(right), context + ": fields differ")
        for name in right:
            _treeclose(left[name], right[name], context + "." + name)
    elif isinstance(right, list):
        require(isinstance(left, list) and len(left) == len(right), context + ": length differs")
        for index, (actual, expected) in enumerate(zip(left, right)):
            _treeclose(actual, expected, context + f"[{index}]")
    elif isinstance(right, float):
        require(np.isfinite(left) and np.isclose(left, right, rtol=1e-10, atol=1e-12), context + ": value differs")
    else:
        require(type(left) is type(right) and left == right, context + ": value differs")


def verify_row(row, payload, test_logits, test_labels, *, warmups=WARMUPS, repetitions=REPETITIONS):
    """Recompute numerical fits and statistics, preserving observed clock samples."""
    fitted = fit_frozen_calibration(**payload)
    fitted.pop("fit_ms")  # A new check's elapsed time is never substituted for the observations.
    _treeclose(row["calibration"], fitted, "frozen recalibration")
    require(row["warmup_fits"] == warmups and row["recorded_repetitions"] == repetitions,
            "recorded fit schedule differs")
    statistics = timing_statistics(row["timing_samples_ms"], expected_repetitions=repetitions)
    require(row["timing_statistics_ms"] == statistics, "observed timing statistics differ")
    _treeclose(row["test_diagnostics"], diagnostics(test_logits, test_labels, fitted), "test diagnostics")


def _runner(root):
    spec = importlib.util.spec_from_file_location("_recalibration_frozen_runner", root / "scripts/45_nonpid_transfer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.torch.set_num_threads(1)
    module.torch.use_deterministic_algorithms(True)
    return module


def _context(root, primary):
    """Read existing records; no DenoiseTask construction or objective call."""
    root, primary = Path(root).resolve(), Path(primary).resolve()
    require(primary.is_relative_to(root), "primary study must be inside repository")
    report = read(primary / "report.json")
    runner = _runner(root)
    primary_protocol = runner.protocol(root)
    require(report["study_id"] == primary_protocol["study_id"] and report["schema_version"] == 1,
            "primary report identity differs")
    require(set(report["source_hashes"]) == set(runner.SOURCES), "primary source manifest incomplete")
    verify_hashes(root, report["source_hashes"])
    names = {f"{kind}_{seed}.json" for kind in ("model", "calibration") for seed in SEEDS}
    require(set(report["artifacts"]) == names, "six frozen primary artifacts required")
    hashes = {str((primary / name).relative_to(root).as_posix()): digest(primary / name)
              for name in ["report.json", "raw.json.gz", *sorted(names)]}
    require(digest(primary / "raw.json.gz") == report["raw_sha256"], "primary raw evidence changed")
    for name in names:
        require(digest(primary / name) == report["artifacts"][name], "primary artifact changed: " + name)
    with gzip.open(primary / "raw.json.gz", "rt", encoding="utf-8") as stream:
        raw = json.load(stream)
    arrays, identities = {}, {}
    for split in ("temperature", "conformal", "test"):
        objects = raw["teacher"][split]
        setting = primary_protocol["splits"][split]
        require(len(objects) == setting["n"] and [obj["task"] for obj in objects] == list(range(setting["n"])),
                "primary split roster differs: " + split)
        require(all(obj["split_seed"] == setting["seed"] and len(obj["states"]) == 1 for obj in objects),
                "primary initial-state identities differ: " + split)
        arrays[split] = (np.asarray([obj["states"][0]["features"] for obj in objects]),
                         np.asarray([obj["states"][0]["labels"] for obj in objects], dtype=np.int64))
        identities[split] = [f"{obj['split_seed']}:{obj['task']}" for obj in objects]
    models, logits = {}, {}
    for seed in SEEDS:
        artifact = read(primary / f"model_{seed}.json")
        require(artifact["seed"] == seed and artifact["inference_shape"] == [1, 16], "model mapping differs")
        model = runner.load_model(artifact)
        models[seed] = artifact
        logits[seed] = {split: np.stack([runner.infer_logits(model, artifact, features)
                                          for features in arrays[split][0][:limit]])
                        for split, limit in (("temperature", max(SIZES)), ("conformal", max(SIZES)), ("test", 256))}
    return {"runner": runner, "report": report, "arrays": arrays, "identities": identities,
            "models": models, "logits": logits, "input_hashes": hashes}


def _payload(context, seed, n):
    return {"temperature_logits": context["logits"][seed]["temperature"][:n],
            "temperature_labels": context["arrays"]["temperature"][1][:n],
            "conformal_logits": context["logits"][seed]["conformal"][:n],
            "conformal_labels": context["arrays"]["conformal"][1][:n],
            "temperature_ids": context["identities"]["temperature"][:n],
            "conformal_ids": context["identities"]["conformal"][:n],
            "model_sha256": hashlib.sha256(canonical(context["models"][seed])).hexdigest(), "alpha": .1}


def render(report):
    table = ["| model seed | n per split (total label states) | TS median / p99 ms | CP median / p99 ms | total median / p99 ms | test coverage per axis | mean set size per axis |",
             "| ---: | ---: | ---: | ---: | ---: | :--- | :--- |"]
    for row in report["rows"]:
        values = row["timing_statistics_ms"]
        times = [f"{values[field]['median']:.6f} / {values[field]['p99']:.6f}" for field in TIMING_FIELDS.values()]
        diagnostic = row["test_diagnostics"]
        table.append(f"| {row['model_seed']} | {row['n_per_split']} ({row['total_label_states']}) | "
                     + " | ".join(times) + " | "
                     + ", ".join(f"{x:.6f}" for x in diagnostic["coverage_per_axis"]) + " | "
                     + ", ".join(f"{x:.6f}" for x in diagnostic["mean_set_size_per_axis"]) + " |")
    rendered = "\n".join(table)
    return f"""# Frozen peripheral recalibration / 冻结模型的外围重标定

[English](#english) · [简体中文](#简体中文)

## English

This descriptive benchmark fits temperature scaling and independent split CP on fixed logits from three trained non-PID artifacts. Each row uses n independent temperature label states and n independent CP label states, totaling 2n; each state has two teacher-axis labels. One warmup fit precedes 31 recorded fits. The primary study's 128/256 calibration remains unchanged; all nine model/sample-count combinations are reported without selection.

{rendered}

The full timing samples, min/max and generated statistics are in [recalibration_benchmark.json](../research/results/recalibration_benchmark.json). Overall benchmark wall time is {report['overall_wall_seconds']:.6f} s, including loading and canonical single-object forward inference. Table fit times exclude label acquisition, model forward inference, communication and hardware execution. Frozen model-file hashes agree before and after. Additional objective/filter evaluations: {report['additional_objective_evaluations']}; neural gradient steps: {report['gradient_steps']}. Labels were already acquired and charged in the primary study; reusing them adds no new independent evidence.

Test diagnostics use the same independent 256 initial-state signals for every row. They never select n, a model or thresholds and never change primary acceptance or operating actions. CP retains complete sets in monitor mode. Its coverage boundary is per-axis teacher-label marginal inclusion under exchangeability, not joint-axis, conditional, reached-state, closed-loop safety or performance coverage. Unique disjoint IDs do not themselves prove exchangeability. Compact or useful sets with tens of labels are an empirical question.

These CPU fit measurements do not establish millisecond end-to-end adaptation, target-board deadlines, cross-day validity, domain-shift robustness, or clinical/hardware readiness. Label collection, reset feasibility and fresh-domain exchangeability remain caller responsibilities. Complex risk research remains paused.

Run `PYTHONPATH=src python scripts/48_recalibration_benchmark.py --check` to recompute fits, diagnostics, hashes and timing statistics. It preserves observed timing samples, performs no objective/filter calls, and does not demand that a new clock run reproduce old milliseconds. The original timing output cannot be overwritten; a new run requires another `--output` path.

## 简体中文

本描述性基准从三个已训练非PID模型的冻结logits拟合温度缩放与独立分裂CP。每行使用n个温度拟合标注状态和另n个CP标注状态，总计2n；每个状态含两个轴的teacher标签。先预热1次，再记录31次拟合。主实验128/256样本的校准保持原样，九个模型/样本量组合全部报告，不据测试结果选择。

{rendered}

逐次原始计时、最小/最大值及统计均保存在[recalibration_benchmark.json](../research/results/recalibration_benchmark.json)。整个基准墙钟耗时{report['overall_wall_seconds']:.6f}秒，包含加载与固定单对象前向推理；表中拟合耗时不包含标签采集、模型推理、通信或硬件执行。模型文件执行前后哈希一致。额外目标/滤波调用{report['additional_objective_evaluations']}次，神经网络梯度更新{report['gradient_steps']}步。标签采集已经在主实验计账，复用标签不构成新增独立证据。

每行诊断使用同一批独立的256个初态测试信号，不用测试表现选择n、模型或阈值，不更改主实验验收或运行时动作。CP保留完整集合并仅监测；覆盖边界是在交换性前提下逐轴teacher标签的边际包含，不涵盖双轴联合、条件、闭环到达状态、闭环安全或性能。唯一且互斥的ID本身不能证明交换性。几十个标签能否得到紧凑且有用的集合，需要看真实数据。

CPU外围拟合计时不能证明毫秒级端到端适配、目标板截止时间、跨天有效性、域偏移稳健性或临床/硬件可用性。标签采集、可重置条件和新域交换性仍由调用方建立；复杂风险研究继续暂停。

运行`PYTHONPATH=src python scripts/48_recalibration_benchmark.py --check`重算拟合、诊断、哈希与计时统计。检查保留原始时钟观测，额外目标/滤波调用为零，不要求重新计时得到相同毫秒数。拒绝覆盖原始计时输出；新的计时运行必须指定另一个`--output`路径。
"""


def run(root=ROOT, *, output=None, primary=None, document=None):
    root = Path(root).resolve()
    output, primary = Path(output or root / RESULT).resolve(), Path(primary or root / PRIMARY).resolve()
    document = Path(document or root / DOC).resolve()
    require(not output.exists(), "refuse to overwrite original recalibration benchmark")
    p = protocol(root)
    require(not subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, text=True).strip(),
            "commit implementation before timing execution")
    subprocess.run(["git", "ls-files", "--error-unmatch", *SOURCES], cwd=root, check=True, capture_output=True)
    started, wall = datetime.now(timezone.utc).isoformat(), time.perf_counter()
    sources = {name: digest(root / name) for name in SOURCES}
    context = _context(root, primary)
    model_names = [str((primary / f"model_{seed}.json").relative_to(root).as_posix()) for seed in SEEDS]
    before = {name: digest(root / name) for name in model_names}
    rows = []
    for seed in SEEDS:
        for n in SIZES:
            row = benchmark_fit(_payload(context, seed, n), context["logits"][seed]["test"],
                                context["arrays"]["test"][1])
            rows.append({"model_seed": seed, "n_per_split": n, "total_label_states": 2*n, **row})
            print(f"timed frozen model {seed}, independent labels {n}+{n}", flush=True)
    after = {name: digest(root / name) for name in model_names}
    require(before == after, "frozen model files changed during benchmark")
    verify_hashes(root, sources)
    verify_hashes(root, context["input_hashes"])
    report = {"schema_version": 1, "study_id": p["study_id"], "protocol": PROTOCOL,
              "source_hashes": sources, "input_hashes": context["input_hashes"],
              "primary_study_directory": primary.relative_to(root).as_posix(),
              "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
              "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
              "environment": {"python": platform.python_version(), "platform": platform.platform(),
                              "packages": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "torch")}},
              "model_hashes_before": before, "model_hashes_after": after,
              "additional_objective_evaluations": 0, "gradient_steps": 0,
              "selection_performed": False, "primary_calibration_modified": False,
              "test_diagnostics_independent_states": 256,
              "overall_wall_seconds": time.perf_counter()-wall, "rows": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(render(report), encoding="utf-8")
    return report


def check(root=ROOT, *, output=None, document=None, check_document=True):
    root = Path(root).resolve()
    p, report = protocol(root), read(output or root / RESULT)
    require(report["schema_version"] == 1 and report["study_id"] == p["study_id"] and report["protocol"] == PROTOCOL,
            "benchmark report identity differs")
    require(set(report["source_hashes"]) == set(SOURCES), "benchmark source manifest incomplete")
    verify_hashes(root, report["source_hashes"])
    context = _context(root, root / report["primary_study_directory"])
    require(report["input_hashes"] == context["input_hashes"], "benchmark frozen inputs differ")
    before, after = report["model_hashes_before"], report["model_hashes_after"]
    expected = {str((root / report["primary_study_directory"] / f"model_{seed}.json").relative_to(root).as_posix()):
                digest(root / report["primary_study_directory"] / f"model_{seed}.json") for seed in SEEDS}
    require(before == after == expected, "frozen model before/after hashes differ")
    require(report["additional_objective_evaluations"] == report["gradient_steps"] == 0
            and report["selection_performed"] is False and report["primary_calibration_modified"] is False
            and report["test_diagnostics_independent_states"] == 256, "recalibration scope/accounting changed")
    require(np.isfinite(report["overall_wall_seconds"]) and report["overall_wall_seconds"] >= 0,
            "invalid observed overall clock")
    require([(row["model_seed"], row["n_per_split"]) for row in report["rows"]]
            == [(seed, n) for seed in SEEDS for n in SIZES], "fixed descriptive row roster differs")
    for row in report["rows"]:
        seed, n = row["model_seed"], row["n_per_split"]
        require(row["total_label_states"] == 2*n, "independent label-state total differs")
        verify_row(row, _payload(context, seed, n), context["logits"][seed]["test"], context["arrays"]["test"][1])
    if check_document:
        require(Path(document or root / DOC).read_text(encoding="utf-8") == render(report), "generated bilingual recalibration document differs")
    return {"ok": True, "rows": len(report["rows"]), "additional_objective_evaluations": 0,
            "additional_check_numerical_fits": len(report["rows"]), "recorded_timings_preserved": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--primary", type=Path)
    parser.add_argument("--document", type=Path)
    args = parser.parse_args()
    value = run(output=args.output, primary=args.primary, document=args.document) if args.run else check(output=args.output, document=args.document)
    print(json.dumps(value if args.check else {"rows": len(value["rows"]), "overall_wall_seconds": value["overall_wall_seconds"],
                                               "additional_objective_evaluations": 0}, indent=2))
