"""MATLAB ``pidtune`` as the industrial baseline.

``pidtune`` designs a controller from the *model* -- it never simulates the
plant -- so it is the first thing an engineer reaches for, and the honest
reference point for any learned tuner.

The bridge deliberately avoids ``matlab.engine``: the engine wheel does not
build on this machine, so we exchange MAT files with ``matlab -batch`` instead.
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from scipy.io import loadmat, savemat

from .baselines import BaselineResult, _eval, zn_gains
from .plants import PlantSet

MATLAB_DIR = Path(__file__).resolve().parents[2] / "matlab"


def _matlab() -> Path | None:
    """Whatever MATLAB this machine has, via the same lookup the CLI uses."""
    from .matlab_runner import find_matlab

    info = find_matlab()
    return info.executable if info.ok else None


def matlab_available() -> bool:
    return _matlab() is not None


def pidtune_gains(plants: PlantSet, ctype: str = "PID") -> tuple[np.ndarray, float]:
    """Return (gains (n,3), wall seconds) from MATLAB ``pidtune``."""
    if not matlab_available():
        raise RuntimeError(f"MATLAB not found at {_matlab()}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_file = tmp / "plants.mat"
        out_file = tmp / "gains.mat"
        savemat(in_file, {"numM": plants.num, "denM": plants.den})

        cmd = (
            f"addpath('{MATLAB_DIR.as_posix()}'); "
            f"jev_pidtune_batch('{in_file.as_posix()}','{out_file.as_posix()}','{ctype}');"
        )
        t0 = time.perf_counter()
        proc = subprocess.run(
            [str(_matlab()), "-batch", cmd],
            capture_output=True,
            text=True,
            timeout=600,
        )
        wall = time.perf_counter() - t0
        if proc.returncode != 0 or not out_file.is_file():
            raise RuntimeError(f"MATLAB pidtune failed: {proc.stderr[-800:]}")

        m = loadmat(out_file)
        gains = np.column_stack(
            [m["kp"].ravel(), m["ki"].ravel(), m["kd"].ravel()]
        ).astype(float)
    return gains, wall


def run_pidtune(plants: PlantSet, ctype: str = "PID") -> BaselineResult:
    gains, wall = pidtune_gains(plants, ctype)
    bad = (~np.isfinite(gains)).any(axis=1) | (gains[:, 0] <= 0)
    if bad.any():
        gains[bad] = zn_gains(plants.subset(np.where(bad)[0]))
    j = _eval(plants, gains)
    return BaselineResult(
        name=f"matlab_pidtune_{ctype}",
        gains=gains,
        best_j=j,
        history=j[:, None],
        eval_axis=np.array([1.0]),
        wall_s=wall,
    )
