"""Compile the production C shell and exercise fault handling, without MATLAB."""
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize("harness", ["test_checked", "test_forward", "test_features", "test_policy"])
def test_checked_shell_and_unchanged_numeric_fixtures(tmp_path, harness):
    cc = shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        pytest.skip("C99 compiler unavailable")
    exe = tmp_path / (harness + ".exe")
    subprocess.run([cc, "-std=c99", "-O2", "-Wall", "-Wextra",
                    "-I", str(ROOT / "c"), str(ROOT / "c" / (harness + ".c")),
                    str(ROOT / "c/jev_head.c"), "-lm", "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
