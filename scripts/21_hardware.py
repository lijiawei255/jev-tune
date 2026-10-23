"""E6: hard numbers for the edge / real-time claim.

These are host measurements, operation counts and compiler stack estimates:

* parameters, split by what actually runs (the ONNX export does not contain the
  unused value head);
* multiply-accumulates per decision, counted from the layer shapes;
* p50/p95/p99 latency from `research/results/latency.json` (scripts/04);
* static footprint of the C99 reference (`size` on the object file, so weights in
  `.rodata` are included; no linker garbage collection);
* decision agreement between float32 and weight-only int8.

It does **not** report cycles on any MCU. Nothing here has run on a board.
"""

from __future__ import annotations

import argparse
import json
import hashlib
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import torch

from jev_tune.decision import read_conformal
from jev_tune.decode import ActionSpace, decide
from jev_tune.model import JevHead, ValueNet
from jev_tune.primitives import Answer, Choice, Noul, Option, Score, softmax

ROOT = Path(__file__).resolve().parents[1]


def count_macs(model: JevHead) -> dict:
    """Count multiply-accumulates for one forward pass, layer by layer."""
    # conv1: 2 -> 16, k=5, stride 2 on 64 samples -> 32 outputs
    conv1 = 16 * 32 * (2 * 5)
    conv2 = 32 * 16 * (16 * 5)
    mlp1 = 64 * 20
    mlp2 = 64 * 64
    trunk1 = 128 * (32 + 64)
    trunk2 = 128 * 128
    choice = sum(layer.in_features * layer.out_features for layer in model.choice)
    score = 5 * 128
    noul = 128
    parts = {
        "conv1": conv1,
        "conv2": conv2,
        "mlp1": mlp1,
        "mlp2": mlp2,
        "trunk1": trunk1,
        "trunk2": trunk2,
        "choice_heads": choice,
        "score_head": score,
        "noul_head": noul,
    }
    parts["total"] = sum(parts.values())
    return parts


def param_counts(models: Path) -> dict:
    meta = json.loads((models / "meta.json").read_text(encoding="utf-8-sig"))
    head = JevHead(n_actions=meta.get("n_actions", 7))
    sd = torch.load(models / "jev_head.pt", map_location="cpu")
    head.load_state_dict(sd)
    # the exported graph contains the encoder + the three choice heads + score +
    # noul, not the unused `value` sub-module
    exported = sum(v.numel() for k, v in sd.items() if not k.startswith("value."))
    builtin_value = sum(v.numel() for k, v in sd.items() if k.startswith("value."))
    value_net = 0
    vp = models / "value_net.pt"
    if vp.is_file():
        value_net = sum(v.numel() for v in torch.load(vp, map_location="cpu").values())
    return {
        "decision_path": int(exported),
        "builtin_value_head": int(builtin_value),
        "separate_value_net": int(value_net),
        "total_if_everything_loaded": int(exported + builtin_value + value_net),
    }


def c_footprint() -> dict:
    gcc = shutil.which("gcc")
    size = shutil.which("size")
    if gcc is None or size is None:
        return {"status": "unavailable", "error": "gcc or size not found"}
    src = ROOT / "c" / "jev_head.c"
    with tempfile.TemporaryDirectory() as tmp:
        obj = Path(tmp) / "jev_head.o"
        proc = subprocess.run(
            [gcc, "-std=c99", "-Os", "-fstack-usage", "-c", str(src), "-o", str(obj)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return {"status": "unavailable", "error": proc.stderr[-500:]}
        s = subprocess.run([size, "-A", str(obj)], capture_output=True, text=True)
        sections = parse_size_sections(s.stdout)
        if s.returncode or not sections:
            return {"status": "unavailable", "error": "size -A failed or had no sections",
                    "object_bytes": obj.stat().st_size}
        out = {"status": "ok", "object_bytes": obj.stat().st_size, **sections,
               "compiler": subprocess.check_output([gcc, "--version"], text=True).splitlines()[0],
               "target": subprocess.check_output([gcc, "-dumpmachine"], text=True).strip(),
               "flags": ["-std=c99", "-Os", "-fstack-usage"],
               "size_raw": s.stdout.replace(str(obj), "jev_head.o")}
        stack = {}
        for su in Path(tmp).glob("*.su"):
            for line in su.read_text().splitlines():
                match = re.match(r".*:\d+:\d+:(\S+)\s+(\d+)\s+(.*)", line)
                if match:
                    stack[match[1]] = {"bytes": int(match[2]), "kind": match[3]}
        out["stack_frames"] = stack
        out["forward_stack_frame_bytes"] = stack.get("jev_forward", {}).get("bytes")
        out["stack_note"] = "per-function compiler estimate; excludes caller buffers, nested frames, libm and runtime; not peak stack"
        out["object_scope"] = "core jev_head.o only; excludes caller-supplied temperature/CP configuration and linked libc/libm/runtime"
        # a linked image is the number a firmware engineer budgets, but it also
        # contains the runtime start-up; report the object, and say so
        return out


def parse_size_sections(output: str) -> dict:
    """Read GNU size -A section rows, both ELF and COFF, excluding totals."""
    result = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0].startswith(".") and fields[1].isdigit():
            result[fields[0]] = int(fields[1])
    return result


def _answer_from_logits(logits, temperature):
    space = ActionSpace()
    probs = np.stack(
        [softmax(logits["choice"][:, i].numpy() / temperature[i]) for i in range(3)]
    )
    return Answer(
        choice=[
            Choice(
                f"step:{a}",
                [Option(f"x{m:g}", float(np.log10(m))) for m in space.multipliers],
                probs[i],
            )
            for i, a in enumerate(("Kp", "Ki", "Kd"))
        ],
        score=Score("quality", list("abcde"), softmax(logits["score"].numpy())),
        noul=Noul("healthy", 1.0 / (1.0 + np.exp(-logits["noul"].numpy()))),
    )


def int8_agreement(models: Path, cases: int = 256) -> dict:
    """Weight-only int8, per-tensor and per-output-channel; activations float32."""
    torch.manual_seed(0)
    meta = json.loads((models / "meta.json").read_text(encoding="utf-8-sig"))
    temp = json.loads((models / "calibration.json").read_text(encoding="utf-8-sig"))[
        "choice_temperature"
    ]

    def load():
        m = JevHead(n_actions=meta.get("n_actions", 7))
        m.load_state_dict(torch.load(models / "jev_head.pt", map_location="cpu"))
        m.eval()
        return m

    base = load()
    z = np.load(ROOT / "data" / "expert_train.npz")
    idx = np.linspace(0, len(z["feats"]) - 1, cases).round().astype(int)
    f = torch.as_tensor(np.asarray(z["feats"][idx], dtype=np.float32))
    c = torch.as_tensor(np.asarray(z["curves"][idx], dtype=np.float32))
    space = ActionSpace()

    with torch.no_grad():
        a = base(f, c)
    ans_a = _answer_from_logits(a, temp)
    conformal = read_conformal(models)
    dec_a = decide(ans_a, space, conformal=conformal)
    sets_a = np.stack(dec_a.conformal_set, axis=-2)
    probs_a = np.stack([ch.probs for ch in ans_a.choice], axis=-2)

    out = {"cases": int(cases), "activations": "float32",
           "conformal_policy": None if conformal is None else {
               "qhat_per_axis": list(conformal.q_hat), "alpha": conformal.alpha, "k_max": conformal.k_max, "mode": conformal.mode},
           "float32_mean_set_size_per_axis": dec_a.set_size.mean(axis=0).tolist()}
    for mode in ("per_tensor", "per_channel"):
        q = load()
        with torch.no_grad():
            for p in q.parameters():
                if p.dim() < 2:
                    continue
                if mode == "per_tensor":
                    scale = p.abs().max().item() / 127.0
                else:
                    scale = (
                        p.reshape(p.shape[0], -1).abs().amax(dim=1, keepdim=True)
                        / 127.0
                    ).reshape(-1, *([1] * (p.dim() - 1)))
                scale_t = torch.as_tensor(scale, dtype=p.dtype)
                scale_t = torch.clamp(scale_t, min=1e-12)
                p.copy_(torch.round(p / scale_t).clamp(-127, 127) * scale_t)
            b = q(f, c)
        ans_b = _answer_from_logits(b, temp)
        dec_b = decide(ans_b, space, conformal=conformal)
        sets_b = np.stack(dec_b.conformal_set, axis=-2)
        set_changed = (sets_a != sets_b).any(axis=-1)
        probs_b = np.stack([ch.probs for ch in ans_b.choice], axis=-2)
        step_diff = np.abs(dec_a.step - dec_b.step)
        same_argmax = probs_a.argmax(-1) == probs_b.argmax(-1)
        held_diff = dec_a.held != dec_b.held
        would_hold_diff = dec_a.conformal_would_hold != dec_b.conformal_would_hold
        out[mode] = {
            "argmax_agreement": float(
                same_argmax.mean()
            ),
            "argmax_joint_agreement": float(same_argmax.all(axis=-1).mean()),
            "argmax_axis_disagreements": int((~same_argmax).sum()),
            "held_axis_disagreements": int(held_diff.sum()),
            "held_state_disagreements": int(held_diff.any(axis=-1).sum()),
            "held_pattern_same": bool(np.array_equal(dec_a.held, dec_b.held)),
            "conformal_would_hold_axis_disagreements": int(would_hold_diff.sum()),
            "conformal_would_hold_state_disagreements": int(would_hold_diff.any(axis=-1).sum()),
            "conformal_set_axis_disagreements": int(set_changed.sum()),
            "conformal_set_state_disagreements": int(set_changed.any(axis=-1).sum()),
            "conformal_set_joint_agreement": float((~set_changed.any(axis=-1)).mean()),
            "mean_set_size_per_axis": dec_b.set_size.mean(axis=0).tolist(),
            "escalation_axis_disagreements": int((dec_a.escalate != dec_b.escalate).sum()),
            "reason_axis_disagreements": int((dec_a.reason != dec_b.reason).sum()),
            "step_max_abs_diff": float(step_diff.max()),
            "step_mean_abs_diff": float(step_diff.mean()),
            "steps_within_1e-3": float((step_diff <= 1e-3).mean()),
            "steps_within_1e-2": float((step_diff <= 1e-2).mean()),
            "joint_steps_within_1e-3": float((step_diff <= 1e-3).all(axis=-1).mean()),
        }
    out["quantisation"] = "weight-only int8, symmetric, activations float32"
    out["implementation"] = "weights rounded then dequantized; float32 kernels, no int8 runtime"
    out["agreement_unit"] = "argmax_agreement and steps_within_* are per-axis; joint_* require every axis"
    out["source"] = "data/expert_train.npz; 256 evenly spaced training states, not held-out rollout performance"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="models")
    ap.add_argument("--latency", default="research/results/latency.json")
    ap.add_argument("--out", default="research/results/hardware.json")
    ap.add_argument("--doc", default="docs/COMPUTE.md")
    args = ap.parse_args()
    torch.set_num_threads(1)

    models = Path(args.models)
    lat = json.loads((ROOT / args.latency).read_text(encoding="utf-8-sig"))
    counts = param_counts(models)
    macs = count_macs(
        JevHead(
            n_actions=json.loads(
                (models / "meta.json").read_text(encoding="utf-8-sig")
            ).get("n_actions", 7)
        )
    )
    csize = c_footprint()
    int8 = int8_agreement(models)
    from _experiment_protocol import manifest

    payload = {
        "manifest": manifest(args, files=[models / "jev_head.pt", models / "calibration.json",
                                          ROOT / args.latency, ROOT / "c/jev_head.c", ROOT / "c/jev_head.h"],
                             extra={"quantization_seed": 0, "quantization_cases": 256}),
        "latency_source": args.latency,
        "onnx_forward_ms": lat["onnx_forward_ms"],
        "onnx_forward_p95_ms": lat["onnx_forward_p95_ms"],
        "onnx_forward_p99_ms": lat.get("onnx_forward_p99_ms"),
        "typed_decision_ms": lat["typed_decision_ms"],
        "typed_decision_p95_ms": lat["typed_decision_p95_ms"],
        "typed_decision_p99_ms": lat.get("typed_decision_p99_ms"),
        "params": counts,
        "macs": macs,
        "c_footprint": csize,
        "c_flash_bytes": _flash_bytes(csize),
        "c_ram_bytes": _ram_bytes(csize),
        "mac_flops_convention": "2 * dense nominal MACs; excludes nonlinear functions, softmax, decode and features",
        "multiply_add_flops": 2 * macs["total"],
        "int8": int8,
        "onnx_file_bytes": lat.get("onnx_file_bytes"),
        "environment": {"platform": platform.platform(), "processor": platform.processor(),
                        "python": platform.python_version(), "torch": torch.__version__},
        "model_sha256": hashlib.sha256((models / "jev_head.pt").read_bytes()).hexdigest(),
        "note": (
            "one CPU thread, batch 1, host CPU. No cycle counts: nothing here "
            "has been run on an MCU."
        ),
    }
    Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    Path(args.doc).write_text(_doc(payload), encoding="utf-8")
    print(
        json.dumps(
            {k: payload[k] for k in ("onnx_forward_ms", "typed_decision_ms")}, indent=2
        )
    )
    print(f"params {counts['decision_path']}, MACs {macs['total']}, int8 {int8}")
    print(f"wrote {args.out} and {args.doc}")


def _fmt_bytes(n):
    if n is None:
        return "—"
    if n < 1024:
        return f"{n} B"
    return f"{n / 1024:.1f} KB"


def _flash_bytes(c: dict):
    if c.get("status") == "unavailable" or "error" in c:
        return None
    prefixes = (".text", ".rodata", ".rdata", ".xdata", ".pdata", ".eh_frame", ".gcc_except_table")
    sections = [v for k, v in c.items() if k.startswith(prefixes) and isinstance(v, int)]
    if not sections:
        return None
    return sum(sections)


def _ram_bytes(c: dict):
    if c.get("status") == "unavailable" or "error" in c or not any(k.startswith((".data", ".bss")) for k in c):
        return None
    return sum(v for k, v in c.items() if k.startswith((".data", ".bss")) and isinstance(v, int))


def _doc(p: dict) -> str:
    q = p["int8"]
    c = p["c_footprint"]
    flash = _flash_bytes(c)
    ram = _ram_bytes(c)
    code = c.get(".text", c.get("text"))
    weights = c.get(".rdata", c.get(".rodata"))
    lines = [
        "# Compute and memory, measured",
        "",
        "> [English](#english) · [简体中文](#简体中文)",
        "",
        "## English",
        "",
        "Generated by `python scripts/21_hardware.py` from `research/results/latency.json`",
        "(scripts/04) and the C object file. **No cycle counts and no MCU target are",
        "claimed**: nothing here was run on a board.",
        "",
        "| quantity | value |",
        "| :--- | ---: |",
        f"| parameters, decision path (what ONNX exports) | {p['params']['decision_path']:,} |",
        f"| parameters, built-in (unused) value head | {p['params']['builtin_value_head']:,} |",
        f"| parameters, separate `value_net.pt` (lookahead, off by default) | {p['params']['separate_value_net']:,} |",
        f"| multiply-accumulates per decision | {p['macs']['total']:,} |",
        f"| ONNX forward, p50 / p95 / p99 | {p['onnx_forward_ms']:.3f} / {p['onnx_forward_p95_ms']:.3f} / {p['onnx_forward_p99_ms']:.3f} ms |",
        f"| complete typed decision, p50 / p95 / p99 | {p['typed_decision_ms']:.3f} / {p['typed_decision_p95_ms']:.3f} / {p['typed_decision_p99_ms']:.3f} ms |",
        f"| ONNX file | {_fmt_bytes(p['onnx_file_bytes'])} |",
        f"| C99 host read-only footprint (code {_fmt_bytes(code)} + read-only data {_fmt_bytes(weights)} + metadata, `-Os`) | {_fmt_bytes(flash)} |",
        f"| C99 static RAM (`.data` + `.bss`) | {_fmt_bytes(ram)} |",
        f"| C99 `jev_forward` stack frame, host compiler estimate | {_fmt_bytes(c.get('forward_stack_frame_bytes'))} |",
        f"| dynamic allocation in `c/` | **0** (no `malloc`/`calloc`/`free`) |",
        f"| int8 (per-tensor): same argmax per axis | {100 * q['per_tensor']['argmax_agreement']:.1f}% of {3 * q['cases']} axes ({q['cases']} training states) |",
        f"| int8 (per-tensor): step within 1e-3 | {100 * q['per_tensor']['steps_within_1e-3']:.1f}% |",
        f"| int8 (per-channel): same argmax | {100 * q['per_channel']['argmax_agreement']:.1f}% |",
        f"| int8 (per-channel): all three argmax choices agree | {100 * q['per_channel']['argmax_joint_agreement']:.1f}% |",
        f"| int8 (per-channel): states with changed hold mask | {q['per_channel']['held_state_disagreements']} / {q['cases']} |",
        f"| int8 (per-channel): changed would-hold diagnostics | {q['per_channel']['conformal_would_hold_state_disagreements']} / {q['cases']} |",
        f"| int8 (per-channel): states with changed conformal sets | {q['per_channel']['conformal_set_state_disagreements']} / {q['cases']} |",
        f"| int8 (per-channel): step within 1e-3 | {100 * q['per_channel']['steps_within_1e-3']:.1f}% |",
        f"| int8 (per-channel): max step difference | {q['per_channel']['step_max_abs_diff']:.2e} |",
        "",
        "The MACs are counted from the layer shapes: 5×2×16 at length 32 for the",
        "first convolution, 5×16×32 at length 16 for the second, then the MLP,",
        "the trunk and the five heads. Batch 1, one forward pass.",
        "",
        "### What this does and does not support",
        "",
        f"* Measured default TS+CP decision p50 / p99: {p['typed_decision_ms']:.3f} / {p['typed_decision_p99_ms']:.3f} ms, including conformal masks and would-hold diagnostics. These are percentiles, not WCET.",
        '* It does **not** support: "runs on chip X". Static footprint from a host',
        "  `gcc -Os` object is not a linker map for your target, and feature",
        "  extraction plus the trace capture are usually the real cost.",
        "* Static RAM excludes stack and caller buffers. The reported stack frame excludes nested frames, libm and runtime: it is not peak stack.",
        "* Weight-only int8 is simulated by rounded/dequantized weights with float32 kernels. Agreement percentages are per axis unless explicitly joint; no int8 speed or footprint was measured.",
        "* Quantized outputs reuse the float32 head's conformal quantiles without recalibration. Label coverage does not automatically transfer to this modified model, and neither coverage nor set agreement certifies control safety.",
        f"* Nominal convolution/linear multiply-add FLOPs: {p['multiply_add_flops']:,} (2 per MAC); excludes nonlinear functions, softmax, features and policy logic.",
        f"* Host: `{p['environment']}`. Compiler/target: `{c.get('compiler', 'unavailable')}` / `{c.get('target', 'unavailable')}`. See hardware.json for flags, section sizes and stack frames.",
        "",
        "---",
        "",
        "## 简体中文",
        "",
        "由 `python scripts/21_hardware.py` 从 `research/results/latency.json`（scripts/04）",
        "与 C 目标文件生成。**不声明任何周期数与 MCU 型号**：这里没有任何东西在板上跑过。",
        "",
        "| 指标 | 数值 |",
        "| :--- | ---: |",
        f"| 参数量（决策路径，即 ONNX 导出的部分） | {p['params']['decision_path']:,} |",
        f"| 参数量（内置但未使用的前瞻头） | {p['params']['builtin_value_head']:,} |",
        f"| 参数量（独立 `value_net.pt`，默认关闭） | {p['params']['separate_value_net']:,} |",
        f"| 单次决策乘加数（MACs） | {p['macs']['total']:,} |",
        f"| ONNX 前向 p50 / p95 / p99 | {p['onnx_forward_ms']:.3f} / {p['onnx_forward_p95_ms']:.3f} / {p['onnx_forward_p99_ms']:.3f} ms |",
        f"| 完整类型化决策 p50 / p95 / p99 | {p['typed_decision_ms']:.3f} / {p['typed_decision_p95_ms']:.3f} / {p['typed_decision_p99_ms']:.3f} ms |",
        f"| ONNX 文件 | {_fmt_bytes(p['onnx_file_bytes'])} |",
        f"| C99 宿主只读占用（代码 {_fmt_bytes(code)} + 只读数据 {_fmt_bytes(weights)} + 元数据，`-Os`） | {_fmt_bytes(flash)} |",
        f"| C99 静态 RAM（`.data` + `.bss`） | {_fmt_bytes(ram)} |",
        f"| C99 `jev_forward` 自身栈帧（宿主编译器估计） | {_fmt_bytes(c.get('forward_stack_frame_bytes'))} |",
        "| `c/` 中的动态分配 | **0**（无 `malloc`/`calloc`/`free`） |",
        f"| 仅权重量化 int8（逐张量）：按轴 argmax 一致 | {100 * q['per_tensor']['argmax_agreement']:.1f}%（{q['cases']} 个训练状态、{3 * q['cases']} 个轴） |",
        f"| int8（逐张量）：步长误差 ≤1e-3 | {100 * q['per_tensor']['steps_within_1e-3']:.1f}% |",
        f"| int8（逐通道）：argmax 一致 | {100 * q['per_channel']['argmax_agreement']:.1f}% |",
        f"| int8（逐通道）：三个轴 argmax 全部一致 | {100 * q['per_channel']['argmax_joint_agreement']:.1f}% |",
        f"| int8（逐通道）：保持掩码改变的状态数 | {q['per_channel']['held_state_disagreements']} / {q['cases']} |",
        f"| int8（逐通道）：would_hold诊断改变的状态数 | {q['per_channel']['conformal_would_hold_state_disagreements']} / {q['cases']} |",
        f"| int8（逐通道）：CP集合改变的状态数 | {q['per_channel']['conformal_set_state_disagreements']} / {q['cases']} |",
        f"| int8（逐通道）：步长误差 ≤1e-3 | {100 * q['per_channel']['steps_within_1e-3']:.1f}% |",
        f"| int8（逐通道）：最大步长差 | {q['per_channel']['step_max_abs_diff']:.2e} |",
        "",
        "MACs 按层形状计：第一层卷积 5×2×16、长度 32；第二层 5×16×32、长度 16；再加 MLP、",
        "trunk 与五个头。批大小 1，一次前向。",
        "",
        "### 这些数字支持什么、不支持什么",
        "",
        f"* 默认TS+CP决策路径（含集合构建与would_hold诊断）实测 p50 / p99：{p['typed_decision_ms']:.3f} / {p['typed_decision_p99_ms']:.3f} ms。这是分位延迟，不是最坏执行时间保证。",
        "* **不支持**「能在某款芯片上跑」：主机 `gcc -Os` 的目标文件不等于你目标板的链接",
        "  映射；而且真正的成本通常是特征提取与波形采集。",
        "* 静态 RAM 不含栈与调用者缓冲区。自身栈帧不含嵌套调用、libm 与运行时，不等于峰值栈。",
        "* 仅权重量化 int8 通过取整后反量化、float32 内核运算来评估敏感性；未测 int8 内核速度与占用。除明确联合指标外，一致率按轴计。",
        "* 量化输出沿用float32头的CP分位数，没有重新校准；修改模型后标签覆盖率不会自动继承，覆盖率与集合一致率都不证明控制安全。",
        f"* 卷积/全连接名义乘加折算 {p['multiply_add_flops']:,} FLOPs（每 MAC 算 2 次），不含非线性、softmax、特征与策略。",
        f"* 宿主环境：`{p['environment']}`；编译器/target：`{c.get('compiler', 'unavailable')}` / `{c.get('target', 'unavailable')}`。flags、section与各函数栈帧见 hardware.json。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
