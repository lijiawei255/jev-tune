"""Command line interface — designed to be driven by an agent as well as a human.

Every subcommand is non-interactive, deterministic given a seed, prints a
one-line summary for humans and can emit machine-readable JSON with ``--json``.
Exit codes: 0 success, 2 missing prerequisites (with the exact command to fix it).
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

REQUIRED = {
    "numpy": "numpy",
    "scipy": "scipy",
    "sklearn": "scikit-learn",
    "torch": "torch",
}


def _has(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except Exception:
        return False


def _n_actions(models_dir: Path) -> int:
    """Read the action-vocabulary size recorded at training time."""
    meta = models_dir / "meta.json"
    if meta.is_file():
        try:
            return int(
                json.loads(meta.read_text(encoding="utf-8-sig")).get("n_actions", 5)
            )
        except Exception:
            pass
    return 5


def cmd_status(args) -> int:
    info = {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "conda_env": os.environ.get("CONDA_DEFAULT_ENV", ""),
        "packages": {m: _has(m) for m in REQUIRED},
        "onnxruntime": _has("onnxruntime"),
        "matlab": shutil.which("matlab") is not None
        or Path(r"C:\Program Files\MATLAB\R2024b\bin\matlab.exe").is_file(),
        "assets": {
            "head_weights": (REPO / "models/jev_head.pt").is_file(),
            "onnx": (REPO / "models/jev_head.onnx").is_file(),
            "matlab_weights": (REPO / "models/jev_head_weights.mat").is_file(),
            "dataset": (REPO / "data/expert_train.npz").is_file(),
            "demo_gif": (REPO / "assets/tuning.gif").is_file(),
        },
    }
    missing = [m for m, ok in info["packages"].items() if not ok]
    if missing:
        info["next"] = (
            "pip install "
            + " ".join(REQUIRED[m] for m in missing)
            + "   # or: bash scripts/agent_setup.sh"
        )
        code = 2
    elif not info["assets"]["head_weights"]:
        info["next"] = "python scripts/01_make_dataset.py && python scripts/02_train.py"
        code = 2
    else:
        info["next"] = "python -m jev_tune.cli demo"
        code = 0
    info["ok"] = code == 0

    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print(f"python      {info['python']}  ({info['conda_env'] or 'no conda env'})")
        print(
            f"packages    "
            + "  ".join(
                f"{k}={'ok' if v else 'MISSING'}" for k, v in info["packages"].items()
            )
        )
        print(
            f"onnxruntime {'ok' if info['onnxruntime'] else 'missing'}   matlab {'ok' if info['matlab'] else 'missing'}"
        )
        print(
            f"assets      "
            + "  ".join(f"{k}={'ok' if v else '-'}" for k, v in info["assets"].items())
        )
        print(f"next        {info['next']}")
    return code


def cmd_demo(args) -> int:
    """Three held-out plants: head vs Z-N vs CMA-ES, ~20 s on CPU."""
    import numpy as np
    import torch

    from jev_tune.baselines import run_cmaes, run_zn, zn_gains
    from jev_tune.evaluate import evaluate_head
    from jev_tune.model import JevHead
    from jev_tune.plants import HELDOUT_FAMILIES, sample_plants, ultimate_gain

    weights = REPO / "models/jev_head.pt"
    if not weights.is_file():
        msg = "models/jev_head.pt not found — run scripts/01_make_dataset.py then 02_train.py"
        print(json.dumps({"ok": False, "next": msg}) if args.json else msg)
        return 2

    plants = sample_plants(
        args.plants, seed=args.seed, families=HELDOUT_FAMILIES, heldout=True
    )
    ku, tu = ultimate_gain(plants)
    gzn = np.column_stack([0.6 * ku, 1.2 * ku / tu, 0.075 * ku * tu])

    head = JevHead(n_actions=_n_actions(weights.parent))
    head.load_state_dict(torch.load(weights, map_location="cpu"))
    head.eval()

    zn = run_zn(plants)
    cma = run_cmaes(plants, zn_gains(plants), budget=18, lam=6, seed=args.seed)
    hr = evaluate_head(
        head,
        plants,
        gzn,
        ku,
        tu,
        iters=20,
        value=None,
        use_value_filter=False,
        seed=args.seed,
    )

    result = {
        "ok": True,
        "plants": plants.n,
        "families": sorted(set(plants.family)),
        "cost_median": {
            "jev_head": float(np.median(hr.best_j)),
            "cmaes_18sims": float(np.median(cma.best_j)),
            "zn": float(np.median(zn.best_j)),
        },
        "improvement_vs_zn": float(np.median(zn.best_j) / np.median(hr.best_j)),
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"{plants.n} held-out {result['families']} plants, cost J (lower is better)"
        )
        for k, v in result["cost_median"].items():
            print(f"  {k:<14} {v:6.3f}")
        print(f"  head is {result['improvement_vs_zn']:.1f}x better than Z-N")
    return 0


def cmd_matlab(args) -> int:
    """Run one Simulink tuning job (or probe MATLAB) and print JSON."""
    from .matlab_runner import probe, run_job

    if args.probe:
        result = probe()
    else:
        if not args.model:
            print("--model is required (or pass --probe)", file=sys.stderr)
            return 2
        cfg = {
            "model": args.model,
            "iters": args.iters,
            "step_gain": args.step_gain,
        }
        for key in ("stop_time", "work_dir", "kp_block", "ki_block", "kd_block",
                    "measure_scope", "input_scope", "ref_source", "u_max"):
            value = getattr(args, key, None)
            if value is not None:
                cfg[key] = value
        result = run_job(cfg, timeout=args.timeout)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if not result.get("ok"):
            print(f"error: {result.get('error')}")
        elif "release" in result:
            print(f"MATLAB {result['release']}  batch={result['supports_batch']}  "
                  f"pidtune={result['has_pid_tune']}  at {result['matlab']}")
        else:
            print(f"model      {result.get('model')}")
            print(f"gains      {[round(x, 4) for x in result.get('final_gains', [])]}")
            print(f"cost       {result.get('final_J'):.3f}  "
                  f"(start {result.get('history', [{}])[0].get('J', float('nan')):.3f})")
            print(f"experiments {result.get('n_experiments')}  "
                  f"rollbacks {result.get('n_rollbacks')}  "
                  f"wall {result.get('wall_s', 0):.1f} s")
    return 0 if result.get("ok") else 2


def cmd_batch(args) -> int:
    """Run a queue of tuning jobs, optionally across several MATLAB workers."""
    from concurrent.futures import ThreadPoolExecutor

    from .matlab_runner import run_batch

    jobs = json.loads(Path(args.jobs).read_text(encoding="utf-8-sig"))
    if isinstance(jobs, dict):
        jobs = [jobs]
    for job in jobs:
        job.setdefault("iters", args.iters)
        job.setdefault("step_gain", args.step_gain)

    if args.workers and args.workers > 1:
        from .matlab_worker import MatlabWorker

        n = min(int(args.workers), len(jobs))
        workers = [MatlabWorker(timeout=args.timeout) for _ in range(n)]
        for w in workers:
            w.start()
        print(f"[batch] {n} MATLAB workers")

        def run_one(pair):
            idx, job = pair
            w = workers[idx % n]
            t0 = time.perf_counter()
            try:
                r = w.run(job)
            except Exception as exc:  # keep the queue moving
                r = {"ok": False, "error": str(exc)}
            r["index"] = idx + 1
            r.setdefault("job_wall_s", time.perf_counter() - t0)
            return r

        try:
            with ThreadPoolExecutor(max_workers=n) as pool:
                results = list(pool.map(run_one, enumerate(jobs)))
        finally:
            for w in workers:
                w.stop()
    else:
        results = run_batch(jobs, timeout=args.timeout)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        ok = sum(1 for r in results if r.get("ok"))
        print(f"{ok}/{len(results)} jobs succeeded")
        for r in results:
            if r.get("ok"):
                print(f"  [{r.get('index', '?')}] {Path(r.get('model', '')).name:<28} "
                      f"J={r.get('final_J', float('nan')):.3f}  {r.get('job_wall_s', 0):.1f}s")
            else:
                print(f"  [{r.get('index', '?')}] FAILED: {r.get('error')}")
    return 0 if any(r.get("ok") for r in results) else 2


def cmd_check(args) -> int:
    """Fast self-test: analytic closed loop, decoding contract, ONNX parity."""
    import subprocess

    cmd = [sys.executable, "-m", "pytest", "-q"]
    if args.json:
        cmd += ["--json-report"] if _has("pytest_jsonreport") else []
    proc = subprocess.run(cmd, cwd=REPO)
    return proc.returncode


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="jev-tune", description="System-1 PID autotuning")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="check environment and assets")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    d = sub.add_parser("demo", help="head vs classical tuners on held-out plants")
    d.add_argument("--plants", type=int, default=12)
    d.add_argument("--seed", type=int, default=0)
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_demo)

    m = sub.add_parser("matlab", help="tune a Simulink model (or probe MATLAB)")
    m.add_argument("--model", help="absolute path to a .slx / .mdl")
    m.add_argument("--iters", type=int, default=20)
    m.add_argument("--stop-time", dest="stop_time", type=float)
    m.add_argument("--step-gain", dest="step_gain", type=float, default=1.0)
    m.add_argument("--work-dir", dest="work_dir")
    m.add_argument("--kp-block", dest="kp_block")
    m.add_argument("--ki-block", dest="ki_block")
    m.add_argument("--kd-block", dest="kd_block")
    m.add_argument("--measure-scope", dest="measure_scope")
    m.add_argument("--input-scope", dest="input_scope")
    m.add_argument("--ref-source", dest="ref_source")
    m.add_argument("--u-max", dest="u_max", type=float)
    m.add_argument("--timeout", type=int, default=900)
    m.add_argument("--probe", action="store_true", help="only report the MATLAB capability")
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=cmd_matlab)

    b = sub.add_parser("batch", help="run a queue of Simulink jobs in one MATLAB process")
    b.add_argument("--jobs", required=True, help="JSON file with a list of job objects")
    b.add_argument("--iters", type=int, default=20)
    b.add_argument("--step-gain", dest="step_gain", type=float, default=1.0)
    b.add_argument("--workers", type=int, default=1,
                   help="parallel MATLAB workers (bounded by your licence)")
    b.add_argument("--timeout", type=int, default=3600)
    b.add_argument("--json", action="store_true")
    b.set_defaults(func=cmd_batch)

    c = sub.add_parser("check", help="run the test suite")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_check)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
