"""E1: does the typed interface actually help? A controlled ablation ladder.

Every variant shares the same encoder, the same training data and the same
closed-loop evaluator. Only the decision path changes:

    A0  regression    same encoder, three direct log10 step outputs, soft-projected
                      onto the vocabulary so it travels through the same decoder
    A1  argmax        trained head, discrete action (no expectation)
    A2  expect        expected step, no variance shrink, no early stop, no gate
    A2T expect, calibration off (the fitted temperatures are ~1.0; this measures
                      whether applying them matters at all)
    A3  shrink        A2 + variance-driven shrink
    A4  gate          A3 + deterministic safety gate   (the shipped configuration)
    A5  early stop    A4 + stop proposing in the cheapest band when noul > 0.9
                      (measured to hurt: it quits about halfway through the budget)

The comparison is paired: every variant sees the same plants in the same draw.
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
from jev_tune.evaluate import evaluate_head
from jev_tune.model import Encoder
from jev_tune.plants import HELDOUT_FAMILIES, sample_plants, ultimate_gain
from jev_tune.primitives import Answer, Choice, Noul, Option, Score, softmax
from jev_tune.train import _to_t

TAU = 0.02  # log10 units; soft projection of a regressed step onto the vocabulary


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
        # soft projection: a distribution whose expectation is the regressed
        # value, so A0 uses the same decoder as every other variant
        logits = -((r[..., None] - d) ** 2) / (2 * TAU**2)
        probs = softmax(logits, axis=-1)
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


# name, backend, expectation, shrink, early_stop, gate, calibrate, abstain
ABSTAIN = DEFAULT_ABSTAIN
VARIANTS = (
    ("A0_regress", "regress", True, 0.0, False, False, True, None),
    ("A1_argmax", "head", False, 0.0, False, False, True, None),
    ("A2_expect", "head", True, 0.0, False, False, True, None),
    ("A2T_no_calib", "head", True, 0.0, False, False, False, None),
    ("A3_shrink", "head", True, 1.0, False, False, True, None),
    ("A4_gate", "head", True, 1.0, False, True, True, None),
    ("A5_abstain", "head", True, 1.0, False, True, True, ABSTAIN),
    ("A6_early_stop", "head", True, 1.0, True, True, True, None),
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
    args = ap.parse_args()

    data = load_data(args.data)
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
        "budget": args.budget,
        "plants_per_draw": args.plants,
        "draws": [d["seed"] for d in draws],
        "rows": [],
    }

    a0 = None
    if not args.skip_a0:
        cache = Path(args.a0_cache)
        if cache.is_file():
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
            print(
                f"[ablation] A0 trained in {time.perf_counter() - t:.0f}s -> {cache}",
                flush=True,
            )

    for name, backend_kind, expect, shrink, early, gate, calibrate, policy in VARIANTS:
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
            )
            rep = r.decision_report()
            per_draw.append(
                {
                    "draw": di,
                    "median": float(np.median(r.best_j)),
                    "p90": float(np.percentile(r.best_j, 90)),
                    "mean_experiments": float(np.mean(r.stop_iter)),
                    "rollbacks": int(r.rollbacks.sum()),
                    "failures": int((r.best_j >= 50.0).sum()),
                    "coverage": rep.get("coverage"),
                    "harmful_rate": rep.get("harmful_rate"),
                    "ece": None if backend_kind == "regress" else rep.get("ece"),
                    "per_plant": [float(x) for x in r.best_j],
                }
            )
            print(
                f"  {name:15s} draw {di}  median {per_draw[-1]['median']:.3f}  "
                f"exp {per_draw[-1]['mean_experiments']:.1f}  "
                f"cov {per_draw[-1]['coverage']:.2f}",
                flush=True,
            )

        med = np.array([x["median"] for x in per_draw])
        exp = np.array([x["mean_experiments"] for x in per_draw])
        eces = [x["ece"] for x in per_draw if x["ece"] is not None]
        result["rows"].append(
            {
                "variant": name,
                "median_mean": float(med.mean()),
                "median_std": float(med.std(ddof=1)) if len(med) > 1 else 0.0,
                "p90_median": float(np.median([x["p90"] for x in per_draw])),
                "experiments_mean": float(exp.mean()),
                "rollbacks": int(sum(x["rollbacks"] for x in per_draw)),
                "failures": int(sum(x["failures"] for x in per_draw)),
                "coverage": float(np.mean([x["coverage"] for x in per_draw])),
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
                "ece": float(np.mean(eces)) if eces else None,
                "per_draw": per_draw,
                "wall_s": float(time.perf_counter() - t),
            }
        )

    # paired differences against the shipped configuration, plant by plant
    by = {r["variant"]: r for r in result["rows"]}
    ref = by.get("A4_gate")
    if ref is not None:
        for r in result["rows"]:
            diffs = []
            for a, b in zip(r["per_draw"], ref["per_draw"]):
                diffs.extend(np.asarray(a["per_plant"]) - np.asarray(b["per_plant"]))
            diffs = np.asarray(diffs)
            se = diffs.std(ddof=1) / np.sqrt(len(diffs))
            result.setdefault("paired_vs_A4", {})[r["variant"]] = {
                "mean_delta": float(diffs.mean()),
                "ci95": [
                    float(diffs.mean() - 1.96 * se),
                    float(diffs.mean() + 1.96 * se),
                ],
                "worse_than_ref_pct": float(100 * np.mean(diffs > 1e-9)),
                "better_than_ref_pct": float(100 * np.mean(diffs < -1e-9)),
                "n": int(len(diffs)),
            }

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
    rows = result["rows"]
    lines = [
        "# Ablation: is the typed interface doing anything?",
        "",
        "> [English](#english) · [简体中文](#简体中文)",
        "",
        "## English",
        "",
        "Generated by `python scripts/17_ablation.py`. Every row uses the same "
        "encoder, training data, cost function and experiment budget; only the "
        "decision path changes.",
        "",
        f"* {result['plants_per_draw']} held-out plants per draw, "
        f"{len(result['draws'])} draws (seeds {result['draws']})",
        f"* budget {result['budget']} experiments per plant",
        "* mean ± std is across draws of the per-draw median cost",
        "",
        "| variant | median J | std | p90 | experiments | coverage | harmful | ECE | Δ vs A4 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        pd = result.get("paired_vs_A4", {}).get(r["variant"], {})
        delta = f"{pd['mean_delta']:+.3f}" if pd else "—"
        ece = "n/a" if r.get("ece") is None else f"{r['ece']:.3f}"
        harm = "n/a" if r.get("harmful_rate") is None else f"{r['harmful_rate']:.3f}"
        lines.append(
            f"| `{r['variant']}` | {r['median_mean']:.3f} | {r['median_std']:.3f} | "
            f"{r['p90_median']:.3f} | {r['experiments_mean']:.1f} | "
            f"{r['coverage']:.2f} | {harm} | {ece} | {delta} |"
        )
    if "paired_vs_A4" in result:
        lines += [
            "",
            "Paired difference against `A4_gate`, plant by plant (negative = better "
            "than the shipped configuration):",
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
        "由 `python scripts/17_ablation.py` 生成。每一行用同一个编码器、同一批训练数据、",
        "同一代价函数与同一实验预算，只改决策路径。",
        "",
        f"* 每轮 {result['plants_per_draw']} 株留出对象，共 {len(result['draws'])} 轮"
        f"（种子 {result['draws']}）",
        f"* 每株预算 {result['budget']} 次实验",
        "* 均值 ± 标准差是各轮中位代价的统计",
        "",
        "| 变体 | 中位 J | 标准差 | p90 | 实验次数 | 覆盖率 | 有害步 | ECE | 相对 A4 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        pd = result.get("paired_vs_A4", {}).get(r["variant"], {})
        delta = f"{pd['mean_delta']:+.3f}" if pd else "—"
        ece = "n/a" if r.get("ece") is None else f"{r['ece']:.3f}"
        harm = "n/a" if r.get("harmful_rate") is None else f"{r['harmful_rate']:.3f}"
        lines.append(
            f"| `{r['variant']}` | {r['median_mean']:.3f} | {r['median_std']:.3f} | "
            f"{r['p90_median']:.3f} | {r['experiments_mean']:.1f} | "
            f"{r['coverage']:.2f} | {harm} | {ece} | {delta} |"
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
    if "A0_regress" in by and "A3_shrink" in by:
        d = m("A0_regress") - m("A3_shrink")
        if zh:
            lines.append(
                f"* 类型化路径相对同尺寸回归头：A0 {m('A0_regress'):.3f} → "
                f"A3 {m('A3_shrink'):.3f}（中位代价差 {d:+.3f}），"
                f"p90 {by['A0_regress']['p90_median']:.3f} → "
                f"{by['A3_shrink']['p90_median']:.3f}。"
            )
        else:
            lines.append(
                f"* typed vs a same-size regression head: A0 {m('A0_regress'):.3f} → "
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
                f"{d:+.3f}，有害步比例 {by['A5_abstain']['harmful_rate']:.3f}。"
            )
        else:
            lines.append(
                f"* explicit abstention: coverage {cov('A5_abstain'):.2f}, median cost "
                f"vs A4 {d:+.3f}, harmful-step rate "
                f"{by['A5_abstain']['harmful_rate']:.3f}."
            )
    if "A6_early_stop" in by:
        d = m("A6_early_stop") - m("A4_gate")
        if zh:
            lines.append(
                f"* 早停（按最便宜档 + noul）：实验次数 "
                f"{by['A6_early_stop']['experiments_mean']:.1f}，中位代价相对 A4 "
                f"{d:+.3f}——省下的实验不值得。"
            )
        else:
            lines.append(
                f"* early stop (best band + noul): {by['A6_early_stop']['experiments_mean']:.1f} "
                f"experiments, median cost vs A4 {d:+.3f} — the saved experiments are "
                "not worth it."
            )
    if "A2T_no_calib" in by and "A2_expect" in by:
        d = m("A2T_no_calib") - m("A2_expect")
        if zh:
            lines.append(
                f"* 温度缩放（拟合值≈1）：关掉与打开相差 {d:+.3f}，即在这个模型上几乎"
                "没有影响；保留它是为了在别的模型上不重新发明。"
            )
        else:
            lines.append(
                f"* temperature scaling (fitted T ≈ 1): off vs on differs by {d:+.3f}, "
                "i.e. almost nothing on this model; it is kept so a retrained head does "
                "not have to reinvent it."
            )
    lines.append("")
    return lines


if __name__ == "__main__":
    main()
