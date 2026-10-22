"""Integration test that drives a real MATLAB.

Skipped unless MATLAB can be started, so the GitHub runners (which have no
MATLAB licence) still run the fast suite.  Locally:

    python -m pytest tests/test_matlab_integration.py -q

It builds three small models whose block names say nothing about their role,
runs discovery on each, and then tunes one of them end to end.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _matlab():
    from jev_tune.matlab_runner import find_matlab

    info = find_matlab()
    return info if info.ok else None


@pytest.mark.skipif(_matlab() is None, reason="MATLAB is not installed")
def test_discover_and_autotune(tmp_path):
    info = _matlab()
    out = tmp_path / "result.json"
    code = (
        f"addpath('{(REPO / 'matlab').as_posix()}'); "
        f"T = test_discover('{(tmp_path / 'work').as_posix()}', 'tune'); "
        f"fid = fopen('{out.as_posix()}','w'); "
        "fwrite(fid, jsonencode(T), 'char'); fclose(fid);"
    )
    proc = subprocess.run(
        [str(info.executable), "-batch", code],
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert out.is_file(), (proc.stdout[-3000:], proc.stderr[-3000:])
    data = json.loads(out.read_text(encoding="utf-8"))
    failed = [c for c in data["cases"] if not c["pass"]]
    assert not failed, failed
    assert len(data["cases"]) >= 4
