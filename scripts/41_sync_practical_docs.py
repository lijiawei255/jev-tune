"""Synchronize the practical mainline status and adapter evidence in both languages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

EN = """**Current mainline: real-model adaptation, applicability boundaries and simulation-budget value.**
Deeper joint-risk research is paused. Its failed acceptance, raw trajectories, frozen protocols and reproduction scripts remain available; the risk head stays in research mode and is not enabled in production. Complete CP sets and their existing coverage boundaries remain unchanged.
On the current checkout, use `python scripts/44_verify_historical_research.py --check` to verify the frozen research against an isolated historical source view. Original study commands remain available on v0.8.0; they must not silently substitute today's repaired runtime for their recorded sources.

The practical audit prioritizes controller equivalence, unambiguous measurements, time-based costs, truthful failure status and complete simulation accounting. See [MODEL_ADAPTATION](docs/MODEL_ADAPTATION.md) and [PRACTICAL_BUDGET](docs/PRACTICAL_BUDGET.md). Generated Simulink fixtures validate adapter behavior; they do not establish performance on an unseen external model or physical hardware.

Earlier MATLAB cost figures, traces and animations below are historical: the corrected time-grid integration changes that objective. They are retained as records, not current performance measurements.
Cross-job model/sweep caching is disabled to preserve each source model and configuration; historical warm-job throughput tables do not describe the current implementation.
"""
ZH = """**当前主线：真实模型适配、适用边界与仿真预算收益。**
暂停深化联合风险研究，保留未通过验收的结论、原始轨迹、冻结协议及复现脚本；风险头继续保留研究模式，不进入生产默认路径。完整CP集合及既有覆盖边界保持不变。
当前检出用`python scripts/44_verify_historical_research.py --check`在隔离的历史源码视图中核验冻结研究。原研究命令保留在v0.8.0，不能偷偷用今天修复后的运行时代替原记录源码。

实用审查优先保证控制器转换等价、测量对象明确、代价按真实时间计算、失败状态准确，以及仿真计账完整。见[MODEL_ADAPTATION](docs/MODEL_ADAPTATION.md)和[PRACTICAL_BUDGET](docs/PRACTICAL_BUDGET.md)。生成的Simulink回归模型用于验证适配器行为，不证明未见外部模型或硬件上的调参效果。

下方旧MATLAB代价、轨迹及动画为历史记录：按实际时间网格积分的修正已改变目标，旧记录不代表当前性能测量。
为保留各任务原件及配置语义，跨任务模型与扫描缓存已停用；历史热启动吞吐表不代表当前实现。
"""


def status_section(chinese=False, in_docs=False):
    text = ZH if chinese else EN
    return text.replace("(docs/", "(") if in_docs else text


def replace_section(body, text, lang, anchor):
    start, end = f"<!-- practical-mainline:{lang}:start -->", f"<!-- practical-mainline:{lang}:end -->"
    block = start + "\n" + text.strip() + "\n" + end
    if start in body or end in body:
        assert body.count(start) == body.count(end) == 1, "Missing or duplicated practical section marker"
        assert body.index(start) < body.index(end), "Reversed practical section markers"
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block, body, flags=re.S)
    assert anchor in body, anchor
    return body.replace(anchor, anchor + "\n\n" + block + "\n", 1)


def render(report):
    result = report["test_results"]
    raw = json.dumps(result, ensure_ascii=False, indent=2)
    en = """# Model adaptation audit / 模型适配审查

[English](#english) · [简体中文](#简体中文)

## English

The joint-risk research branch is paused with its evidence intact. This audit fixes errors in the existing Simulink adapter and automation surface. It does not retrain the shipped policy or claim a new safety guarantee.

| Priority | Defect | Implemented contract |
| :--- | :--- | :--- |
| P1 | Ideal PID conversion changed the original controller before measuring its cost | Preserve the Simulink Ideal transfer function when converting to Parallel; verify pre/post conversion responses |
| P1 | A multi-element Scope Dataset silently selected its first signal | Reject ambiguous measurement data instead of evaluating a reference channel as the plant output |
| P1 | Variable-step sampling density changed the reported integral cost | Integrate against actual time and reject invalid time/signal data |
| P1 | An input file could coincide with the scratch model destination | Reject source/destination collisions before modifying files |
| P1 | Multi-loop CLI discarded explicit options; write-back failure could report success | Forward supported configuration, reject unsupported requests, and return failure when the requested output was not written |
| P1 | Partial worker responses could be deleted before successful parsing | Retry incomplete responses and publish queue files atomically |
| P2 | Discovery simulations and padded histories obscured actual cost | Include discovery in total attempts and report actual simulations separately from requested tuning budget |

Simulink Ideal uses `P * (1 + I/s + D*N*s/(s+N))`, so the corresponding Parallel gains are `[P, P*I, P*D]`. These are Simulink mask parameters, not `pidstd` time constants. [MathWorks controller definitions](https://www.mathworks.com/help/simulink/slref/pidcontroller.html).

Ideal conversion is restricted to internal coefficients and internal zero initial conditions, without reset, tracking, anti-windup or output/integrator limits; other configurations return `unsupported_pid_configuration`. For a multi-element Dataset, supply `measure_element` (and, when needed, `input_element`) as an index or unique signal name in `--config`; ambiguous selection defaults to `wide_signal`. A multi-loop request succeeds only when every loop succeeds. Partial results use `ok=false`, `partial_success=true`, `code=partial_failure` and may retain an output copy.

MATLAB integration metrics now use the recorded time grid. Historical MATLAB cost pages, traces and animations predate this correction and retain their historical numbers; they are not current reruns and must not be compared numerically with the corrected objective. Python fixed-grid benchmark metrics and the frozen CP studies are unchanged. This metric change also means old calibration data do not establish label coverage for arbitrary Simulink trajectories.

`iters` is the tuning-loop allowance, not a hard end-to-end simulation cap. Discovery, reference probing, ultimate-gain sweep, original-gain measurement and final verification can add work. `n_total_simulations` reports actual attempted simulations, including failed attempts; ledger components explain the overhead. A reused final observation is not charged as a fresh simulation. An early stop is not evidence of a better controller. Positive scalar step-response tasks are the supported objective; ambiguous channels and unsupported objectives require an explicit adapter rather than a guessed interpretation.

The generated fixtures exercise API behavior on the recorded MATLAB installation. They do not replace acceptance on a user's external plant. Before deployment, validate the selected feedback/output/reference, preserve the original model, compare its own gains using the same objective, and inspect both returned cost and trial failures. Returning the measured best does not bound intermediate trials or prove stability.

Reproduce the real regression with `PYTHONPATH=src python scripts/40_verify_model_adaptation.py`; verify saved evidence without MATLAB with `python scripts/40_verify_model_adaptation.py --check`. The JSON includes the original MATLAB log and source hashes. The following block is generated from `research/results/model_adaptation.json`:

```json
""" + raw + "\n```\n"
    en += "\nFor the separate fixed-budget study, `python scripts/43_verify_practical_budget.py` also checks the complete protocol cohort roster. It permits only original-hash-matching LF/CRLF differences in source/protocol/calibration text, records those paths, and keeps model weights and compressed raw evidence byte-exact. It does not regenerate trajectories or establish cross-platform bitwise simulation replay.\n"
    en += "\nHistorical research verification uses `python scripts/44_verify_historical_research.py --check`. The current baseline and adapter fixes differ from the original research source manifest. The verifier creates a physical temporary copy, restores only the explicitly archived historical files after checking their original hashes, and runs the unchanged study verifiers in an isolated subprocess. Current runtime code, old results and original acceptance remain unchanged; verification does not count as a new experiment or establish the missing coverage premises. Direct original commands require the historical v0.8.0 checkout.\n"
    zh = """
## 简体中文

联合风险研究暂停，已有证据完整保留。本次修复既有Simulink适配器及自动化入口，不重训出厂策略，也不新增安全保证。

| 优先级 | 问题 | 修复后的约定 |
| :--- | :--- | :--- |
| P1 | Ideal PID转换在测量原始代价前改变控制器 | 按Simulink定义等价转换为Parallel，并对比转换前后响应 |
| P1 | 多元素Scope Dataset静默取第一个信号 | 拒绝含糊测量，避免把参考通道当作对象输出 |
| P1 | 可变步长的采样密度影响积分代价 | 根据实际时间积分，拒绝无效时间及信号数据 |
| P1 | 输入原件可能与工作副本目标重合 | 修改文件前拒绝源与目标路径冲突 |
| P1 | 多回路命令忽略显式选项，写回失败仍报成功 | 转发支持的配置，拒绝不支持请求，输出未写成时返回失败 |
| P1 | worker可能删除尚未解析成功的半写入结果 | 等待完整响应，队列文件采用原子发布 |
| P2 | 发现开销和补齐历史掩盖实耗 | 总仿真包含发现阶段，实际次数与请求预算分别报告 |

Simulink Ideal的表达式为`P * (1 + I/s + D*N*s/(s+N))`，对应Parallel增益为`[P, P*I, P*D]`。这里是Simulink掩码参数，不是`pidstd`时间常数。参见[MathWorks控制器定义](https://www.mathworks.com/help/simulink/slref/pidcontroller.html)。

Ideal转换仅限内部系数、内部零初态，且无reset、tracking、anti-windup及输出/积分器限制；其他配置返回`unsupported_pid_configuration`。多元素Dataset可在`--config`内用索引或唯一信号名指定`measure_element`，必要时也指定`input_element`；缺省选择不明确时返回`wide_signal`。多回路请求只有全部成功才成功，部分结果返回`ok=false`、`partial_success=true`和`code=partial_failure`，可能仍保留输出副本。

MATLAB积分指标现按记录的时间网格计算。历史MATLAB结果页、轨迹及动画保留修正前的原数字，不代表当前重跑，不可与修正后的目标直接比较。Python固定网格基准指标与冻结CP研究保持不变；指标变化也意味着旧校准数据不能为任意Simulink轨迹提供标签覆盖证据。

`iters`限制调参循环，不是端到端仿真硬上限。发现、参考探测、临界增益扫描、原增益测量和最终验证会增加开销。`n_total_simulations`记录实际尝试次数，包含失败尝试，分项账本解释额外开销；复用最终观测不算新仿真。提前停止本身不代表控制器更好。支持的目标为正向标量阶跃响应，含糊通道和其他目标需要明确适配，不能猜测含义。

生成模型只验证记录的MATLAB环境中的接口行为，不替代用户实际对象的验收。部署前仍需确认反馈、输出与参考，保留原件，在相同目标下测量原增益，并同时检查返回代价和搜索过程中的失败。返回实测最优不能约束中间试验或证明稳定性。

真实回归入口为`PYTHONPATH=src python scripts/40_verify_model_adaptation.py`；无MATLAB时可用`python scripts/40_verify_model_adaptation.py --check`验证保存的证据。JSON包含原始MATLAB日志及源码哈希。下列记录由`research/results/model_adaptation.json`生成：

```json
""" + raw + "\n```\n"
    zh += "\n独立固定预算研究可用`python scripts/43_verify_practical_budget.py`额外核对协议完整分组。它仅接受源码、协议及校准文本中可匹配原哈希的LF/CRLF差异，列出对应路径；模型权重和压缩原始证据仍逐字节核验。不重生成轨迹，也不建立跨平台仿真逐位重放保证。\n"
    zh += "\n历史研究核验入口为`python scripts/44_verify_historical_research.py --check`。当前基线及适配器修复已不同于原研究源码清单；核验器建立物理临时副本，只有明确归档的历史文件在匹配原哈希后才被恢复，并在隔离子进程中运行原研究检查器。当前运行时代码、旧结果和原验收规则不变；核验不计为新实验，也不补足尚未建立的覆盖前提。直接使用原命令需检出历史v0.8.0版本。\n"
    return en + zh


def updates(root=ROOT):
    root = Path(root)
    output = {}
    for name, zh in (("README.md", False), ("README.zh-CN.md", True)):
        path = root / name
        output[name] = replace_section(path.read_text(encoding="utf-8"), status_section(zh),
                                       "zh" if zh else "en", "# jev-tune")
    for name in ("docs/ARCHITECTURE.md", "docs/TRANSFER.md"):
        body = (root / name).read_text(encoding="utf-8")
        for zh in (False, True):
            body = replace_section(body, status_section(zh, True), "zh" if zh else "en",
                                   "## 简体中文" if zh else "## English")
        output[name] = body
    name = "docs/GENERALIZATION.md"
    body = (root / name).read_text(encoding="utf-8")
    notes = (
        "The v0.9 practical-budget study uses a separate fixed non-oracle start and new parameter instances of these known scenarios; see [PRACTICAL_BUDGET](PRACTICAL_BUDGET.md). It does not replace this frozen oracle-prior table. Scenario jitter multiplies the numerator and one denominator coefficient by `10**U(-0.3,0.3)` and delay by `U(0.8,1.2)`, not merely ±20% gain. Failed and divergent starts remain included.",
        "v0.9实用预算研究使用单独固定的非oracle起点，以及这些已知场景的新参数实例，见[PRACTICAL_BUDGET](PRACTICAL_BUDGET.md)，不替换本页冻结的oracle先验表。场景扰动将分子及一个分母系数分别乘以`10**U(-0.3,0.3)`，延时乘以`U(0.8,1.2)`，并非增益仅±20%。失败及发散起点均保留。",
    )
    for zh in (False, True):
        body = replace_section(body, notes[int(zh)], "zh" if zh else "en", "## 简体中文" if zh else "## English")
    output[name] = body
    report = json.loads((root / "research/results/model_adaptation.json").read_text(encoding="utf-8"))
    output["docs/MODEL_ADAPTATION.md"] = render(report)
    registry = json.loads((root / "docs/claims.json").read_text(encoding="utf-8"))
    definitions = (
        ("adapter_ideal_trajectory_difference", "Ideal/Parallel measured trajectory difference / Ideal与Parallel实测轨迹差", "model_adaptation.json", "test_results.ideal.max_trajectory_difference"),
        ("adapter_auto_simulations", "Automatic discovery plus tuning attempts / 自动发现及调参仿真实耗", "model_adaptation.json", "test_results.auto_ledger.reported_total"),
        ("adapter_all_loops_simulations", "Independent-loop fixture total attempts / 独立多回路模型总仿真实耗", "model_adaptation.json", "test_results.all_loops_ledger.reported_total"),
        ("practical_budget_actual_simulations", "Fixed practical comparison actual simulations / 固定实用对照实际仿真", "practical_budget.json", "summary.actual_simulations"),
    )
    for identifier, label, artifact, path in definitions:
        value = json.loads((root / "research/results" / artifact).read_text(encoding="utf-8"))
        for part in path.split("."):
            value = value[part]
        claim = {"id": identifier, "label": label, "text": label,
                 "source": "research/results/" + artifact, "path": path,
                 "value": float(value), "tol": 1e-12,
                 "reproduce": "python scripts/40_verify_model_adaptation.py" if artifact == "model_adaptation.json" else "python scripts/39_practical_budget.py --run",
                 "documents": [{"file": "docs/CLAIMS.md", "format": ".6f"}]}
        existing = next((row for row in registry["claims"] if row["id"] == identifier), None)
        if existing is None:
            registry["claims"].append(claim)
        else:
            # The common claim renderer normalizes numeric tolerance to 1e-9.
            claim["tol"] = existing.get("tol", claim["tol"])
            existing.clear(); existing.update(claim)
    output["docs/claims.json"] = json.dumps(registry, indent=2, ensure_ascii=False) + "\n"
    return output


def check(root=ROOT):
    return all((Path(root) / name).read_text(encoding="utf-8") == text for name, text in updates(root).items())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        if not check():
            raise SystemExit("Stale practical mainline documentation")
    else:
        for name, text in updates().items():
            (ROOT / name).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
