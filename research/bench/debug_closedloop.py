"""Check one analytically-known closed loop against scipy."""

import numpy as np
from scipy import signal

from jev_tune.plants import PlantSet, simulate

# plant: G = 1 / (s^2 + 0.6 s + 1)   (wn=1, zeta=0.3), no delay
num = np.array([1.0])
den = np.array([1.0, 0.6, 1.0])
a, b, c, d = signal.tf2ss(num, den)
ad, bd, cd, dd, _ = signal.cont2discrete((a, b, c, d), 5e-3, method="zoh")

ps = PlantSet(
    n=1,
    family=["sopdt"],
    num=num[None],
    den=den[None],
    delay_s=np.zeros(1),
    a=ad[None],
    b=np.asarray(bd).reshape(1, -1),
    c=np.asarray(cd).reshape(1, -1),
    d=np.array([float(np.asarray(dd).reshape(-1)[0])]),
    u_max=np.array([100.0]),
    u_min=np.array([-100.0]),
    params=[{}],
)

for kp in (1.0, 4.0):
    res = simulate(ps, np.array([[kp, 0.0, 0.0]]), horizon=20.0, n_curve=200)
    y = res["y_curve"][0]
    t = np.linspace(0, 20, 200)
    # analytic closed loop
    cl_num = np.polymul(np.array([kp]), num)
    cl_den = np.polyadd(den, cl_num)
    _, y_an = signal.step(signal.TransferFunction(cl_num, cl_den), T=t)
    print(
        f"Kp={kp}: simulated y_end={y[-1]:.4f}  analytic y_end={y_an[-1]:.4f}  "
        f"max|diff|={np.max(np.abs(y - y_an)):.4f}"
    )
    print("   sim   ", np.round(y[::20], 3))
    print("   analytic", np.round(y_an[::20], 3))
