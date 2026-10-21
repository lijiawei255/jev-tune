"""Plant zoo and closed-loop simulation invariants."""

import numpy as np
import pytest
from scipy import signal

from jev_tune.plants import PlantSet, sample_plants, simulate


def _single(num, den, delay=0.0, ulim=2.5):
    a, b, c, d = signal.tf2ss(np.asarray(num, float), np.asarray(den, float))
    ad, bd, cd, dd, _ = signal.cont2discrete((a, b, c, d), 5e-3, method="zoh")
    return PlantSet(
        n=1,
        family=["test"],
        num=np.asarray(num, float)[None],
        den=np.asarray(den, float)[None],
        delay_s=np.array([delay]),
        a=ad[None],
        b=np.asarray(bd).reshape(1, -1),
        c=np.asarray(cd).reshape(1, -1),
        d=np.array([float(np.asarray(dd).reshape(-1)[0])]),
        u_max=np.array([ulim]),
        u_min=np.array([-ulim]),
        params=[{}],
    )


def test_closed_loop_matches_analytic():
    """P control on 1/(s^2+0.6s+1) must match scipy's closed-loop step."""
    ps = _single([1.0], [1.0, 0.6, 1.0])
    kp = 1.0
    res = simulate(ps, np.array([[kp, 0.0, 0.0]]), horizon=20.0, n_curve=200)
    y = res["y_curve"][0]
    t = np.linspace(0, 20, 200)
    cl = signal.TransferFunction([kp], np.polyadd([1.0, 0.6, 1.0], [kp]))
    _, y_an = signal.step(cl, T=t)
    assert np.max(np.abs(y - y_an)) < 0.03
    assert abs(y[-1] - y_an[-1]) < 0.01


def test_transport_delay_shifts_response():
    fast = _single([1.0], [0.2, 1.0], delay=0.0)
    slow = _single([1.0], [0.2, 1.0], delay=0.10)
    g = np.array([[2.0, 0.0, 0.0]])
    y0 = simulate(fast, g, horizon=2.0, n_curve=400)["y_curve"][0]
    y1 = simulate(slow, g, horizon=2.0, n_curve=400)["y_curve"][0]
    assert np.all(np.abs(y1[: 400 // 20 - 2]) < 1e-9), (
        "output must stay at 0 during the delay"
    )
    assert y1[-1] == pytest.approx(y0[-1], rel=0.05)


def test_unit_dc_gain_normalisation():
    p = sample_plants(200, seed=0)
    for i in range(p.n):
        num, den = p.num[i], p.den[i]
        if abs(den[-1]) < 1e-12:
            continue  # integrating families have no DC gain
        assert num[-1] / den[-1] == pytest.approx(1.0, abs=1e-9)


def test_simulation_is_finite_and_masked():
    p = sample_plants(50, seed=1)
    res = simulate(p, np.tile([1.0, 1.0, 0.0], (p.n, 1)))
    assert np.isfinite(res["metrics"]).all()
    assert res["y_curve"].shape == (p.n, 64)
    assert np.isfinite(res["y_curve"]).all()
