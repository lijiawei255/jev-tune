"""Vectorised plant zoo and closed-loop simulation.

Everything is batched across plants: one call simulates N plants x M gain
vectors at once, which is what makes CPU-only dataset generation cheap.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import signal

# --------------------------------------------------------------------------- #
# Plant sampling
# --------------------------------------------------------------------------- #

TRAIN_FAMILIES = (
    "fopdt",
    "sopdt",
    "third_rhp",
    "integrating",
    "pmsm_speed",
    "position_loop",
)
HELDOUT_FAMILIES = ("two_mass",)

# actuator range: unit DC gain plants need u_ss = 1 for a unit step, so 2.5x
# peak headroom reproduces a real drive (rated + peak current) rather than an
# actuator that is permanently saturated
_U_RANGE = (-2.5, 2.5)


def _tf(family: str, p: dict):
    """Return (num, den) for one family member."""
    if family == "fopdt":
        return np.array([p["K"]]), np.array([p["T"], 1.0])
    if family == "sopdt":
        wn, z = p["wn"], p["zeta"]
        return np.array([p["K"] * wn**2]), np.array([1.0, 2 * z * wn, wn**2])
    if family == "third_rhp":
        wn, z, zr = p["wn"], p["zeta"], p["z_rhp"]
        # RHP zero at +zr, expressed in rad/s and tied to wn (0.5..3 x wn)
        return (
            np.array([-p["K"] * wn**2 / zr, p["K"] * wn**2]),
            np.array(
                [1.0, 2 * z * wn + p["p"], wn**2 + 2 * z * wn * p["p"], wn**2 * p["p"]]
            ),
        )
    if family == "integrating":
        return np.array([p["K"]]), np.array([p["T"], 1.0, 0.0])
    if family == "pmsm_speed":
        # K / ( s (tau_e s + 1)(tau_m s + 1) )
        te, tm = p["tau_e"], p["tau_m"]
        return (
            np.array([p["K"]]),
            np.array([te * tm, te + tm, 1.0, 0.0]),
        )
    if family == "position_loop":
        # type-1 3rd order: current loop (fast) -> speed loop (slow) -> 1/s.
        # This is the shape of the motor-valve benchmark motor: K / (s (T1 s + 1)(T2 s + 1)).
        t1, t2 = p["tau_c"], p["tau_s"]
        return (
            np.array([p["K"]]),
            np.convolve(np.array([t1, 1.0, 0.0]), np.array([t2, 1.0])),
        )
    if family == "two_mass":
        # two-mass resonance: K * wa^2 / ((s^2+2 z1 w1 s+w1^2)(s^2+2 za wa s+wa^2))
        w1, z1, wa, za = p["w1"], p["z1"], p["wa"], p["za"]
        d1 = np.array([1.0, 2 * z1 * w1, w1**2])
        d2 = np.array([1.0, 2 * za * wa, wa**2])
        return np.array([p["K"] * wa**2]), np.convolve(d1, d2)
    raise ValueError(f"unknown family {family}")


def _normalize_gain(num: np.ndarray, den: np.ndarray):
    """Scale so the plant has unit DC gain (unit velocity gain if integrating).

    Without this every plant would need its own actuator range and the gain
    scale of the tuning problem would be arbitrary.
    """
    if abs(den[-1]) > 1e-12:
        g0 = num[-1] / den[-1]
    else:  # pure integrator: normalise against the 1/s behaviour
        g0 = num[-1]
    if abs(g0) > 1e-12:
        num = num / g0
    return num, den


def _dominant_time(p: dict) -> float:
    """Dominant time constant of a sampled plant (used to size the delay)."""
    for key in ("T", "tau_m", "tau_s"):
        if key in p:
            return float(p[key])
    for key in ("wn", "w1"):
        if key in p:
            return 1.0 / max(float(p[key]), 1e-6)
    return 0.1


def _sample_params(family: str, rng: np.random.Generator, heldout: bool) -> dict:
    if heldout:  # shifted, wider, never seen in training
        lo, hi = 1.15, 1.6
    else:
        lo, hi = 1.0, 1.0
    s = lambda a, b: float(rng.uniform(a, b))  # noqa: E731
    l = lambda a, b: float(np.exp(rng.uniform(np.log(a), np.log(b))))  # noqa: E731

    if family == "fopdt":
        return {"K": s(0.5, 2.0) * lo, "T": l(0.05, 2.0) * hi, "tdom": None}
    if family == "sopdt":
        return {
            "K": s(0.5, 2.0) * lo,
            "wn": l(2.0, 60.0) / hi,
            "zeta": s(0.08, 1.2),
        }
    if family == "third_rhp":
        return {
            "K": s(0.5, 2.0),
            "wn": l(3.0, 40.0) / hi,
            "zeta": s(0.15, 0.9),
            "p": l(2.0, 30.0),
            "z_rhp": l(0.5, 3.0) * l(3.0, 40.0),
        }
    if family == "integrating":
        return {"K": s(0.1, 1.0), "T": l(0.05, 1.0) * hi}
    if family == "pmsm_speed":
        return {
            "K": s(0.2, 3.0),
            "tau_e": l(0.0008, 0.01),
            "tau_m": l(0.02, 0.6) * hi,
        }
    if family == "position_loop":
        return {
            "K": s(0.3, 3.0),
            "tau_c": l(0.003, 0.03),  # current/torque loop
            "tau_s": l(0.05, 0.6) * hi,  # speed loop + mechanics
        }
    if family == "two_mass":
        return {
            "K": s(0.5, 2.0),
            "w1": l(2.0, 12.0),
            "z1": s(0.3, 1.0),
            "wa": l(60.0, 400.0),
            "za": s(0.01, 0.12),
        }
    raise ValueError(family)


@dataclass
class PlantSet:
    """Batched plant representation (all arrays have leading dim n)."""

    n: int
    family: list[str]
    num: np.ndarray  # (n, nd) padded, highest power first
    den: np.ndarray  # (n, nd)
    delay_s: np.ndarray  # (n,)
    a: np.ndarray  # (n, s, s) discrete state matrix
    b: np.ndarray  # (n, s)
    c: np.ndarray  # (n, s)
    d: np.ndarray  # (n,)
    u_max: np.ndarray  # (n,)
    u_min: np.ndarray  # (n,)
    noise_sigma: np.ndarray | None = None  # measurement noise (std, output units)
    dead_zone: np.ndarray | None = None  # actuator dead zone (input units)
    params: list[dict] = field(default_factory=list)

    def subset(self, idx) -> "PlantSet":
        idx = np.atleast_1d(idx)
        return PlantSet(
            n=len(idx),
            family=[self.family[i] for i in idx],
            num=self.num[idx],
            den=self.den[idx],
            delay_s=self.delay_s[idx],
            a=self.a[idx],
            b=self.b[idx],
            c=self.c[idx],
            d=self.d[idx],
            u_max=self.u_max[idx],
            u_min=self.u_min[idx],
            noise_sigma=None if self.noise_sigma is None else self.noise_sigma[idx],
            dead_zone=None if self.dead_zone is None else self.dead_zone[idx],
            params=[self.params[i] for i in idx],
        )

    def take(self, idx) -> "PlantSet":
        """Broadcast index array (allows repeats) -> new PlantSet."""
        idx = np.asarray(idx)
        return PlantSet(
            n=len(idx),
            family=[self.family[i] for i in idx],
            num=self.num[idx],
            den=self.den[idx],
            delay_s=self.delay_s[idx],
            a=self.a[idx],
            b=self.b[idx],
            c=self.c[idx],
            d=self.d[idx],
            u_max=self.u_max[idx],
            u_min=self.u_min[idx],
            noise_sigma=None if self.noise_sigma is None else self.noise_sigma[idx],
            dead_zone=None if self.dead_zone is None else self.dead_zone[idx],
            params=[self.params[i] for i in idx],
        )


def sample_plants(
    n: int,
    seed: int = 0,
    families=TRAIN_FAMILIES,
    heldout: bool = False,
    ts: float = 5e-3,
) -> PlantSet:
    rng = np.random.default_rng(seed)
    fams = [families[i % len(families)] for i in range(n)]
    rng.shuffle(fams)

    num_list, den_list, delays, params = [], [], [], []
    for f in fams:
        p = _sample_params(f, rng, heldout)
        num, den = _tf(f, p)
        num, den = _normalize_gain(num, den)
        params.append(p)
        num_list.append(num)
        den_list.append(den)
        # every digital loop has transport delay (sensor/compute/PWM); size it
        # relative to the dominant time constant, as on real hardware, so that
        # the ultimate gain stays in a physically meaningful range
        delays.append(0.0015 + rng.uniform(0.03, 0.15) * _dominant_time(p))

    # actuator headroom: a tight limit saturates the proportional action, so
    # derivative damping becomes the binding knob (this is the regime where a
    # real position loop like the motor-valve benchmark motor lives)
    u_max = rng.choice(np.array([1.0, 1.6, 2.5]), size=n, p=[0.33, 0.34, 0.33])

    nd = max(len(x) for x in den_list)
    num_mat = np.zeros((n, nd))
    den_mat = np.zeros((n, nd))
    for i, (nu, de) in enumerate(zip(num_list, den_list)):
        num_mat[i, nd - len(nu) :] = nu
        den_mat[i, nd - len(de) :] = de

    # per-plant ZOH discretisation, padded to a common state dimension
    disc = []
    for i in range(n):
        ad, bd, cd, dd, _ = signal.cont2discrete(
            signal.tf2ss(num_list[i], den_list[i]), ts, method="zoh"
        )
        disc.append(
            (
                np.atleast_2d(ad),
                np.atleast_1d(bd),
                np.atleast_1d(cd),
                float(np.asarray(dd).reshape(-1)[0]),
            )
        )

    s = max(x[0].shape[0] for x in disc)
    a = np.zeros((n, s, s))
    b = np.zeros((n, s))
    c = np.zeros((n, s))
    d = np.zeros(n)
    for i, (ad, bd, cd, dd) in enumerate(disc):
        k = ad.shape[0]
        a[i, :k, :k] = ad
        b[i, :k] = np.asarray(bd).reshape(-1)
        c[i, :k] = np.asarray(cd).reshape(-1)
        d[i] = float(np.asarray(dd).reshape(-1)[0])

    return PlantSet(
        n=n,
        family=fams,
        num=num_mat,
        den=den_mat,
        delay_s=np.asarray(delays, dtype=float),
        a=a,
        b=b,
        c=c,
        d=d,
        u_max=u_max,
        u_min=np.full(n, _U_RANGE[0]),
        params=params,
    )


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #

DEFAULT_TS = 5e-3
DEFAULT_HORIZON = 10.0
N_CURVE = 64  # resampled trace length stored per run


def _freq_response(plants: PlantSet, w: np.ndarray) -> np.ndarray:
    """H(jw) for every plant, shape (n, len(w))."""
    deg = plants.den.shape[1] - 1
    jw = 1j * w
    # powers[k] = (jw) ** (deg - k)
    powers = jw[None, :] ** np.arange(deg, -1, -1)[:, None]
    num = plants.num @ powers
    den = plants.den @ powers
    with np.errstate(divide="ignore", invalid="ignore"):
        h = num / den
    # transport delay: pure phase lag, |H| unchanged
    if np.any(plants.delay_s > 0):
        h = h * np.exp(-1j * w[None, :] * plants.delay_s[:, None])
    return h


def ultimate_gain(
    plants: PlantSet, w_lo: float = 1e-2, w_hi: float = 1e4, n_w: int = 6000
):
    """Ultimate gain Ku and ultimate period Tu (phase-crossover search)."""
    w = np.logspace(np.log10(w_lo), np.log10(w_hi), n_w)
    h = _freq_response(plants, w)
    ph = np.unwrap(np.angle(h), axis=1)
    target = -np.pi
    # first crossing from above (phase decreasing from ~0 to -pi)
    cross = ph <= target + 1e-9
    idx = np.argmax(cross, axis=1)
    idx = np.clip(idx, 1, n_w - 1)
    # linear interpolation between idx-1 and idx
    i0 = idx - 1
    ar = np.arange(plants.n)
    p0 = ph[ar, i0]
    p1 = ph[ar, idx]
    w0 = w[i0]
    w1 = w[idx]
    frac = (target - p0) / np.where(np.abs(p1 - p0) < 1e-12, 1e-12, p1 - p0)
    frac = np.clip(frac, 0.0, 1.0)
    wu = w0 + frac * (w1 - w0)
    hw = np.abs(h)[ar, idx]
    ku = 1.0 / np.maximum(hw, 1e-12)
    tu = 2 * np.pi / np.maximum(wu, 1e-9)
    valid = cross.any(axis=1)
    ku = np.where(valid, ku, np.nan)
    tu = np.where(valid, tu, np.nan)
    return ku, tu


def simulate(
    plants: PlantSet,
    gains: np.ndarray,
    *,
    ref: float = 1.0,
    horizon: float = DEFAULT_HORIZON,
    ts: float = DEFAULT_TS,
    n_curve: int = N_CURVE,
    der_filter: float = 0.02,
    profile: str = "step",
    ramp_delay: float = 1.0,
    ramp_rate: float = 0.1,
    disturb_amp: float = 0.0,
    disturb_time: float = 0.0,
):
    """Batch closed-loop step simulation.

    Parameters
    ----------
    plants : PlantSet with n == len(gains) (or n == 1, broadcast)
    gains  : (N, 3) array of (Kp, Ki, Kd)

    Returns
    -------
    dict with 'metrics' (N x n_metrics), 'y_curve', 'u_curve' (N x n_curve)
    """
    gains = np.atleast_2d(np.asarray(gains, dtype=float))
    N = gains.shape[0]
    if plants.n == 1 and N > 1:
        plants = plants.take(np.zeros(N, dtype=int))
    elif plants.n != N:
        raise ValueError(f"plant/gain mismatch: {plants.n} vs {N}")

    nsteps = int(round(horizon / ts)) + 1
    t = np.arange(nsteps) * ts

    kp, ki, kd = gains[:, 0], gains[:, 1], gains[:, 2]
    umax, umin = plants.u_max, plants.u_min
    amp = np.maximum(np.abs(umax - umin), 1e-9)

    d_steps = np.clip(np.round(plants.delay_s / ts).astype(int), 0, nsteps - 1)
    dmax = int(d_steps.max()) if N else 0

    a, b, c, d = plants.a, plants.b, plants.c, plants.d
    x = np.zeros((N, a.shape[1]))
    hist = np.zeros((N, dmax + 1))
    rows = np.arange(N)

    df = np.zeros(N)
    integ = np.zeros(N)
    e_prev = np.zeros(N)
    y_prev = np.zeros(N)

    # integrator clamp: keep Ki*I inside +/- 2*span
    ilim = 2.0 * amp / np.maximum(np.abs(ki), 1e-9)

    alpha = ts / (der_filter + ts)
    y = np.zeros(N)
    curve_idx = np.linspace(0, nsteps - 1, n_curve).round().astype(int)
    y_curve = np.zeros((N, n_curve))
    u_curve = np.zeros((N, n_curve))
    ci = 0

    peak = np.full(N, -np.inf)
    peak_t = np.zeros(N)
    t10 = np.full(N, np.nan)
    t90 = np.full(N, np.nan)
    t_settle = np.zeros(N)
    iae = np.zeros(N)
    itae = np.zeros(N)
    sat = np.zeros(N)
    n_cross = np.zeros(N)
    above = np.zeros(N, dtype=bool)
    prev_y = np.zeros(N)
    sat_max = np.zeros(N)

    # reference profile: a scalar step, or a ramp that starts moving at
    # ramp_delay.  Everything downstream works on r(k) so the metrics stay the
    # same definitions.
    r_vec = np.full((nsteps, N), float(ref))
    if profile == "ramp":
        ramp = np.clip(t - ramp_delay, 0.0, None) * ramp_rate
        r_vec = np.minimum(float(ref), ramp)[:, None] * np.ones((1, N))
    elif profile != "step":
        raise ValueError(f"unknown profile {profile!r}")
    band_vec = 0.02 * np.abs(r_vec)
    lag_sum = np.zeros(N)

    # real sensors are noisy and real valves have a dead band; both are opt-in
    noise = (
        np.zeros(N)
        if plants.noise_sigma is None
        else np.asarray(plants.noise_sigma, float)
    )
    dz = (
        np.zeros(N) if plants.dead_zone is None else np.asarray(plants.dead_zone, float)
    )
    rng = np.random.default_rng(12345)
    has_noise = bool(np.any(noise > 0))

    for k in range(nsteps):
        # buffer layout: hist[:, j] holds u[k-1-dmax+j], so a transport delay of
        # d steps is at index dmax+1-d (clipped: the plant already carries one
        # sample of delay through the ZOH state update)
        u_del = hist[rows, np.clip(dmax + 1 - d_steps, 0, dmax)]
        y = np.einsum("ni,ni->n", x, c) + d * u_del
        if has_noise:
            y = y + noise * rng.standard_normal(N)
            y_curve_noise_flag = True

        r = r_vec[k]
        e = r - y
        integ = np.clip(integ + e * ts, -ilim, ilim)
        # derivative on measurement (no setpoint kick) -- the textbook structure
        de = -(y - y_prev) / ts
        df = df + alpha * (de - df)
        e_prev = e
        y_prev = y

        u_raw = kp * e + ki * integ + kd * df
        if disturb_amp and k * ts >= disturb_time:
            # load disturbance on the plant input (not on the measurement)
            pass
        if np.any(dz > 0):
            u_raw = np.sign(u_raw) * np.maximum(np.abs(u_raw) - dz, 0.0)
        u = np.clip(u_raw, umin, umax)
        sat += np.abs(u - u_raw) > 1e-12
        sat_max = np.maximum(sat_max, np.abs(u_raw - u))

        u_plant = u_del
        if disturb_amp and k * ts >= disturb_time:
            u_plant = u_plant + disturb_amp
        x = np.einsum("nij,nj->ni", a, x) + b * u_plant[:, None]

        hist = np.roll(hist, -1, axis=1)
        hist[:, -1] = u

        # ---- streaming metrics
        progressed = np.isnan(t10) & (y >= 0.1 * r)
        t10 = np.where(progressed & np.isnan(t10), t[k], t10)
        crossed90 = np.isnan(t90) & (y >= 0.9 * r)
        t90 = np.where(crossed90, t[k], t90)
        grew = y > peak
        peak = np.where(grew, y, peak)
        peak_t = np.where(grew, t[k], peak_t)
        iae += np.abs(e) * ts
        itae += t[k] * np.abs(e) * ts
        outside = np.abs(y - r) > band_vec[k]
        lag_sum += r - y
        t_settle = np.where(outside, t[k], t_settle)
        now_above = y > r
        n_cross += (now_above != above) & (k > 0)
        above = now_above
        prev_y = y

        if ci < n_curve and k == curve_idx[ci]:
            y_curve[:, ci] = y
            u_curve[:, ci] = u
            ci += 1

    y_final = y
    lag = lag_sum / nsteps
    ref_final = float(r_vec[-1, 0])
    metrics = np.column_stack(
        [
            (peak - ref_final)
            / max(abs(ref_final), 1e-9)
            * (peak > ref_final),  # overshoot (signed, 0 if none)
            (t90 - t10),  # rise time
            t_settle,  # settling time
            (ref_final - y_final) / max(abs(ref_final), 1e-9),  # steady-state error
            iae,
            itae,
            n_cross / 2.0,  # oscillations
            sat / nsteps,  # saturation fraction
            sat_max / amp,  # worst overdrive
            lag,  # mean signed tracking error
        ]
    )
    # NaN rise time -> treat as never rose (slow/failed)
    metrics[:, 1] = np.where(np.isnan(metrics[:, 1]), horizon, metrics[:, 1])
    return {"metrics": metrics, "y_curve": y_curve, "u_curve": u_curve, "t": t}


METRIC_NAMES = (
    "overshoot",
    "rise_time",
    "settling_time",
    "ss_error",
    "iae",
    "itae",
    "oscillations",
    "sat_frac",
    "sat_over",
    "lag",
)


def gains_to_params(gains: np.ndarray) -> np.ndarray:
    """Clip to the admissible box and return as float array."""
    g = np.asarray(gains, dtype=float)
    return np.clip(g, 1e-6, 1e3)


def make_plant(
    num,
    den,
    *,
    delay_s: float = 0.0,
    u_max: float = 2.5,
    u_min: float = -2.5,
    noise_sigma: float = 0.0,
    dead_zone: float = 0.0,
    name: str = "custom",
    ts: float = 5e-3,
) -> "PlantSet":
    """Build a one-plant PlantSet from raw transfer-function coefficients."""
    num = np.atleast_1d(np.asarray(num, dtype=float))
    den = np.atleast_1d(np.asarray(den, dtype=float))
    a_c, b_c, c_c, d_c = signal.tf2ss(num, den)
    ad, bd, cd, dd, _ = signal.cont2discrete((a_c, b_c, c_c, d_c), ts, method="zoh")
    nd = max(len(num), len(den))
    num_p = np.zeros((1, nd))
    den_p = np.zeros((1, nd))
    num_p[0, nd - len(num) :] = num
    den_p[0, nd - len(den) :] = den
    return PlantSet(
        n=1,
        family=[name],
        num=num_p,
        den=den_p,
        delay_s=np.array([delay_s]),
        a=np.atleast_2d(ad)[None],
        b=np.asarray(bd).reshape(1, -1),
        c=np.asarray(cd).reshape(1, -1),
        d=np.array([float(np.asarray(dd).reshape(-1)[0])]),
        u_max=np.array([u_max]),
        u_min=np.array([u_min]),
        noise_sigma=np.array([noise_sigma]),
        dead_zone=np.array([dead_zone]),
        params=[{}],
    )
