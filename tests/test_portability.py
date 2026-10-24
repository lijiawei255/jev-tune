"""Reference ports must validate committed artifacts, including failure paths."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_committed_vectors_match_current_model_and_policy():
    from jev_tune.domains.pid.decision import load_backend
    from jev_tune.core.policy import decide

    artifact = json.loads((ROOT / "c/test_vectors.json").read_text())
    assert artifact["schema_version"] == 5
    assert artifact["model_sha256"] == hashlib.sha256((ROOT / "models/jev_head.pt").read_bytes()).hexdigest()
    backend = load_backend(ROOT / "models")
    config = artifact["configuration"]
    assert config["policy"] == {"tau_act": 0., "tau_esc": 0., "tau_noul": 0.}
    assert config["conformal"]["enabled"]
    assert config["conformal"]["mode"] == backend.conformal.mode == "monitor"
    assert config["conformal"]["qhat_per_axis"] == list(backend.conformal.q_hat)
    assert config["conformal"]["k_max"] == backend.conformal.k_max
    np.testing.assert_array_equal(config["temperature"], backend.temperature)
    cases = artifact["cases"]
    ans = backend.answer(np.array([c["feats"] for c in cases], dtype=np.float32),
                         np.array([c["curves"] for c in cases], dtype=np.float32))
    decision = decide(ans, conformal=backend.conformal)
    np.testing.assert_allclose(decision.step, [c["step"] for c in cases], atol=artifact["tolerance"]["step"], rtol=0)
    np.testing.assert_array_equal(decision.held, [c["held"] for c in cases])
    np.testing.assert_array_equal(decision.escalate, [c["escalate"] for c in cases])
    np.testing.assert_array_equal(decision.set_size, [c["set_size"] for c in cases])
    np.testing.assert_array_equal(decision.conformal_would_hold, [c["conformal_would_hold"] for c in cases])
    np.testing.assert_array_equal(decision.conformal_reason, [c["conformal_reason"] for c in cases])
    np.testing.assert_array_equal(np.stack(decision.conformal_set, axis=-2), [c["conformal_set"] for c in cases])
    np.testing.assert_allclose(decision.proposed, [c["proposed"] for c in cases], atol=artifact["tolerance"]["step"], rtol=0)
    for actual, expected in [(ans.score.dist, [c["score_probs"] for c in cases]),
                             (ans.noul.p_true, [c["noul"] for c in cases])]:
        np.testing.assert_allclose(actual, expected, atol=artifact["tolerance"]["probs"], rtol=0)
    for axis, ch in enumerate(ans.choice):
        np.testing.assert_allclose(ch.probs, [c["probs"][axis] for c in cases], atol=artifact["tolerance"]["probs"], rtol=0)


def test_portable_modes_share_sets_but_only_hard_hold_changes_actions():
    artifact = json.loads((ROOT / "c/test_vectors.json").read_text())
    cases = {c["name"]: c for c in artifact["policy_cases"]}
    for name, hard in cases.items():
        if hard["conformal_mode"] != "hard_hold":
            continue
        monitor = cases[name + "_monitor"]
        for key in ("conformal_set", "set_size", "conformal_would_hold", "conformal_reason", "proposed"):
            assert monitor[key] == hard[key], (name, key)
        if hard["policy"] == {"tau_act": 0., "tau_esc": 0., "tau_noul": 0.}:
            assert not any(monitor["held"]) and not any(monitor["escalate"])
            assert monitor["reason"] == [0, 0, 0]
            assert monitor["step"] == monitor["proposed"]
            assert hard["held"] == hard["conformal_would_hold"]


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc unavailable")
def test_c_reference_and_nan_mutation(tmp_path):
    compiler = shutil.which("gcc")
    for name in ("test_forward", "test_features", "test_policy", "nan_mutant", "inf_mutant"):
        mutant = name.endswith("_mutant")
        source = "test_forward" if mutant else name
        command = [compiler, "-std=c99", "-O2", "-I", str(ROOT / "c")]
        if name == "nan_mutant":
            command.append("-DJEV_TEST_NAN_MUTATION")
        if name == "inf_mutant":
            command.append("-DJEV_TEST_INF_MUTATION")
        exe = tmp_path / (name + ".exe")
        build = subprocess.run(command + [str(ROOT / "c" / f"{source}.c"), str(ROOT / "c/jev_head.c"), "-lm", "-o", str(exe)], capture_output=True, text=True)
        assert build.returncode == 0, build.stdout + build.stderr
        result = subprocess.run([str(exe)], capture_output=True, text=True)
        assert (result.returncode != 0) == mutant, result.stdout + result.stderr


def test_matlab_production_decoder(tmp_path):
    from jev_tune.domains.pid.matlab_runner import find_matlab
    matlab = find_matlab()
    if not matlab.ok:
        pytest.skip("MATLAB unavailable")
    result = subprocess.run([str(matlab.executable), "-batch",
                             f"addpath('{(ROOT / 'matlab').as_posix()}'); test_portability; test_tune_history('{tmp_path.as_posix()}')"],
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
