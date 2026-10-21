"""Debug the ultimate-gain search per family."""

import numpy as np

from jev_tune.plants import TRAIN_FAMILIES, _freq_response, sample_plants, ultimate_gain

p = sample_plants(500, seed=1)
w = np.logspace(-2, np.log10(2e3), 4000)
h = _freq_response(p, w)
ph = np.unwrap(np.angle(h), axis=1)

for fam in TRAIN_FAMILIES:
    idx = [i for i, f in enumerate(p.family) if f == fam]
    sub = p.subset(idx)
    ku, tu = ultimate_gain(sub)
    ok = np.isfinite(ku)
    print(
        f"{fam:12s} n={len(idx):3d} finite={ok.mean():5.1%} "
        f"phase_end_median={np.median(ph[idx, -1]):7.2f} "
        f"phase_start_median={np.median(ph[idx, 0]):6.2f} "
        f"nan_h={np.isnan(h[idx]).mean():.2%}"
    )
    if ok.any():
        print(
            f"             Ku={np.nanmedian(ku[ok]):8.3f} Tu={np.nanmedian(tu[ok]):7.4f}"
        )
