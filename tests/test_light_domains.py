"""The light instances reuse the unchanged core and keep their documented outputs."""
import sys

import numpy as np
import pytest

from jev_tune.domains.light import linear_shell, vla_mask


def test_linear_shell_documented_result():
    state, decision = linear_shell.toy_step(np.array([.5, .5]))
    np.testing.assert_allclose(state, [.6, .35])
    assert not decision.held.any()


def test_vla_mask_never_executes_a_forbidden_token_and_holds_with_noop():
    r = vla_mask.run(seed=0)
    assert r["raw_forbidden_rate"] > 0 and r["shell_forbidden_rate"] == 0
    assert r["cp_coverage"] >= 0.85 and 0 < r["shell_hold_rate"] < 1
    assert r["shell_error_rate_when_acting"] < r["raw_error_rate"]
    shell = vla_mask.VlaShell(temperature=1.0, qhat=0.5)
    holding = vla_mask.allowed_actions(holding=True)
    grasp = np.eye(len(vla_mask.ACTIONS))[vla_mask.ACTIONS.index("grasp")] * 20
    assert shell.act(grasp, holding) == (vla_mask.NOOP, "forbidden_top")


def test_light_instances_import_without_torch_or_the_pid_testbed(monkeypatch):
    for name in [m for m in sys.modules if m.startswith(("torch", "jev_tune"))]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "torch", None)
    import jev_tune.domains.light.vla_mask  # noqa: F401
    assert not any(m.startswith("jev_tune.domains.pid") for m in sys.modules)


@pytest.mark.parametrize("seed", [1, 2])
def test_vla_mask_is_deterministic(seed):
    assert vla_mask.run(seed=seed) == vla_mask.run(seed=seed)
