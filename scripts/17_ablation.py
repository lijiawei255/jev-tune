"""E1: matched-gate MLP / uncalibrated / temperature / temperature+CP controls.

Every variant shares the same encoder, the same training data and the same
closed-loop evaluator. Only the decision path changes:

    A0  regression    same encoder, three direct log10 step outputs, encoded by
                      adjacent-bin interpolation that preserves their expectation
    A1  argmax        trained head, discrete action (no expectation)
    A2  expect        expected step, no variance shrink, no early stop, no gate
    A2T expect, temperature calibration off
    A3  shrink        A2 + variance-driven shrink
    A4  gate          A3 + deterministic safety gate
    A5  abstain       A4 + legacy pmax confidence hold (CP disabled)
    A6  early stop    A4 + stop in the cheapest band when noul > 0.9

The C0-C3 primary comparison uses one deterministic gate and no pmax heuristic.
Only C3 enables split conformal prediction; A0-A6 retain their CP-off definitions.
Every variant sees the same plants in the same draw.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from jev_tune.decision import AXES, SCORE_LEVELS, NumericBackend, tuner_questions
from jev_tune.decode import DEFAULT_ABSTAIN, AbstainPolicy, ActionSpace
from jev_tune.evaluate import HARM_METRIC, evaluate_head
from jev_tune.model import Encoder
from jev_tune.plants import HELDOUT_FAMILIES, sample_plants, ultimate_gain
from jev_tune.primitives import Answer, Choice, Noul, Option, Score, softmax
from jev_tune.train import _to_t
from _experiment_protocol import (
    conformal_evidence_lines, expectation_preserving_probs, manifest, sha256, training_indices,
)


# --------------------------------------------------------------------------- #
# A0: the same encoder with a regression head instead of the choice heads
# --------------------------------------------------------------------------- #


class RegressionHead(nn.Module):
    def __init__(self, n_feats=20, n_curve=64, hidden=128, n_levels=5):
        super().__init__()
        self.enc = Encoder(n_feats, n_curve, hidden)
        self.step = nn.Linear(hidden, 3)  # the only difference from JevHead
        self.score = nn.Linear(hidden, n_levels)
        self.noul = nn.Linear(hidden, 1)

    def forward(self, feats, curves):
        h = self.enc(feats, curves)
        return {
            "step": self.step(h),
            "score": self.score(h),
            "noul": self.noul(h).squeeze(-1),
        }


def train_regression(data, *, epochs=40, batch=512, lr=2e-3, seed=0):
    """Same optimiser/schedule/epochs as `train_head`, MSE instead of CE."""
    torch.manual_seed(seed)
    space = ActionSpace()
    deltas = torch.as_tensor(space.deltas, dtype=torch.float32)
    y_step = deltas[torch.as_tensor(data.choice, dtype=torch.long)]  # (N,3)
    feats, curves = _to_t(data.feats), _to_t(data.curves)
    y_score = _to_t(data.score, torch.long)
    y_noul = _to_t(data.noul)

    n = len(feats)
    ds = torch.utils.data.TensorDataset(feats, curves, y_step, y_score, y_noul)
    bs = max(1, min(batch, n // 2))
    dl = torch.utils.data.DataLoader(ds, batch_size=bs, shuffle=True, drop_last=False)

    model = RegressionHead(n_feats=feats.shape[1], n_curve=curves.shape[-1])
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    mse = nn.MSELoss()
    ce = nn.CrossEntropyLoss()
    bce = nn.BCEWithLogitsLoss()

    for ep in range(epochs):
        model.train()
        for f, c, ys, ysc, yn in dl:
            out = model(f, c)
            loss = (
                mse(out["step"], ys)
                + 0.5 * ce(out["score"], ysc)
                + 0.5 * bce(out["noul"], yn)
            )
            opt.zero_grad()
            loss.backward()
            opt.step()
        sched.step()
        if ep % 10 == 0 or ep == epochs - 1:
            print(f"    [A0] epoch {ep:3d} loss {loss.item():.4f}", flush=True)
    model.eval()
    return model


class RegressionBackend:
    """Typed answers built from a regressed step (A0 only)."""

    name = "regression"

    def __init__(self, model, *, space: ActionSpace | None = None):
        self.model = model
        self.space = space or ActionSpace()
        self.questions = tuner_questions(self.space)
        self._options = [
            [
                Option(label=f"x{m:g}", delta=float(np.log10(m)))
                for m in self.space.multipliers
            ]
            for _ in AXES
        ]

    def answer(self, feats, curves, questions=None) -> Answer:
        f = torch.as_tensor(np.asarray(feats), dtype=torch.float32)
        c = torch.as_tensor(np.asarray(curves), dtype=torch.float32)
        with torch.no_grad():
            out = self.model(f, c)
        r = out["step"].numpy()
        d = self.space.deltas
        # The A0 variant disables variance shrinkage. Its decoded expectation
        # equals the continuous output clipped to the same vocabulary bounds.
        probs = expectation_preserving_probs(r, d)
        return Answer(
            choice=[
                Choice(f"step:{a}", self._options[i], probs[:, i])
                for i, a in enumerate(AXES)
            ],
            score=Score(
                "quality", list(SCORE_LEVELS), softmax(out["score"].numpy(), axis=-1)
            ),
            noul=Noul("healthy", torch.sigmoid(out["noul"]).numpy()),
        )


# --------------------------------------------------------------------------- #
# Data / variants
# --------------------------------------------------------------------------- #


def load_data(path: str):
    from jev_tune.expert import ExpertData

    z = np.load(path)
    return ExpertData(
        feats=z["feats"],
        curves=z["curves"],
        choice=z["choice"],
        score=z["score"],
        noul=z["noul"],
        cost=z["cost"],
        act_state=z["act_state"],
        act_delta=z["act_delta"],
        act_cost=z["act_cost"],
        act_best=z["act_best"],
    )


def regression_training_subset(data):
    """Reuse 02_train's exact 90% split; value-network arrays are not consumed."""
    from jev_tune.expert import ExpertData
    tr, va = training_indices(len(data.feats))
    fields = {key: getattr(data, key)[tr]
              for key in ("feats", "curves", "choice", "score", "noul", "cost")}
    fields.update({key: getattr(data, key)
                   for key in ("act_state", "act_delta", "act_cost", "act_best")})
    return ExpertData(**fields), tr, va


# name, backend, expectation, shrink, early_stop, gate, temperature, abstain, CP
ABSTAIN = DEFAULT_ABSTAIN
VARIANTS = (
    ("C0_MLP_regression", "regress", True, 0.0, False, True, False, None, False),
    ("C1_uncalibrated", "head", True, 1.0, False, True, False, None, False),
    ("C2_temperature_only", "head", True, 1.0, False, True, True, None, False),
    ("C3_temperature_CP", "head", True, 1.0, False, True, True, None, "hard_hold"),
    ("C4_CP_monitor", "head", True, 1.0, False, True, True, None, "monitor"),
    ("C5_CP_hold_stop", "head", True, 1.0, False, True, True, None, "hard_hold"),
    ("A0_regress", "regress", True, 0.0, False, False, True, None, False),
    ("A1_argmax", "head", False, 0.0, False, False, True, None, False),
    ("A2_expect", "head", True, 0.0, False, False, True, None, False),
    ("A2T_no_calib", "head", True, 0.0, False, False, False, None, False),
    ("A3_shrink", "head", True, 1.0, False, False, True, None, False),
    ("A4_gate", "head", True, 1.0, False, True, True, None, False),
    ("A5_abstain", "head", True, 1.0, False, True, True, ABSTAIN, False),
    ("A6_early_stop", "head", True, 1.0, True, True, True, None, False),
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plants", type=int, default=120)
    ap.add_argument("--draws", type=int, default=3, help="independent plant samples")
    ap.add_argument("--seed0", type=int, default=7)
    ap.add_argument("--budget", type=int, default=20)
    ap.add_argument("--data", default="data/expert_train.npz")
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="research/results/ablation.json")
    ap.add_argument("--doc", default="docs/ABLATION.md")
    ap.add_argument("--skip-a0", action="store_true")
    ap.add_argument("--a0-cache", default="models/ablation_a0.pt")
    ap.add_argument("--train-only", action="store_true", help="prepare the matched A0 cache and exit")
    args = ap.parse_args()
    provenance = manifest(args, files=[args.data, Path(args.models)/"jev_head.pt",
                                      Path(args.models)/"calibration.json"])

    data = load_data(args.data)
    data, tr, va = regression_training_subset(data)
    print(
        f"[ablation] {len(data.feats):,} states, {args.draws} draws x {args.plants} plants",
        flush=True,
    )

    draws = []
    for d in range(args.draws):
        seed = args.seed0 + 10 * d
        plants = sample_plants(
            args.plants, seed=seed, families=HELDOUT_FAMILIES, heldout=True
        )
        ku, tu = ultimate_gain(plants)
        gzn = np.column_stack([0.6 * ku, 1.2 * ku / tu, 0.075 * ku * tu])
        draws.append({"seed": seed, "plants": plants, "ku": ku, "tu": tu, "gzn": gzn})
        print(f"[ablation] draw {d}: seed {seed}, {plants.n} plants", flush=True)

    head_backends = {}
    result = {
        "harm_metric": dict(HARM_METRIC),
        "budget": args.budget,
        "plants_per_draw": args.plants,
        "draws": [d["seed"] for d in draws],
        "rows": [],
        "calibration_evidence": json.loads((Path(args.models)/"calibration.json").read_text(encoding="utf-8")),
        "policy_protocol": "C3 historical hard_hold repeats; C4 default monitor; C5 hard_hold stops unchanged gains. Fixed configurations, no outcome-based selection.",
        "training_protocol": {
            "training_seed": 0, "training_seeds_repeated": False,
            "training_states": len(tr), "legacy_validation_states": len(va),
            "temperature_CP_splits": "fresh independent plant-level splits from calibration_evidence; not the old 10% state validation split",
            "split": "numpy.default_rng(0).permutation; first 90%; identical to 02_train.py",
            "epochs": 40, "batch": 512, "lr": 2e-3,
            "typed_head": "shipped checkpoint; training protocol from 02_train.py",
            "limitation": "one checkpoint per architecture; draw variation is evaluation sampling, not training-seed robustness",
            "a0_adapter": "two-neighbour interpolation, preserves bounded expectation; shrinkage=0",
        },
    }

    a0 = None
    if not args.skip_a0:
        cache = Path(args.a0_cache)
        metadata_path = cache.with_suffix(".manifest.json")
        cache_protocol = {
            "data_sha256": sha256(args.data), "states": len(tr),
            "split": "default_rng(0), first90pct", "seed": 0, "epochs": 40,
            "implementation": "matched_split_expectation_v2",
        }
        compatible = (cache.is_file() and metadata_path.is_file()
                      and json.loads(metadata_path.read_text(encoding="utf-8")).get("protocol") == cache_protocol)
        if compatible:
            a0 = RegressionHead(n_feats=20, n_curve=64)
            a0.load_state_dict(torch.load(cache, map_location="cpu"))
            a0.eval()
            print(f"[ablation] A0 loaded from {cache}", flush=True)
        else:
            t = time.perf_counter()
            print(
                "[ablation] training A0 regression head (same encoder/epochs/data)",
                flush=True,
            )
            a0 = train_regression(data, epochs=40, seed=0)
            Path(cache).parent.mkdir(parents=True, exist_ok=True)
            torch.save(a0.state_dict(), cache)
            metadata_path.write_text(json.dumps({
                "protocol": cache_protocol,
                "manifest": manifest(args, files=[args.data, cache]),
            }, indent=2), encoding="utf-8")
            print(
                f"[ablation] A0 trained in {time.perf_counter() - t:.0f}s -> {cache}",
                flush=True,
            )

    if args.train_only:
        return

    for name, backend_kind, expect, shrink, early, gate, calibrate, policy, cp in VARIANTS:
        if backend_kind == "regress" and a0 is None:
            continue
        per_draw = []
        t = time.perf_counter()
        for di, d in enumerate(draws):
            if backend_kind == "regress":
                backend = RegressionBackend(a0)
            else:
                key = calibrate
                if key not in head_backends:
                    head_backends[key] = NumericBackend.from_checkpoint(
                        args.models, calibrate=calibrate
                    )
                backend = head_backends[key]

            if cp and getattr(backend, "conformal", None) is None:
                raise ValueError("C3 requires split CP metadata; run 02_train.py --calibrate-only first")

            r = evaluate_head(
                backend,
                d["plants"],
                d["gzn"],
                d["ku"],
                d["tu"],
                budget=args.budget,
                value=None,
                use_value_filter=False,
                seed=d["seed"],
                use_expectation=expect,
                shrinkage=shrink,
                early_stop=early,
                safety_gate=gate,
                abstain=policy,
                conformal=cp if cp else None,
                stop_on_no_action=name in ("C4_CP_monitor", "C5_CP_hold_stop"),
            )
            rep = r.decision_report()
            per_draw.append(
                {
                    "draw": di,
                    "median": float(np.median(r.best_j)),
                    "p90": float(np.percentile(r.best_j, 90)),
                    "mean_experiments": float(np.mean(r.actual_simulations)),
                    "mean_stop_index": float(np.mean(r.stop_iter)),
                    "rollbacks": int(r.rollbacks.sum()),
                    "failures": int((r.best_j >= 50.0).sum()),
                    "coverage": rep.get("coverage"),
                    "measured_transition_coverage": rep.get("coverage"),
                    "proposal_coverage": rep.get("proposal_coverage"),
                    "n_measured_policy_transitions": rep.get("n_decisions"),
                    "n_proposals": rep.get("n_proposals"),
                    "harmful_rate": rep.get("harmful_rate"),
                    "harmful_gt_2pct_rate": rep.get("harmful_gt_2pct_rate"),
                    "ece": None if backend_kind == "regress" else rep.get("ece"),
                    "decision_report": rep,
                    "per_plant": [float(x) for x in r.best_j],
                }
            )
            print(
                f"  {name:15s} draw {di}  median {per_draw[-1]['median']:.3f}  "
                f"exp {per_draw[-1]['mean_experiments']:.1f}  "
                f"proposal cov {per_draw[-1]['proposal_coverage']:.2f}  "
                f"measured cov {per_draw[-1]['coverage']:.2f}",
                flush=True,
            )

        med = np.array([x["median"] for x in per_draw])
        exp = np.array([x["mean_experiments"] for x in per_draw])
        eces = [x["ece"] for x in per_draw if x["ece"] is not None]
        set_sizes = [x['decision_report'].get('average_set_size') for x in per_draw
                     if x['decision_report'].get('average_set_size') is not None]
        result["rows"].append(
            {
                "variant": name,
                "configuration": {"backend":backend_kind,"temperature":calibrate if backend_kind == "head" else False,
                    "conformal":bool(cp),"conformal_mode":cp or "off", "stop_on_no_action":name in ("C4_CP_monitor", "C5_CP_hold_stop"),"gate":gate,"shrinkage":shrink,
                    "pmax_abstention":policy is not None},
                "median_mean": float(med.mean()),
                "median_std": float(med.std(ddof=1)) if len(med) > 1 else 0.0,
                "p90_median": float(np.median([x["p90"] for x in per_draw])),
                "experiments_mean": float(exp.mean()),
                "rollbacks": int(sum(x["rollbacks"] for x in per_draw)),
                "failures": int(sum(x["failures"] for x in per_draw)),
                "coverage": float(np.mean([x["coverage"] for x in per_draw])),
                "measured_transition_coverage": float(np.mean([x["coverage"] for x in per_draw])),
                "proposal_coverage": float(np.mean([x["proposal_coverage"] for x in per_draw])),
                "n_measured_policy_transitions": int(sum(x["n_measured_policy_transitions"] for x in per_draw)),
                "n_proposals": int(sum(x["n_proposals"] for x in per_draw)),
                "harmful_rate": float(
                    np.mean(
                        [
                            x["harmful_rate"]
                            for x in per_draw
                            if x["harmful_rate"] is not None
                        ]
                    )
                )
                if any(x["harmful_rate"] is not None for x in per_draw)
                else None,
                "harmful_gt_2pct_rate": float(np.mean([
                    x["harmful_gt_2pct_rate"] for x in per_draw
                    if x["harmful_gt_2pct_rate"] is not None]))
                if any(x["harmful_gt_2pct_rate"] is not None for x in per_draw) else None,
                "n_harmful": sum(x["decision_report"]["n_harmful"] for x in per_draw),
                "n_harmful_gt_2pct": sum(x["decision_report"]["n_harmful_gt_2pct"] for x in per_draw),
                "ece": float(np.mean(eces)) if eces else None,
                "average_set_size": float(np.mean(set_sizes)) if set_sizes else None,
                "per_draw": per_draw,
                "wall_s": float(time.perf_counter() - t),
            }
        )

    # Paired plant-wise differences, conditional on these fixed checkpoints.
    by = {r["variant"]: r for r in result["rows"]}
    for ref_name, report_key in (("A4_gate", "paired_vs_A4"),
                                 ("C2_temperature_only", "paired_vs_temperature_only")):
        ref = by.get(ref_name)
        if ref is None:
            continue
        for r in result["rows"]:
            diffs = []
            for a, b in zip(r["per_draw"], ref["per_draw"]):
                diffs.extend(np.asarray(a["per_plant"]) - np.asarray(b["per_plant"]))
            diffs = np.asarray(diffs)
            se = diffs.std(ddof=1) / np.sqrt(len(diffs))
            result.setdefault(report_key, {})[r["variant"]] = {
                "mean_delta": float(diffs.mean()),
                "ci95": [
                    float(diffs.mean() - 1.96 * se),
                    float(diffs.mean() + 1.96 * se),
                ],
                "worse_than_ref_pct": float(100 * np.mean(diffs > 1e-9)),
                "better_than_ref_pct": float(100 * np.mean(diffs < -1e-9)),
                "n": int(len(diffs)),
            }

    provenance["file_sha256"][args.a0_cache] = sha256(args.a0_cache)
    result["manifest"] = provenance
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    Path(args.doc).write_text(_doc(result), encoding="utf-8")
    print(f"[ablation] wrote {args.out} and {args.doc}")

    print(
        f"\n{'variant':<16}{'median':>9}{'std':>7}{'p90':>7}{'experiments':>13}{'vs A4':>9}"
    )
    print("-" * 62)
    for r in result["rows"]:
        pd = result.get("paired_vs_A4", {}).get(r["variant"], {}).get("mean_delta", 0.0)
        print(
            f"{r['variant']:<16}{r['median_mean']:>9.3f}{r['median_std']:>7.3f}"
            f"{r['p90_median']:>7.3f}{r['experiments_mean']:>13.1f}{pd:>+9.3f}"
        )


def _doc(result: dict) -> str:
    if result.get("harm_metric", {}).get("version") != HARM_METRIC["version"]:
        raise ValueError("rerun E1: historical harmful_rate used the >2% definition")
    rows = result["rows"]
    lines = [
        "# Ablation: temperature, split CP and matched MLP control",
        "",
        "> [English](#english) · [简体中文](#简体中文)",
        "",
        "## English",
        "",
        "Generated by `python scripts/17_ablation.py`. The controls share encoder "
        "architecture, the 02_train training split, objective and maximum budget. "
        "The ladder changes decoding and optional safeguards; all rows return the best measured point.",
        "",
        f"* {result['plants_per_draw']} validation-family plants per draw, "
        f"{len(result['draws'])} draws (seeds {result['draws']})",
        f"* budget {result['budget']} experiments per plant",
        "* mean ± std is across draws of the per-draw median cost",
        "* one trained checkpoint per architecture; these are evaluation draws, not repeated training seeds",
        f"* A0 reuses the {result['training_protocol']['training_states']:,}-state training split and preserves its bounded continuous output; the typed checkpoint follows the 02_train protocol",
        "* experiments counts actual simulator plant-runs, including initial/final measurements",
        "* argmax uses the same trained classification checkpoint; these contrasts compare predictors/decoders, not the causal effect of wrapping arrays in typed containers",
        "* C0 MLP Regression / C1 Uncalibrated / C2 Temp Only / C3 Temp+CP share the start, plants, maximum budget and deterministic gate; none uses the pmax heuristic",
        "* C0 preserves its continuous expectation without variance shrinkage; C1-C3 share the same expectation/variance decoder. C3 alone enables CP, so C3 versus C2 isolates its hold rule",
        "* the A0-A6 ladder disables CP; A5 is the legacy pmax policy, not the shipped default",
        "* both action-coverage columns count at least one permitted axis. Proposal coverage includes terminal proposals; measured transition coverage (the JSON coverage alias) includes only policy decisions followed by an actual measurement, excluding rollbacks. Rates are means across draws; counts in the JSON are totals",
        "* stopping after a fully held proposal excludes that proposal from the measured denominator. C5 can therefore have measured transition coverage 1.0 while rejecting proposals; proposal coverage shows those holds. Neither quantity is teacher-label set coverage, whose independent evaluation is stored in calibration_evidence",
        "* harm >0 is the canonical strict after > before definition, with zero tolerance. Legacy harm >2% retains after > 1.02 × before for comparison with v0.6. Both rates condition on measured policy decisions with at least one permitted axis, excluding rollbacks and terminal proposals; neither is an unconditional joint-risk guarantee",
        "",
        "| variant | median J | std | p90 | experiments | proposal coverage | measured transition coverage | harm >0 | legacy harm >2% | ECE | Δ vs A4 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        pd = result.get("paired_vs_A4", {}).get(r["variant"], {})
        delta = f"{pd['mean_delta']:+.3f}" if pd else "—"
        ece = "n/a" if r.get("ece") is None else f"{r['ece']:.3f}"
        harm = "n/a" if r.get("harmful_rate") is None else f"{r['harmful_rate']:.3f}"
        legacy_harm = "n/a" if r.get("harmful_gt_2pct_rate") is None else f"{r['harmful_gt_2pct_rate']:.3f}"
        lines.append(
            f"| `{r['variant']}` | {r['median_mean']:.3f} | {r['median_std']:.3f} | "
            f"{r['p90_median']:.3f} | {r['experiments_mean']:.1f} | "
            f"{r['proposal_coverage']:.4f} | {r['measured_transition_coverage']:.4f} | {harm} | {legacy_harm} | {ece} | {delta} |"
        )
    if "paired_vs_A4" in result:
        lines += [
            "",
            "Paired difference against `A4_gate`, plant by plant (negative = better "
            "than the gate-enabled, no-abstention reference):",
            "",
            "| variant | mean Δ | 95% CI | better | worse |",
            "| :--- | ---: | :--- | ---: | ---: |",
        ]
        for r in rows:
            pd = result["paired_vs_A4"].get(r["variant"])
            if not pd:
                continue
            lines.append(
                f"| `{r['variant']}` | {pd['mean_delta']:+.3f} | "
                f"[{pd['ci95'][0]:+.3f}, {pd['ci95'][1]:+.3f}] | "
                f"{pd['better_than_ref_pct']:.0f}% | {pd['worse_than_ref_pct']:.0f}% |"
            )
    lines += _reading(result, zh=False)
    lines += [
        "",
        "A0 is not a runtime path: `src/jev_tune` contains no direct-regression "
        "decoder. It exists only in `scripts/17_ablation.py`, because the project's "
        "claim is precisely that the typed path is worth its constraints, and that "
        "claim needs a control.",
        "",
        "---",
        "",
        "## 简体中文",
        "",
        "由 `python scripts/17_ablation.py` 生成。对照共享编码器结构、02_train训练划分、",
        "目标函数与预算上限；阶梯改变解码及可选保护。所有行返回历史实测最优。",
        "",
        f"* 每轮 {result['plants_per_draw']} 株验证族对象，共 {len(result['draws'])} 轮"
        f"（种子 {result['draws']}）",
        f"* 每株预算 {result['budget']} 次实验",
        "* 均值 ± 标准差是各轮中位代价的统计",
        "* 每种结构仅一个训练检查点；三个种子用于评测抽样，不代表训练种子重复",
        f"* A0复用{result['training_protocol']['training_states']:,}状态训练划分，保留有界连续输出；类型头沿用02_train协议的出厂检查点",
        "* 实验次数统计真实对象仿真，包含初始与末次测量",
        "* argmax复用同一分类检查点；这些对照比较预测器和解码规则，不证明把数组包装为类型容器本身产生性能收益",
        "* C0 MLP Regression / C1 Uncalibrated / C2 Temp Only / C3 Temp+CP共享起点、对象、预算上限与确定性安全门，均不使用pmax启发式阈值",
        "* C0保持连续期望且不做方差缩步；C1-C3共享期望/方差解码。只有C3启用CP，故C3与C2的差异隔离CP保持规则",
        "* A0-A6阶梯关闭CP；A5是旧pmax策略，不是当前出厂默认",
        "* 两种动作覆盖率均统计至少一轴获准的比例。提案覆盖率包含终止提案；已测转移覆盖率（JSON中的coverage别名）仅统计后续确有测量的策略决策，不含回滚。覆盖率取各轮均值，JSON中的计数为各轮合计",
        "* 全轴保持后立即终止的提案不进入已测转移分母。因此C5的已测转移覆盖率可以是1.0，同时仍拒绝部分提案；提案覆盖率会计入这些保持。二者均不是专家标签集合覆盖率，后者的独立评估保存在calibration_evidence",
        "* 主有害口径为严格after > before，零容差；旧口径保留after > 1.02 × before，供v0.6结果比较。两种比例均以至少一轴获准且实际测量的策略决策为分母，排除回滚和终止提案；均不是联合风险的无条件保证",
        "",
        "| 变体 | 中位 J | 标准差 | p90 | 实验次数 | 提案覆盖率 | 已测转移覆盖率 | 有害 >0 | 旧口径有害 >2% | ECE | 相对 A4 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        pd = result.get("paired_vs_A4", {}).get(r["variant"], {})
        delta = f"{pd['mean_delta']:+.3f}" if pd else "—"
        ece = "n/a" if r.get("ece") is None else f"{r['ece']:.3f}"
        harm = "n/a" if r.get("harmful_rate") is None else f"{r['harmful_rate']:.3f}"
        legacy_harm = "n/a" if r.get("harmful_gt_2pct_rate") is None else f"{r['harmful_gt_2pct_rate']:.3f}"
        lines.append(
            f"| `{r['variant']}` | {r['median_mean']:.3f} | {r['median_std']:.3f} | "
            f"{r['p90_median']:.3f} | {r['experiments_mean']:.1f} | "
            f"{r['proposal_coverage']:.4f} | {r['measured_transition_coverage']:.4f} | {harm} | {legacy_harm} | {ece} | {delta} |"
        )
    lines += _reading(result, zh=True)
    lines += [
        "",
        "A0 不是运行路径：`src/jev_tune` 里没有「直接回归增益」的解码器。它只存在于",
        "`scripts/17_ablation.py`，因为本项目的主张正是「类型化路径值得它的约束」，",
        "而这个主张需要一个对照。",
        "",
    ]
    return "\n".join(lines)


def _reading(result: dict, *, zh: bool) -> list[str]:
    """Numbers-to-sentence summary, so the doc cannot drift from the table."""
    by = {r["variant"]: r for r in result["rows"]}

    def m(name):
        return by[name]["median_mean"] if name in by else float("nan")

    def cov(name):
        return by[name]["coverage"] if name in by else float("nan")

    lines = ["", "**What the ladder says**" if not zh else "**阶梯说了什么**", ""]
    lines += conformal_evidence_lines(result.get('calibration_evidence', {}), zh=zh)
    if all(name in by for name in ("C0_MLP_regression", "C1_uncalibrated", "C2_temperature_only", "C3_temperature_CP")):
        for name in ("C0_MLP_regression", "C1_uncalibrated", "C2_temperature_only", "C3_temperature_CP", "C4_CP_monitor", "C5_CP_hold_stop"):
            r = by[name]
            set_size = 'n/a' if r.get('average_set_size') is None else f"{r['average_set_size']:.4f}"
            lines.append(
                f"* {name}: median {r['median_mean']:.4f}, p90 {r['p90_median']:.4f}, "
                f"{'回滚' if zh else 'rollbacks'} {r['rollbacks']}, "
                f"{'提案覆盖率' if zh else 'proposal coverage'} {r['proposal_coverage']:.4f} "
                f"(n={r['n_proposals']}), "
                f"{'已测转移覆盖率' if zh else 'measured transition coverage'} {r['measured_transition_coverage']:.4f} "
                f"(n={r['n_measured_policy_transitions']}), "
                f"{'闭环平均集合大小' if zh else 'rollout mean set size'} {set_size}."
            )
        pd = result.get("paired_vs_temperature_only", {}).get("C3_temperature_CP")
        if pd:
            lines.append(
                ("* CP相对Temp Only的配对平均代价差" if zh else "* CP minus Temp Only paired mean cost difference")
                + f" {pd['mean_delta']:+.4f}, 95% CI [{pd['ci95'][0]:+.4f}, {pd['ci95'][1]:+.4f}]."
            )
    if "A0_regress" in by and "A3_shrink" in by:
        d = m("A0_regress") - m("A3_shrink")
        if zh:
            lines.append(
                f"* 类型化路径相对同编码器结构的回归对照：A0 {m('A0_regress'):.3f} → "
                f"A3 {m('A3_shrink'):.3f}（中位代价差 {d:+.3f}），"
                f"p90 {by['A0_regress']['p90_median']:.3f} → "
                f"{by['A3_shrink']['p90_median']:.3f}。"
            )
        else:
            lines.append(
                f"* typed vs the matched-encoder regression control: A0 {m('A0_regress'):.3f} → "
                f"A3 {m('A3_shrink'):.3f} (median difference {d:+.3f}), "
                f"p90 {by['A0_regress']['p90_median']:.3f} → "
                f"{by['A3_shrink']['p90_median']:.3f}."
            )
    if "A3_shrink" in by and "A4_gate" in by:
        d = m("A3_shrink") - m("A4_gate")
        if zh:
            lines.append(
                f"* 确定性安全门单独贡献：A3 {m('A3_shrink'):.3f} → "
                f"A4 {m('A4_gate'):.3f}（{d:+.3f}），回滚 "
                f"{by['A3_shrink']['rollbacks']} → {by['A4_gate']['rollbacks']} 次。"
            )
        else:
            lines.append(
                f"* the deterministic gate alone: A3 {m('A3_shrink'):.3f} → "
                f"A4 {m('A4_gate'):.3f} ({d:+.3f}), rollbacks "
                f"{by['A3_shrink']['rollbacks']} → {by['A4_gate']['rollbacks']}."
            )
    if "A5_abstain" in by:
        d = m("A5_abstain") - m("A4_gate")
        if zh:
            lines.append(
                f"* 事前显式弃权：覆盖率 {cov('A5_abstain'):.2f}，中位代价相对 A4 "
                f"{d:+.3f}，零容差有害步比例 {by['A5_abstain']['harmful_rate']:.3f}，"
                f"旧口径>2%比例 {by['A5_abstain']['harmful_gt_2pct_rate']:.3f}。"
            )
        else:
            lines.append(
                f"* explicit abstention: coverage {cov('A5_abstain'):.2f}, median cost "
                f"vs A4 {d:+.3f}, zero-tolerance harmful-step rate "
                f"{by['A5_abstain']['harmful_rate']:.3f}, legacy >2% rate "
                f"{by['A5_abstain']['harmful_gt_2pct_rate']:.3f}."
            )
    if "A6_early_stop" in by:
        d = m("A6_early_stop") - m("A4_gate")
        if zh:
            lines.append(
                f"* 早停（按最便宜档 + noul）：实验次数 "
                f"{by['A6_early_stop']['experiments_mean']:.1f}，中位代价相对 A4 "
                f"{d:+.3f}；这是实验支出与最终代价的权衡，不给出通用取舍。"
            )
        else:
            lines.append(
                f"* early stop (best band + noul): {by['A6_early_stop']['experiments_mean']:.1f} "
                f"experiments, median cost vs A4 {d:+.3f}; this reports the tradeoff "
                "between experiment cost and final objective without a universal preference."
            )
    if "A2T_no_calib" in by and "A2_expect" in by:
        d = m("A2T_no_calib") - m("A2_expect")
        if zh:
            lines.append(
                f"* 旧阶梯的温度缩放对照：关掉与打开的中位代价差为 {d:+.3f}；不预设温度校准改善闭环代价。"
            )
        else:
            lines.append(
                f"* temperature scaling in the legacy ladder: off minus on median cost is {d:+.3f}; "
                "calibration is not assumed to improve closed-loop cost."
            )
    lines.append("")
    return lines


if __name__ == "__main__":
    main()
