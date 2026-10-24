"""Timing evidence is observed once; checks validate formulas without objectives."""
import copy
import importlib.util
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("peripheral_recalibration_tests", ROOT / "scripts/48_recalibration_benchmark.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def payload():
    rng = np.random.default_rng(123)
    n, m, a, k = 4, 9, 2, 3
    fitting = {"temperature_logits": rng.normal(size=(n, a, k)),
               "temperature_labels": rng.integers(0, k, size=(n, a)),
               "conformal_logits": rng.normal(size=(m, a, k)),
               "conformal_labels": rng.integers(0, k, size=(m, a)),
               "temperature_ids": [f"unit-temp:{i}" for i in range(n)],
               "conformal_ids": [f"unit-cp:{i}" for i in range(m)], "model_sha256": "a" * 64}
    return fitting, rng.normal(size=(7, a, k)), rng.integers(0, k, size=(7, a))


def test_timing_statistics_use_original_samples_including_p99():
    samples = [{"temperature": float(i), "conformal": float(2*i), "total": float(3*i)} for i in (1, 2, 3)]
    values = benchmark.timing_statistics(samples, expected_repetitions=3)
    assert values["temperature_fit_ms"] == {"median": 2., "p99": 2.98, "min": 1., "max": 3.}
    assert values["conformal_fit_ms"]["p99"] == 5.96
    assert values["total_fit_ms"]["median"] == 6.


@pytest.mark.parametrize("samples", [[], [{"temperature": 1., "conformal": 1., "total": -1.}],
                                    [{"temperature": 1., "conformal": 1., "total": np.inf}],
                                    [{"temperature": 1., "conformal": 1., "total": 3.}],
                                    [{"temperature": 1., "total": 1.}]])
def test_bad_or_incomplete_timing_evidence_rejected(samples):
    with pytest.raises(ValueError):
        benchmark.timing_statistics(samples, expected_repetitions=1)


def test_real_frozen_fits_record_every_repetition_and_check_without_retiming(monkeypatch):
    fitting, test_logits, test_labels = payload()
    calls, original = [], benchmark.fit_frozen_calibration

    def observed(**arguments):
        calls.append((arguments["temperature_ids"], arguments["conformal_ids"]))
        return original(**arguments)

    monkeypatch.setattr(benchmark, "fit_frozen_calibration", observed)
    row = benchmark.benchmark_fit(fitting, test_logits, test_labels, warmups=1, repetitions=3)
    assert len(calls) == 4 and len(row["timing_samples_ms"]) == 3
    preserved = copy.deepcopy(row["timing_samples_ms"])

    def later_fit(**arguments):
        result = original(**arguments)
        # A check must not compare/substitute current host timing observations.
        result["fit_ms"] = {"temperature": 10000., "conformal": 20000., "total": 30000.}
        return result

    monkeypatch.setattr(benchmark, "fit_frozen_calibration", later_fit)
    benchmark.verify_row(row, fitting, test_logits, test_labels, warmups=1, repetitions=3)
    assert row["timing_samples_ms"] == preserved


def test_test_labels_are_diagnostic_and_cannot_change_fit_or_sample_count():
    fitting, test_logits, test_labels = payload()
    first = benchmark.benchmark_fit(fitting, test_logits, test_labels, warmups=0, repetitions=1)
    changed = (test_labels + 1) % 3
    second = benchmark.benchmark_fit(fitting, test_logits, changed, warmups=0, repetitions=1)
    assert first["calibration"] == second["calibration"]
    assert first["test_diagnostics"]["coverage_per_axis"] != second["test_diagnostics"]["coverage_per_axis"]
    assert first["calibration"]["n_temperature"] == 4
    assert first["calibration"]["n_calibration"] == 9


@pytest.mark.parametrize("mutation", ["temperature", "qhat", "coverage", "statistics", "repetitions"])
def test_row_verification_rejects_mutated_fits_diagnostics_and_statistics(mutation):
    fitting, test_logits, test_labels = payload()
    row = benchmark.benchmark_fit(fitting, test_logits, test_labels, warmups=0, repetitions=1)
    if mutation == "temperature":
        row["calibration"]["temperatures"][0] *= 1.1
    elif mutation == "qhat":
        row["calibration"]["qhat_per_axis"][0] = .123
    elif mutation == "coverage":
        row["test_diagnostics"]["coverage_per_axis"][0] += .1
    elif mutation == "statistics":
        row["timing_statistics_ms"]["total_fit_ms"]["p99"] += 1.
    else:
        row["recorded_repetitions"] = 2
    with pytest.raises(ValueError):
        benchmark.verify_row(row, fitting, test_logits, test_labels, warmups=0, repetitions=1)


def test_input_hashes_fail_closed_on_content_change_but_accept_checkout_newlines(tmp_path):
    source = tmp_path / "source.json"
    source.write_bytes(b'{"model":"frozen"}\n')
    hashes = {"source.json": benchmark.digest(source)}
    source.write_bytes(b'{"model":"frozen"}\r\n')
    benchmark.verify_hashes(tmp_path, hashes)
    source.write_bytes(b'{"model":"changed"}\n')
    with pytest.raises(ValueError, match="changed"):
        benchmark.verify_hashes(tmp_path, hashes)


def test_benchmark_rejects_existing_output_before_any_input_loading(tmp_path, monkeypatch):
    existing = tmp_path / "result.json"
    existing.write_text("original clock evidence", encoding="utf-8")
    monkeypatch.setattr(benchmark, "_context", lambda *args: pytest.fail("existing output must reject before inputs"))
    with pytest.raises(ValueError, match="overwrite"):
        benchmark.run(root=tmp_path, output=existing)
    assert existing.read_text(encoding="utf-8") == "original clock evidence"


def test_generated_document_is_bilingual_and_limits_peripheral_fit_claims():
    fitting, test_logits, test_labels = payload()
    row = benchmark.benchmark_fit(fitting, test_logits, test_labels, warmups=0, repetitions=1)
    document = benchmark.render({"rows": [{"model_seed": 123, "n_per_split": 4,
                                          "total_label_states": 8, **row}],
                                 "overall_wall_seconds": .125, "additional_objective_evaluations": 0,
                                 "gradient_steps": 0})
    assert document.index("## English") < document.index("## 简体中文")
    assert "totaling 2n" in document and "总计2n" in document
    assert "exclude label acquisition" in document and "不包含标签采集" in document
    assert "cross-day validity" in document and "跨天有效性" in document
    assert "millisecond end-to-end adaptation" in document
    assert "0.125000" in document


def test_protocol_and_source_constants_match_frozen_recalibration_plan():
    value = benchmark.protocol()
    assert value["accounting"]["additional_objective_evaluations"] == 0
    assert benchmark.SIZES == (16, 32, 64)
    assert benchmark.REPETITIONS == 31 and benchmark.WARMUPS == 1
    assert "src/jev_tune/calibration.py" in benchmark.SOURCES
