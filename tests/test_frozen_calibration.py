"""Frozen-logit calibration preserves its data boundary and finite-sample rank."""
import copy

import numpy as np
import pytest

import jev_tune.calibration as calibration
from jev_tune.primitives import conformal_prediction_set, fit_split_conformal, softmax


def inputs(axes=2, options=3, n_temperature=12, n_conformal=19):
    rng = np.random.default_rng(123)
    return {
        "temperature_logits": rng.normal(size=(n_temperature, axes, options)),
        "temperature_labels": rng.integers(0, options, size=(n_temperature, axes)),
        "conformal_logits": rng.normal(size=(n_conformal, axes, options)),
        "conformal_labels": rng.integers(0, options, size=(n_conformal, axes)),
        "temperature_ids": [f"temperature:{i}" for i in range(n_temperature)],
        "conformal_ids": [f"conformal:{i}" for i in range(n_conformal)],
        "model_sha256": "a" * 64,
    }


@pytest.mark.parametrize("axes,options", [(1, 1), (2, 3), (4, 7)])
def test_frozen_calibration_supports_arbitrary_axes_and_options_without_mutating_inputs(axes, options):
    payload = inputs(axes, options)
    arrays = {name: value.copy() for name, value in payload.items() if isinstance(value, np.ndarray)}
    for value in arrays.values():
        value.setflags(write=False)
    payload.update(arrays)
    before = {name: value.copy() for name, value in arrays.items()}
    result = calibration.fit_frozen_calibration(**payload)
    assert len(result["temperatures"]) == len(result["qhat_per_axis"]) == axes
    assert result["n_temperature"] == 12 and result["n_calibration"] == 19
    assert result["quantile_rank"] == 18 and result["alpha"] == .1
    assert result["mode"] == "monitor" and result["model_sha256"] == "a" * 64
    p = softmax(payload["conformal_logits"], temperature=np.array(result["temperatures"])[None, :, None])
    independent = fit_split_conformal(p, payload["conformal_labels"], alpha=.1)
    np.testing.assert_array_equal(result["qhat_per_axis"], independent.qhat_per_axis)
    for name, value in before.items():
        np.testing.assert_array_equal(payload[name], value)
    timing = result["fit_ms"]
    assert np.isfinite(list(timing.values())).all() and min(timing.values()) >= 0.
    assert timing["total"] == pytest.approx(timing["temperature"] + timing["conformal"], abs=1e-12)
    assert "do not establish independence or exchangeability" in result["scope"]
    assert "excludes label acquisition" in result["scope"]


def test_temperature_is_fitted_only_on_its_own_split_and_cp_uses_scaled_probabilities(monkeypatch):
    payload = inputs()
    calls = []

    def known_temperature(logits, labels):
        axis = len(calls)
        np.testing.assert_array_equal(logits, payload["temperature_logits"][:, axis, :])
        np.testing.assert_array_equal(labels, payload["temperature_labels"][:, axis])
        calls.append(axis)
        return [2., 4.][axis]

    monkeypatch.setattr(calibration, "calibrate_temperature", known_temperature)
    result = calibration.fit_frozen_calibration(**payload)
    assert calls == [0, 1] and result["temperatures"] == [2., 4.]
    expected_p = softmax(payload["conformal_logits"], temperature=np.array([2., 4.])[None, :, None])
    scores = 1. - np.take_along_axis(expected_p, payload["conformal_labels"][..., None], axis=-1)[..., 0]
    np.testing.assert_array_equal(result["qhat_per_axis"], np.sort(scores, axis=0)[17])


def test_conformal_label_changes_cannot_refit_temperature():
    payload = inputs()
    first = calibration.fit_frozen_calibration(**payload)
    payload["conformal_labels"] = (payload["conformal_labels"] + 1) % 3
    second = calibration.fit_frozen_calibration(**payload)
    assert first["temperatures"] == second["temperatures"]
    assert first["qhat_per_axis"] != second["qhat_per_axis"]


def test_small_calibration_sample_uses_endpoint_and_complete_prediction_sets():
    payload = inputs(n_conformal=1)
    result = calibration.fit_frozen_calibration(**payload)
    assert result["quantile_rank"] == 2 and result["qhat_per_axis"] == [1., 1.]
    assert conformal_prediction_set(np.array([[[1., 0., 0.], [0., 1., 0.]]]),
                                    result["qhat_per_axis"]).all()


@pytest.mark.parametrize("field,value", [
    ("temperature_logits", np.zeros((2, 3))),
    ("temperature_logits", np.zeros((0, 2, 3))),
    ("temperature_logits", np.full((12, 2, 3), np.nan)),
    ("conformal_logits", np.full((19, 2, 3), np.inf)),
    ("conformal_logits", np.zeros((19, 1, 3))),
    ("conformal_logits", np.zeros((19, 2, 4))),
    ("temperature_labels", np.zeros((12, 2), dtype=float)),
    ("conformal_labels", np.zeros((19, 2), dtype=bool)),
    ("conformal_labels", np.zeros((19, 1), dtype=int)),
    ("temperature_labels", np.full((12, 2), -1, dtype=int)),
    ("conformal_labels", np.full((19, 2), 3, dtype=int)),
])
def test_invalid_logits_schema_and_labels_rejected_before_fitting(monkeypatch, field, value):
    payload = inputs()
    payload[field] = value

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid records must be rejected before temperature fitting")

    monkeypatch.setattr(calibration, "calibrate_temperature", forbidden)
    with pytest.raises(ValueError):
        calibration.fit_frozen_calibration(**payload)


@pytest.mark.parametrize("field,value", [
    ("temperature_ids", ["same"] * 12),
    ("conformal_ids", ["same"] * 19),
    ("temperature_ids", ["temperature:0"]),
    ("conformal_ids", None),
    ("temperature_ids", "twelve chars"),
    ("temperature_ids", [True] + list(range(11))),
    ("temperature_ids", [None] + list(range(11))),
    ("temperature_ids", [""] + list(range(11))),
    ("temperature_ids", [0.] + list(range(1, 12))),
])
def test_invalid_or_nonunique_sampling_identities_rejected(field, value):
    payload = inputs()
    payload[field] = value
    with pytest.raises(ValueError, match="IDs"):
        calibration.fit_frozen_calibration(**payload)


def test_overlapping_ids_rejected_and_disjoint_numpy_integer_ids_accepted():
    payload = inputs()
    payload["conformal_ids"][2] = payload["temperature_ids"][0]
    with pytest.raises(ValueError, match="disjoint"):
        calibration.fit_frozen_calibration(**payload)
    payload["temperature_ids"] = np.arange(12)
    payload["conformal_ids"] = np.arange(12, 31)
    assert calibration.fit_frozen_calibration(**payload)["n_calibration"] == 19


@pytest.mark.parametrize("model_hash", [None, "x" * 64, "a" * 63, "a" * 65, "sha256:" + "a" * 64])
def test_model_identity_requires_exact_sha256_hex(model_hash):
    payload = inputs()
    payload["model_sha256"] = model_hash
    with pytest.raises(ValueError, match="model_sha256"):
        calibration.fit_frozen_calibration(**payload)


@pytest.mark.parametrize("alpha", [0, 1, -.1, np.nan, np.inf, [.1]])
def test_invalid_alpha_rejected(alpha):
    payload = inputs()
    with pytest.raises(ValueError, match="alpha"):
        calibration.fit_frozen_calibration(**payload, alpha=alpha)


def test_repeated_frozen_arrays_have_exact_same_fits_without_external_checkpoint_access():
    payload = inputs()
    # The opaque hash has no associated file. Fitting uses only frozen arrays.
    payload["model_sha256"] = "ABCDEF0123456789" * 4
    first = calibration.fit_frozen_calibration(**payload)
    repeated = calibration.fit_frozen_calibration(**copy.deepcopy(payload))
    assert first["model_sha256"] == payload["model_sha256"].lower()
    for key in set(first) - {"fit_ms"}:
        assert first[key] == repeated[key]
