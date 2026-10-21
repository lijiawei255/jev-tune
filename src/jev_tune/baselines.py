"""Classical baselines, all batched across plants.

Every method returns the same ``BaselineResult`` so the comparison table can be
built mechanically: wall-clock, simulations used, and best-so-far cost after
each evaluation batch.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .metrics import cost_from_metrics
from .plants import PlantSet, simulate, ultimate_gain

ZN_TABLE = {
    # (Kp/Ku, Ki*Tu/Ku, Kd/(Ku*Tu)) -- classic Ziegler-Nichols variants
    "classic": (0.6, 1.2, 0.075),
    "some_overshoot": (0.33, 0.66, 0.11),
    "no_overshoot": (0.2, 0.4, 0.0667),
}

LOG_LO, LOG_HI = np.log10(1e-4), np.log10(1e3)


@dataclass
class BaselineResult:
    name: str
    gains: np.ndarray  # (N,3)
    best_j: np.ndarray  # (N,)
    history: np.ndarray  # (N, n_batches) best-so-far cost
    eval_axis: np.ndarray  # (n_batches,) cumulative simulations per plant
    wall_s: float = 0.0

    def sims_to_target(self, target: np.ndarray) -> np.ndarray:
        hit = self.history <= np.asarray(target)[:, None]
        idx = np.argmax(hit, axis=1)
        out = np.where(hit.any(axis=1), self.eval_axis[idx], np.inf)
        return out


def _eval(plants: PlantSet, gains: np.ndarray) -> np.ndarray:
    res = simulate(plants, gains)
    return cost_from_metrics(res["metrics"], y_curve=res["y_curve"])


# --------------------------------------------------------------------------- #
# Ziegler-Nichols (analytic ultimate gain)
# --------------------------------------------------------------------------- #


def zn_gains(plants: PlantSet, variant: str = "classic") -> np.ndarray:
    ku, tu = ultimate_gain(plants)
    kp_f, ki_fac, kd_fac = ZN_TABLE[variant]
    ku = np.where(np.isfinite(ku), ku, 1.0)
    tu = np.where(np.isfinite(tu) & (tu > 1e-6), tu, 1.0)
    kp = kp_f * ku
    ki = ki_fac * ku / tu
    kd = kd_fac * ku * tu
    return np.column_stack([kp, ki, kd])


def run_zn(plants: PlantSet, variant: str = "classic") -> BaselineResult:
    g = zn_gains(plants, variant)
    j = _eval(plants, g)
    return BaselineResult(
        name=f"zn_{variant}",
        gains=g,
        best_j=j,
        history=j[:, None],
        eval_axis=np.array([1.0]),
    )


# --------------------------------------------------------------------------- #
# Relay feedback autotune (Astrom-Hagglund)
# --------------------------------------------------------------------------- #


def run_relay(
    plants: PlantSet, *, horizon: float = 30.0, ts: float = 5e-3
) -> BaselineResult:
    n = plants.n
    nsteps = int(horizon / ts)
    x = np.zeros((n, plants.a.shape[1]))
    d_steps = np.clip(np.round(plants.delay_s / ts).astype(int), 0, nsteps - 1)
    dmax = int(d_steps.max())
    hist = np.zeros((n, dmax + 1))
    rows = np.arange(n)
    d = 0.05 * (plants.u_max - plants.u_min)
    u = np.full(n, d)
    prev_sign = np.sign(u)
    flips, flip_y = [], []

    for k in range(nsteps):
        u_del = hist[rows, dmax - d_steps]
        y = np.einsum("ni,ni->n", x, plants.c) + plants.d * u_del
        u = np.where(y > 0.5, -d, d)
        s = np.sign(u)
        changed = s != prev_sign
        if changed.any():
            flips.append(np.where(changed, k * ts, np.nan))
            flip_y.append(np.where(changed, y, np.nan))
        prev_sign = s
        x = np.einsum("nij,nj->ni", plants.a, x) + plants.b * u_del[:, None]
        hist = np.roll(hist, -1, axis=1)
        hist[:, -1] = u

    ku = np.full(n, np.nan)
    tu = np.full(n, np.nan)
    if flips:
        T = np.vstack(flips)
        Y = np.vstack(flip_y)
        for i in range(n):
            tt = T[:, i][~np.isnan(T[:, i])]
            yy = Y[:, i][~np.isnan(Y[:, i])]
            if len(tt) >= 5 and len(yy) >= 5:
                period = 2 * float(np.median(np.diff(tt)))
                amp = 0.5 * (np.nanmax(yy[-4:]) - np.nanmin(yy[-4:]))
                if period > 1e-6 and amp > 1e-9:
                    tu[i] = period
                    ku[i] = 4 * d[i] / (np.pi * amp)
    bad = ~np.isfinite(ku) | ~np.isfinite(tu)
    ku = np.where(bad, 1.0, ku)
    tu = np.where(bad, 1.0, tu)
    g = np.column_stack([0.6 * ku, 1.2 * ku / tu, 0.075 * ku * tu])
    j = _eval(plants, g)
    return BaselineResult(
        name="relay_zn",
        gains=g,
        best_j=j,
        history=j[:, None],
        eval_axis=np.array([2.0]),
    )


# --------------------------------------------------------------------------- #
# Batched Nelder-Mead simplex
# --------------------------------------------------------------------------- #


def run_simplex(
    plants: PlantSet, x0: np.ndarray, *, budget: int = 60, step: float = 0.15
) -> BaselineResult:
    n = plants.n
    sim = np.repeat(np.log10(np.maximum(x0, 1e-9))[None], 4, axis=0)  # (4,n,3)
    for k in range(3):
        sim[k + 1, :, k] += step

    plants4 = plants.take(np.tile(np.arange(n), 4))
    fv = _eval(plants4, (10**sim).reshape(-1, 3)).reshape(4, n)

    history = [fv.min(axis=0).copy()]
    axis_ = [4.0]
    evals = 4

    while evals < budget:
        order = np.argsort(fv, axis=0)
        sim = np.take_along_axis(sim, order[:, :, None], axis=0)
        fv = np.take_along_axis(fv, order, axis=0)

        centroid = sim[:3].mean(axis=0)
        xr = centroid + (centroid - sim[3])
        fr = _eval(plants, 10**xr)
        evals += 1
        better = fr < fv[2]
        sim[3] = np.where(better[:, None], xr, sim[3])
        fv[3] = np.where(better, fr, fv[3])

        if (~better).any():
            base = sim[0]
            for k in range(1, 4):
                cand = base + 0.5 * (sim[k] - base)
                fk = _eval(plants, 10**cand)
                evals += 1
                sim[k] = np.where((~better)[:, None], cand, sim[k])
                fv[k] = np.where(~better, fk, fv[k])

        history.append(np.minimum(history[-1], fv.min(axis=0)))
        axis_.append(float(evals))

    order = np.argsort(fv, axis=0)
    best = np.take_along_axis(sim, order[:1, :, None], axis=0)[0]
    return BaselineResult(
        name="simplex",
        gains=10**best,
        best_j=history[-1],
        history=np.column_stack(history),
        eval_axis=np.asarray(axis_),
    )


# --------------------------------------------------------------------------- #
# Batched CMA-ES (diagonal covariance)
# --------------------------------------------------------------------------- #


class _DiagCMA:
    def __init__(self, n: int, x0: np.ndarray, sigma: float = 0.12):
        self.mean = np.asarray(x0, dtype=float).copy()
        self.sigma = np.full(n, sigma)
        self.diag = np.ones((n, 3))

    def ask(self, lam: int, rng: np.random.Generator) -> np.ndarray:
        z = rng.standard_normal((lam, self.mean.shape[0], 3))
        return (
            self.mean[None] + self.sigma[None, :, None] * z * np.sqrt(self.diag)[None]
        )

    def tell(self, cand: np.ndarray, j: np.ndarray):
        lam = cand.shape[0]
        mu = max(1, lam // 2)
        order = np.argsort(j, axis=0)
        w = np.log(mu + 0.5) - np.log(np.arange(1, mu + 1))
        w = w / w.sum()
        best = np.take_along_axis(cand, order[:mu][:, :, None], axis=0)
        new_mean = np.einsum("m,mni->ni", w, best)
        var = np.einsum("m,mni->ni", w, (best - new_mean[None]) ** 2)
        self.mean = new_mean
        self.diag = 0.8 * self.diag + 0.2 * np.maximum(var, 1e-8) / (
            self.sigma[:, None] ** 2
        )
        self.sigma = np.clip(self.sigma * 0.99, 0.02, 0.4)


def run_cmaes(
    plants: PlantSet, x0: np.ndarray, *, budget: int = 120, lam: int = 6, seed: int = 0
) -> BaselineResult:
    rng = np.random.default_rng(seed)
    n = plants.n
    opt = _DiagCMA(n, np.clip(np.log10(np.maximum(x0, 1e-9)), LOG_LO, LOG_HI))

    history, axis_ = [], []
    best = np.full(n, np.inf)
    evals = 0
    idx = np.arange(n)
    for _ in range(max(1, budget // lam)):
        cand = opt.ask(lam, rng)
        flat = plants.take(np.tile(idx, lam))
        j = _eval(flat, (10 ** np.clip(cand, LOG_LO, LOG_HI)).reshape(-1, 3)).reshape(
            lam, n
        )
        evals += lam
        opt.tell(cand, j)
        best = np.minimum(best, j.min(axis=0))
        history.append(best.copy())
        axis_.append(float(evals))

    return BaselineResult(
        name="cmaes",
        gains=10 ** np.clip(opt.mean, LOG_LO, LOG_HI),
        best_j=best,
        history=np.column_stack(history),
        eval_axis=np.asarray(axis_),
    )


# --------------------------------------------------------------------------- #
# Bayesian optimisation (GP + expected improvement)
# --------------------------------------------------------------------------- #


def run_bo(
    plants: PlantSet,
    x0: np.ndarray,
    *,
    budget: int = 32,
    seed: int = 0,
    n_init: int = 6,
) -> BaselineResult:
    from scipy.stats import norm
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel, Matern

    rng = np.random.default_rng(seed)
    n = plants.n
    kernel = ConstantKernel(1.0) * Matern(length_scale=0.4, nu=2.5)

    X = np.clip(
        np.log10(np.maximum(x0, 1e-9))[None] + rng.normal(0, 0.2, size=(n_init, n, 3)),
        LOG_LO,
        LOG_HI,
    )
    Y = np.stack([_eval(plants, 10 ** X[k]) for k in range(n_init)])  # (n_init,n)

    best = Y.min(axis=0)
    history = [best.copy()]
    axis_ = [float(n_init)]
    evals = n_init

    for _ in range(budget - n_init):
        xn = np.zeros((n, 3))
        for i in range(n):
            gp = GaussianProcessRegressor(
                kernel=kernel, optimizer=None, normalize_y=True
            )
            gp.fit(X[: evals - n_init + n_init][:, i, :], Y[:, i])
            cand = rng.uniform(LOG_LO, LOG_HI, size=(512, 3))
            mu, sd = gp.predict(cand, return_std=True)
            sd = np.maximum(sd, 1e-9)
            z = (best[i] - mu) / sd
            ei = (best[i] - mu) * norm.cdf(z) + sd * norm.pdf(z)
            xn[i] = cand[int(np.argmax(ei))]
        j = _eval(plants, 10**xn)
        evals += 1
        X = np.concatenate([X, xn[None]], axis=0)
        Y = np.concatenate([Y, j[None]], axis=0)
        best = np.minimum(best, j)
        history.append(best.copy())
        axis_.append(float(evals))

    gi = np.argmin(Y, axis=0)
    gains = 10 ** X[gi, np.arange(n)]
    return BaselineResult(
        name="bo",
        gains=gains,
        best_j=best,
        history=np.column_stack(history),
        eval_axis=np.asarray(axis_),
    )


__all__ = [
    "BaselineResult",
    "zn_gains",
    "run_zn",
    "run_relay",
    "run_simplex",
    "run_cmaes",
    "run_bo",
]
