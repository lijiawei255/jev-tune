"""Smoke test for the script that produces the headline numbers.

`scripts/03_evaluate.py` is the single command the README tells a reader to run.
A unit test of `evaluate_head` does not catch a broken CLI flag, a renamed row,
or a budget that leaks; this runs the script end to end on three plants.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_evaluate_script_runs_end_to_end(tmp_path):
    out = tmp_path / "results"
    table = tmp_path / "table.md"
    env = dict(os.environ)
    roots = [str(REPO / "src")]
    if env.get("PYTHONPATH"):
        roots.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(roots)
    env["PYTHONUTF8"] = "1"

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "03_evaluate.py"),
            "--plants",
            "3",
            "--budget",
            "9",
            "--out",
            str(out),
            "--table",
            str(table),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=env,
        timeout=900,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]

    payload = json.loads((out / "eval_heldout_3.json").read_text(encoding="utf-8-sig"))
    assert payload["budget_per_plant"] == 9
    assert payload["n_plants"] == 3
    names = {row["method"] for row in payload["rows"]}
    assert {"jev_head", "cmaes", "bo", "vocab_hill", "swept_zn"} <= names
    # every row spent at most the budget it was given
    assert all(row["budget"] <= 9 for row in payload["rows"]), payload["rows"]

    text = table.read_text(encoding="utf-8")
    assert "budget 9" in text
    assert "jev_head" in text
