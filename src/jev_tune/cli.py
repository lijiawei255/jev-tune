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


def cmd_discover(args) -> int:
    """Find the PID gains, the measured signal and the reference in a model."""
    from .matlab_runner import run_discover

    if not args.model:
        print("--model is required", file=sys.stderr)
        return 2
    result = run_discover(
        args.model,
        work_dir=args.work_dir,
        probe=not args.no_probe,
        timeout=args.timeout,
    )

    if args.out and result.get("ok"):
        Path(args.out).write_text(
            json.dumps(result.get("config", {}), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif not result.get("ok"):
        print(f"error ({result.get('code')}): {result.get('error')}")
        for w in result.get("warnings") or []:
            print(f"  ! {w}")
    else:
        c = result.get("controller", {})
        m = result.get("measure", {})
        r = result.get("reference", {})
        print(f"model       {Path(result.get('model', '')).name}")
        print(f"confidence  {result.get('confidence')}")
        print(f"junction    {result.get('error_junction')}")
        if c.get("kind") == "pid_block":
            print(f"controller  PID block {c.get('block')} (form {c.get('form')})")
        else:
            print(
                f"controller  Kp={c.get('kp_block')}  Ki={c.get('ki_block')}  "
                f"Kd={c.get('kd_block')}"
            )
        print(f"measured    {m.get('block')} port {m.get('port')}")
        print(f"reference   {r.get('value')}  ({r.get('source')})")
        if args.out:
            print(f"config      {args.out}")
        for w in result.get("warnings") or []:
            print(f"  ! {w}")
    return 0 if result.get("ok") else 2


def cmd_matlab(args) -> int:
    """Run one Simulink tuning job (or probe MATLAB) and print JSON."""
    from .matlab_runner import probe, run_job

    if args.probe:
        result = probe()
    else:
        if not args.model:
            print("--model is required (or pass --probe)", file=sys.stderr)
            return 2
        cfg: dict = {
            "model": args.model,
            "iters": args.iters,
            "step_gain": args.step_gain,
        }
        if getattr(args, "auto", False):
            cfg["auto_discover"] = True
        # a discovered config file is a starting point: explicit flags still win
        if getattr(args, "config", None):
            seed = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
            if isinstance(seed, dict):
                cfg.update(seed)
            cfg.update(
                {"model": args.model, "iters": args.iters, "step_gain": args.step_gain}
            )
            if getattr(args, "auto", False):
                cfg["auto_discover"] = True
        for key in (
            "stop_time",
            "work_dir",
            "kp_block",
            "ki_block",
            "kd_block",
            "measure_scope",
            "input_scope",
            "ref_source",
            "u_max",
            "controller",
            "pid_block",
            "instrument_block",
            "instrument_port",
        ):
            value = getattr(args, key, None)
            if value is not None:
                cfg[key] = value
        result = run_job(cfg, timeout=args.timeout)
        if result.get("ok"):
            result["config"] = {k: v for k, v in cfg.items() if k != "model"}
            if getattr(args, "plot", None):
                from .plot import save_before_after

                result["plot"] = str(save_before_after(result, args.plot))
            if getattr(args, "write_back", False):
                from .matlab_runner import run_writeback

                blocks = {
                    "kp_block": cfg.get("kp_block"),
                    "ki_block": cfg.get("ki_block"),
                    "kd_block": cfg.get("kd_block"),
                    "pid_block": cfg.get("pid_block"),
                }
                disc = result.get("discovery") or {}
                # --auto found the layout inside MATLAB, so fall back to what it
                # reported when the caller did not name the blocks
                controller = cfg.get("controller") or (
                    "pid_block"
                    if disc.get("controller_kind") == "pid_block"
                    else "gains"
                )
                for key in blocks:
                    if not blocks[key]:
                        blocks[key] = disc.get(key)
                result["write_back"] = run_writeback(
                    args.model,
                    result.get("final_gains", []),
                    controller=controller,
                    blocks=blocks,
                )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if not result.get("ok"):
            print(f"error: {result.get('error')}")
        elif "release" in result:
            print(
                f"MATLAB {result['release']}  batch={result['supports_batch']}  "
                f"pidtune={result['has_pid_tune']}  at {result['matlab']}"
            )
        else:

            def _num(value, fmt="{:.3f}"):
                # a diverged experiment is JSON null, not a number
                try:
                    return fmt.format(float(value))
                except (TypeError, ValueError):
                    return "n/a"

            hist = result.get("history") or [{}]
            print(f"model      {result.get('model')}")
            print(f"gains      {[round(x, 4) for x in result.get('final_gains', [])]}")
            print(
                f"cost       {_num(result.get('final_J'))}  "
                f"(start {_num(hist[0].get('J'))})"
            )
            print(
                f"experiments {result.get('n_experiments')}  "
                f"rollbacks {result.get('n_rollbacks')}  "
                f"wall {result.get('wall_s', 0):.1f} s"
            )
            if result.get("plot"):
                print(f"plot        {result['plot']}")
            wb = result.get("write_back") or {}
            if wb:
                print(
                    f"written     {wb.get('target')}"
                    if wb.get("ok")
                    else f"write-back failed: {wb.get('error')}"
                )
            disc = result.get("discovery") or {}
            if disc.get("used"):
                print(
                    f"discovered  {disc.get('measure_block')} "
                    f"({disc.get('confidence')})"
                )
    return 0 if result.get("ok") else 2


def cmd_loop(args) -> int:
    """Tune a transfer function given on the command line, with no MATLAB.

    This is the second plant adapter: the same head, the same decision contract,
    a different way to run an experiment.  It exists so a user without MATLAB can
    see the loop work, and so CI exercises the decision path on every push.
    """
    from .evaluate import evaluate_head
    from .model import JevHead
    from .plants import make_plant, ultimate_gain

    import numpy as np

    weights = REPO / "models/jev_head.pt"
    if not weights.is_file():
        msg = "models/jev_head.pt not found: run scripts/01_make_dataset.py then 02_train.py"
        print(json.dumps({"ok": False, "next": msg}) if args.json else msg)
        return 2

    def _coef(text: str) -> list[float]:
        return [float(x) for x in str(text).replace(",", " ").split()]

    num, den = _coef(args.num), _coef(args.den)
    plant = make_plant(
        num,
        den,
        delay_s=args.delay,
        u_max=args.u_max,
        dead_zone=args.dead_zone,
        name=args.name,
    )
    ku, tu = ultimate_gain(plant)
    gzn = np.array([[0.6 * ku[0], 1.2 * ku[0] / tu[0], 0.075 * ku[0] * tu[0]]])

    import torch

    head = JevHead(n_actions=_n_actions(weights.parent))
    head.load_state_dict(torch.load(weights, map_location="cpu"))
    head.eval()
    result = evaluate_head(
        head,
        plant,
        gzn,
        ku,
        tu,
        iters=args.iters,
        use_value_filter=False,
        seed=args.seed,
    )
    history = result.history
    start_j = float(history[0][0])
    final_j = float(result.best_j[0])
    gains = [float(x) for x in result.gains[0]]

    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "plant": {
                        "num": num,
                        "den": den,
                        "delay_s": args.delay,
                        "dead_zone": args.dead_zone,
                        "u_max": args.u_max,
                    },
                    "reference": 1.0,
                    "zn_start": [float(x) for x in gzn[0]],
                    "final_gains": gains,
                    "start_J": start_j,
                    "final_J": final_j,
                    "n_experiments": int(result.stop_iter[0]) or len(history),
                    "hist": [float(h) for h in history[0]],
                },
                indent=2,
            )
        )
    else:
        print(f"plant       {num} / {den}   delay {args.delay}s  u_max {args.u_max}")
        print(
            f"start (Z-N) J={start_j:.3f}  gains {[round(float(x), 4) for x in gzn[0]]}"
        )
        print(
            f"tuned       J={final_j:.3f}  gains {[round(float(x), 4) for x in gains]}"
        )
        print(f"experiments {history.shape[1]}")
    return 0


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
                print(
                    f"  [{r.get('index', '?')}] {Path(r.get('model', '')).name:<28} "
                    f"J={r.get('final_J', float('nan')):.3f}  {r.get('job_wall_s', 0):.1f}s"
                )
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

    d = sub.add_parser("discover", help="find the gains, signal and reference")
    d.add_argument("--model", required=True, help="absolute path to a .slx / .mdl")
    d.add_argument(
        "--no-probe",
        action="store_true",
        help="skip the confirming simulations (faster, less certain)",
    )
    d.add_argument("--work-dir", dest="work_dir")
    d.add_argument("--out", help="write the discovered config to this JSON file")
    d.add_argument("--timeout", type=int, default=600)
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_discover)

    m = sub.add_parser("matlab", help="tune a Simulink model (or probe MATLAB)")
    m.add_argument("--model", help="absolute path to a .slx / .mdl")
    m.add_argument(
        "--auto",
        action="store_true",
        help="discover the blocks and the measured signal first",
    )
    m.add_argument("--config", help="JSON config from `jev-tune discover --out`")
    m.add_argument(
        "--write-back",
        dest="write_back",
        action="store_true",
        help="save the tuned gains to <name>_tuned.slx",
    )
    m.add_argument("--plot", help="write a before/after PNG here")
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
    m.add_argument("--controller", choices=["gains", "pid_block"])
    m.add_argument("--pid-block", dest="pid_block")
    m.add_argument("--instrument-block", dest="instrument_block")
    m.add_argument("--instrument-port", dest="instrument_port", type=int)
    m.add_argument("--timeout", type=int, default=900)
    m.add_argument(
        "--probe", action="store_true", help="only report the MATLAB capability"
    )
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=cmd_matlab)

    l = sub.add_parser(
        "loop", help="tune a transfer function on the command line (no MATLAB)"
    )
    l.add_argument("--num", default="1", help='numerator coefficients, e.g. "1"')
    l.add_argument("--den", default="1 0.6 1", help="denominator coefficients")
    l.add_argument("--delay", type=float, default=0.0, help="transport delay (s)")
    l.add_argument("--dead-zone", dest="dead_zone", type=float, default=0.0)
    l.add_argument("--u-max", dest="u_max", type=float, default=2.5)
    l.add_argument("--iters", type=int, default=20)
    l.add_argument("--seed", type=int, default=0)
    l.add_argument("--name", default="custom")
    l.add_argument("--json", action="store_true")
    l.set_defaults(func=cmd_loop)

    b = sub.add_parser(
        "batch", help="run a queue of Simulink jobs in one MATLAB process"
    )
    b.add_argument("--jobs", required=True, help="JSON file with a list of job objects")
    b.add_argument("--iters", type=int, default=20)
    b.add_argument("--step-gain", dest="step_gain", type=float, default=1.0)
    b.add_argument(
        "--workers",
        type=int,
        default=1,
        help="parallel MATLAB workers (bounded by your licence)",
    )
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
