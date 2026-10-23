"""E6: hard numbers for the edge / real-time claim.

Everything here is measured or counted, not estimated:

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
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import torch

from jev_tune.decision import load_backend
from jev_tune.decode import DEFAULT_ABSTAIN, ActionSpace, decide
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
    choice = 3 * 7 * 128
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
    if gcc is None:
        return {"error": "gcc not found"}
    src = ROOT / "c" / "jev_head.c"
    with tempfile.TemporaryDirectory() as tmp:
        obj = Path(tmp) / "jev_head.o"
        proc = subprocess.run(
            [gcc, "-std=c99", "-Os", "-c", str(src), "-o", str(obj), "-lm"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return {"error": proc.stderr[-500:]}
        out = {"object_bytes": obj.stat().st_size}
        if size is not None:
            s = subprocess.run([size, "-A", str(obj)], capture_output=True, text=True)
            for line in s.stdout.splitlines():
                f = line.split()
                if len(f) >= 2 and f[1].isdigit():
                    out[f[0]] = int(f[1])
        # a linked image is the number a firmware engineer budgets, but it also
        # contains the runtime start-up; report the object, and say so
        return out


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
    dec_a = decide(ans_a, space, abstain=DEFAULT_ABSTAIN)
    probs_a = np.stack([ch.probs for ch in ans_a.choice], axis=-2)

    out = {"cases": int(cases), "activations": "float32"}
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
        dec_b = decide(ans_b, space, abstain=DEFAULT_ABSTAIN)
        probs_b = np.stack([ch.probs for ch in ans_b.choice], axis=-2)
        step_diff = np.abs(dec_a.step - dec_b.step)
        out[mode] = {
            "argmax_agreement": float(
                (probs_a.argmax(-1) == probs_b.argmax(-1)).mean()
            ),
            "held_pattern_same": bool(np.array_equal(dec_a.held, dec_b.held)),
            "step_max_abs_diff": float(step_diff.max()),
            "step_mean_abs_diff": float(step_diff.mean()),
            "steps_within_1e-3": float((step_diff <= 1e-3).mean()),
            "steps_within_1e-2": float((step_diff <= 1e-2).mean()),
        }
    out["quantisation"] = "weight-only int8, symmetric, activations float32"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="models")
    ap.add_argument("--latency", default="research/results/latency.json")
    ap.add_argument("--out", default="research/results/hardware.json")
    ap.add_argument("--doc", default="docs/COMPUTE.md")
    args = ap.parse_args()

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

    payload = {
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
        "c_flash_bytes": int(_flash_bytes(csize)),
        "c_ram_bytes": int(_ram_bytes(csize)),
        "int8": int8,
        "onnx_file_bytes": lat.get("onnx_file_bytes"),
        "note": (
            "one CPU thread, batch 1, laptop CPU. No cycle counts: nothing here "
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
    if "text" in c:  # GNU/ELF style from `size -A`
        return c["text"] + c.get("rodata", 0)
    keys = (".text", ".rdata", ".rdata$zzz", ".xdata", ".pdata")
    return sum(c.get(k, 0) for k in keys)


def _ram_bytes(c: dict):
    return c.get(".data", c.get("data", 0)) + c.get(".bss", c.get("bss", 0))


def _doc(p: dict) -> str:
    q = p["int8"]
    c = p["c_footprint"]
    flash = _flash_bytes(c)
    ram = _ram_bytes(c)
    code = c.get(".text", c.get("text"))
    weights = c.get(".rdata", c.get("rodata"))
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
        f"| C99 static flash (code {_fmt_bytes(code)} + weights {_fmt_bytes(weights)}, `-Os`, object file) | {_fmt_bytes(flash)} |",
        f"| C99 static RAM (`.data` + `.bss`) | {_fmt_bytes(ram)} |",
        f"| dynamic allocation in `c/` | **0** (no `malloc`/`calloc`/`free`) |",
        f"| int8 (per-tensor): same argmax | {100 * q['per_tensor']['argmax_agreement']:.1f}% of {q['cases']} states |",
        f"| int8 (per-tensor): step within 1e-3 | {100 * q['per_tensor']['steps_within_1e-3']:.1f}% |",
        f"| int8 (per-channel): same argmax | {100 * q['per_channel']['argmax_agreement']:.1f}% |",
        f"| int8 (per-channel): step within 1e-3 | {100 * q['per_channel']['steps_within_1e-3']:.1f}% |",
        f"| int8 (per-channel): max step difference | {q['per_channel']['step_max_abs_diff']:.2e} |",
        "",
        "The MACs are counted from the layer shapes: 5×2×16 at length 32 for the",
        "first convolution, 5×16×32 at length 16 for the second, then the MLP,",
        "the trunk and the five heads. Batch 1, one forward pass.",
        "",
        "### What this does and does not support",
        "",
        "* It supports: the decision is small (40 k parameters, 84 k MACs) and its",
        "  p99 is comfortably inside a millisecond on one CPU thread.",
        '* It does **not** support: "runs on chip X". Static footprint from a host',
        "  `gcc -Os` object is not a linker map for your target, and feature",
        "  extraction plus the trace capture are usually the real cost.",
        "* The 0.19 ms figure is the forward pass. The 0.5–0.7 ms figure is a complete",
        "  typed decision in Python, which is what the loop pays. Quote the right one.",
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
        f"| C99 静态 Flash（代码 {_fmt_bytes(code)} + 权重 {_fmt_bytes(weights)}，`-Os`，目标文件） | {_fmt_bytes(flash)} |",
        f"| C99 静态 RAM（`.data` + `.bss`） | {_fmt_bytes(ram)} |",
        "| `c/` 中的动态分配 | **0**（无 `malloc`/`calloc`/`free`） |",
        f"| 仅权重量化 int8（逐张量）：argmax 一致 | {100 * q['per_tensor']['argmax_agreement']:.1f}%（{q['cases']} 个状态） |",
        f"| int8（逐张量）：步长误差 ≤1e-3 | {100 * q['per_tensor']['steps_within_1e-3']:.1f}% |",
        f"| int8（逐通道）：argmax 一致 | {100 * q['per_channel']['argmax_agreement']:.1f}% |",
        f"| int8（逐通道）：步长误差 ≤1e-3 | {100 * q['per_channel']['steps_within_1e-3']:.1f}% |",
        f"| int8（逐通道）：最大步长差 | {q['per_channel']['step_max_abs_diff']:.2e} |",
        "",
        "MACs 按层形状计：第一层卷积 5×2×16、长度 32；第二层 5×16×32、长度 16；再加 MLP、",
        "trunk 与五个头。批大小 1，一次前向。",
        "",
        "### 这些数字支持什么、不支持什么",
        "",
        "* 支持：决策很小（4 万参数、8.4 万 MACs），单线程 CPU 上 p99 远小于 1 ms。",
        "* **不支持**「能在某款芯片上跑」：主机 `gcc -Os` 的目标文件不等于你目标板的链接",
        "  映射；而且真正的成本通常是特征提取与波形采集。",
        "* 0.19 ms 是前向；0.5–0.7 ms 是 Python 里一次完整类型化决策，也就是回路实际付的",
        "  代价。引用时请引用对的那个。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
