"""Fixed, descriptive practical-budget comparison; no fitting or risk research.

The independently committed protocol controls every cohort and method setting.
Every real simulation is recorded; check() rebuilds summaries without simulation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import gzip
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "research/protocols/practical_budget_v090.json"
RESULT = "research/results/practical_budget.json"
RAW = "research/results/practical_budget_raw.json.gz"
DOC = "docs/PRACTICAL_BUDGET.md"
PREREGISTRATION_COMMIT = "f6aafde"
SOURCES = ["scripts/39_practical_budget.py"] + [
    f"src/jev_tune/{name}.py" for name in
    ("baselines", "evaluate", "plants", "scenarios", "state", "metrics", "model",
     "decision", "decode", "primitives")
]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cohorts(protocol):
    from jev_tune.plants import sample_plants, make_plant
    from jev_tune.scenarios import _stack, variants

    first, thermal, outside = protocol["cohorts"]
    groups = [(first["name"], "two_mass", sample_plants(first["n"], seed=first["seed"],
        families=("two_mass",), heldout=first["heldout"]))]
    anchors = sample_plants(thermal["n"], families=("thermal_deadtime",))
    rng = np.random.default_rng(thermal["seed"])
    thermal_plants = []
    for i, params in enumerate(anchors.params):
        factors = rng.uniform(.9, 1.1, size=2)
        thermal_plants.append(make_plant([1.], [params["T"] * factors[0], 1.],
            delay_s=params["L"] * factors[1], u_min=float(anchors.u_min[i]),
            u_max=float(anchors.u_max[i]), name="thermal_jitter"))
    groups.append((thermal["name"], "thermal_jitter", _stack(thermal_plants)))
    for name in outside["scenarios"]:
        groups.append((name, "out_of_zoo", variants(name, 4, seed=outside["seed"])))
    return groups


def plant_record(plants, i):
    values = {key: np.asarray(getattr(plants, key)[i]).tolist()
        for key in ("num", "den", "a", "b", "c", "d", "delay_s", "u_min", "u_max")}
    values.update(family=plants.family[i], noise_seed=int(plants.noise_seed[i]),
        noise_sigma=0. if plants.noise_sigma is None else float(plants.noise_sigma[i]),
        dead_zone=0. if plants.dead_zone is None else float(plants.dead_zone[i]))
    return {"id": hashlib.sha256(canonical(values)).hexdigest(), "physical": values}


@contextmanager
def capture_simulations(module, plants):
    """Observe real calls through the method's simulator, without extra runs."""
    from jev_tune.metrics import cost_from_metrics, is_failed, DIVERGED_J

    original = module.simulate
    indices = {int(seed): i for i, seed in enumerate(plants.noise_seed)}
    if len(indices) != plants.n:
        raise ValueError("cohort contains repeated plant noise identities")
    trials = [[] for _ in range(plants.n)]
    batches = []

    def measured(subplants, gains, **kwargs):
        result = original(subplants, gains, **kwargs)
        normalization = {key: kwargs[key] for key in ("horizon", "ref") if key in kwargs}
        costs = cost_from_metrics(result["metrics"], y_curve=result["y_curve"], **normalization)
        failed = is_failed(result["metrics"], result["y_curve"], ref=kwargs.get("ref", 1.))
        plant_indices = [indices[int(seed)] for seed in subplants.noise_seed]
        batches.append(plant_indices)
        for row, index in enumerate(plant_indices):
            trials[index].append({"gains": np.asarray(gains[row]).tolist(),
                "J": float(costs[row]), "failed": bool(failed[row]),
                "diverged": bool(costs[row] >= DIVERGED_J)})
        return result

    module.simulate = measured
    try:
        yield trials, batches
    finally:
        module.simulate = original


def run_method(protocol, backend, plants, method, budget):
    import jev_tune.baselines as baseline
    import jev_tune.evaluate as evaluation

    start = np.tile(protocol["shared_start"], (plants.n, 1))
    settings = protocol["method_settings"]
    module = evaluation if method == "jev_head" else baseline
    begin = time.perf_counter()
    with capture_simulations(module, plants) as (trials, batches):
        if method == "jev_head":
            r = evaluation.evaluate_head(backend, plants, start, np.ones(plants.n),
                np.ones(plants.n), budget=budget, init_scale=0., record=True,
                seed=settings[method]["seed"], value=None, use_value_filter=False,
                safety_gate=True, stop_on_no_action=True, early_stop=False)
        elif method == "vocab_hill":
            r = baseline.run_vocab_hill(plants, start, budget=budget)
        elif method == "cmaes":
            r = baseline.run_cmaes(plants, start, budget=budget,
                lam=settings[method]["lam"], seed=settings[method]["seed"])
        elif method == "simplex":
            r = baseline.run_simplex(plants, start, budget=budget, step=settings[method]["step"])
        else:
            raise ValueError(method)
    actual = (r.actual_simulations if method == "jev_head" else
        np.full(plants.n, int(r.eval_axis[-1])))
    rows = []
    for i in range(plants.n):
        rows.append({"index": i, "trials": trials[i], "actual_calls": len(trials[i]),
            "reported_calls": int(actual[i]), "returned_J": float(r.best_j[i]),
            "returned_gains": r.gains[i].tolist(),
            "stop_reason": str(r.stop_reason[i]) if method == "jev_head" else "budget",
            "rollbacks": int(r.rollbacks[i]) if method == "jev_head" else None})
    return {"method": method, "budget": budget, "plants": rows,
        "simulation_batches": batches, "wall_s": time.perf_counter() - begin}


def _summarize(rows):
    final = np.array([p["returned_J"] for p in rows])
    initial = np.array([p["trials"][0]["J"] for p in rows])
    counts = np.array([p["actual_calls"] for p in rows])
    worst = np.array([max(t["J"] for t in p["trials"]) for p in rows])
    final_trial = [next(t for t in p["trials"] if t["J"] == p["returned_J"] and
        t["gains"] == p["returned_gains"]) for p in rows]
    return {"n": len(rows), "final_J_mean": float(final.mean()),
        "final_J_median": float(np.median(final)), "final_J_p90": float(np.quantile(final, .9)),
        "initial_J_mean": float(initial.mean()), "improved_plants": int((final < initial).sum()),
        "median_relative_improvement": float(np.median(1-final/np.maximum(initial, 1e-12))),
        "actual_calls_total": int(counts.sum()), "actual_calls_mean": float(counts.mean()),
        "actual_calls_min": int(counts.min()), "actual_calls_max": int(counts.max()),
        "worst_trial_J_max": float(worst.max()), "worst_trial_J_p90": float(np.quantile(worst, .9)),
        "plants_with_trial_worse_than_start": int((worst > initial).sum()),
        "plants_with_failed_trial": sum(any(t["failed"] for t in p["trials"]) for p in rows),
        "plants_with_divergent_trial": sum(any(t["diverged"] for t in p["trials"]) for p in rows),
        "returned_failed_plants": sum(t["failed"] for t in final_trial),
        "returned_divergent_plants": sum(t["diverged"] for t in final_trial)}


def summarize(raw, protocol):
    """Independently validate the ledger and derive all report numbers."""
    expected = {(c["name"], method, budget) for c in raw["cohorts"]
        for method in protocol["methods"] for budget in protocol["budgets"]}
    observed = set()
    cohorts_by_name = {c["name"]: c for c in raw["cohorts"]}
    if sum(len(c["plants"]) for c in raw["cohorts"]) != protocol["n_plants"]:
        raise ValueError("cohort size differs from protocol")
    for c in raw["cohorts"]:
        for p in c["plants"]:
            if hashlib.sha256(canonical(p["physical"])).hexdigest() != p["id"]:
                raise ValueError("plant identity differs from recorded physical parameters")
    initial_costs = {}
    grouped = {}
    paired = {}
    total = 0
    for run in raw["runs"]:
        key = (run["cohort"], run["method"], run["budget"])
        if key not in expected or key in observed:
            raise ValueError("unexpected or duplicate run")
        observed.add(key)
        c = cohorts_by_name[run["cohort"]]
        if len(run["plants"]) != len(c["plants"]):
            raise ValueError("missing plants")
        batch_counts = np.bincount([i for batch in run["simulation_batches"] for i in batch],
            minlength=len(run["plants"]))
        for i, p in enumerate(run["plants"]):
            trials = p["trials"]
            if p["index"] != i or not 1 <= len(trials) <= run["budget"]:
                raise ValueError("plant order or simulation budget violated")
            if len(trials) != p["actual_calls"] or p["actual_calls"] != p["reported_calls"] or batch_counts[i] != p["actual_calls"]:
                raise ValueError("actual simulation accounting mismatch")
            if trials[0]["gains"] != protocol["shared_start"]:
                raise ValueError("first measured point is not the common start")
            initial_key = (run["cohort"], i)
            if initial_key in initial_costs and initial_costs[initial_key] != trials[0]["J"]:
                raise ValueError("common starting cost differs between paired runs")
            initial_costs[initial_key] = trials[0]["J"]
            gains = np.array([t["gains"] for t in trials])
            lo, hi = protocol["gain_bounds"]
            if not np.isfinite(gains).all() or (gains < lo).any() or (gains > hi).any():
                raise ValueError("measured gain outside common bounds")
            if not all(np.isfinite(t["J"]) for t in trials):
                raise ValueError("non-finite measured cost")
            if p["returned_J"] != min(t["J"] for t in trials):
                raise ValueError("returned cost is not the measured best")
            if not any(t["J"] == p["returned_J"] and t["gains"] == p["returned_gains"] for t in trials):
                raise ValueError("returned gains have no matching measured best cost")
            total += len(trials)
        for group in dict.fromkeys(["all", c["group"], c["name"]]):
            bucket = grouped.setdefault((group, run["method"], run["budget"]), [])
            bucket.extend(run["plants"])
        paired[key] = run["plants"]
    if observed != expected or total > protocol["accounting"]["maximum_simulations"]:
        raise ValueError("incomplete protocol or overall budget exceeded")
    rows = [{"group": group, "method": method, "budget": budget, **_summarize(plants)}
        for (group, method, budget), plants in sorted(grouped.items())]
    differences = []
    for budget in protocol["budgets"]:
        for method in protocol["methods"][1:]:
            deltas, calls = [], []
            for c in raw["cohorts"]:
                head = paired[(c["name"], "jev_head", budget)]
                other = paired[(c["name"], method, budget)]
                deltas.extend(h["returned_J"]-b["returned_J"] for h, b in zip(head, other))
                calls.extend(h["actual_calls"]-b["actual_calls"] for h, b in zip(head, other))
            d = np.asarray(deltas)
            differences.append({"budget": budget, "baseline": method, "n": len(d),
                "head_minus_baseline_J_mean": float(d.mean()),
                "head_minus_baseline_J_median": float(np.median(d)),
                "head_better_plants": int((d < 0).sum()), "equal_plants": int((d == 0).sum()),
                "head_worse_plants": int((d > 0).sum()),
                "head_minus_baseline_calls_mean": float(np.mean(calls))})
    return {"actual_simulations": total, "maximum_simulations": protocol["accounting"]["maximum_simulations"],
        "n_plants": protocol["n_plants"], "rows": rows, "paired_comparisons": differences,
        "numerical_invariants": {"all_measured_starts_equal": True, "all_actual_counts_within_budget": True,
            "all_gains_within_common_bounds": True, "all_returned_gains_measured_at_reported_best": True}}


def render(report):
    summary = report["summary"]
    all_rows = [r for r in summary["rows"] if r["group"] == "all"]
    table = ["| budget | method | mean / median / p90 J | actual calls mean (min–max) | final failed | trial divergence |", "| ---: | :--- | ---: | ---: | ---: | ---: |"]
    for r in sorted(all_rows, key=lambda r: (r["budget"], r["method"])):
        table.append(f"| {r['budget']} | {r['method']} | {r['final_J_mean']:.6f} / {r['final_J_median']:.6f} / {r['final_J_p90']:.6f} | {r['actual_calls_mean']:.3f} ({r['actual_calls_min']}–{r['actual_calls_max']}) | {r['returned_failed_plants']}/{r['n']} | {r['plants_with_divergent_trial']}/{r['n']} |")
    boundary = ["| group, budget 20 | head J | hill J | CMA J | simplex J | head actual calls | head failed |", "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    indexed = {(r["group"], r["method"], r["budget"]): r for r in summary["rows"]}
    groups = sorted({r["group"] for r in summary["rows"] if r["group"] not in ("all", "out_of_zoo")})
    for group in groups:
        head = indexed[(group, "jev_head", 20)]
        cells = " | ".join(f"{indexed[(group, method, 20)]['final_J_mean']:.6f}" for method in report["protocol"]["methods"])
        boundary.append(f"| {group} (n={head['n']}) | {cells} | {head['actual_calls_mean']:.3f} | {head['returned_failed_plants']}/{head['n']} |")
    paired = ["| budget | baseline | head − baseline mean J | head better / equal / worse | head − baseline mean calls |", "| ---: | :--- | ---: | ---: | ---: |"]
    for r in summary["paired_comparisons"]:
        paired.append(f"| {r['budget']} | {r['baseline']} | {r['head_minus_baseline_J_mean']:.6f} | {r['head_better_plants']} / {r['equal_plants']} / {r['head_worse_plants']} | {r['head_minus_baseline_calls_mean']:.3f} |")
    tables = "\n".join(table)+"\n\n"+"\n".join(boundary)+"\n\n"+"\n".join(paired)
    return f"""# Practical simulation budgets / 实用仿真预算

[English](#english) · [简体中文](#简体中文)

## English

This descriptive check keeps the existing model and runtime settings. It spends {summary['actual_simulations']} actual simulations against a preregistered maximum of {summary['maximum_simulations']}; each arm's initial measurement is included. The protocol was committed as `{report['preregistration_commit']}` before execution. No training, parameter selection, reference optimization or additional verification simulations were performed.

All four methods start at PID gains `[0.6, 1.2, 0.075]`, use bounds `[0.0001, 1000]`, and reset the same simulator for a 10-second unit-step response. The head receives fixed assumed Ku=Tu=1, not an analytic oracle or a successful identification. Budgets 4, 8 and 20 are separate runs. CP is monitoring only. The cohorts contain 12 fresh two-mass draws, 12 seeded jitters of known thermal anchors and four fresh variants of each of ten existing out-of-zoo scenarios. These are known families, not a new independent family-level validation. Thermal T and delay each vary by ±10%; scenario numerator and one denominator coefficient each vary by a factor 10**U(-0.3,0.3), and delay by ±20%.

Lower returned J is better; compare it together with actual calls. Fewer calls alone is not success. A failed response follows `metrics.is_failed` (absolute final error >0.5, nonfinite error or sampled output magnitude >12); divergence uses the simulator cost sentinel J≥50. Failed starts, trials and returned controllers are retained. Returning the best measured point cannot prove safe exploration. Trial-worse-than-start counts and worst trial costs are also available per group in JSON; they are simulation diagnostics, not a trajectory-risk guarantee. The pooled mean weights each plant equally and the small scenario groups have only four plants.

{tables}

All cost differences are paired by object; negative head-minus-baseline J means lower head cost. Boundary-table J is the group mean. There is no significance test, superiority acceptance, deployment gate or CP/PAC guarantee. The fixed starting point may be poor and these numbers do not establish benefit with accurate user priors, a new objective, arbitrary Simulink models or hardware. Numerical batch layout and the reference environment are recorded; cross-platform bitwise trajectory reproduction is not claimed.

Sources: [protocol](../{PROTOCOL}), [summary](../{RESULT}), [complete measured ledger](../{RAW}). After freezing the protocol and code, `python scripts/39_practical_budget.py --run` writes new artifacts and refuses existing output. Use `--output-root <new-directory>` for a separate replay. `python scripts/39_practical_budget.py --check` validates protocol/source/model/raw hashes, all real-call and measured-best invariants, raw-derived summaries, and this bilingual document without running a simulation. No historical scientific result is overwritten.

## 简体中文

本描述性检查固定现有模型与运行设置，共实测{summary['actual_simulations']}次仿真，协议上限为{summary['maximum_simulations']}次，每臂初测均在预算内。协议在执行前独立提交为`{report['preregistration_commit']}`。没有训练、选参、参考优化或额外复测。

四种方法均从PID增益`[0.6, 1.2, 0.075]`出发，范围为`[0.0001, 1000]`，使用同一重置仿真器的10秒单位阶跃响应。head的Ku=Tu=1是固定假设，不来自解析真值或成功辨识。4、8、20次预算分别真实运行；CP仅监测。对象包括12个新双质量参数实例、12个已知热工锚点的固定种子扰动，以及十个既有域外场景各4个新变体。这些是已知族，不能称新的独立族级验证。热工T和延时分别±10%；场景分子及一个分母系数分别乘10**U(-0.3,0.3)，延时±20%。

返回代价J越低越好，必须与实际次数一起看，少调用本身不代表成功。失败响应沿用`metrics.is_failed`：末值绝对误差>0.5、非有限误差或采样输出幅值>12；发散沿用J≥50代价标志。差初态、失败试验和失败返回全部保留。返回实测最优不保证探索安全。JSON还按组列出试验比初态更差的株数及最差试验代价，属于仿真诊断而非轨迹风险保证。总体均值每株等权，每个域外场景仅4株。

{tables}

代价差按对象配对；head减基线J为负表示head代价更低。边界表列组内平均J。没有显著性检验、优越性验收、部署开关或CP/PAC保证。固定起点可能很差，结果不能外推到准确用户先验、新目标函数、任意Simulink模型或硬件。记录数值批布局和参考环境，不宣称跨平台逐位轨迹复现。

来源：[协议](../{PROTOCOL})、[汇总](../{RESULT})、[完整逐次实测账本](../{RAW})。协议与代码冻结后运行`python scripts/39_practical_budget.py --run`，若输出已存在则拒绝覆盖；另用`--output-root <new-directory>`单独复现。`python scripts/39_practical_budget.py --check`不运行仿真，检查协议/源码/模型/原始账本hash、真实次数与返回实测最优约束、由原始账本重算的汇总及本双语文档。旧科学结果不覆盖。
"""


def check(root=ROOT, output_root=None):
    root = Path(root)
    output_root = Path(output_root) if output_root else root
    errors = []
    try:
        report = load(output_root/RESULT)
        protocol = load(root/PROTOCOL)
        if report["protocol"] != protocol or report["protocol_sha256"] != sha(root/PROTOCOL):
            errors.append("protocol content/hash mismatch")
        if report["preregistration_commit"] != PREREGISTRATION_COMMIT:
            errors.append("preregistration commit differs")
        for path, digest in report["source_sha256"].items():
            if sha(root/path) != digest:
                errors.append(f"source mismatch: {path}")
        if set(report["source_sha256"]) != set(SOURCES):
            errors.append("incomplete source manifest")
        for path, digest in report["model_sha256"].items():
            if sha(root/path) != digest:
                errors.append(f"model mismatch: {path}")
        if set(report["model_sha256"]) != {"models/jev_head.pt", "models/calibration.json"}:
            errors.append("incomplete model manifest")
        if report["raw_sha256"] != sha(output_root/RAW):
            errors.append("raw hash mismatch")
        with gzip.open(output_root/RAW, "rt", encoding="utf-8") as stream:
            raw = json.load(stream)
        if raw["protocol_sha256"] != report["protocol_sha256"] or raw["source_sha256"] != report["source_sha256"] or raw["model_sha256"] != report["model_sha256"]:
            errors.append("raw provenance mismatch")
        if summarize(raw, protocol) != report["summary"]:
            errors.append("raw-derived summary mismatch")
        if (output_root/DOC).read_text(encoding="utf-8") != render(report):
            errors.append("generated document mismatch")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    return errors


def run(root=ROOT, output_root=None):
    import scipy
    import torch
    from jev_tune.decision import load_backend

    root = Path(root)
    output_root = Path(output_root) if output_root else root
    for path in (RESULT, RAW, DOC):
        if (output_root/path).exists():
            raise FileExistsError(f"refusing to overwrite {output_root/path}")
    protocol = load(root/PROTOCOL)
    committed_protocol = subprocess.check_output(["git", "show", f"{PREREGISTRATION_COMMIT}:{PROTOCOL}"], cwd=root)
    if json.loads(committed_protocol) != protocol:
        raise ValueError("protocol differs from the independently committed preregistration")
    torch.set_num_threads(1)
    backend = load_backend(root/"models")
    if backend.conformal is None or backend.conformal.mode != "monitor":
        raise ValueError("protocol requires the production CP monitor backend")
    provenance = {"protocol_sha256": sha(root/PROTOCOL),
        "source_sha256": {p: sha(root/p) for p in SOURCES},
        "model_sha256": {p: sha(root/p) for p in ("models/jev_head.pt", "models/calibration.json")}}
    raw = {"schema_version": 1, **provenance, "cohorts": [], "runs": []}
    for name, group, plants in cohorts(protocol):
        raw["cohorts"].append({"name": name, "group": group,
            "plants": [plant_record(plants, i) for i in range(plants.n)]})
        for budget in protocol["budgets"]:
            for method in protocol["methods"]:
                result = run_method(protocol, backend, plants, method, budget)
                result["cohort"] = name
                raw["runs"].append(result)
                print(json.dumps({"cohort": name, "method": method, "budget": budget,
                    "calls": sum(p["actual_calls"] for p in result["plants"]),
                    "mean_J": float(np.mean([p["returned_J"] for p in result["plants"]]))}), flush=True)
    summary = summarize(raw, protocol)
    if provenance["source_sha256"] != {p: sha(root/p) for p in SOURCES}:
        raise ValueError("source changed during evaluation")
    for path in (RESULT, RAW, DOC):
        (output_root/path).parent.mkdir(parents=True, exist_ok=True)
    with (output_root/RAW).open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped:
            zipped.write(canonical(raw))
    report = {"schema_version": 1, "study_id": protocol["study_id"], "status": "descriptive_completed",
        "preregistration_commit": PREREGISTRATION_COMMIT,
        "execution_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        **provenance, "protocol": protocol, "raw_path": RAW, "raw_sha256": sha(output_root/RAW),
        "environment": {"platform": platform.platform(), "python": sys.version, "numpy": np.__version__,
            "scipy": scipy.__version__, "torch": torch.__version__, "torch_threads": torch.get_num_threads()},
        "summary": summary}
    (output_root/RESULT).write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    (output_root/DOC).write_text(render(report), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--run", action="store_true")
    action.add_argument("--check", action="store_true")
    action.add_argument("--render-only", action="store_true")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    if args.check:
        errors = check(output_root=args.output_root)
        print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
        raise SystemExit(bool(errors))
    if args.render_only:
        (ROOT/DOC).write_text(render(load(ROOT/RESULT)), encoding="utf-8")
    else:
        report = run(output_root=args.output_root)
        print(json.dumps({"actual_simulations": report["summary"]["actual_simulations"],
            "maximum_simulations": report["summary"]["maximum_simulations"]}))


if __name__ == "__main__":
    main()
