"""Shared provenance and sampling helpers for reproducible experiment scripts."""
from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def sha256(path):
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def manifest(args, *, files=(), extra=None):
    root = Path(__file__).resolve().parents[1]
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, text=True).strip())
    except (OSError, subprocess.SubprocessError):
        revision, dirty = None, None
    sources = list(root.glob("src/jev_tune/**/*.py")) + list(root.glob("scripts/*.py"))
    hashes = {str(p.relative_to(root)): sha256(p) for p in sources}
    for filename in files:
        p = Path(filename)
        hashes[str(p)] = sha256(p)
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_revision": revision,
        "tracked_worktree_dirty": dirty,
        "arguments": vars(args),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "packages": {name: importlib.metadata.version(name)
                     for name in ("numpy", "scipy", "torch", "scikit-learn")},
        "file_sha256": hashes,
        **(extra or {}),
    }


def training_indices(n):
    """Exactly the state split used by scripts/02_train.py."""
    idx = np.random.default_rng(0).permutation(n)
    return idx[:int(0.9*n)], idx[int(0.9*n):]


def conformal_evidence_lines(calibration, *, zh=False):
    """Describe independent label-set evidence without equating it to safety."""
    cp = calibration.get('split_conformal')
    if not cp:
        return []
    def values(v):
        return '[' + ', '.join(f'{float(x):.4f}' for x in v) + ']'
    ev = cp.get('evaluation', {})
    first = (f"CP alpha={cp['alpha']}, n={cp['n_calibration']}, "
             f"rank={cp['quantile_rank']}, qhat={values(cp['qhat_per_axis'])}.")
    second = (
        ("独立评估的专家标签逐轴覆盖率" if zh else "Independent evaluation teacher-label coverage per axis")
        + f" {values(ev.get('coverage_per_axis', []))}; "
        + ("平均集合大小" if zh else "mean set size")
        + f" {values(ev.get('mean_set_size_per_axis', []))}."
    )
    limitation = (
        '这是IID对象初态分布上的标签集合覆盖诊断，不保证多步闭环、域外分布或获准执行子集达到90%覆盖，也不是闭环改善概率或安全保证。'
        if zh else 'This diagnoses label-set coverage on IID plant initial states. It does not ensure 90% coverage over multi-step rollouts, shifted domains or the accepted-action subset, nor does it certify closed-loop improvement or safety.'
    )
    return [first, '', second + ' ' + limitation, '']


def expectation_preserving_probs(values, deltas):
    """Barycentric two-neighbour projection; E[delta] == clipped values.

    This is an experiment adapter, not a production regression decoder.
    Variance shrinkage must be disabled for this continuous-output control.
    """
    d = np.asarray(deltas, dtype=float)
    if d.ndim != 1 or len(d) < 2 or not np.all(np.diff(d) > 0):
        raise ValueError("deltas must be a strictly increasing vocabulary")
    x = np.clip(np.asarray(values, dtype=float), d[0], d[-1])
    hi = np.clip(np.searchsorted(d, x, side="right"), 1, len(d)-1)
    lo = hi - 1
    weight = (x-d[lo])/(d[hi]-d[lo])
    probs = np.zeros(x.shape + (len(d),))
    np.put_along_axis(probs, lo[..., None], (1-weight)[..., None], axis=-1)
    np.put_along_axis(probs, hi[..., None], weight[..., None], axis=-1)
    return probs
