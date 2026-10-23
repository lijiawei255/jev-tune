"""A real LLM-agent baseline: same plant, same budget, same parser.

The README compares against an "agent in the loop" whose latency was an
assumption.  This script replaces the assumption with a measurement: it asks a
hosted model (Together AI, `zai-org/GLM-5.3-Flash`) for the next gain step once
per experiment, exactly like an agent with a MATLAB tool would.

Fairness contract
-----------------
* same plants, same 20-experiment budget, same cost function as `03_evaluate.py`
* the model gets the same information the decision head gets (metrics + the last
  few actions), rendered as JSON rather than as tensors
* it must answer with three integers (multiplicative % steps); unparseable
  answers count as "hold" and are reported, not retried silently
* every request and response is logged to the JSON next to the result

Run:  python scripts/14_agent_baseline.py --plants 2 --iters 20
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import torch

from jev_tune.evaluate import evaluate_head
from jev_tune.metrics import cost_from_metrics
from jev_tune.model import JevHead
from jev_tune.plants import HELDOUT_FAMILIES, sample_plants, simulate, ultimate_gain

API = "https://api.together.ai/v1/chat/completions"
MODEL = "zai-org/GLM-5.3-Flash"
UA = "jev-tune-agent-baseline/1.0 (+https://github.com/lijiawei255/jev-tune)"

PROMPT = """You are tuning a PID controller on a simulated plant.
The plant is unknown to you. Each experiment applies gains, runs a step, and
reports the response metrics.

Current state (JSON):
{state}

Answer with exactly three integers, the percentage change to apply to each gain,
chosen from [-20, -10, 0, +10, +20]:
KP=<int> KI=<int> KD=<int>
No other text."""


def _find_cli() -> str | None:
    import shutil

    for name in ("opencode.exe", "opencode-cli.exe"):
        p = shutil.which(name)
        if p:
            return p
    base = Path(os.environ.get("APPDATA", "")) / "ai.opencode.desktop" / "cli"
    if base.is_dir():
        for d in sorted(base.iterdir(), reverse=True):
            exe = d / "opencode-cli.exe"
            if exe.is_file():
                return str(exe)
    return None


def get_key() -> str:
    key = os.environ.get("TOGETHER_API_KEY")
    if key:
        return key
    cli = os.environ.get("OPENCODE_CLI") or _find_cli()
    if not cli:
        raise SystemExit("opencode CLI not found; set OPENCODE_CLI or TOGETHER_API_KEY")
    out = subprocess.run(
        [cli, "api", "get", "/api/credential"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    data = json.loads(out.stdout) if out.stdout.strip() else {}
    for c in data.get("data", []):
        if c.get("integrationID") == "togetherai" and c.get("active"):
            v = c.get("value")
            val = v.get("key") if isinstance(v, dict) else v
            if val:
                return val
    raise SystemExit("no Together credential found (set TOGETHER_API_KEY)")


def ask(key: str, prompt: str, timeout: int = 120):
    body = json.dumps(
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 900,
        }
    ).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": UA,
        },
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode("utf-8"))
    dt = time.perf_counter() - t0
    msg = payload["choices"][0]["message"]
    # reasoning models spend the budget on reasoning_content first
    text = (msg.get("content") or "") + " " + (msg.get("reasoning_content") or "")
    usage = payload.get("usage", {})
    return text, dt, usage


def parse(text: str):
    vals = {}
    for name in ("KP", "KI", "KD"):
        m = re.search(rf"{name}\s*=\s*([+-]?\d+)", text.upper())
        vals[name.lower()] = int(m.group(1)) if m else None
    return vals


def state_json(metrics, gains, prev, prev_cost, cost, it) -> str:
    m = np.asarray(metrics, dtype=float).ravel()
    return json.dumps(
        {
            "experiment": it,
            "gains": [round(float(g), 4) for g in gains],
            "metrics": {
                "overshoot": round(float(np.clip(m[0], -1, 3)), 3),
                "rise_time": round(float(m[1]), 3),
                "settling_time": round(float(m[2]), 3),
                "steady_state_error": round(float(m[3]), 4),
                "iae": round(float(m[4]), 4),
                "itae": round(float(m[5]), 3),
                "oscillations": round(float(m[6]), 2),
                "saturation_fraction": round(float(m[7]), 3),
            },
            "cost": round(float(cost), 4),
            "previous_step_percent": [int(round(float(x) * 100)) for x in prev],
            "previous_cost_change": round(float(prev_cost - cost), 4),
        },
        ensure_ascii=False,
    )


def run_agent(plants, key, iters: int, log: list):
    ku, tu = ultimate_gain(plants)
    gzn = np.column_stack([0.6 * ku, 1.2 * ku / np.maximum(tu, 1e-9), 0.075 * ku * tu])
    gains = gzn.copy()
    prev = np.zeros(3)
    prev_cost = 0.0
    best = np.full(plants.n, np.inf)
    history, latencies, failures = [], [], 0

    for it in range(iters):
        res = simulate(plants, gains)
        cost = cost_from_metrics(res["metrics"], y_curve=res["y_curve"])
        best = np.minimum(best, cost)
        history.append(best.copy())

        for i in range(plants.n):
            prompt = PROMPT.format(
                state=state_json(
                    res["metrics"][i], gains[i], prev, prev_cost, cost[i], it
                )
            )
            text, dt, usage = ask(key, prompt)
            latencies.append(dt)
            vals = parse(text)
            if any(v is None for v in vals.values()):
                failures += 1
                step = np.zeros(3)
            else:
                step = np.clip(
                    np.array([vals["kp"], vals["ki"], vals["kd"]], float) / 100.0,
                    -0.2,
                    0.2,
                )
            log.append(
                {
                    "iter": it,
                    "plant": i,
                    "text": text,
                    "latency_s": round(dt, 3),
                    "usage": usage,
                    "step": step.tolist(),
                }
            )
            gains[i] = np.clip(gains[i] * (10**step), 1e-4, 1e3)
        prev = np.mean([l["step"] for l in log[-plants.n :]], axis=0)
        prev_cost = float(np.mean(cost))

    res = simulate(plants, gains)
    cost = cost_from_metrics(res["metrics"], y_curve=res["y_curve"])
    best = np.minimum(best, cost)
    return {
        "best_j": best,
        "history": np.column_stack(history),
        "n_calls": len(latencies),
        "latency_median": float(np.median(latencies)),
        "latency_p90": float(np.percentile(latencies, 90)),
        "wall_s": float(np.sum(latencies)),
        "parse_failures": failures,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plants", type=int, default=2)
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--seed", type=int, default=41)
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="research/results/agent_baseline.json")
    args = ap.parse_args()

    key = get_key()
    plants = sample_plants(
        args.plants, seed=args.seed, families=HELDOUT_FAMILIES, heldout=True
    )
    print(
        f"[agent] {plants.n} plants, {args.iters} experiments, model {MODEL}",
        flush=True,
    )

    t0 = time.perf_counter()
    log: list = []
    agent = run_agent(plants, key, args.iters, log)
    print(
        f"[agent] {agent['n_calls']} calls, median {agent['latency_median']:.2f}s/call",
        f"parse failures {agent['parse_failures']}",
        flush=True,
    )
    print(f"[agent] median best J {np.median(agent['best_j']):.3f}", flush=True)

    from jev_tune.decision import load_backend

    head = load_backend(args.models)
    ku, tu = ultimate_gain(plants)
    gzn = np.column_stack([0.6 * ku, 1.2 * ku / np.maximum(tu, 1e-9), 0.075 * ku * tu])
    hres = evaluate_head(
        head,
        plants,
        gzn,
        ku,
        tu,
        iters=args.iters,
        value=None,
        use_value_filter=False,
        seed=args.seed,
    )
    print(f"[agent] head median best J {np.median(hres.best_j):.3f}", flush=True)

    report = {
        "model": MODEL,
        "plants": int(plants.n),
        "iters": args.iters,
        "agent": {
            k: (v.tolist() if isinstance(v, np.ndarray) else v)
            for k, v in agent.items()
            if k != "history"
        },
        "agent_history": agent["history"].tolist(),
        "head": {"best_j": hres.best_j.tolist(), "history": hres.history.tolist()},
        "head_decision_ms": 0.188,
        "wall_total_s": time.perf_counter() - t0,
        "requests": log,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[agent] wrote {args.out}")


if __name__ == "__main__":
    main()
