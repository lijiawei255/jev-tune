"""Export the inference weights to C99 and generate language-neutral test vectors.

Outputs (all generated, do not edit by hand):

    c/jev_head_weights.h   float32 weight arrays, hex float literals (exact)
    c/test_vectors.json    inputs, expected logits / probabilities / steps
    c/test_vectors.h       the same vectors as C arrays (same source of truth)

The JSON is the portable artifact: any language can read it and check a port.
The header exists so the C harness stays dependency-free.

Verify with:

    python scripts/18_export_c.py --verify      # compiles with gcc and compares
"""

from __future__ import annotations

import argparse
import json
import hashlib
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import torch

from jev_tune.decision import read_conformal, read_temperature
from jev_tune.decode import AbstainPolicy, ActionSpace, ConformalPolicy, apply_step, decide
from jev_tune.model import JevHead
from jev_tune.primitives import softmax

ROOT = Path(__file__).resolve().parents[1]

LAYERS = [
    ("jev_w_cv1", "enc.curve.0.weight", False),
    ("jev_b_cv1", "enc.curve.0.bias", True),
    ("jev_w_cv2", "enc.curve.2.weight", False),
    ("jev_b_cv2", "enc.curve.2.bias", True),
    ("jev_w_mlp1", "enc.mlp.0.weight", False),
    ("jev_b_mlp1", "enc.mlp.0.bias", True),
    ("jev_w_mlp2", "enc.mlp.2.weight", False),
    ("jev_b_mlp2", "enc.mlp.2.bias", True),
    ("jev_w_tr1", "enc.trunk.0.weight", False),
    ("jev_b_tr1", "enc.trunk.0.bias", True),
    ("jev_w_tr2", "enc.trunk.2.weight", False),
    ("jev_b_tr2", "enc.trunk.2.bias", True),
    ("jev_w_ch0", "choice.0.weight", False),
    ("jev_b_ch0", "choice.0.bias", True),
    ("jev_w_ch1", "choice.1.weight", False),
    ("jev_b_ch1", "choice.1.bias", True),
    ("jev_w_ch2", "choice.2.weight", False),
    ("jev_b_ch2", "choice.2.bias", True),
    ("jev_w_score", "score.weight", False),
    ("jev_b_score", "score.bias", True),
    ("jev_w_noul", "noul.weight", False),
    ("jev_b_noul", "noul.bias", True),
]


def _c_array(name: str, values: np.ndarray) -> str:
    """Float32 array as C hex-float literals (exact round-trip)."""
    flat = np.asarray(values, dtype=np.float32).reshape(-1)
    body = ", ".join(float(x).hex() + "f" for x in flat)
    return f"static const float {name}[{flat.size}] = {{{body}}};\n"


def _c_double(name: str, values, *, rows=False) -> str:
    """CP quantiles must retain binary64 precision, particularly near one."""
    a = np.asarray(values, dtype=float)
    if not rows:
        return f"static const double {name}[{a.size}] = {{" + ", ".join(float(x).hex() for x in a.flat) + "};\n"
    a = a.reshape(a.shape[0], -1)
    body = ",\n    ".join("{" + ", ".join(float(x).hex() for x in row) + "}" for row in a)
    return f"static const double {name}[{a.shape[0]}][{a.shape[1]}] = {{\n    {body}\n}};\n"


def _conformal_config(cp):
    return {"enabled": cp is not None, "qhat_per_axis": list(cp.q_hat) if cp else [0.] * 3,
            "alpha": cp.alpha if cp else .1, "k_max": cp.k_max if cp else 3,
            "mode": cp.mode if cp else "monitor",
            "inclusion": "(1 - p) <= qhat; equivalent to p >= 1-qhat",
            "would_hold": "empty or size > k_max or both positive and negative payloads",
            "execution": "monitor records diagnostics; hard_hold applies would_hold as a veto",
            "coverage_target": "per-axis teacher-label coverage, not closed-loop safety"}


def _c_2d(name: str, arr: np.ndarray) -> str:
    """(N, M) array as C[M][N]? -> keep [N][M] for readability."""
    a = np.asarray(arr, dtype=np.float32)
    rows = []
    for row in a.reshape(a.shape[0], -1):
        rows.append("{" + ", ".join(float(x).hex() + "f" for x in row) + "}")
    return (
        f"static const float {name}[{a.shape[0]}][{a.reshape(a.shape[0], -1).shape[1]}] "
        "= {\n    " + ",\n    ".join(rows) + "\n};\n"
    )


def _state_cases() -> list[dict]:
    """Feature-assembly cases: inputs to jev_build_state and its output.

    Real simulated responses, so the cases exercise the same numbers the loop
    sees rather than synthetic noise.
    """
    from jev_tune.metrics import cost_from_metrics
    from jev_tune.plants import sample_plants, simulate, ultimate_gain
    from jev_tune.state import build_state

    plants = sample_plants(6, seed=3)
    ku, tu = ultimate_gain(plants)
    ku = np.where(np.isfinite(ku) & (ku > 0), ku, 1.0)
    tu = np.where(np.isfinite(tu) & (tu > 0), tu, 1.0)
    gzn = np.column_stack([0.6 * ku, 1.2 * ku / tu, 0.075 * ku * tu])
    gains = gzn * np.array(
        [
            [1.3, 0.7, 1.1],
            [0.8, 1.4, 0.9],
            [1.0, 1.0, 1.0],
            [2.0, 0.5, 0.4],
            [0.5, 2.0, 1.6],
            [1.1, 0.9, 0.6],
        ]
    )
    res = simulate(plants, gains)
    cost = cost_from_metrics(res["metrics"], y_curve=res["y_curve"])
    prev_action = np.array(
        [
            [0.05, -0.02, 0.0],
            [0.0, 0.0, 0.0],
            [-0.1, 0.03, 0.02],
            [0.12, -0.3, 0.0],
            [0.0, 0.2, -0.05],
            [0.0, 0.0, 0.0],
        ]
    )
    prev_cost = cost + np.array([0.1, 0.0, -0.2, 0.5, 0.05, 0.0])
    iteration = np.arange(6, dtype=float) * 3.0
    feats, curves = build_state(
        res["metrics"],
        res["y_curve"],
        res["u_curve"],
        gains,
        gzn,
        ku,
        tu,
        prev_action=prev_action,
        prev_cost=prev_cost,
        cost=cost,
        iteration=iteration,
    )
    cases = []
    for i in range(plants.n):
        cases.append(
            {
                "metrics": [float(x) for x in res["metrics"][i]],
                "y_curve": [float(x) for x in res["y_curve"][i]],
                "u_curve": [float(x) for x in res["u_curve"][i]],
                "gains": [float(x) for x in gains[i]],
                "gains_zn": [float(x) for x in gzn[i]],
                "ku": float(ku[i]),
                "tu": float(tu[i]),
                "prev_action": [float(x) for x in prev_action[i]],
                "prev_cost": float(prev_cost[i]),
                "cost": float(cost[i]),
                "iteration": float(iteration[i]),
                "horizon": 10.0,
                "ref": 1.0,
                "feats": [float(x) for x in feats[i]],
                "curves": [
                    [float(x) for x in curves[i][0]],
                    [float(x) for x in curves[i][1]],
                ],
            }
        )
    return cases


def _resample_cases() -> list[dict]:
    """Raw traces -> 64 samples, the same index rule as np.linspace().round().

    The trace is built from exact IEEE operations (+, -, *, /) rather than
    sin/cos/exp: transcendental functions differ in the last ULP between libm
    implementations, which made the generated vectors platform-dependent.
    """
    cases = []
    for n in (2001, 501, 137):
        t = np.linspace(0.0, 10.0, n)
        y = (t * 0.7 - 0.3) * (t - 10.0) / 25.0
        u = 0.2 + t / 3.0
        idx = np.linspace(0, n - 1, 64).round().astype(int)
        cases.append(
            {
                "n": int(n),
                "y": [float(x) for x in y],
                "u": [float(x) for x in u],
                "y_out": [float(x) for x in y[idx]],
                "u_out": [float(x) for x in u[idx]],
            }
        )
    return cases


def _policy_cases() -> list[dict]:
    """Synthetic edge cases, independent of what the checkpoint happens to emit."""
    from jev_tune.primitives import Answer, Choice, Noul, Option, Score

    space = ActionSpace()
    unit = np.eye(space.k)
    uniform = np.full(space.k, 1 / space.k)
    half = np.array([0, 0, 0, 0, 0, .5, .5])
    quarter = np.array([0, 0, 0, .25, .25, .25, .25])
    legacy_specs = [
        ("confident_no_change", [unit[3]] * 3, 1., (.35, .25, 0.)),
        ("all_low", [uniform] * 3, 1., (.35, .25, 0.)),
        ("partial_and_act_boundary", [unit[6], uniform, half], 1., (.5, .25, 0.)),
        ("escalation_boundary", [quarter, uniform, half], 1., (.5, .25, 0.)),
        ("noul_boundary", [unit[6]] * 3, .5, (.35, .25, .5)),
        ("noul_veto", [unit[6], uniform, unit[3]], .49, (.35, .25, .5)),
        ("stop_boundary", [unit[6]] * 3, .9, (.35, .25, 0.)),
    ]
    mixed = np.array([.5, 0, 0, 0, 0, 0, .5])
    tails = np.array([0, 0, 0, 0, .125, .125, .75])
    tiny_tail = np.array([0, 0, 0, 0, 0, 2.**-41, 1 - 2.**-41])
    cp = lambda q: ConformalPolicy(q_hat=(q,) * 3, alpha=.1, k_max=3, mode="hard_hold")
    specs = [(*s, None) for s in legacy_specs] + [
        ("cp_empty", [uniform] * 3, 1., (0., 0., 0.), cp(.5)),
        ("cp_oversized", [quarter] * 3, 1., (0., 0., 0.), cp(.75)),
        ("cp_mixed_signs", [mixed] * 3, 1., (0., 0., 0.), cp(.5)),
        ("cp_inclusive_boundary", [half] * 3, 1., (0., 0., 0.), cp(.5)),
        ("cp_exact_kmax", [tails] * 3, 1., (0., 0., 0.), cp(.875)),
        ("cp_full_distribution_proposal", [tails] * 3, 1., (0., 0., 0.), cp(.5)),
        ("cp_confident_no_change", [unit[3]] * 3, 1., (0., 0., 0.), cp(0.)),
        ("cp_near_one_quantile", [tiny_tail] * 3, 1., (0., 0., 0.), cp(1 - 2.**-40)),
        ("cp_noul_precedence", [mixed, half, uniform], .49, (0., 0., .5), cp(.5)),
        ("cp_legacy_precedence", [uniform, half, unit[3]], 1., (.35, .25, 0.), cp(.5)),
    ]
    specs += [(name + "_monitor", probs, noul, thresholds, replace(conformal, mode="monitor"))
              for name, probs, noul, thresholds, conformal in specs if conformal is not None]
    cases = []
    for name, probs, noul, thresholds, conformal in specs:
        policy = AbstainPolicy(*thresholds)
        score = np.array([1., 0, 0, 0, 0])
        ans = Answer(
            choice=[Choice(str(a), [Option(str(j), float(d)) for j, d in enumerate(space.deltas)],
                           np.asarray(p)) for a, p in enumerate(probs)],
            score=Score("quality", list("abcde"), score), noul=Noul("healthy", noul),
        )
        dec = decide(ans, space, abstain=policy, conformal=conformal)
        argmax_dec = decide(ans, space, abstain=policy, conformal=conformal, use_expectation=False)
        cases.append({"name": name, "probs": np.asarray(probs).tolist(),
                      "score_probs": score.tolist(), "noul": noul,
                      "policy": dict(zip(("tau_act", "tau_esc", "tau_noul"), thresholds)),
                      "conformal": _conformal_config(conformal),
                      "step": dec.step.tolist(), "held": dec.held.tolist(),
                      "proposed": dec.proposed.tolist(), "set_size": dec.set_size.tolist(),
                      "conformal_set": np.stack(dec.conformal_set).tolist(),
                      "conformal_mode": dec.conformal_mode,
                      "conformal_would_hold": dec.conformal_would_hold.tolist(),
                      "conformal_reason": dec.conformal_reason.tolist(),
                      "argmax_step": argmax_dec.step.tolist(),
                      "escalate": dec.escalate.tolist(), "reason": dec.reason.tolist(),
                      "should_stop": noul > .9})
    return cases


def _gate_cases() -> list[dict]:
    return [{"cost": j, "best_cost": best, "rollbacks": n, "max_rollbacks": cap,
             "rollback": j > max(3 * best + 1, 8) and n < cap}
            for j, best, n, cap in [(8., 1., 0, 4), (8.01, 1., 0, 4),
                                   (10., 3., 0, 4), (10.01, 3., 0, 4),
                                   (100., 1., 4, 4), (100., 1., 0, 0)]]


def _apply_cases() -> list[dict]:
    return [{"gains": g, "step": d, "expected": apply_step(g, d).tolist()}
            for g, d in [([1., 2., 3.], [0., 0., 0.]),
                         ([1e-4, 1e3, 1.], [-.32, .32, .1]),
                         ([1., 2., 3.], [-.2, .2, -.3])]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="models")
    ap.add_argument("--data", default="data/expert_train.npz")
    ap.add_argument("--cases", type=int, default=24)
    ap.add_argument("--out-dir", default="c")
    ap.add_argument(
        "--verify", action="store_true", help="compile and compare with gcc"
    )
    args = ap.parse_args()

    models = Path(args.models)
    meta = json.loads((models / "meta.json").read_text(encoding="utf-8-sig"))
    model = JevHead(
        n_feats=meta.get("n_feats", 20),
        n_curve=meta.get("n_curve", 64),
        n_actions=meta.get("n_actions", 7),
    )
    model.load_state_dict(torch.load(models / "jev_head.pt", map_location="cpu"))
    model.eval()
    sd = model.state_dict()
    temperature = read_temperature(models) or [1.0, 1.0, 1.0]
    conformal = read_conformal(models)
    space = ActionSpace()
    config = {"multipliers": list(space.multipliers), "deltas": space.deltas.tolist(),
              "max_step": space.max_step, "var_ref": space.var_ref, "shrinkage": 1.,
              "temperature": list(temperature),
              "policy": {"tau_act": 0., "tau_esc": 0., "tau_noul": 0.},
              "conformal": _conformal_config(conformal),
              "gain_bounds": [1e-4, 1e3], "rollback": {"factor": .6, "max_count": 4,
                                                       "cost_floor": 8., "best_factor": 3., "offset": 1.}}
    if conformal is not None:
        calibration_cp = json.loads((models / "calibration.json").read_text(encoding="utf-8-sig"))["split_conformal"]
        config["conformal"].update({key: calibration_cp.get(key) for key in
                                    ("method", "n_calibration", "quantile_rank", "fit_split")})
    model_hash = hashlib.sha256((models / "jev_head.pt").read_bytes()).hexdigest()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    header = [
        "/* generated by scripts/18_export_c.py -- do not edit */",
        "#ifndef JEV_HEAD_WEIGHTS_H",
        "#define JEV_HEAD_WEIGHTS_H",
        "",
    ]
    for name, key, _ in LAYERS:
        header.append(_c_array(name, sd[key].numpy()))
    header.append("#endif")
    (out / "jev_head_weights.h").write_text("\n".join(header), encoding="utf-8")
    (out / "jev_config.h").write_text("\n".join([
        "/* generated by scripts/18_export_c.py -- do not edit */",
        "#ifndef JEV_CONFIG_H", "#define JEV_CONFIG_H",
        f'#define JEV_MODEL_SHA256 "{model_hash}"',
        _c_array("JEV_DEFAULT_TEMPERATURE", temperature),
        _c_array("JEV_DEFAULT_POLICY", list(config["policy"].values())),
        f'#define JEV_DEFAULT_CP_ENABLED {int(conformal is not None)}',
        f'#define JEV_DEFAULT_CP_MODE {int(config["conformal"]["mode"] == "hard_hold")}',
        f'#define JEV_DEFAULT_CP_K_MAX {config["conformal"]["k_max"]}',
        f'#define JEV_DEFAULT_CP_ALPHA {config["conformal"]["alpha"]}',
        _c_double("JEV_DEFAULT_CP_QHAT", config["conformal"]["qhat_per_axis"]),
        "#endif",
    ]), encoding="utf-8")

    # ---- test vectors: real states, spread over the dataset
    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = ROOT / data_path
    prev_vectors = out / "test_vectors.json"
    if data_path.is_file():
        z = np.load(data_path)
        feats_all, curves_all = z["feats"], z["curves"]
        n = len(feats_all)
        idx = np.linspace(0, n - 1, args.cases).round().astype(int)
        feats = np.asarray(feats_all[idx], dtype=np.float32)
        curves = np.asarray(curves_all[idx], dtype=np.float32)
        source_rows = [int(i) for i in idx]
    elif prev_vectors.is_file():
        # CI does not carry data/expert_train.npz (it is 20 MB and generated).
        # Reuse the inputs from the committed vectors so the parity check still
        # runs against real states; the expected outputs are recomputed from the
        # checkpoint, which is what makes this a check rather than a copy.
        prev = json.loads(prev_vectors.read_text(encoding="utf-8"))
        cases_in = prev["cases"][: args.cases]
        feats = np.asarray([c["feats"] for c in cases_in], dtype=np.float32)
        curves = np.asarray([c["curves"] for c in cases_in], dtype=np.float32)
        source_rows = list(prev.get("source_rows", []))[: len(cases_in)]
        print(
            f"[c] dataset missing: reusing {len(cases_in)} inputs from {prev_vectors}"
        )
    else:
        rng = np.random.default_rng(0)
        feats = rng.standard_normal((args.cases, 20)).astype(np.float32)
        curves = rng.standard_normal((args.cases, 2, 64)).astype(np.float32)
        source_rows = []
        print("[c] no dataset and no previous vectors: using random states")

    with torch.no_grad():
        logits = model(torch.as_tensor(feats), torch.as_tensor(curves))

    space = ActionSpace()
    cases = []
    for i in range(len(feats)):
        choice_logits = logits["choice"][i].numpy()  # (3, K)
        probs = np.stack(
            [softmax(choice_logits[a] / temperature[a]) for a in range(3)], axis=0
        )
        from jev_tune.primitives import Answer, Choice, Noul, Option, Score

        answer = Answer(
            choice=[
                Choice(
                    f"step:{a}",
                    [Option(f"x{m:g}", float(np.log10(m))) for m in space.multipliers],
                    probs[a],
                )
                for a in range(3)
            ],
            score=Score("quality", list("abcde"), softmax(logits["score"][i].numpy())),
            noul=Noul("healthy", 1.0 / (1.0 + np.exp(-logits["noul"][i].numpy()))),
        )
        decision = decide(answer, space, conformal=conformal)
        step = decision.step
        cases.append(
            {
                "feats": [float(x) for x in feats[i]],
                "curves": [
                    [float(x) for x in curves[i][0]],
                    [float(x) for x in curves[i][1]],
                ],
                "logits": [[float(x) for x in row] for row in choice_logits],
                "score_logits": [float(x) for x in logits["score"][i].numpy()],
                "noul_logit": float(logits["noul"][i].numpy()),
                "probs": [[float(x) for x in row] for row in probs],
                "score_probs": answer.score.dist.tolist(),
                "noul": float(answer.noul.p_true),
                "step": [float(x) for x in step],
                "proposed": decision.proposed.tolist(),
                "set_size": decision.set_size.tolist(),
                "conformal_set": np.stack(decision.conformal_set).tolist(),
                "conformal_mode": decision.conformal_mode,
                "conformal_would_hold": decision.conformal_would_hold.tolist(),
                "conformal_reason": decision.conformal_reason.tolist(),
                "held": [bool(x) for x in decision.held],
                "escalate": decision.escalate.tolist(),
                "reason": decision.reason.tolist(),
            }
        )

    payload = {
        "generated_by": "scripts/18_export_c.py",
        "schema_version": 4,
        "model_sha256": model_hash,
        "configuration_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        "calibration_sha256": hashlib.sha256((models / "calibration.json").read_bytes().replace(b"\r\n", b"\n")).hexdigest() if (models / "calibration.json").is_file() else None,
        "hash_normalization": "CRLF to LF for text files; binary files byte-exact; configuration sorted JSON",
        "numeric_format": {"weights_and_C_arrays": "IEEE754 binary32", "conformal_quantiles": "IEEE754 binary64", "JSON_reference": "Python floats; compare with supplied tolerances"},
        "configuration": config,
        "model": str(models / "jev_head.pt"),
        "source_rows": source_rows,
        "temperature": [float(t) for t in temperature],
        "tolerance": {"logits": 5e-4, "probs": 1e-5, "step": 1e-5, "feats": 1e-5},
        "note": (
            "logits are the raw head outputs; probs apply the fitted temperature; "
            "step is full-distribution expectation + variance shrink + clip; "
            "CP monitor preserves step and hard_hold alone applies its veto; "
            "held records policy vetoes, never merely a zero-valued action"
        ),
        "cases": cases,
        "state_cases": _state_cases(),
        "resample_cases": _resample_cases(),
        "policy_cases": _policy_cases(),
        "gate_cases": _gate_cases(),
        "apply_cases": _apply_cases(),
    }
    (out / "test_vectors.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8"
    )

    # ---- the same vectors as C arrays
    vec = [
        "/* generated by scripts/18_export_c.py -- do not edit */",
        "#ifndef JEV_TEST_VECTORS_H",
        "#define JEV_TEST_VECTORS_H",
        "",
        f"#define JEV_TV_N {len(cases)}",
        f"#define JEV_TOL_LOGITS {payload['tolerance']['logits']:.1e}f",
        f"#define JEV_TOL_PROBS {payload['tolerance']['probs']:.1e}f",
        f"#define JEV_TOL_STEP {payload['tolerance']['step']:.1e}f",
        "",
        "static const float JEV_TV_TEMP[3] = {"
        + ", ".join(f"{t:.9g}f" for t in temperature)
        + "};",
        "",
        _c_2d("JEV_TV_FEATS", feats),
        _c_2d("JEV_TV_CURVES", curves.reshape(len(curves), 2 * curves.shape[-1])),
        _c_2d(
            "JEV_TV_LOGITS",
            np.array([c["logits"] for c in cases]).reshape(len(cases), 21),
        ),
        _c_2d(
            "JEV_TV_PROBS",
            np.array([c["probs"] for c in cases]).reshape(len(cases), 21),
        ),
        _c_2d("JEV_TV_STEP", np.array([c["step"] for c in cases])),
        _c_2d("JEV_TV_PROPOSED", np.array([c["proposed"] for c in cases])),
        _c_2d("JEV_TV_SET_SIZE", np.array([c["set_size"] for c in cases])),
        _c_2d("JEV_TV_CONFORMAL_SET", np.array([c["conformal_set"] for c in cases])),
        _c_2d("JEV_TV_CONFORMAL_WOULD_HOLD", np.array([c["conformal_would_hold"] for c in cases])),
        _c_2d("JEV_TV_CONFORMAL_REASON", np.array([c["conformal_reason"] for c in cases])),
        _c_2d("JEV_TV_SCORE_LOGITS", np.array([c["score_logits"] for c in cases])),
        _c_2d("JEV_TV_SCORE_PROBS", np.array([c["score_probs"] for c in cases])),
        _c_2d("JEV_TV_NOUL_LOGITS", np.array([[c["noul_logit"]] for c in cases])),
        _c_2d("JEV_TV_NOUL", np.array([[c["noul"]] for c in cases])),
        _c_2d("JEV_TV_HELD", np.array([c["held"] for c in cases])),
        _c_2d("JEV_TV_ESCALATE", np.array([c["escalate"] for c in cases])),
        _c_2d("JEV_TV_REASON", np.array([c["reason"] for c in cases])),
        "",
        "static const float JEV_TV_TAU_ACT = 0.0f;",
        "static const float JEV_TV_TAU_ESC = 0.0f;",
        "static const float JEV_TV_TAU_NOUL = 0.0f;",
        f'#define JEV_TV_CP_ENABLED {int(conformal is not None)}',
        f'#define JEV_TV_CP_MODE {int(config["conformal"]["mode"] == "hard_hold")}',
        f'#define JEV_TV_CP_K_MAX {config["conformal"]["k_max"]}',
        _c_double("JEV_TV_CP_QHAT", config["conformal"]["qhat_per_axis"]),
        "",
        "#endif",
    ]
    (out / "test_vectors.h").write_text("\n".join(vec), encoding="utf-8")

    pc, gc, ac = payload["policy_cases"], payload["gate_cases"], payload["apply_cases"]
    policy_header = ["/* generated by scripts/18_export_c.py -- do not edit */",
                     f"#define JEV_PC_N {len(pc)}", f"#define JEV_GC_N {len(gc)}",
                     f"#define JEV_AC_N {len(ac)}"]
    for name, values in {
        "JEV_PC_PROBS": [c["probs"] for c in pc],
        "JEV_PC_SCORE": [c["score_probs"] for c in pc],
        "JEV_PC_NOUL": [[c["noul"]] for c in pc],
        "JEV_PC_POLICY": [list(c["policy"].values()) for c in pc],
        "JEV_PC_STEP": [c["step"] for c in pc],
        "JEV_PC_PROPOSED": [c["proposed"] for c in pc],
        "JEV_PC_SET_SIZE": [c["set_size"] for c in pc],
        "JEV_PC_CONFORMAL_SET": [c["conformal_set"] for c in pc],
        "JEV_PC_CONFORMAL_WOULD_HOLD": [c["conformal_would_hold"] for c in pc],
        "JEV_PC_CONFORMAL_REASON": [c["conformal_reason"] for c in pc],
        "JEV_PC_CP_ENABLED": [[c["conformal"]["enabled"]] for c in pc],
        "JEV_PC_CP_K_MAX": [[c["conformal"]["k_max"]] for c in pc],
        "JEV_PC_CP_MODE": [[int(c["conformal"]["mode"] == "hard_hold")] for c in pc],
        "JEV_PC_ARGMAX_STEP": [c["argmax_step"] for c in pc],
        "JEV_PC_HELD": [c["held"] for c in pc],
        "JEV_PC_ESCALATE": [c["escalate"] for c in pc],
        "JEV_PC_REASON": [c["reason"] for c in pc],
        "JEV_PC_STOP": [[c["should_stop"]] for c in pc],
        "JEV_GC": [[c[k] for k in ("cost", "best_cost", "rollbacks", "max_rollbacks", "rollback")] for c in gc],
        "JEV_AC_GAINS": [c["gains"] for c in ac],
        "JEV_AC_STEP": [c["step"] for c in ac],
        "JEV_AC_EXPECTED": [c["expected"] for c in ac],
    }.items():
        policy_header.append(_c_2d(name, np.asarray(values)))
    policy_header.append(_c_double("JEV_PC_CP_QHAT", [c["conformal"]["qhat_per_axis"] for c in pc], rows=True))
    (out / "test_policy.h").write_text("\n".join(policy_header), encoding="utf-8")

    # ---- feature-assembly and resampling vectors (separate harness)
    sc = payload["state_cases"]
    rc = payload["resample_cases"]
    longest = max(c["n"] for c in rc)
    rv_y = np.zeros((len(rc), longest), dtype=np.float32)
    rv_u = np.zeros((len(rc), longest), dtype=np.float32)
    for i, c in enumerate(rc):
        rv_y[i, : c["n"]] = np.asarray(c["y"], dtype=np.float32)
        rv_u[i, : c["n"]] = np.asarray(c["u"], dtype=np.float32)

    feat = [
        "/* generated by scripts/18_export_c.py -- do not edit */",
        "#ifndef JEV_TEST_FEATURES_H",
        "#define JEV_TEST_FEATURES_H",
        "",
        f"#define JEV_SV_N {len(sc)}",
        f"#define JEV_RV_N {len(rc)}",
        f"#define JEV_RV_MAX {longest}",
        f"#define JEV_TOL_FEATS {payload['tolerance']['feats']:.1e}f",
        "",
        _c_2d("JEV_SV_METRICS", np.array([c["metrics"] for c in sc])),
        _c_2d("JEV_SV_Y", np.array([c["y_curve"] for c in sc])),
        _c_2d("JEV_SV_U", np.array([c["u_curve"] for c in sc])),
        _c_2d("JEV_SV_GAINS", np.array([c["gains"] for c in sc])),
        _c_2d("JEV_SV_GZN", np.array([c["gains_zn"] for c in sc])),
        _c_2d("JEV_SV_KU", np.array([[c["ku"] for c in sc]])),
        _c_2d("JEV_SV_TU", np.array([[c["tu"] for c in sc]])),
        _c_2d("JEV_SV_PREV", np.array([c["prev_action"] for c in sc])),
        _c_2d("JEV_SV_PREV_COST", np.array([[c["prev_cost"] for c in sc]])),
        _c_2d("JEV_SV_COST", np.array([[c["cost"] for c in sc]])),
        _c_2d("JEV_SV_ITER", np.array([[c["iteration"] for c in sc]])),
        _c_2d("JEV_SV_FEATS", np.array([c["feats"] for c in sc])),
        _c_2d(
            "JEV_SV_CURVES", np.array([c["curves"] for c in sc]).reshape(len(sc), 128)
        ),
        "",
        "static const int JEV_RV_LEN[%d] = {%s};"
        % (len(rc), ", ".join(str(c["n"]) for c in rc)),
        _c_2d("JEV_RV_Y", rv_y),
        _c_2d("JEV_RV_U", rv_u),
        _c_2d("JEV_RV_Y_OUT", np.array([c["y_out"] for c in rc])),
        _c_2d("JEV_RV_U_OUT", np.array([c["u_out"] for c in rc])),
        "",
        "#endif",
    ]
    (out / "test_features.h").write_text("\n".join(feat), encoding="utf-8")

    print(f"[c] wrote {out}/jev_head_weights.h, test_vectors.h, test_vectors.json")
    print(f"[c] {len(cases)} cases from rows {source_rows[:5]}...")
    print(f"[c] temperature {np.round(temperature, 4)}")

    if args.verify:
        raise SystemExit(_verify(out))


def _verify(out: Path) -> int:
    gcc = shutil.which("gcc")
    if gcc is None:
        print("[c] gcc not found: cannot verify (report this, do not claim it passed)")
        return 2
    common = [
        gcc,
        "-std=c99",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Wno-unused-parameter",
    ]
    rc = 0
    for src, exe in (
        ("test_forward.c", "test_forward.exe"),
        ("test_features.c", "test_features.exe"),
        ("test_policy.c", "test_policy.exe"),
    ):
        cmd = common + [
            "-o",
            str(out / exe),
            str(out / src),
            str(out / "jev_head.c"),
            "-lm",
        ]
        print("[c] " + " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            return 1
        run = subprocess.run([str(out / exe)], capture_output=True, text=True)
        print(run.stdout.strip())
        if run.returncode != 0:
            print(run.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    main()
