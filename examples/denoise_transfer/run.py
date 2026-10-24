"""Replay one signal with an existing non-PID checkpoint; never train.

使用已有非PID检查点重放一个信号，不执行训练，也不重新验收研究。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def _runner():
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    spec = importlib.util.spec_from_file_location(
        "denoise_example_runner", ROOT / "scripts/45_nonpid_transfer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def replay(artifacts_dir, *, seed=101, index=0, budget=20):
    runner = _runner()
    protocol = runner.protocol()
    artifacts_dir = Path(artifacts_dir).resolve()
    report_path = artifacts_dir / "report.json"
    if not report_path.is_file():
        raise FileNotFoundError(
            "A completed study report and its trained artifacts are required: "
            + str(report_path))
    report = _read(report_path)
    if (report["study_id"] != protocol["study_id"]
            or report["protocol"] != runner.PROTOCOL):
        raise ValueError("Artifacts do not belong to the frozen non-PID study")
    if seed not in protocol["training"]["seeds"]:
        raise ValueError("seed must identify one of the registered trained models")
    if not 0 <= index < protocol["splits"]["test"]["n"]:
        raise ValueError("index must identify an object in the recorded test cohort")
    if budget not in protocol["operating"]["budgets"]:
        raise ValueError("budget must be one of the recorded operating budgets")
    if set(report["source_hashes"]) != set(runner.SOURCES):
        raise ValueError("Incomplete recorded source manifest")
    for name, expected in report["source_hashes"].items():
        if runner.digest(ROOT / name) != expected:
            raise ValueError("Replay source differs from the recorded study: " + name)
    loaded = []
    for name in (f"model_{seed}.json", f"calibration_{seed}.json"):
        path = artifacts_dir / name
        if runner.digest(path) != report["artifacts"][name]:
            raise ValueError("Trained artifact hash differs: " + name)
        loaded.append(_read(path))
    artifact, calibration = loaded
    if artifact["seed"] != seed or calibration["seed"] != seed:
        raise ValueError("Model/calibration seed differs")
    if calibration["mode"] != "monitor":
        raise ValueError("This example requires the recorded CP monitor policy")

    runner.torch.set_num_threads(1)
    runner.torch.use_deterministic_algorithms(True)
    count = {"evaluations": 0}
    original_task = runner.DenoiseTask

    class CountedTask(original_task):
        __slots__ = ()

        def evaluate(self, theta):
            # Count actual filter attempts, including an exception, without
            # changing the task or the frozen runner's per-arm cache.
            count["evaluations"] += 1
            return super().evaluate(theta)

    runner.DenoiseTask = CountedTask
    common = {
        "kind": "additional_replay_not_independent_validation",
        "study_report": str(report_path),
        "study_acceptance_from_report": report["acceptance"],
        "model_seed": seed,
        "task_split_seed": protocol["splits"]["test"]["seed"],
        "task_index": index,
        "budget": budget,
        "primary_study_changed": False,
    }
    try:
        result = runner.rollout(
            common["task_split_seed"], index, f"typed_seed_{seed}", budget,
            artifact=artifact, calibration=calibration)
        if count["evaluations"] != len(result["measurements"]):
            raise ValueError("Replay evaluation count disagrees with the measured ledger")
        returned = result["measurements"][result["returned"]]
        return {
            **common, "ok": True,
            "additional_objective_evaluations": count["evaluations"],
            "requests": len(result["requests"]),
            "cached_requests": sum(row["cached"] for row in result["requests"]),
            "initial_cost": result["measurements"][0]["cost"],
            "returned_theta": returned["theta"],
            "returned_cost": returned["cost"],
            "stop": result["stop"],
        }
    except Exception as exc:
        return {**common, "ok": False,
                "additional_objective_evaluations": count["evaluations"],
                "error": f"{type(exc).__name__}: {exc}"}
    finally:
        runner.DenoiseTask = original_task


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True,
                        help="explicitly perform an additional measured replay")
    parser.add_argument("--artifacts-dir", type=Path,
                        default=ROOT / "research/results/nonpid_transfer")
    parser.add_argument("--seed", type=int, default=101, help="trained model seed")
    parser.add_argument("--index", type=int, default=0, help="recorded test object index")
    parser.add_argument("--budget", type=int, default=20,
                        help="maximum fresh objective evaluations, including the start")
    args = parser.parse_args(argv)
    try:
        result = replay(args.artifacts_dir, seed=args.seed, index=args.index,
                        budget=args.budget)
    except Exception as exc:
        # Artifact/schema/source checks precede every task construction.
        result = {"ok": False, "additional_objective_evaluations": 0,
                  "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
