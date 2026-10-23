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
    ap.add_argument("--weights", default="jev_head.pt", help="checkpoint file name")
    args = ap.parse_args()

    import json

    meta = json.loads((Path(args.models) / "meta.json").read_text(encoding="utf-8-sig"))
    model = JevHead(n_actions=meta.get("n_actions", 5))
    model.load_state_dict(
        torch.load(f"{args.models}/{args.weights}", map_location="cpu")
    )
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

    # a real state from the training rollouts, so the parity vector exercises a
    # non-uniform choice distribution (random noise decodes to ~0 on every axis)
    data_path = Path(__file__).resolve().parents[1] / "data" / "expert_train.npz"
    if data_path.is_file():
        z = np.load(data_path)
        feats = np.asarray(z["feats"][:1], dtype=np.float64)
        curves = np.asarray(z["curves"][:1], dtype=np.float64)
        print("[weights] reference state: data/expert_train.npz row 0")
    else:
        rng = np.random.default_rng(0)
        feats = rng.standard_normal((1, 20))
        curves = rng.standard_normal((1, 2, 64))
        print("[weights] reference state: random (dataset not found)")

    with torch.no_grad():
        out = model(
            torch.as_tensor(feats, dtype=torch.float32),
            torch.as_tensor(curves, dtype=torch.float32),
        )
        ref_choice = out["choice"].numpy().reshape(-1)  # (15,)
        ref_score = out["score"].numpy().reshape(-1)
        ref_noul = out["noul"].numpy().reshape(-1)

    # the fitted temperatures travel with the weights, so `jev_tune_model.m`
    # decodes with the same distribution the Python loop uses
    cal = Path(args.models) / "calibration.json"
    temperature = np.ones(3)
    if cal.is_file():
        temperature = np.asarray(
            json.loads(cal.read_text(encoding="utf-8-sig"))["choice_temperature"],
            dtype=float,
        )

    # reference *step*, not just logits: lets MATLAB verify the whole decode
    # (temperature -> softmax -> expectation -> variance shrink -> abstention -> clip)
    from jev_tune.decode import DEFAULT_ABSTAIN, ActionSpace, decide
    from jev_tune.primitives import Answer, Choice, Noul, Option, Score, softmax

    space = ActionSpace()
    probs = np.stack(
        [softmax(out["choice"].numpy()[0, i] / temperature[i]) for i in range(3)],
        axis=0,
    )
    answer = Answer(
        choice=[
            Choice(
                f"step:{a}",
                [Option(f"x{m:g}", float(np.log10(m))) for m in space.multipliers],
                probs[a],
            )
            for a in range(3)
        ],
        score=Score("quality", list("abcde"), softmax(out["score"].numpy()[0])),
        noul=Noul("healthy", 1.0 / (1.0 + np.exp(-out["noul"].numpy()[0]))),
    )
    ref_step = decide(answer, space, abstain=DEFAULT_ABSTAIN).step.reshape(1, 3)

    W.update(
        {
            "ref_feats": feats,
            "ref_curves": curves,
            "ref_choice": ref_choice,
            "ref_score": ref_score,
            "ref_noul": ref_noul,
            "temperature": temperature.reshape(1, 3),
            "ref_step": ref_step,
            "decode_max_step": np.array([[space.max_step]]),
            "tau_act": np.array([[DEFAULT_ABSTAIN.tau_act]]),
            "tau_esc": np.array([[DEFAULT_ABSTAIN.tau_esc]]),
        }
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    savemat(args.out, W)
    print(f"[weights] wrote {args.out} ({len(W)} arrays)")
    print(f"[weights] temperatures {np.round(temperature, 4)}")
    print(
        f"[weights] abstention tau_act={DEFAULT_ABSTAIN.tau_act} "
        f"tau_esc={DEFAULT_ABSTAIN.tau_esc}"
    )
    print(f"[weights] ref choice logits: {np.round(ref_choice[:5], 4)}")
    print(f"[weights] ref step: {np.round(ref_step, 5)}")


if __name__ == "__main__":
    main()
