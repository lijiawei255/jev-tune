"""Dump the trained head to a plain .mat file for the MATLAB bridge.

The Simulink loop must not depend on Python at runtime, otherwise the 0.19 ms
decision is buried under an IPC round trip.  The head is small enough to run
with a hand-written forward pass in MATLAB; this script writes the weights and
a reference state/output pair used to verify parity.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch
from scipy.io import savemat

from jev_tune.model import JevHead


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="models/jev_head_weights.mat")
    args = ap.parse_args()

    import json

    meta = json.loads((Path(args.models) / "meta.json").read_text(encoding="utf-8-sig"))
    model = JevHead(n_actions=meta.get("n_actions", 5))
    model.load_state_dict(torch.load(f"{args.models}/jev_head.pt", map_location="cpu"))
    model.eval()
    sd = model.state_dict()

    def col(a):
        return np.asarray(a).reshape(-1, 1)

    W = {
        "cv1_w": sd["enc.curve.0.weight"].numpy(),  # (16,2,5)
        "cv1_b": sd["enc.curve.0.bias"].numpy(),
        "cv2_w": sd["enc.curve.2.weight"].numpy(),  # (32,16,5)
        "cv2_b": sd["enc.curve.2.bias"].numpy(),
        "mlp1_w": sd["enc.mlp.0.weight"].numpy(),
        "mlp1_b": col(sd["enc.mlp.0.bias"].numpy()),
        "mlp2_w": sd["enc.mlp.2.weight"].numpy(),
        "mlp2_b": col(sd["enc.mlp.2.bias"].numpy()),
        "tr1_w": sd["enc.trunk.0.weight"].numpy(),
        "tr1_b": col(sd["enc.trunk.0.bias"].numpy()),
        "tr2_w": sd["enc.trunk.2.weight"].numpy(),
        "tr2_b": col(sd["enc.trunk.2.bias"].numpy()),
        "score_w": sd["score.weight"].numpy(),
        "score_b": col(sd["score.bias"].numpy()),
        "noul_w": sd["noul.weight"].numpy(),
        "noul_b": col(sd["noul.bias"].numpy()),
    }
    for i in range(3):
        W[f"ch{i}_w"] = sd[f"choice.{i}.weight"].numpy()
        W[f"ch{i}_b"] = col(sd[f"choice.{i}.bias"].numpy())

    rng = np.random.default_rng(0)
    feats = rng.standard_normal((1, 20)).astype(np.float64)
    curves = rng.standard_normal((1, 2, 64)).astype(np.float64)

    with torch.no_grad():
        out = model(
            torch.as_tensor(feats, dtype=torch.float32),
            torch.as_tensor(curves, dtype=torch.float32),
        )
        ref_choice = out["choice"].numpy().reshape(-1)  # (15,)
        ref_score = out["score"].numpy().reshape(-1)
        ref_noul = out["noul"].numpy().reshape(-1)

    W.update(
        {
            "ref_feats": feats,
            "ref_curves": curves,
            "ref_choice": ref_choice,
            "ref_score": ref_score,
            "ref_noul": ref_noul,
        }
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    savemat(args.out, W)
    print(f"[weights] wrote {args.out} ({len(W)} arrays)")
    print(f"[weights] ref choice logits: {np.round(ref_choice[:5], 4)}")


if __name__ == "__main__":
    main()

