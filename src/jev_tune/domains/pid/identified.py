"""The realistic practitioner baseline: identify, then design.

An engineer rarely has the exact transfer function.  The usual workflow is:

1. one open-loop step test -> first-order-plus-dead-time (FOPDT) fit,
2. `pidtune` on the fitted model (with a Pade approximation of the delay),
3. one verification run.

The implemented linear-probe baseline costs two simulations when it succeeds.
Unsupported probe physics, missing MATLAB and failed designs are explicit
failures; they never substitute gains computed from the true plant model.
"""

from __future__ import annotations

import numpy as np

from .baselines import BaselineResult, _eval
from .plants import PlantSet


class IdentificationUnavailable(RuntimeError):
    """An unreported controller must not masquerade as identify + pidtune."""

    def __init__(self, reason: str, *, status: str, simulations_per_plant: int = 0):
        super().__init__(reason)
        self.status = status
        self.simulations_per_plant = simulations_per_plant


def open_loop_step(
    plants: PlantSet, *, u: float = 1.0, ts: float = 5e-3, horizon: float = 10.0
):
    """Constant-input open-loop response (N, n_curve) plus time vector."""
    n = plants.n
    nsteps = int(round(horizon / ts)) + 1
    t = np.arange(nsteps) * ts
    x = np.zeros((n, plants.a.shape[1]))
    d_steps = np.clip(np.round(plants.delay_s / ts).astype(int), 0, nsteps - 1)
    dmax = int(d_steps.max())
    hist = np.zeros((n, dmax + 1))
    rows = np.arange(n)
    n_curve = 64
    idx = np.linspace(0, nsteps - 1, n_curve).round().astype(int)
    y_curve = np.zeros((n, n_curve))
    ci = 0
    y = np.zeros(n)
    for k in range(nsteps):
        u_del = hist[rows, dmax - d_steps]
        y = np.einsum("ni,ni->n", x, plants.c) + plants.d * u_del
        x = np.einsum("nij,nj->ni", plants.a, x) + plants.b * u_del[:, None]
        hist = np.roll(hist, -1, axis=1)
        hist[:, -1] = u
        if ci < n_curve and k == idx[ci]:
            y_curve[:, ci] = y
            ci += 1
    return t[idx], y_curve


def identify_fopdt(t: np.ndarray, y: np.ndarray, u: float = 1.0):
    """Two-point (28.3 %, 63.2 %) FOPDT fit.  y: (N, T)."""
    k_ss = y[:, -1] / u
    k_ss = np.where(np.abs(k_ss) < 1e-6, 1e-6, k_ss)
    t283 = np.full(y.shape[0], np.nan)
    t632 = np.full(y.shape[0], np.nan)
    for i in range(y.shape[0]):
        target283 = 0.283 * y[i, -1]
        target632 = 0.632 * y[i, -1]
        i283 = np.argmax(y[i] >= target283) if np.any(y[i] >= target283) else -1
        i632 = np.argmax(y[i] >= target632) if np.any(y[i] >= target632) else -1
        if i283 > 0:
            t283[i] = t[i283]
        if i632 > 0:
            t632[i] = t[i632]
    tau = 1.5 * (t632 - t283)
    delay = np.maximum(t632 - tau, 0.0)
    tau = np.where(np.isfinite(tau) & (tau > 1e-4), tau, 0.5)
    delay = np.where(np.isfinite(delay), delay, 0.05)
    return k_ss, tau, delay


def fopdt_pade_tf(k, tau, delay):
    """(num, den) matrices for K (1 - Ls/2) / ((tau s + 1)(1 + Ls/2))."""
    n = len(k)
    nd = 3
    num = np.zeros((n, nd))
    den = np.zeros((n, nd))
    for i in range(n):
        L = max(delay[i], 1e-3)
        num[i] = np.concatenate([[0.0], k[i] * np.array([-L / 2.0, 1.0])])
        den[i] = np.convolve([tau[i], 1.0], [L / 2.0, 1.0])
    return num, den


def run_identify_pidtune(plants: PlantSet, ctype: str = "PID") -> BaselineResult:
    from .matlab_baseline import matlab_available, pidtune_gains

    if not matlab_available():
        raise IdentificationUnavailable("MATLAB is unavailable; no identification or verification was run", status="unavailable")
    # open_loop_step is a linear constant-input probe, not the nonlinear
    # simulator. Reject cases it cannot represent instead of claiming a real
    # actuator/sensor experiment or silently consulting the transfer-function
    # oracle to replace a failed controller.
    unsupported = (plants.u_max < 1.0) | (plants.u_min > 0.0)
    if plants.dead_zone is not None:
        unsupported |= plants.dead_zone != 0
    if plants.noise_sigma is not None:
        unsupported |= plants.noise_sigma != 0
    if unsupported.any():
        raise IdentificationUnavailable(
            "linear open-loop probe does not implement the requested saturation, dead zone or sensor noise",
            status="unsupported_probe_physics",
        )
    t, y = open_loop_step(plants)
    k, tau, delay = identify_fopdt(t, y)
    num, den = fopdt_pade_tf(k, tau, delay)

    proxy = PlantSet(
        n=plants.n,
        family=plants.family,
        num=num,
        den=den,
        delay_s=np.zeros(plants.n),
        a=plants.a,
        b=plants.b,
        c=plants.c,
        d=plants.d,
        u_max=plants.u_max,
        u_min=plants.u_min,
        params=plants.params,
    )

    try:
        gains, _ = pidtune_gains(proxy, ctype)
    except Exception as exc:
        raise IdentificationUnavailable(
            f"pidtune design failed after the probe: {exc}", status="failed_design",
            simulations_per_plant=1,
        ) from exc

    bad = (~np.isfinite(gains)).any(axis=1) | (gains[:, 0] <= 0)
    if bad.any():
        raise IdentificationUnavailable(
            f"pidtune returned invalid gains for {int(bad.sum())}/{plants.n} plants; whole arm omitted, no oracle fallback",
            status="failed_design", simulations_per_plant=1,
        )

    j = _eval(plants, gains)
    return BaselineResult(
        name=f"identify+pidtune_{ctype}",
        gains=gains,
        best_j=j,
        history=j[:, None],
        eval_axis=np.array([2.0]),  # one step test + one verification run
    )
