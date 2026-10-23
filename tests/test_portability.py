"""Reference ports must validate committed artifacts, including failure paths."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_matlab_report_binds_the_exported_inputs_and_implementation():
    report = json.loads((ROOT / "research/results/matlab_parity.json").read_text())
    assert report["ok"] and report["cases"] == 24 and report["policy_cases"] >= 17
    assert report["schema_version"] == 2 and report["configuration"]["conformal"]["enabled"]
    for field, name in {
        "model_sha256": "models/jev_head.pt",
        "calibration_sha256": "models/calibration.json",
        "vectors_sha256": "c/test_vectors.json",
        "weights_mat_sha256": "models/jev_head_weights.mat",
        "decoder_sha256": "matlab/jev_decode.m",
        "forward_sha256": "matlab/jev_head_forward.m",
    }.items():
        data = (ROOT / name).read_bytes()
        if name.endswith((".m", ".json")):
            data = data.replace(b"\r\n", b"\n")
        assert report[field] == hashlib.sha256(data).hexdigest(), name
    assert max(report["max_errors"].values()) < 2e-5


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_vectors_match_current_model_and_policy():
    from jev_tune.decision import load_backend
    from jev_tune.decode import decide

    artifact = json.loads((ROOT / "c/test_vectors.json").read_text())
    assert artifact["schema_version"] == 3
    assert artifact["model_sha256"] == hashlib.sha256((ROOT / "models/jev_head.pt").read_bytes()).hexdigest()
    backend = load_backend(ROOT / "models")
    config = artifact["configuration"]
    assert config["policy"] == {"tau_act": 0., "tau_esc": 0., "tau_noul": 0.}
    assert config["conformal"]["enabled"]
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
    np.testing.assert_array_equal(np.stack(decision.conformal_set, axis=-2), [c["conformal_set"] for c in cases])
    np.testing.assert_allclose(decision.proposed, [c["proposed"] for c in cases], atol=artifact["tolerance"]["step"], rtol=0)
    for actual, expected in [(ans.score.dist, [c["score_probs"] for c in cases]),
                             (ans.noul.p_true, [c["noul"] for c in cases])]:
        np.testing.assert_allclose(actual, expected, atol=artifact["tolerance"]["probs"], rtol=0)
    for axis, ch in enumerate(ans.choice):
        np.testing.assert_allclose(ch.probs, [c["probs"][axis] for c in cases], atol=artifact["tolerance"]["probs"], rtol=0)


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


def test_elf_coff_and_unavailable_memory_accounting():
    module = _script("21_hardware")
    elf = module.parse_size_sections("section size addr\n.text 20 0\n.rodata 100 0\n.rodata.str1.1 7 0\n.data 8 0\n.bss 9 0\nTotal 144\n")
    coff = module.parse_size_sections(".text 20 0\n.rdata 100 0\n.rdata$zzz 7 0\n.data 8 0\n.bss 9 0\n")
    assert module._flash_bytes(elf) == module._flash_bytes(coff) == 127
    assert module._ram_bytes(elf) == module._ram_bytes(coff) == 17
    assert module._flash_bytes({"status": "unavailable", "error": "no compiler"}) is None
    assert module._ram_bytes({}) is None


def test_matlab_production_decoder(tmp_path):
    from jev_tune.matlab_runner import find_matlab
    matlab = find_matlab()
    if not matlab.ok:
        pytest.skip("MATLAB unavailable")
    result = subprocess.run([str(matlab.executable), "-batch",
                             f"addpath('{(ROOT / 'matlab').as_posix()}'); test_portability; test_tune_history('{tmp_path.as_posix()}')"],
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
