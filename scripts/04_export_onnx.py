"""Export the decision head to ONNX and measure CPU latency.

This is the number that decides whether the "system-1" claim holds: one forward
pass must be well under a millisecond of pure inference on a laptop CPU.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import time

import numpy as np
import torch

from jev_tune.model import JevHead


class _Export(torch.nn.Module):
    """Tuple-returning wrapper so the ONNX graph has plain outputs."""

    def __init__(self, model: JevHead):
        super().__init__()
        self.model = model

    def forward(self, feats, curves):
        out = self.model(feats, curves)
        return out["choice"], out["score"], out["noul"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="models/jev_head.onnx")
    ap.add_argument("--reps", type=int, default=2000)
    args = ap.parse_args()

    import json

    meta = json.loads((Path(args.models) / "meta.json").read_text(encoding="utf-8-sig"))
    model = JevHead(n_actions=meta.get("n_actions", 5))
    model.load_state_dict(torch.load(f"{args.models}/jev_head.pt", map_location="cpu"))
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

    lat = np.empty(args.reps)
    for i in range(args.reps):
        t = time.perf_counter()
        sess.run(None, {"feats": f, "curves": c})
        lat[i] = (time.perf_counter() - t) * 1e3

    # parity against torch
    with torch.no_grad():
        t_out = wrapper(torch.as_tensor(f), torch.as_tensor(c))
    o_out = sess.run(None, {"feats": f, "curves": c})
    max_diff = max(float(np.max(np.abs(a.numpy() - b))) for a, b in zip(t_out, o_out))

    print(
        f"[onnx] latency p50 {np.percentile(lat, 50):.3f} ms  "
        f"p95 {np.percentile(lat, 95):.3f} ms  p99 {np.percentile(lat, 99):.3f} ms"
    )
    print(f"[onnx] max |onnx - torch| = {max_diff:.2e}")

    torch_lat = np.empty(min(args.reps, 300))
    with torch.no_grad():
        for i in range(len(torch_lat)):
            t = time.perf_counter()
            wrapper(torch.as_tensor(f), torch.as_tensor(c))
            torch_lat[i] = (time.perf_counter() - t) * 1e3
    print(f"[torch] latency p50 {np.percentile(torch_lat, 50):.3f} ms")


if __name__ == "__main__":
    main()
