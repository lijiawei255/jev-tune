"""Minimal MCP server (stdio, JSON-RPC 2.0) exposing the tuner as agent tools.

Deliberately dependency-free: the Model Context Protocol over stdio is just
line-delimited JSON-RPC, so a ~200 line implementation avoids pinning an SDK
version and works with any client that speaks the protocol.

Tools
-----
tune_status        environment, assets and the next recommended action
tune_probe_matlab  which MATLAB release is installed and what it supports
tune_simulink      run one tuning job on a .slx model, return gains + history
tune_demo          head vs classical tuners on held-out plants (no MATLAB)

Run:  python -m jev_tune.mcp_server      (or the `jev-tune-mcp` entry point)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "tune_status",
        "description": (
            "Report the environment, trained assets and the next recommended "
            "action. Call this first; it is cheap and never runs a simulation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "tune_probe_matlab",
        "description": (
            "Report the installed MATLAB release and whether it supports Fast "
            "Restart, scope logging and pidtune. Use before tune_simulink if the "
            "user's MATLAB version is unknown."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "tune_simulink",
        "description": (
            "Tune the PID gains of a Simulink model and return the final gains, "
            "the cost at every experiment, and the number of rollbacks. Runs "
            "entirely inside MATLAB (Fast Restart), typically 1-3 s for 20 "
            "experiments. Block names default to Gain_Kp/Gain_Ki/Gain_Kd and "
            "Scope_Position/Scope_Current."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "absolute path to the .slx model",
                },
                "iters": {"type": "integer", "default": 20},
                "stop_time": {
                    "type": "number",
                    "description": "simulation horizon (s); default = model StopTime",
                },
                "step_gain": {"type": "number", "default": 1.0},
                "work_dir": {"type": "string"},
                "kp_block": {"type": "string", "default": "Gain_Kp"},
                "ki_block": {"type": "string", "default": "Gain_Ki"},
                "kd_block": {"type": "string", "default": "Gain_Kd"},
                "measure_scope": {"type": "string", "default": "Scope_Position"},
                "input_scope": {"type": "string", "default": "Scope_Current"},
                "ref_source": {"description": "'auto' or a number"},
                "u_max": {"type": "number"},
            },
            "required": ["model"],
        },
    },
    {
        "name": "tune_demo",
        "description": (
            "Compare the Jev head against CMA-ES and Ziegler-Nichols on held-out "
            "plants the model never saw. No MATLAB needed; ~20 s on CPU."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "plants": {"type": "integer", "default": 12},
                "seed": {"type": "integer", "default": 0},
            },
        },
    },
]


# --------------------------------------------------------------------------- #
# Tool implementations
# --------------------------------------------------------------------------- #


def _status() -> dict:
    from .cli import REPO as CLI_REPO
    from .cli import _has, _n_actions

    models = CLI_REPO / "models"
    info = {
        "ok": True,
        "python": sys.version.split()[0],
        "packages": {
            m: _has(m) for m in ("numpy", "scipy", "sklearn", "torch", "onnxruntime")
        },
        "assets": {
            "head": (models / "jev_head.pt").is_file(),
            "onnx": (models / "jev_head.onnx").is_file(),
            "matlab_weights": (models / "jev_head_weights.mat").is_file(),
        },
        "n_actions": _n_actions(models),
        "matlab": None,
    }
    try:
        from .matlab_runner import find_matlab

        m = find_matlab()
        info["matlab"] = str(m.executable) if m.ok else None
    except Exception:
        pass
    missing = [k for k, v in info["packages"].items() if not v]
    info["next"] = (
        "pip install " + " ".join(missing)
        if missing
        else "python -m jev_tune.cli demo"
        if info["assets"]["head"]
        else "python scripts/01_make_dataset.py && python scripts/02_train.py"
    )
    return info


def _probe() -> dict:
    from .matlab_runner import probe

    return probe()


def _tune_simulink(args: dict) -> dict:
    from .matlab_runner import run_job

    model = args.get("model")
    if not model:
        return {"ok": False, "error": "model is required"}
    cfg = {
        "model": model,
        "iters": int(args.get("iters", 20)),
        "step_gain": float(args.get("step_gain", 1.0)),
    }
    for key in ("stop_time", "work_dir"):
        if args.get(key) not in (None, ""):
            cfg[key] = args[key]
    for key in (
        "kp_block",
        "ki_block",
        "kd_block",
        "measure_scope",
        "input_scope",
        "ref_source",
        "u_max",
    ):
        if key in args and args[key] not in (None, ""):
            cfg[key] = args[key]
    return run_job(cfg)


def _tune_demo(args: dict) -> dict:
    from .cli import cmd_demo

    class _Args:
        plants = int(args.get("plants", 12))
        seed = int(args.get("seed", 0))
        json = True

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cmd_demo(_Args())
    text = buf.getvalue().strip()
    try:
        return json.loads(text)
    except Exception:
        return {"ok": code == 0, "raw": text}


HANDLERS = {
    "tune_status": lambda a: _status(),
    "tune_probe_matlab": lambda a: _probe(),
    "tune_simulink": _tune_simulink,
    "tune_demo": _tune_demo,
}


# --------------------------------------------------------------------------- #
# JSON-RPC plumbing
# --------------------------------------------------------------------------- #


def _ok(req_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(req: dict) -> dict | None:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return _ok(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "jev-tune", "version": "0.2.0"},
            },
        )
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return _ok(req_id, {})
    if method in ("resources/list", "prompts/list"):
        return _ok(
            req_id, {"resources": []} if "resources" in method else {"prompts": []}
        )
    if method == "tools/list":
        return _ok(req_id, {"tools": TOOLS})
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = HANDLERS.get(name)
        if fn is None:
            return _err(req_id, -32601, f"unknown tool: {name}")
        try:
            result = fn(args)
            return _ok(
                req_id,
                {
                    "content": [
                        {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
                    ],
                    "isError": not bool(result.get("ok", True)),
                },
            )
        except Exception as exc:  # keep the server alive for the next call
            return _ok(
                req_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({"ok": False, "error": str(exc)}),
                        }
                    ],
                    "isError": True,
                },
            )
    if req_id is None:
        return None
    return _err(req_id, -32601, f"unknown method: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
