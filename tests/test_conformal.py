"""Finite-sample SplitCP boundaries and independent calibration evidence."""
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

from jev_tune.core.primitives import (
    SplitConformal, conformal_prediction_set, conformal_quantile, fit_split_conformal,
)


def training_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "02_train.py"
    spec = importlib.util.spec_from_file_location("train_with_conformal", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("n", [1, 2, 8])
def test_rank_n_plus_one_uses_endpoint_not_observed_max(n):
    scores = np.full((n, 3), .2)
    np.testing.assert_array_equal(conformal_quantile(scores, .1), np.ones(3))
    # Even zero-probability labels must be included at the bounded endpoint.
    assert conformal_prediction_set([[1., 0., 0.]], 1.).all()


def test_finite_sample_order_statistic_without_interpolation():
    scores = np.column_stack([np.linspace(0, .9, 19), np.linspace(.05, 1., 19)])
    np.testing.assert_array_equal(conformal_quantile(scores, .1), scores[17])
    assert conformal_quantile(np.arange(9) / 10, .1) == .8


def test_boundary_ties_are_included_and_axes_broadcast():
    p = np.tile([.3, .7], (9, 3, 1))
    fit = fit_split_conformal(p, np.zeros((9, 3), dtype=int))
    assert fit.quantile_rank == 9
    # Reconstructing 1-q = 0.30000000000000004 must not lose p=0.3.
    assert fit.prediction_set(p).all()
    masks = conformal_prediction_set(np.array([[[.8, .2], [.4, .6]]]), [.2, .6])
    np.testing.assert_array_equal(masks, [[[True, False], [True, True]]])


def test_empirical_evaluation_counts_labels_and_set_sizes_without_refit():
    fitted = SplitConformal(.1, 19, np.array([.2, .6]))
    p = np.array([[[.9, .1], [.4, .6]], [[.5, .5], [.2, .8]]])
    q_before = fitted.qhat_per_axis.copy()
    report = fitted.evaluate(p, np.array([[0, 0], [1, 0]]))
    assert report["n_states"] == 2
    assert report["coverage_per_axis"] == [.5, .5]
    assert report["mean_set_size_per_axis"] == [.5, 1.5]
    assert report["set_size_histogram_per_axis"] == [[1, 1, 0], [0, 1, 1]]
    np.testing.assert_array_equal(fitted.qhat_per_axis, q_before)


def test_iid_empirical_teacher_label_coverage_on_an_independent_sample():
    rng = np.random.default_rng(9183)
    p_fit = rng.dirichlet(np.ones(7), size=(2000, 3))
    p_test = rng.dirichlet(np.ones(7), size=(6000, 3))
    # Sampling labels from the categorical model gives a known IID experiment.
    def labels(p):
        return (rng.random(p.shape[:-1])[..., None] > p.cumsum(axis=-1)).sum(-1)
    fit = fit_split_conformal(p_fit, labels(p_fit))
    report = fit.evaluate(p_test, labels(p_test))
    coverage = np.array(report["coverage_per_axis"])
    assert np.all((coverage > .87) & (coverage < .94))


@pytest.mark.parametrize("alpha", [0, 1, -.1, np.nan, np.inf])
def test_invalid_alpha_rejected(alpha):
    with pytest.raises(ValueError, match="alpha"):
        conformal_quantile([.1], alpha)


@pytest.mark.parametrize("probs,labels", [
    ([[.3, .3]], [0]), ([[np.nan, .2]], [0]), ([[1., 0.]], [2]),
    ([[1., 0.]], [.5]), ([[1., 0.]], [[0]]),
])
def test_invalid_fit_distributions_or_labels_rejected(probs, labels):
    with pytest.raises(ValueError):
        fit_split_conformal(probs, labels)


def test_empirical_labels_cannot_change_temperature_or_qhat():
    module = training_script()
    rng = np.random.default_rng(412)
    splits = {}
    for name in module.SPLITS:
        splits[name] = {
            "choice_logits": rng.normal(size=(30, 3, 7)),
            "choice": rng.integers(0, 7, size=(30, 3)),
            "score_logits": rng.normal(size=(30, 5)), "score": np.zeros(30, dtype=int),
            "noul_logits": np.ones(30), "noul": np.ones(30),
        }
    before = module.fit_calibration(splits)
    splits["empirical_eval"]["choice"] = (splits["empirical_eval"]["choice"] + 1) % 7
    after = module.fit_calibration(splits)
    assert before["choice_temperature"] == after["choice_temperature"]
    assert before["split_conformal"]["qhat_per_axis"] == after["split_conformal"]["qhat_per_axis"]
    assert not after["split_conformal"]["evaluation"]["threshold_reselected_on_eval"]


def test_calibrate_only_preserves_weights_and_saves_three_independent_splits(tmp_path, monkeypatch):
    import torch
    from jev_tune.domains.pid.model import JevHead

    module = training_script()
    torch.manual_seed(41)
    checkpoint = tmp_path / "jev_head.pt"
    meta = tmp_path / "meta.json"
    torch.save(JevHead(n_actions=7).state_dict(), checkpoint)
    meta.write_text(json.dumps({"n_feats": 20, "n_curve": 64, "n_actions": 7}))
    before = (checkpoint.read_bytes(), meta.read_bytes())
    monkeypatch.setattr(sys, "argv", [str(module.__file__), "--calibrate-only",
        "--out-dir", str(tmp_path), "--data", str(tmp_path / "does-not-exist.npz"),
        "--calibration-plants", "4", "--calibration-data-dir", str(tmp_path / "split_data")])
    module.main()
    assert before == (checkpoint.read_bytes(), meta.read_bytes())
    result = json.loads((tmp_path / "calibration.json").read_text())
    assert result["split_conformal"]["n_calibration"] == 4
    assert result["split_conformal"]["quantile_rank"] == 5
    assert result["split_conformal"]["qhat_per_axis"] == [1., 1., 1.]
    assert len({x["seed"] for x in result["splits"].values()}) == 3
    assert len({x["data_sha256"] for x in result["splits"].values()}) == 3
    assert all(x["n_states"] == x["n_plants"] == 4 for x in result["splits"].values())
    splits = {}
    for name in module.SPLITS:
        with np.load(tmp_path / "split_data" / f"{name}.npz") as raw:
            splits[name] = {key: raw[key] for key in raw.files}
    reproduced = module.fit_calibration(splits)
    assert reproduced["split_conformal"] == result["split_conformal"]
    assert reproduced["choice_temperature"] == result["choice_temperature"]
