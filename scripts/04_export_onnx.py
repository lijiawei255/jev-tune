"""Export the decision head to ONNX and measure CPU latency.

Two numbers matter and they are not the same:

* ``session.run`` -- the model-only forward pass;
* ``answer + decode`` -- one complete typed decision, including the softmax,
  the ``Choice``/``Score``/``Noul`` objects and the gain step.  This is what the
  loop actually pays per iteration.

Both are written to ``research/results/latency.json`` so ``docs/claims.json``
can re-read them instead of trusting prose.
"""

from __future__ import annotations

import argparse
import json
import hashlib
import platform
import time
from pathlib import Path

import numpy as np
import torch

from jev_tune.decision import OnnxBackend, read_conformal, read_temperature
from jev_tune.decode import decide
from jev_tune.model import JevHead


class _Export(torch.nn.Module):
    """Tuple-returning wrapper so the ONNX graph has plain outputs."""

    def __init__(self, model: JevHead):
        super().__init__()
        self.model = model

    def forward(self, feats, curves):
        out = self.model(feats, curves)
        return out["choice"], out["score"], out["noul"]


def _p50(lat):
    return float(np.percentile(lat, 50))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="models/jev_head.onnx")
    ap.add_argument("--weights", default="jev_head.pt", help="checkpoint file name")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--json-out", default="research/results/latency.json")
    args = ap.parse_args()
    if args.reps < 1:
        ap.error("--reps must be positive")
    torch.set_num_threads(1)

    meta = json.loads((Path(args.models) / "meta.json").read_text(encoding="utf-8-sig"))
    model = JevHead(n_actions=meta.get("n_actions", 5))
    model.load_state_dict(
        torch.load(f"{args.models}/{args.weights}", map_location="cpu")
    )
    model.eval()
    wrapper = _Export(model).eval()

    feats = torch.zeros(1, 20)
    curves = torch.zeros(1, 2, 64)
    torch.onnx.export(
        wrapper,
        (feats, curves),
        args.out,
        input_names=["feats", "curves"],
        output_names=["choice", "score", "noul"],
        opset_version=17,
        dynamic_axes={
            "feats": {0: "batch"},
            "curves": {0: "batch"},
            "choice": {0: "batch"},
            "score": {0: "batch"},
            "noul": {0: "batch"},
        },
        dynamo=False,
    )
    print(f"[onnx] exported {args.out}")

    import onnxruntime as ort

    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    so.inter_op_num_threads = 1
    sess = ort.InferenceSession(args.out, so, providers=["CPUExecutionProvider"])

    rng = np.random.default_rng(0)
    f = rng.standard_normal((1, 20)).astype(np.float32)
    c = rng.standard_normal((1, 2, 64)).astype(np.float32)

    for _ in range(50):  # warm-up
        sess.run(None, {"feats": f, "curves": c})

    raw = np.empty(args.reps)
    for i in range(args.reps):
        t = time.perf_counter()
        sess.run(None, {"feats": f, "curves": c})
        raw[i] = (time.perf_counter() - t) * 1e3

    # parity against torch
    with torch.no_grad():
        t_out = wrapper(torch.as_tensor(f), torch.as_tensor(c))
    o_out = sess.run(None, {"feats": f, "curves": c})
    max_diff = max(float(np.max(np.abs(a.numpy() - b))) for a, b in zip(t_out, o_out))

    print(
        f"[onnx] forward p50 {_p50(raw):.3f} ms  "
        f"p95 {np.percentile(raw, 95):.3f} ms  p99 {np.percentile(raw, 99):.3f} ms"
    )
    print(f"[onnx] max |onnx - torch| = {max_diff:.2e}")

    # the number the loop pays: typed answer + decode
    backend = OnnxBackend(args.out, temperature=read_temperature(args.models),
                          conformal=read_conformal(args.models))
    for _ in range(200):
        decide(backend.answer(f, c), conformal=backend.conformal)
    typed = np.empty(args.reps)
    for i in range(args.reps):
        t = time.perf_counter()
        decide(backend.answer(f, c), conformal=backend.conformal)
        typed[i] = (time.perf_counter() - t) * 1e3
    print(
        f"[onnx] typed decision p50 {_p50(typed):.3f} ms "
        f"p95 {np.percentile(typed, 95):.3f} ms"
    )

    torch_lat = np.empty(min(args.reps, 300))
    with torch.no_grad():
        for i in range(len(torch_lat)):
            t = time.perf_counter()
            wrapper(torch.as_tensor(f), torch.as_tensor(c))
            torch_lat[i] = (time.perf_counter() - t) * 1e3
    print(f"[torch] forward p50 {_p50(torch_lat):.3f} ms")

    params = sum(p.numel() for p in model.parameters())
    from _experiment_protocol import manifest

    payload = {
        "manifest": manifest(args, files=[Path(args.models) / args.weights,
                                         Path(args.models) / "calibration.json", Path(args.out)],
                             extra={"input_seed": 0, "measurement_scope": "model forward and default typed decision"}),
        "onnx_forward_ms": _p50(raw),
        "onnx_forward_p95_ms": float(np.percentile(raw, 95)),
        "onnx_forward_p99_ms": float(np.percentile(raw, 99)),
        "typed_decision_ms": _p50(typed),
        "typed_decision_p95_ms": float(np.percentile(typed, 95)),
        "typed_decision_p99_ms": float(np.percentile(typed, 99)),
        "torch_forward_ms": _p50(torch_lat),
        "reps": args.reps,
        "threads": 1,
        "batch": 1,
        "input_workload": "one NumPy seed-0 normal state repeated for all samples; excludes feature assembly and simulation",
        "warmup_reps": {"onnx_forward": 50, "typed_decision": 200},
        "decision_path": "OnnxBackend.answer + decide(conformal=backend.conformal, abstain=None)",
        "abstention_policy": {"tau_act": 0., "tau_esc": 0., "tau_noul": 0.},
        "conformal_policy": None if backend.conformal is None else {
            "qhat_per_axis": list(backend.conformal.q_hat), "alpha": backend.conformal.alpha,
            "k_max": backend.conformal.k_max},
        "environment": {"platform": platform.platform(), "processor": platform.processor(),
                        "python": platform.python_version(), "torch": torch.__version__, "onnxruntime": ort.__version__},
        "model_sha256": hashlib.sha256((Path(args.models) / args.weights).read_bytes()).hexdigest(),
        "onnx_sha256": hashlib.sha256(Path(args.out).read_bytes()).hexdigest(),
        "samples_ms": {"onnx_forward": raw.tolist(), "typed_decision": typed.tolist()},
        "params_total": int(params),
        "params_backbone": int(sum(p.numel() for p in model.enc.parameters())),
        "onnx_max_abs_diff_vs_torch": max_diff,
        "onnx_file_bytes": Path(args.out).stat().st_size,
        "note": "one CPU thread, batch 1, host CPU; median of the reps; feature assembly and simulation excluded",
    }
    Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[onnx] wrote {args.json_out}")


if __name__ == "__main__":
    main()
