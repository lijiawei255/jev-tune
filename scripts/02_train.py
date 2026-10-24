"""Train the head, or preserve its weights and fit Temperature + SplitCP.

Three fresh independent plant samples fit temperature, fit CP, and evaluate.
Each contributes only its initial state, not an adaptively correlated rollout.
Teacher-label coverage is not a closed-loop safety guarantee.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from jev_tune.domains.pid.expert import ExpertData, generate
from jev_tune.domains.pid.model import JevHead
from jev_tune.domains.pid.plants import TRAIN_FAMILIES, sample_plants
from jev_tune.core.primitives import calibrate_temperature, fit_split_conformal, softmax
from jev_tune.domains.pid.train import save, train_head, train_value

SPLITS = ("temperature_fit", "cp_fit", "empirical_eval")
DEFAULT_SEEDS = (62601, 62602, 62603)


def load(path: str) -> ExpertData:
    with np.load(path) as z:
        return ExpertData(**{key: z[key] for key in (
            "feats", "curves", "choice", "score", "noul", "cost", "act_state",
            "act_delta", "act_cost", "act_best",
        )})


def _sha256(path):
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def _arrays_sha256(arrays):
    digest = hashlib.sha256()
    for name in sorted(arrays):
        arr = np.ascontiguousarray(arrays[name])
        digest.update(json.dumps([name, arr.dtype.str, list(arr.shape)]).encode())
        digest.update(arr.tobytes())
    return digest.hexdigest()


def _ece(p, y, bins=10):
    conf, pred = p.max(1), p.argmax(1)
    correct = (pred == y).astype(float)
    edges = np.linspace(0, 1, bins + 1)
    result = 0.0
    for i in range(bins):
        selected = (conf > edges[i]) & (conf <= edges[i + 1])
        if selected.any():
            result += selected.mean() * abs(correct[selected].mean() - conf[selected].mean())
    return float(result)


def independent_plants(n: int, seed: int):
    """IID family-mixture sampling, rather than fixed family-count strata."""
    rng = np.random.default_rng(seed)
    family = rng.choice(np.asarray(TRAIN_FAMILIES), size=n)
    # Passing one sampled family per plant avoids the usual fixed-count cycle.
    # The simulator's independent shuffle preserves the IID mixture law.
    return sample_plants(n, families=family.tolist(),
                         seed=int(rng.integers(0, 2**31 - 1)))


def collect_calibration_split(model, n: int, seed: int):
    plants = independent_plants(n, seed)
    data, *_ = generate(plants, steps=1, seed=seed, verbose=False)
    if len(data.feats) != plants.n:
        raise RuntimeError("calibration must contain exactly one state per plant")
    arrays = {name: np.asarray(getattr(data, name)) for name in (
        "feats", "curves", "choice", "score", "noul", "cost",
    )}
    arrays["plant_identity"] = plants.noise_seed
    model.eval()
    with torch.inference_mode():
        out = model(torch.as_tensor(data.feats, dtype=torch.float32),
                    torch.as_tensor(data.curves, dtype=torch.float32))
        arrays["choice_logits"] = out["choice"].numpy().copy()
        arrays["score_logits"] = out["score"].numpy().copy()
        arrays["noul_logits"] = out["noul"].numpy().copy()
    metadata = {
        "seed": seed, "n_plants": n, "n_states": len(data.feats),
        "one_state_per_plant": True, "expert_steps": 1, "init_scale": 0.0,
        "state_sampling": "initial analytic ZN state; IID uniform training-family mixture",
        "families": list(TRAIN_FAMILIES),
        "data_sha256": _arrays_sha256(arrays),
        "simulation_counts": data.simulation_counts,
    }
    return arrays, metadata


def fit_calibration(splits: dict, alpha: float = .10, k_max: int = 3):
    """Fit only on the two named fitting splits; evaluate without reselection."""
    temperature_data = splits["temperature_fit"]
    temperatures = np.array([
        calibrate_temperature(temperature_data["choice_logits"][:, axis],
                              temperature_data["choice"][:, axis])
        for axis in range(3)
    ])

    def probabilities(name):
        return softmax(splits[name]["choice_logits"],
                       temperature=temperatures[None, :, None])

    conformal = fit_split_conformal(probabilities("cp_fit"), splits["cp_fit"]["choice"], alpha)
    evaluation = splits["empirical_eval"]
    p_eval = probabilities("empirical_eval")
    before = softmax(evaluation["choice_logits"])
    cp_eval = conformal.evaluate(p_eval, evaluation["choice"])
    cp_eval["split"] = "empirical_eval"
    cp_eval["threshold_reselected_on_eval"] = False
    return {
        "schema_version": 2,
        "choice_temperature": temperatures.tolist(),
        "temperature_fit_split": "temperature_fit",
        "ece_before": [_ece(before[:, a], evaluation["choice"][:, a]) for a in range(3)],
        "ece_after": [_ece(p_eval[:, a], evaluation["choice"][:, a]) for a in range(3)],
        "ece_evaluation_split": "empirical_eval",
        "val_choice_acc": (p_eval.argmax(-1) == evaluation["choice"]).mean(0).tolist(),
        "val_score_acc": float((evaluation["score_logits"].argmax(-1) == evaluation["score"]).mean()),
        "val_noul_acc": float(((evaluation["noul_logits"] >= 0) == (evaluation["noul"] > .5)).mean()),
        "split_conformal": {
            "method": "split_conformal_lac", "alpha": alpha,
            "n_calibration": conformal.n_calibration,
            "quantile_rank": conformal.quantile_rank,
            "quantile_rule": "ceil((n+1)*(1-alpha)); rank n+1 uses bounded endpoint 1",
            "qhat_per_axis": conformal.qhat_per_axis.tolist(),
            "k_max": k_max, "score": "1 - p_teacher_label", "fit_split": "cp_fit",
            "candidate_rule": "p >= 1-qhat (implemented as 1-p <= qhat to preserve ties)",
            "fit_diagnostics": conformal.evaluate(probabilities("cp_fit"), splits["cp_fit"]["choice"]),
            "evaluation": cp_eval,
            "theory": {
                "target": "expert single-axis best-action label on a fresh initial ZN state",
                "nominal_marginal_coverage": 1 - alpha,
                "conditions": "exchangeable CP-fit and test states; model and temperature fixed independently before CP fitting",
                "scope": "per-axis marginal teacher-label inclusion; empirical evaluation is a separate finite sample",
                "not_guaranteed": [
                    "joint or simultaneous coverage across all gain axes",
                    "coverage conditional on plant family or on passing action gates",
                    "coverage on adaptively visited closed-loop states or shifted plants",
                    "closed-loop safety, stability, performance improvement, or safe physical trials",
                ],
            },
        },
    }


def calibrate(model, out_dir, *, n=512, seeds=DEFAULT_SEEDS, alpha=.10, k_max=3,
              training_data=None, training_seed=0, data_dir=None):
    if n < 1 or len(seeds) != 3 or len(set(seeds)) != 3:
        raise ValueError("calibration needs positive plant count and three distinct seeds")
    if set(seeds) & {0, 7, training_seed}:
        raise ValueError("calibration seeds must differ from training seed and reference seeds 0 and 7")
    if not np.isfinite(alpha) or not 0 < alpha < 1 or k_max < 1:
        raise ValueError("alpha must be in (0,1) and k_max positive")
    out_dir = Path(out_dir)
    checkpoint = out_dir / "jev_head.pt"
    before_hash = _sha256(checkpoint)
    splits, metadata = {}, {}
    for name, seed in zip(SPLITS, seeds):
        print(f"[calibration] {name}: {n} independent plants, seed={seed}", flush=True)
        splits[name], metadata[name] = collect_calibration_split(model, n, seed)
    for i, first in enumerate(SPLITS):
        for second in SPLITS[i + 1:]:
            if np.intersect1d(splits[first]["plant_identity"], splits[second]["plant_identity"]).size:
                raise RuntimeError("calibration splits unexpectedly share a plant")
    result = fit_calibration(splits, alpha, k_max)
    if _sha256(checkpoint) != before_hash:
        raise RuntimeError("calibration must not modify the model checkpoint")
    data_dir = Path(data_dir) if data_dir is not None else out_dir / "calibration_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_files = {}
    for name, arrays in splits.items():
        data_path = data_dir / f"{name}.npz"
        np.savez_compressed(data_path, **arrays)
        metadata[name]["data_file"] = str(data_path)
        metadata[name]["file_sha256"] = _sha256(data_path)
        data_files[name] = {"path": str(data_path), "sha256": _sha256(data_path)}
    root = Path(__file__).resolve().parents[1]
    result.update({
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "splits": metadata,
        "artifacts": {
            "checkpoint_sha256": before_hash,
            "checkpoint_unchanged": True,
            "calibration_data_files": data_files,
            "training_data_sha256": _sha256(training_data) if training_data else None,
            "source_sha256": {name: _sha256(root / name) for name in (
                "scripts/02_train.py", "src/jev_tune/primitives.py", "src/jev_tune/expert.py",
                "src/jev_tune/plants.py", "src/jev_tune/state.py", "src/jev_tune/model.py",
            )},
        },
    })
    (out_dir / "calibration.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    cp = result["split_conformal"]
    print(f"[calibration] temperature={result['choice_temperature']} qhat={cp['qhat_per_axis']}", flush=True)
    print(f"[calibration] held-out teacher-label marginal coverage={cp['evaluation']['coverage_per_axis']}; "
          f"mean set size={cp['evaluation']['mean_set_size_per_axis']}", flush=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/expert_train.npz")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--value-epochs", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", default="models")
    ap.add_argument("--calibrate-only", action="store_true", help="preserve checkpoint/meta and regenerate calibration only")
    ap.add_argument("--calibration-plants", type=int, default=512, help="independent plants in each of three splits")
    ap.add_argument("--calibration-data-dir", default="data/calibration", help="save all three independent datasets for reproducibility")
    ap.add_argument("--temperature-seed", type=int, default=DEFAULT_SEEDS[0])
    ap.add_argument("--cp-seed", type=int, default=DEFAULT_SEEDS[1])
    ap.add_argument("--eval-seed", type=int, default=DEFAULT_SEEDS[2])
    ap.add_argument("--alpha", type=float, default=.10)
    ap.add_argument("--cp-k-max", type=int, default=3)
    ap.add_argument("--threads", type=int, default=1)
    args = ap.parse_args()
    torch.set_num_threads(args.threads)
    directory = Path(args.out_dir)
    if args.calibrate_only:
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8-sig"))
        model = JevHead(n_feats=meta.get("n_feats", 20), n_curve=meta.get("n_curve", 64),
                        n_actions=meta.get("n_actions", 7))
        model.load_state_dict(torch.load(directory / "jev_head.pt", map_location="cpu", weights_only=True))
    else:
        t0 = time.perf_counter()
        data = load(args.data)
        n = len(data.feats)
        print(f"[train] {n:,} states, {len(data.act_state):,} lookahead rows", flush=True)
        for axis, name in enumerate(("Kp", "Ki", "Kd")):
            counts = np.bincount(data.choice[:, axis], minlength=int(data.choice.max()) + 1)
            print(f"[train] {name} label distribution: {np.round(counts / counts.sum(), 3)}", flush=True)
        idx = np.random.default_rng(0).permutation(n)
        tr, va = idx[:int(.9 * n)], idx[int(.9 * n):]
        tr_data = ExpertData(**{
            key: getattr(data, key)[tr] if key in {"feats", "curves", "choice", "score", "noul", "cost"}
            else getattr(data, key)
            for key in ("feats", "curves", "choice", "score", "noul", "cost",
                        "act_state", "act_delta", "act_cost", "act_best")
        })
        model = train_head(tr_data, epochs=args.epochs, seed=args.seed)
        directory.mkdir(parents=True, exist_ok=True)
        save(model, str(directory / "jev_head.pt"))
        value = train_value(data, epochs=args.value_epochs, seed=args.seed)
        save(value, str(directory / "value_net.pt"))
        with torch.inference_mode():
            out = model(torch.as_tensor(data.feats[va]), torch.as_tensor(data.curves[va]))
            accuracy = (out["choice"].argmax(-1).numpy() == data.choice[va]).mean(0)
        print(f"[train] state-split validation choice accuracy {accuracy}; elapsed {time.perf_counter()-t0:.1f}s", flush=True)
        (directory / "meta.json").write_text(json.dumps({
            "n_actions": int(max(5, data.choice.max() + 1)),
            "n_feats": int(data.feats.shape[1]), "n_curve": int(data.curves.shape[-1]),
        }, indent=2), encoding="utf-8")
    calibrate(model, directory, n=args.calibration_plants,
              seeds=(args.temperature_seed, args.cp_seed, args.eval_seed),
              alpha=args.alpha, k_max=args.cp_k_max, training_data=args.data,
              training_seed=args.seed, data_dir=args.calibration_data_dir)


if __name__ == "__main__":
    main()
