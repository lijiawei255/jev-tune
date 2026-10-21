# Third-party notices and compliance

This repository is released under the MIT licence (see `LICENSE`). This file
records what is **in** the repository, what is **not**, and which third-party
licences apply to the things it depends on.

## What is in the repository

| Item | Origin | Licence |
| :--- | :--- | :--- |
| `src/jev_tune/**`, `matlab/**`, `scripts/**`, `tests/**` | written for this project | MIT |
| `models/jev_head.pt`, `.onnx`, `_weights.mat`, `meta.json`, `calibration.json` | trained in this project on synthetic plants | MIT |
| `assets/*.png`, `assets/*.gif` | plotted with matplotlib from simulations run in this project | MIT |
| `docs/**`, `README*`, `AGENTS.md` | written for this project | MIT (text) |
| `research/results/*.json` | benchmark output of this project | MIT |

No third-party source code, model weights, or datasets are vendored here.

## What is *not* in the repository (and why)

| Item | Why it is excluded |
| :--- | :--- |
| External motor-valve benchmark model and geometry | Used locally for measurements; no redistribution licence is asserted. Reproduction requires a model the user is authorized to use. |
| MATLAB / Simulink engine sources | Proprietary MathWorks code. The MATLAB bridge only *calls* documented APIs (`sim`, `set_param`, `pidtune`); nothing from MathWorks is copied. |
| Jev / Laya model weights | Not used at runtime. The project implements the *interface*, not the model. |
| Datasets (`data/*.npz`) | Generated locally, reproducible with `scripts/01_make_dataset.py`. |

## Runtime dependencies (not redistributed, only required)

| Package | Licence |
| :--- | :--- |
| NumPy, SciPy, scikit-learn | BSD-3-Clause |
| PyTorch | BSD-3-Clause |
| Matplotlib | PSF-based (Matplotlib licence) |
| ONNX, ONNX Runtime | Apache-2.0 / MIT |
| pytest | MIT |
| MATLAB, Simulink, Control System Toolbox | commercial, licensed by the user |

Installing these as dependencies does not relicense this project, and this
project does not relicense them.

## Names and trademarks

* **Jev** is a product of TypeSafe AI. **Laya** is a project by Convai
  Innovations. This repository is **not affiliated with, endorsed by, or
  sponsored by** either of them; the names are used descriptively to identify
  the interface style (`choice` / `score` / `noul`).
* **MATLAB** and **Simulink** are registered trademarks of The MathWorks, Inc.
  This project is not affiliated with MathWorks.

## Evidence boundaries

The motor-valve benchmark is a development-feedback/regression example.
Observations influenced later synthetic-zoo design, including actuator headroom;
it is not an untouched independent external test. The published training-data
generator uses synthetic plants. Final NPZ hashes establish file identity, not a
complete causal record of historical training.

The response figures in `README.md` and `docs/STEP4_RESULTS.md` are the project's
own plots of recorded measurements. These renderings do not assert authorship or
redistribution rights over an external model. Dependencies retain their own
licences; this notice records the distribution inventory.

## If you reuse this

MIT requires you to keep the copyright notice. It does not require you to
redistribute your trained specialists, your plant models, or your results.
