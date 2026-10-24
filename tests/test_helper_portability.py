"""Keep optional MATLAB helpers independent of private checkout/input names."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ["bench_iter", "cmp_gains", "save_demo_traces", "sens_lab"]


def test_helpers_do_not_embed_personal_paths_or_private_model():
    for name in HELPERS:
        source = (ROOT / "matlab" / (name + ".m")).read_text(encoding="utf-8")
        assert not re.search(r"[A-Za-z]:[\\/]|/(?:home|Users)/", source), name
        assert "jev_lab_model" not in source, name
        assert source.startswith("function S = " + name + "("), name
        assert "jev:helperInputs" in source, name
    engine = (ROOT / "matlab/save_demo_traces.m").read_text(encoding="utf-8")
    assert "mfilename('fullpath')" in engine
    assert engine.index("jev:helperMissingInput") < engine.index("load_system(")
    assert "Simulink.SimulationInput" in engine
    assert "setModelParameter" in engine
    assert "onCleanup" in engine
