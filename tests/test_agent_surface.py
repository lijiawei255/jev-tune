"""The agent-facing surface: discover, config files, write-back, MCP tools.

None of this needs MATLAB; the parts that do are in test_matlab_integration.py.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"

HAS_MPL = bool(__import__("importlib").util.find_spec("matplotlib"))


def _run(*args, timeout=120):
    import os

    return subprocess.run(
        [sys.executable, "-m", "jev_tune.cli", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(SRC)},
        timeout=timeout,
    )


def test_discover_is_a_subcommand():
    proc = _run("discover", "--help")
    assert proc.returncode == 0
    assert "--no-probe" in proc.stdout
    assert "--out" in proc.stdout


def test_matlab_accepts_the_agent_flags():
    proc = _run("matlab", "--help")
    assert proc.returncode == 0
    for flag in (
        "--auto",
        "--config",
        "--write-back",
        "--plot",
        "--pid-block",
        "--instrument-port",
        "--all-loops",
    ):
        assert flag in proc.stdout, flag


def test_discover_without_matlab_reports_a_code(monkeypatch):
    """A missing MATLAB must be a machine-readable failure, not a traceback."""
    from jev_tune import matlab_runner

    class _Missing:
        ok = False
        executable = None
        source = "none"

    monkeypatch.setattr(matlab_runner, "find_matlab", lambda: _Missing())
    result = matlab_runner.run_discover("nope.slx")
    assert result["ok"] is False
    assert result["code"] == "matlab_missing"
    assert "MATLAB_EXE" in result["error"]


def test_loop_command_tunes_without_matlab():
    """The second plant adapter: same head, no Simulink, runs in CI."""
    proc = _run(
        "loop",
        "--num",
        "1",
        "--den",
        "1 0.6 1",
        "--delay",
        "0.02",
        "--iters",
        "8",
        "--json",
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["final_J"] <= data["start_J"]
    assert len(data["final_gains"]) == 3


def test_gain_verdict_says_kept_or_beat():
    """A result that equals the model's own gains is a success, not a non-event."""
    from jev_tune.cli import _gain_verdict

    kept = _gain_verdict({"own_J": 0.3925, "final_J": 0.3925,
                          "own_gains": [280, 300, 30]})
    assert kept.startswith("kept") and "0.393" in kept

    beat = _gain_verdict({"own_J": 0.3925, "final_J": 0.31,
                          "own_gains": [280, 300, 30]})
    assert beat.startswith("beat") and "0.310" in beat

    assert _gain_verdict({"own_J": None, "final_J": 0.5}) == ""


def test_doctor_is_a_subcommand():
    proc = _run("doctor", "--help")
    assert proc.returncode == 0
    assert "--no-discover" in proc.stdout
    assert "--model" in proc.stdout


def test_doctor_without_matlab_reports_a_code(monkeypatch):
    from jev_tune import matlab_runner

    class _Missing:
        ok = False
        executable = None
        source = "none"

    monkeypatch.setattr(matlab_runner, "find_matlab", lambda: _Missing())
    result = matlab_runner.run_doctor("nope.slx")
    assert result["ok"] is False
    assert result["code"] == "matlab_missing"


def test_all_loops_without_matlab_reports_a_code(monkeypatch):
    from jev_tune import matlab_runner

    class _Missing:
        ok = False
        executable = None
        source = "none"

    monkeypatch.setattr(matlab_runner, "find_matlab", lambda: _Missing())
    result = matlab_runner.run_all_loops("nope.slx")
    assert result["ok"] is False
    assert result["code"] == "matlab_missing"


def test_mcp_exposes_discover_and_writeback():
    from jev_tune.mcp_server import handle

    resp = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert {"tune_discover", "tune_apply_gains", "tune_doctor"} <= names
    # the schemas must stay self-describing: an agent has nothing else to read
    for tool in resp["result"]["tools"]:
        assert tool["description"].strip()
        assert tool["inputSchema"]["type"] == "object"


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib is an optional dependency")
def test_plot_writes_a_png(tmp_path):
    from jev_tune.plot import save_before_after

    result = {
        "model": "Motor.slx",
        "final_gains": [91.5, 172.3, 14.1],
        "reference": 0.5236,
        "history": [{"J": 1.24}, {"J": 0.86}, {"J": 0.60}],
        "trace": {
            "start": {"t": [0, 1, 2, 3], "y": [0, 0, 0.9, 1.4], "J": 1.24},
            "best": {"t": [0, 1, 2, 3], "y": [0, 0, 0.5, 0.53], "J": 0.60},
        },
    }
    out = save_before_after(result, tmp_path / "ba.png")
    assert out.is_file() and out.stat().st_size > 5000


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib is an optional dependency")
def test_plot_without_traces_still_succeeds(tmp_path):
    """A result with no curves must not crash the agent's pipeline."""
    from jev_tune.plot import save_before_after

    out = save_before_after(
        {"model": "x.slx", "history": [{"J": 1.0}]}, tmp_path / "empty.png"
    )
    assert out.is_file()
