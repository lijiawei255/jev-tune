"""Out-of-zoo control scenarios used to measure how badly the head overfits.

None of these plants appear in the training zoo (which only contains FOPDT,
SOPDT, third-order + RHP zero, integrating, PMSM speed loop, type-1 position
loop, and a two-mass resonance).  They are the kind of thing a control engineer
meets in other projects: dead-time dominated loops, unstable plants, double
integrators, sensor noise, valve dead bands, closely spaced resonances.

Everything is on the same 10 s horizon and 5 ms sample time as the benchmark so
that the metrics remain comparable; only the *dynamics* change.
"""

from __future__ import annotations

import numpy as np

from .plants import PlantSet, make_plant


def _p(num, den, **kw) -> PlantSet:
    return make_plant(num, den, **kw)


SCENARIOS = {
    # 1. dead time dominates the dynamics (L/T = 2)
    "dead_time": lambda: _p(
        [1.0], [0.4, 1.0], delay_s=0.8, u_max=1.6, name="dead_time"
    ),
    # 2. double integrator: position of a frictionless mass
    "double_integrator": lambda: _p(
        [1.0], [1.0, 0.0, 0.0], delay_s=0.02, u_max=1.6, name="double_integrator"
    ),
    # 3. open-loop unstable first-order pole
    "unstable_pole": lambda: _p(
        [1.0], [1.0, -1.0], delay_s=0.02, u_max=2.5, name="unstable_pole"
    ),
    # 4. inverted pendulum angle dynamics
    "inverted_pendulum": lambda: _p(
        [1.0], [1.0, 0.0, -2.0], delay_s=0.01, u_max=25.0, name="inverted_pendulum"
    ),
    # 5. same family as the held-out benchmark but with much sharper resonance
    "sharp_resonance": lambda: _p(
        np.array([1.0 * 200.0**2]),
        np.convolve([1.0, 2 * 0.4 * 6.0, 36.0], [1.0, 2 * 0.02 * 200.0, 200.0**2]),
        delay_s=0.012,
        u_max=2.5,
        name="sharp_resonance",
    ),
    # 6. fine sensor noise on an otherwise ordinary servo
    "noisy_sensor": lambda: _p(
        [1.0],
        [0.2, 1.0],
        delay_s=0.03,
        noise_sigma=0.01,
        u_max=1.6,
        name="noisy_sensor",
    ),
    # 7. sticky valve: 5 % dead band on the actuator
    "valve_dead_zone": lambda: _p(
        [0.8],
        [0.5, 1.0],
        delay_s=0.05,
        dead_zone=0.05,
        u_max=1.6,
        name="valve_dead_zone",
    ),
    # 8. flexible arm: two closely spaced structural modes
    "flexible_arm": lambda: _p(
        np.array([1.0 * 120.0**2]),
        np.convolve(
            np.convolve(
                [1.0, 2 * 0.02 * 120.0, 120.0**2], [1.0, 2 * 0.03 * 160.0, 160.0**2]
            ),
            [1.0, 0.05],
        ),
        delay_s=0.008,
        u_max=2.5,
        name="flexible_arm",
    ),
    # 9. process with a slow right-half-plane zero (inverse response)
    "inverse_response": lambda: _p(
        np.array([-0.8, 0.8]),
        np.convolve([0.6, 1.0], [0.1, 1.0]),
        delay_s=0.04,
        u_max=1.6,
        name="inverse_response",
    ),
    # 10. hydraulic actuator: third order with a fast pole and a delay
    "hydraulic": lambda: _p(
        [2.0],
        np.convolve(np.convolve([0.02, 1.0], [0.3, 1.0]), [1.0, 0.0]),
        delay_s=0.06,
        u_max=1.0,
        name="hydraulic",
    ),
}


SPECS = {
    # name: (num, den, kwargs) -- kept as data so variants can be generated
    "dead_time": ([1.0], [0.4, 1.0], dict(delay_s=0.8, u_max=1.6)),
    "double_integrator": ([1.0], [1.0, 0.0, 0.0], dict(delay_s=0.02, u_max=1.6)),
    "unstable_pole": ([1.0], [1.0, -1.0], dict(delay_s=0.02, u_max=2.5)),
    "inverted_pendulum": ([1.0], [1.0, 0.0, -2.0], dict(delay_s=0.01, u_max=25.0)),
    "sharp_resonance": (
        [200.0**2],
        list(
            np.convolve([1.0, 2 * 0.4 * 6.0, 36.0], [1.0, 2 * 0.02 * 200.0, 200.0**2])
        ),
        dict(delay_s=0.012, u_max=2.5),
    ),
    "noisy_sensor": (
        [1.0],
        [0.2, 1.0],
        dict(delay_s=0.03, noise_sigma=0.01, u_max=1.6),
    ),
    "valve_dead_zone": (
        [0.8],
        [0.5, 1.0],
        dict(delay_s=0.05, dead_zone=0.05, u_max=1.6),
    ),
    "flexible_arm": (
        [120.0**2],
        list(
            np.convolve(
                np.convolve(
                    [1.0, 2 * 0.02 * 120.0, 120.0**2], [1.0, 2 * 0.03 * 160.0, 160.0**2]
                ),
                [1.0, 0.05],
            )
        ),
        dict(delay_s=0.008, u_max=2.5),
    ),
    "inverse_response": (
        [-0.8, 0.8],
        list(np.convolve([0.6, 1.0], [0.1, 1.0])),
        dict(delay_s=0.04, u_max=1.6),
    ),
    "hydraulic": (
        [2.0],
        list(np.convolve(np.convolve([0.02, 1.0], [0.3, 1.0]), [1.0, 0.0])),
        dict(delay_s=0.06, u_max=1.0),
    ),
}


def get(name: str) -> PlantSet:
    return SCENARIOS[name]()


def names() -> list[str]:
    return list(SCENARIOS)


def variants(name: str, n: int = 4, seed: int = 0) -> PlantSet:
    """n jittered draws of one scenario (+-20 % gain, +-20 % delay).

    The per-scenario offset must be stable across processes, so it comes from
    crc32 of the name, not Python's `hash()` (which is salted per interpreter and
    silently made every out-of-zoo result non-reproducible).
    """
    import zlib

    num, den, kw = SPECS[name]
    rng = np.random.default_rng(zlib.crc32(name.encode("utf-8")) + seed)
    plants = []
    for _ in range(n):
        num_v = np.array(num, float) * 10 ** rng.uniform(-0.3, 0.3)
        den_v = np.array(den, float).copy()
        # perturb the slowest coefficient that keeps the plant proper
        idx = 0 if den_v[-1] == 0 else len(den_v) - 1
        den_v[idx] *= 10 ** rng.uniform(-0.3, 0.3)
        kw_v = dict(kw)
        kw_v["delay_s"] = float(kw.get("delay_s", 0.0)) * rng.uniform(0.8, 1.2)
        plants.append(make_plant(num_v, den_v, name=name, **kw_v))
    return _stack(plants)


def _stack(plants) -> PlantSet:
    # scenarios of different orders have different coefficient widths: pad to
    # a common length before concatenating (highest power first, so pad left)
    nd = max(p.num.shape[1] for p in plants)

    def _pad(a):
        if a.shape[1] == nd:
            return a
        return np.concatenate([np.zeros((a.shape[0], nd - a.shape[1])), a], axis=1)

    # state-space realisations also differ in order
    ns = max(p.a.shape[1] for p in plants)

    def _grow(a, n):
        out = np.zeros((a.shape[0], n, n))
        k = a.shape[1]
        out[:, :k, :k] = a
        return out

    def _padv(v, n):
        out = np.zeros((v.shape[0], n))
        out[:, : v.shape[1]] = v
        return out

    return PlantSet(
        n=sum(p.n for p in plants),
        family=[f for p in plants for f in p.family],
        num=np.concatenate([_pad(p.num) for p in plants]),
        den=np.concatenate([_pad(p.den) for p in plants]),
        delay_s=np.concatenate([p.delay_s for p in plants]),
        a=np.concatenate([_grow(p.a, ns) for p in plants]),
        b=np.concatenate([_padv(p.b, ns) for p in plants]),
        c=np.concatenate([_padv(p.c, ns) for p in plants]),
        d=np.concatenate([p.d for p in plants]),
        u_max=np.concatenate([p.u_max for p in plants]),
        u_min=np.concatenate([p.u_min for p in plants]),
        noise_sigma=np.concatenate([p.noise_sigma for p in plants]),
        dead_zone=np.concatenate([p.dead_zone for p in plants]),
        params=[pp for p in plants for pp in p.params],
        noise_seed=np.concatenate([p.noise_seed for p in plants]),
    )


__all__ = ["SCENARIOS", "get", "names"]
