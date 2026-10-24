"""Tests for the CLI surface and the specialist plumbing (no MATLAB needed)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_status_reports_missing_or_ready():
    proc = subprocess.run(
        [sys.executable, "-m", "jev_tune.cli", "status", "--json"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO / "src")},
        timeout=180,
    )
    assert proc.returncode in (0, 2)
    data = json.loads(proc.stdout)
    assert "assets" in data and "next" in data
    assert data["ok"] is (proc.returncode == 0)


def test_meta_reader_falls_back():
    from jev_tune.cli import _n_actions

    assert _n_actions(REPO / "nope") == 5


def test_train_head_accepts_an_initial_model(tmp_path):
    """Fine-tuning must update the model it is given, not silently clone it."""
    import numpy as np
    import torch

    from jev_tune.domains.pid.expert import ExpertData
    from jev_tune.domains.pid.model import JevHead
    from jev_tune.domains.pid.train import train_head

    n = 64
    data = ExpertData(
        feats=np.random.default_rng(0).standard_normal((n, 20)).astype("float32"),
        curves=np.random.default_rng(0).standard_normal((n, 2, 64)).astype("float32"),
        choice=np.zeros((n, 3), dtype=np.int64),
        score=np.zeros(n, dtype=np.int64),
        noul=np.ones(n, dtype="float32"),
        cost=np.zeros(n, dtype="float32"),
        act_state=np.zeros(0, np.int64),
        act_delta=np.zeros((0, 3)),
        act_cost=np.zeros(0),
        act_best=np.zeros(0, np.int8),
    )
    base = JevHead(n_actions=7)
    before = {k: v.clone() for k, v in base.state_dict().items()}
    out = train_head(data, epochs=1, batch=16, seed=0, model=base, verbose=False)
    assert out is base
    changed = any(not torch.equal(before[k], v) for k, v in base.state_dict().items())
    assert changed


def test_specialize_requires_a_plant():
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "10_specialize.py")],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO / "src")},
        timeout=120,
    )
    assert proc.returncode != 0
    assert "scenario" in (proc.stderr + proc.stdout).lower()
