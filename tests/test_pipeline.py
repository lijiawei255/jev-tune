"""The expert (label source), identification, scenarios and the MCP plumbing.

All of these are cheap on two plants; the point is that the code that *makes the
labels* is exercised, not just the code that consumes them.
"""

import numpy as np

from jev_tune.expert import FAMILY_TO_ID, generate
from jev_tune.identified import fopdt_pade_tf, identify_fopdt, open_loop_step
from jev_tune.plants import TRAIN_FAMILIES, sample_plants
from jev_tune.scenarios import _stack, names, variants
from jev_tune.train import train_head


def _plants(n=2):
    return sample_plants(n, seed=5, families=TRAIN_FAMILIES)


def test_expert_rollout_has_the_shapes_the_trainer_expects():
    plants = _plants(2)
    data, gains, j_now, gzn = generate(plants, steps=2, seed=0, verbose=False)
    n_states = 2 * plants.n
    assert data.feats.shape == (n_states, 20)
    assert data.curves.shape == (n_states, 2, 64)
    assert data.choice.shape == (n_states, 3)
    assert data.score.shape == (n_states,)
    assert data.noul.shape == (n_states,)
    assert gains.shape == gzn.shape == (plants.n, 3)
    assert j_now.shape == (plants.n,)
    # 3 axes x 7 options of lookahead data per state
    assert len(data.act_state) == n_states * 21
    assert set(np.unique(data.choice)).issubset(set(range(7)))
    assert set(np.unique(data.score)).issubset(set(range(5)))
    assert set(FAMILY_TO_ID) >= set(plants.family)


def test_one_epoch_of_training_on_the_tiny_rollout():
    plants = _plants(2)
    data, _, _, _ = generate(plants, steps=1, seed=0, verbose=False)
    model = train_head(data, epochs=1, batch=8, verbose=False)
    out = model(
        __import__("torch").as_tensor(data.feats),
        __import__("torch").as_tensor(data.curves),
    )
    assert out["choice"].shape == (len(data.feats), 3, 7)
    assert out["score"].shape == (len(data.feats), 5)
    assert out["noul"].shape == (len(data.feats),)


def test_identification_fits_a_first_order_model():
    plants = _plants(2)
    t, y = open_loop_step(plants)
    k, tau, delay = identify_fopdt(t, y)
    assert k.shape == tau.shape == delay.shape == (plants.n,)
    assert np.all(np.isfinite(k))
    assert np.all(tau > 0)
    assert np.all(delay >= 0)
    num, den = fopdt_pade_tf(k, tau, delay)
    assert num.shape == den.shape
    assert num.shape[0] == plants.n


def test_scenarios_are_listed_and_stackable():
    assert len(names()) == 10
    one = variants("noisy_sensor", 3, seed=1)
    assert one.n == 3
    assert set(one.family) == {"noisy_sensor"}
    both = _stack([one, variants("hydraulic", 2, seed=1)])
    assert both.n == 5


def test_mcp_handshake_and_tool_list():
    from jev_tune.mcp_server import handle

    init = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"]
    tools = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    listed = {t["name"] for t in tools["result"]["tools"]}
    assert {
        "tune_status",
        "tune_probe_matlab",
        "tune_doctor",
        "tune_discover",
        "tune_simulink",
        "tune_apply_gains",
        "tune_demo",
    } <= listed
