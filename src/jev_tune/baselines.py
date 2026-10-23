"""Classical baselines, all batched across plants.

Every method returns the same ``BaselineResult`` so the comparison table can be
built mechanically: wall-clock, simulations used, and best-so-far cost after
each evaluation batch.

Budget honesty (see ``docs/BENCHMARK.md``):

* ``eval_axis`` is the number of closed-loop simulations spent *per plant*,
  including the ones a method needs to estimate its own priors;
* iterative competitors in ``scripts/03_evaluate.py`` share a maximum budget;
  one-shot competitors report their smaller actual counts;
* the head's training cost is paid once, off-line, and is **not** in its
  per-plant budget -- that asymmetry is stated in the README rather than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .decode import ActionSpace
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


def run_shrunk_zn(plants: PlantSet, factors) -> BaselineResult:
    """Z-N scaled by a fixed triple, e.g. ``(0.3, 0.1, 1.0)``.

    One simulation at deployment.  ``choose_zn_shrink`` picks the triple on the
    *training* families; that selection is a prior, like the head's weights, and
    its cost is reported separately instead of being hidden.
    """
    f = np.asarray(factors, dtype=float)
    g = zn_gains(plants) * f
    j = _eval(plants, g)
    return BaselineResult(
        name="shrunk_zn",
        gains=g,
        best_j=j,
        history=j[:, None],
        eval_axis=np.array([1.0]),
    )


def choose_zn_shrink(
    train_plants: PlantSet,
    *,
    kp=(0.15, 0.25, 0.35, 0.5, 0.75),
    ki=(0.02, 0.05, 0.1, 0.25, 0.5),
    kd=(0.25, 0.5, 1.0, 2.0),
) -> tuple[tuple[float, float, float], float, int]:
    """Grid-search the Z-N scale triple on the training zoo.

    Returns ``(factors, median_train_cost, simulations_per_train_plant)``.
    """
    best, best_j = None, np.inf
    for a in kp:
        for b in ki:
            for c in kd:
                j = _eval(train_plants, zn_gains(train_plants) * np.array([a, b, c]))
                m = float(np.median(j))
                if m < best_j:
                    best, best_j = (a, b, c), m
    return best, best_j, len(kp) * len(ki) * len(kd)


# --------------------------------------------------------------------------- #
# Relay feedback autotune (Astrom-Hagglund)
# --------------------------------------------------------------------------- #


def relay_estimate(
    plants: PlantSet, *, horizon: float = 30.0, ts: float = 5e-3
) -> tuple[np.ndarray, np.ndarray]:
    """Astrom-Hagglund relay experiment: Ku, Tu from the limit cycle.

    This *is* one experiment on the real loop (a relay is wired around the
    controller and the oscillation is measured), so callers that feed these
    numbers to another method must count one simulation for it.
    """
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
    return np.where(bad, np.nan, ku), np.where(bad, np.nan, tu)


def run_relay(
    plants: PlantSet, *, horizon: float = 30.0, ts: float = 5e-3
) -> BaselineResult:
    ku, tu = relay_estimate(plants, horizon=horizon, ts=ts)
    ku = np.where(np.isfinite(ku), ku, 1.0)
    tu = np.where(np.isfinite(tu), tu, 1.0)
    g = np.column_stack([0.6 * ku, 1.2 * ku / tu, 0.075 * ku * tu])
    j = _eval(plants, g)
    return BaselineResult(
        name="relay_zn",
        gains=g,
        best_j=j,
        history=j[:, None],
        eval_axis=np.array([2.0]),  # relay experiment + one verification run
    )


# --------------------------------------------------------------------------- #
# Batched Nelder-Mead simplex
# --------------------------------------------------------------------------- #


def run_simplex(
    plants: PlantSet, x0: np.ndarray, *, budget: int = 60, step: float = 0.15
) -> BaselineResult:
    """Bounded simplex search, measuring the shared start within the budget.

    Budgets below four measure only the available initial vertices. Every
    measurement, including batch-wide contractions, competes for returned best.
    """
    if budget < 1:
        raise ValueError("budget must be positive")
    n = plants.n
    start = np.clip(np.asarray(x0, dtype=float), 1e-4, 1e3)
    sim = np.repeat(np.log10(start)[None], 4, axis=0)  # (4,n,3)
    for k in range(3):
        sim[k + 1, :, k] += step
    sim = np.clip(sim, LOG_LO, LOG_HI)
    fv = np.full((4, n), np.inf)
    best_j = np.full(n, np.inf)
    best_gains = start.copy()
    history = []
    evals = 0

    def measure(gains):
        nonlocal evals, best_j, best_gains
        values = _eval(plants, gains)
        improved = values < best_j
        best_j = np.where(improved, values, best_j)
        best_gains = np.where(improved[:, None], gains, best_gains)
        evals += 1
        history.append(best_j.copy())
        return values

    for k in range(min(4, budget)):
        fv[k] = measure(start if k == 0 else 10**sim[k])

    while evals < budget:
        if evals + 1 > budget:  # not even one reflection left
            break
        order = np.argsort(fv, axis=0)
        sim = np.take_along_axis(sim, order[:, :, None], axis=0)
        fv = np.take_along_axis(fv, order, axis=0)

        centroid = sim[:3].mean(axis=0)
        xr = np.clip(centroid + (centroid - sim[3]), LOG_LO, LOG_HI)
        fr = measure(10**xr)
        better = fr < fv[2]
        sim[3] = np.where(better[:, None], xr, sim[3])
        fv[3] = np.where(better, fr, fv[3])

        if (~better).any():
            base = sim[0]
            for k in range(1, 4):
                if evals + 1 > budget:  # do not overshoot the budget
                    break
                cand = np.clip(base + 0.5 * (sim[k] - base), LOG_LO, LOG_HI)
                fk = measure(10**cand)
                sim[k] = np.where((~better)[:, None], cand, sim[k])
                fv[k] = np.where(~better, fk, fv[k])

    return BaselineResult(
        name="simplex",
        gains=best_gains,
        best_j=best_j,
        history=np.column_stack(history),
        eval_axis=np.arange(1, evals + 1, dtype=float),
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
    """Measure the shared start, then spend the remaining budget on samples.

    The returned gain set is an actually evaluated candidate, not the final
    distribution mean (which need not have been evaluated).
    """
    if budget < 1 or lam < 1:
        raise ValueError("budget and population size must be positive")
    rng = np.random.default_rng(seed)
    n = plants.n
    best_gains = np.clip(np.asarray(x0, dtype=float), 10**LOG_LO, 10**LOG_HI).copy()
    opt = _DiagCMA(n, np.log10(best_gains))

    best = _eval(plants, best_gains)
    history, axis_ = [best.copy()], [1.0]
    evals = 1
    idx = np.arange(n)
    while evals < budget:
        m = min(lam, budget - evals)
        cand = np.clip(opt.ask(m, rng), LOG_LO, LOG_HI)
        flat = plants.take(np.tile(idx, m))
        sampled_gains = 10**cand
        j = _eval(flat, sampled_gains.reshape(-1, 3)).reshape(m, n)
        evals += m
        opt.tell(cand, j)
        winner = np.argmin(j, axis=0)
        candidate_cost = j[winner, idx]
        improved = candidate_cost < best
        best_gains = np.where(
            improved[:, None], sampled_gains[winner, idx], best_gains
        )
        best = np.minimum(best, candidate_cost)
        history.append(best.copy())
        axis_.append(float(evals))

    return BaselineResult(
        name="cmaes",
        gains=best_gains,
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
    """Bayesian optimisation with the shared starting point in its budget."""
    if budget < 1:
        raise ValueError("budget must be positive")
    from scipy.stats import norm
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel, Matern

    rng = np.random.default_rng(seed)
    n = plants.n
    # a budget below the default initial design would otherwise spend more
    # experiments than the budget it was given
    n_init = max(1, min(n_init, budget))
    kernel = ConstantKernel(1.0) * Matern(length_scale=0.4, nu=2.5)

    X = np.clip(
        np.log10(np.maximum(x0, 1e-9))[None] + rng.normal(0, 0.2, size=(n_init, n, 3)),
        LOG_LO,
        LOG_HI,
    )
    X[0] = np.clip(np.log10(np.maximum(x0, 1e-9)), LOG_LO, LOG_HI)
    Y = np.stack([_eval(plants, 10 ** X[k]) for k in range(n_init)])  # (n_init,n)

    best = Y.min(axis=0)
    history = list(np.minimum.accumulate(Y, axis=0))
    axis_ = list(np.arange(1, n_init + 1, dtype=float))
    evals = n_init

    for _ in range(budget - n_init):
        xn = np.zeros((n, 3))
        for i in range(n):
            gp = GaussianProcessRegressor(
                kernel=kernel, optimizer=None, normalize_y=True
            )
            gp.fit(X[:, i, :], Y[:, i])
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


def run_swept_zn(
    plants: PlantSet, *, horizon: float = 4.0, n_grid: int = 7
) -> BaselineResult:
    """Z-N from Ku/Tu measured by a Kp sweep (what the Simulink bridge does).

    The sweep is 7 deliberately unstable runs, so the row is charged 8
    experiments (7 + one verification run) instead of pretending Ku is free.
    """
    from .plants import estimate_ultimate_gain

    ku, tu, sims = estimate_ultimate_gain(plants, horizon=horizon, n_grid=n_grid)
    ok = np.isfinite(ku) & np.isfinite(tu) & (ku > 0) & (tu > 0)
    ku = np.where(ok, ku, 1.0)
    tu = np.where(ok, tu, 1.0)
    g = np.column_stack([0.6 * ku, 1.2 * ku / tu, 0.075 * ku * tu])
    j = _eval(plants, g)
    return BaselineResult(
        name="swept_zn",
        gains=g,
        best_j=j,
        history=j[:, None],
        eval_axis=np.array([float(sims + 1)]),
    )


def run_vocab_hill(
    plants: PlantSet,
    x0: np.ndarray,
    *,
    budget: int = 20,
    space: ActionSpace | None = None,
) -> BaselineResult:
    """Greedy hill climb over the *same* vocabulary the head emits.

    Each experiment probes one (axis, multiplier) candidate in a fixed
    round-robin order (one step of Kp, Ki, Kd at 0.5x, then at 0.7x, ...),
    accepts the candidate if it lowers the cost, and stops when the budget is
    spent.  No prior, no model, same action space, same number of experiments:
    this is the cheapest honest "is the learned prior doing anything" control.
    """
    space = space or ActionSpace()
    n = plants.n
    gains = np.asarray(x0, dtype=float).copy()
    best = _eval(plants, gains)
    history = [best.copy()]
    axis_ = [1.0]

    order = [(axis, k) for k in range(space.k) for axis in range(3)]
    for i, (axis, k) in enumerate(order[: max(0, budget - 1)], start=2):
        trial = gains.copy()
        trial[:, axis] = np.clip(trial[:, axis] * space.multipliers[k], 1e-4, 1e3)
        jt = _eval(plants, trial)
        better = jt < best
        best = np.where(better, jt, best)
        gains = np.where(better[:, None], trial, gains)
        history.append(best.copy())
        axis_.append(float(i))

    return BaselineResult(
        name="vocab_hill",
        gains=gains,
        best_j=best,
        history=np.column_stack(history),
        eval_axis=np.asarray(axis_),
    )


def run_grid(
    plants: PlantSet,
    x0: np.ndarray,
    *,
    kp: tuple[float, ...] = (0.4, 0.7, 1.0, 1.4, 2.0),
    ki: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 4.0),
    kd: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 4.0),
    batch: int = 25,
) -> BaselineResult:
    """Brute-force log-spaced grid around Z-N -- the "linear sweep" baseline.

    This is what people do when they have no model and no policy: multiply each
    gain through a fixed set of factors and keep the best.  Cost is the full
    grid, 125 simulations for the default 5x5x5.
    """
    n = plants.n
    grid = np.array(np.meshgrid(kp, ki, kd, indexing="ij")).reshape(3, -1).T
    total = grid.shape[0]

    history, axis_ = [], []
    best = np.full(n, np.inf)
    best_gains = np.asarray(x0, dtype=float).copy()
    evals = 0
    for start in range(0, total, batch):
        chunk = grid[start : start + batch]
        m = chunk.shape[0]
        flat = plants.take(np.tile(np.arange(n), m))
        gains = (x0[None, :, :] * chunk[:, None, :]).reshape(-1, 3)
        j = _eval(flat, gains).reshape(m, n)
        evals += m
        winner = np.argmin(j, axis=0)
        candidate_cost = j[winner, np.arange(n)]
        candidate_gains = gains.reshape(m, n, 3)[winner, np.arange(n)]
        improved = candidate_cost < best
        best_gains = np.where(improved[:, None], candidate_gains, best_gains)
        best = np.minimum(best, candidate_cost)
        history.append(best.copy())
        axis_.append(float(evals))

    return BaselineResult(
        name="grid_sweep",
        gains=best_gains,
        best_j=best,
        history=np.column_stack(history),
        eval_axis=np.asarray(axis_),
    )


__all__ = [
    "BaselineResult",
    "zn_gains",
    "run_zn",
    "run_shrunk_zn",
    "choose_zn_shrink",
    "relay_estimate",
    "run_relay",
    "run_swept_zn",
    "run_simplex",
    "run_vocab_hill",
    "run_cmaes",
    "run_bo",
    "run_grid",
]
