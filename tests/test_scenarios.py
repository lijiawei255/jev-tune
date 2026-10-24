"""Scenario draws must not depend on the interpreter's hash seed.

Before 0.4.0 `variants()` seeded with Python's salted `hash(name)`, so every
process generated different plants. That silently invalidated published
generalisation and robustness numbers. This test starts two interpreters with
different `PYTHONHASHSEED` values and compares what they generate.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

CODE = (
    "import json;"
    "from jev_tune.domains.pid.scenarios import variants;"
    "p = variants('valve_dead_zone', 2, seed=3);"
    "print(json.dumps({'u_max': p.u_max.tolist(),"
    " 'u_min': p.u_min.tolist(),"
    " 'delay': p.delay_s.tolist(),"
    " 'den': p.den.tolist()}))"
)


def _run(hash_seed: int) -> str:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(hash_seed)
    roots = [str(REPO / "src")]
    if env.get("PYTHONPATH"):
        roots.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(roots)
    out = subprocess.run(
        [sys.executable, "-c", CODE],
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    assert out.returncode == 0, out.stderr[-1000:]
    return out.stdout.strip()


def test_scenario_draws_do_not_depend_on_pythonhashseed():
    a = _run(0)
    b = _run(1)
    assert a == b, "scenario plants changed with PYTHONHASHSEED: the seed is not stable"
    payload = json.loads(a)
    assert len(payload["den"]) == 2 and len(payload["delay"]) == 2
