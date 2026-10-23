"""E2: how much should the head be allowed to hold, and is holding worth it?

The abstention threshold is policy, not physics.  This script sweeps
`AbstainPolicy.tau_act` on one held-out draw, reports coverage against final
cost and the harmful-step rate, picks a threshold by a stated rule, then
**validates that threshold on two draws it was not chosen on**.

    python scripts/20_abstention.py --plants 120 --draws 3

Outputs `research/results/abstention.json` and `docs/ABSTENTION.md`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from jev_tune.decision import load_backend
from jev_tune.decode import AbstainPolicy
from jev_tune.evaluate import evaluate_head
from jev_tune.plants import HELDOUT_FAMILIES, sample_plants, ultimate_gain

GRID = (None, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70)


def _draw(seed: int, n: int) -> dict:
    plants = sample_plants(n, seed=seed, families=HELDOUT_FAMILIES, heldout=True)
    ku, tu = ultimate_gain(plants)
    gzn = np.column_stack([0.6 * ku, 1.2 * ku / tu, 0.075 * ku * tu])
    return {"seed": seed, "plants": plants, "ku": ku, "tu": tu, "gzn": gzn}


def _run(backend, d, tau):
    policy = (
        None
        if tau is None
        else AbstainPolicy(tau_act=tau, tau_esc=max(0.0, tau - 0.10))
    )
    r = evaluate_head(
        backend,
        d["plants"],
        d["gzn"],
        d["ku"],
        d["tu"],
        budget=20,
        seed=d["seed"],
        abstain=policy,
    )
    rep = r.decision_report()
    return {
        "tau_act": tau,
        "coverage": rep.get("coverage"),
        "abstain_rate": rep.get("abstain_rate"),
        "harmful_rate": rep.get("harmful_rate"),
        "improvement_rate": rep.get("improvement_rate"),
        "ece": rep.get("ece"),
        "median": float(np.median(r.best_j)),
        "p90": float(np.percentile(r.best_j, 90)),
        "failures": int((r.best_j >= 50.0).sum()),
        "per_plant": [float(x) for x in r.best_j],
        "confidence_mean": float(np.mean(r.decisions["confidence"])),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plants", type=int, default=120)
    ap.add_argument("--draws", type=int, default=3)
    ap.add_argument("--seed0", type=int, default=7)
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="research/results/abstention.json")
    ap.add_argument("--doc", default="docs/ABSTENTION.md")
    args = ap.parse_args()

    backend = load_backend(args.models)
    draws = [_draw(args.seed0 + 10 * i, args.plants) for i in range(args.draws)]
    print(f"[abstain] {args.draws} draws x {args.plants} plants", flush=True)

    sweep = []
    for tau in GRID:
        row = _run(backend, draws[0], tau)
        sweep.append(row)
        print(
            f"  tau={str(tau):>5}  coverage {row['coverage']:.2f}  "
            f"median {row['median']:.3f}  p90 {row['p90']:.3f}  "
            f"harmful {row['harmful_rate']:.3f}  ece {row['ece']:.3f}",
            flush=True,
        )

    # selection rule, stated before the validation runs: minimise median cost
    # among thresholds that still execute at least half of the proposals.
    eligible = [r for r in sweep if r["coverage"] is not None and r["coverage"] >= 0.5]
    chosen = min(eligible, key=lambda r: r["median"]) if eligible else sweep[0]
    tau_star = chosen["tau_act"]
    print(
        f"[abstain] chosen tau_act={tau_star} (rule: coverage >= 0.50, lowest median)"
    )

    validation = []
    for d in draws:
        for tau in (None, tau_star):
            row = _run(backend, d, tau)
            row["draw_seed"] = d["seed"]
            validation.append(row)
            print(
                f"  validate seed {d['seed']} tau={str(tau):>5}  "
                f"coverage {row['coverage']:.2f}  median {row['median']:.3f}  "
                f"harmful {row['harmful_rate']:.3f}",
                flush=True,
            )

    def summarise(tau):
        rows = [r for r in validation if r["tau_act"] == tau]
        return {
            "tau_act": tau,
            "median_mean": float(np.mean([r["median"] for r in rows])),
            "median_std": float(np.std([r["median"] for r in rows], ddof=1))
            if len(rows) > 1
            else 0.0,
            "coverage": float(np.mean([r["coverage"] for r in rows])),
            "harmful_rate": float(np.mean([r["harmful_rate"] for r in rows])),
            "ece": float(np.mean([r["ece"] for r in rows])),
            "failures": int(sum(r["failures"] for r in rows)),
        }

    summary = [summarise(None), summarise(tau_star)]
    payload = {
        "plants_per_draw": args.plants,
        "draws": [d["seed"] for d in draws],
        "sweep_draw_seed": draws[0]["seed"],
        "selection_rule": "among tau with coverage >= 0.50, lowest median cost",
        "chosen_tau_act": tau_star,
        "sweep": [{k: v for k, v in r.items() if k != "per_plant"} for r in sweep],
        "validation": [
            {k: v for k, v in r.items() if k != "per_plant"} for r in validation
        ],
        "summary": summary,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    Path(args.doc).write_text(_doc(payload), encoding="utf-8")
    print(f"[abstain] wrote {args.out} and {args.doc}")


def _doc(p: dict) -> str:
    s0, s1 = p["summary"][0], p["summary"][1]
    tau = p["chosen_tau_act"]
    lines = [
        "# Explicit abstention: coverage against cost",
        "",
        "> [English](#english) · [简体中文](#简体中文)",
        "",
        "## English",
        "",
        "Generated by `python scripts/20_abstention.py`. The head may hold an axis",
        "(`delta = 0`, gains unchanged) when the calibrated `p_max` is below",
        "`tau_act`. `tau_act` was swept on draw 0 and then validated on all draws,",
        "including the one it was chosen on.",
        "",
        f"* {p['plants_per_draw']} held-out plants per draw, draws {p['draws']}",
        f"* selection rule: {p['selection_rule']}",
        f"* chosen `tau_act` = **{tau}**",
        "",
        "| tau_act | coverage | median J | p90 | harmful steps | ECE |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in p["sweep"]:
        tau_s = "off" if r["tau_act"] is None else f"{r['tau_act']:.2f}"
        lines.append(
            f"| {tau_s} | {r['coverage']:.2f} | {r['median']:.3f} | {r['p90']:.3f} | "
            f"{r['harmful_rate']:.3f} | {r['ece']:.3f} |"
        )
    lines += [
        "",
        "Validation (mean over the draws):",
        "",
        "| policy | median J | coverage | harmful steps | ECE | diverged |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
        f"| no abstention | {s0['median_mean']:.3f} ± {s0['median_std']:.3f} | "
        f"{s0['coverage']:.2f} | {s0['harmful_rate']:.3f} | {s0['ece']:.3f} | "
        f"{s0['failures']} |",
        f"| `tau_act={tau}` | {s1['median_mean']:.3f} ± {s1['median_std']:.3f} | "
        f"{s1['coverage']:.2f} | {s1['harmful_rate']:.3f} | {s1['ece']:.3f} | "
        f"{s1['failures']} |",
        "",
        "**How to read it.** The confidence of this head sits in a narrow band",
        "(the calibration table in `STEP1_RESULTS.md` shows 7-way accuracy around",
        "0.67), so a high threshold holds almost everything and a low one almost",
        "nothing. The table is the honest version of that trade-off: coverage is",
        "what you give up, the harmful-step rate is what you buy, and the median",
        "cost is the net. An abstention rule that lowers the median cost *and*",
        "keeps coverage is worth shipping; one that only lowers the harmful rate",
        "while making the median worse is a safety knob, not a better tuner, and",
        "should be described that way.",
        "",
        "---",
        "",
        "## 简体中文",
        "",
        "由 `python scripts/20_abstention.py` 生成。当校准后的 `p_max` 低于 `tau_act`",
        "时，决策头可以**弃权**（`delta = 0`，增益保持不变）。`tau_act` 在第 0 轮上扫描，",
        "再在所有轮上验证（包括选择时用过的那一轮）。",
        "",
        f"* 每轮 {p['plants_per_draw']} 株留出对象，轮次 {p['draws']}",
        f"* 选择规则：{p['selection_rule']}",
        f"* 选定 `tau_act` = **{tau}**",
        "",
        "| tau_act | 覆盖率 | 中位 J | p90 | 有害步比例 | ECE |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in p["sweep"]:
        tau_s = "关闭" if r["tau_act"] is None else f"{r['tau_act']:.2f}"
        lines.append(
            f"| {tau_s} | {r['coverage']:.2f} | {r['median']:.3f} | {r['p90']:.3f} | "
            f"{r['harmful_rate']:.3f} | {r['ece']:.3f} |"
        )
    lines += [
        "",
        "验证（各轮均值）：",
        "",
        "| 策略 | 中位 J | 覆盖率 | 有害步比例 | ECE | 发散数 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
        f"| 不弃权 | {s0['median_mean']:.3f} ± {s0['median_std']:.3f} | "
        f"{s0['coverage']:.2f} | {s0['harmful_rate']:.3f} | {s0['ece']:.3f} | "
        f"{s0['failures']} |",
        f"| `tau_act={tau}` | {s1['median_mean']:.3f} ± {s1['median_std']:.3f} | "
        f"{s1['coverage']:.2f} | {s1['harmful_rate']:.3f} | {s1['ece']:.3f} | "
        f"{s1['failures']} |",
        "",
        "**怎么读。** 这个决策头的置信度落在一个很窄的区间里（`STEP1_RESULTS.md` 的校准表",
        "显示 7 选一准确率约 0.67），所以阈值定高几乎全部弃权，定低几乎不弃权。上表是",
        "这个权衡的诚实版本：覆盖率是你付出的，有害步比例是你换来的，中位代价是净结果。",
        "如果一条弃权规则既降低中位代价又保住覆盖率，那它值得发布；如果它只降低有害步",
        "比例却让中位代价变差，那它是安全旋钮，不是更好的调参器——就应该照这个说法写。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
