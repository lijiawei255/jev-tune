"""Locate and drive MATLAB without assuming a specific release or install path.

The old code hard-coded ``C:\\Program Files\\MATLAB\\R2024b\\bin\\matlab.exe``.
That is exactly the kind of assumption that breaks for anyone else, so discovery
now goes: explicit override -> PATH -> registry (Windows) -> conventional roots,
and the launcher picks ``-batch`` only when the release supports it.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MATLAB_DIR = REPO / "matlab"


@dataclass
class MatlabInfo:
    executable: Path | None
    source: str

    @property
    def ok(self) -> bool:
        return self.executable is not None


def _candidates() -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []

    explicit = os.environ.get("MATLAB_EXE")
    if explicit:
        out.append((Path(explicit), "MATLAB_EXE"))

    on_path = shutil.which("matlab")
    if on_path:
        out.append((Path(on_path), "PATH"))

    system = platform.system()
    if system == "Windows":
        # MATLAB.exe lives under <root>\bin\win64; matlab.exe is the launcher
        roots = [
            Path(r"C:\Program Files\MATLAB"),
            Path(r"C:\Program Files (x86)\MATLAB"),
        ]
        for root in roots:
            if not root.is_dir():
                continue
            for release in sorted(root.iterdir(), reverse=True):
                exe = release / "bin" / "matlab.exe"
                if exe.is_file():
                    out.append((exe, f"scan:{release.name}"))
        try:  # registry: HKCU\Software\MathWorks\MATLAB\<ver>\MATLABROOT
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\MathWorks\MATLAB")
            n = winreg.QueryInfoKey(key)[0]
            for i in range(n):
                sub = winreg.EnumKey(key, i)
                try:
                    root, _ = winreg.QueryValueEx(
                        winreg.OpenKey(key, sub), "MATLABROOT"
                    )
                    exe = Path(root) / "bin" / "matlab.exe"
                    if exe.is_file():
                        out.append((exe, f"registry:{sub}"))
                except OSError:
                    continue
        except Exception:
            pass
    elif system == "Darwin":
        base = Path("/Applications")
        if base.is_dir():
            for app in sorted(base.glob("MATLAB_R*.app"), reverse=True):
                exe = app / "bin" / "matlab"
                if exe.is_file():
                    out.append((exe, f"scan:{app.name}"))
    else:
        for pattern in ("/usr/local/MATLAB/*/bin/matlab", "/opt/MATLAB/*/bin/matlab"):
            for exe in sorted(Path("/").glob(pattern.lstrip("/")), reverse=True):
                if exe.is_file():
                    out.append((exe, str(exe.parent.parent)))

    return out


def find_matlab() -> MatlabInfo:
    for exe, source in _candidates():
        if exe.is_file():
            return MatlabInfo(exe, source)
    return MatlabInfo(None, "not found")


def run_matlab(
    code: str, *, timeout: int = 900, matlab: MatlabInfo | None = None
) -> subprocess.CompletedProcess:
    """Run MATLAB code non-interactively, using -batch when available."""
    info = matlab or find_matlab()
    if not info.ok:
        raise RuntimeError(
            "MATLAB not found. Set MATLAB_EXE to the matlab executable, or add it to PATH."
        )
    exe = str(info.executable)
    if _supports_batch(exe):
        cmd = [exe, "-batch", code]
    else:  # R2019a and older: no -batch
        cmd = [exe, "-nodisplay", "-nosplash", "-r", f"{code}; exit"]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _supports_batch(exe: str) -> bool:
    """-batch exists from R2019a; assume yes when the version cannot be parsed."""
    try:
        out = subprocess.run([exe, "-help"], capture_output=True, text=True, timeout=30)
        return "-batch" in (out.stdout + out.stderr)
    except Exception:
        return True


def run_job(cfg: dict, *, timeout: int = 900) -> dict:
    """Run one tuning job through jev_tune_json.m and return the parsed result."""
    info = find_matlab()
    if not info.ok:
        return {
            "ok": False,
            "error": "MATLAB not found; set MATLAB_EXE or add matlab to PATH",
            "matlab": None,
        }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cfg_file = tmp_path / "job.json"
        out_file = tmp_path / "result.json"
        cfg_file.write_text(json.dumps(cfg), encoding="utf-8")

        code = (
            f"addpath('{MATLAB_DIR.as_posix()}'); "
            f"jev_tune_json('{cfg_file.as_posix()}','{out_file.as_posix()}');"
        )
        proc = run_matlab(code, timeout=timeout, matlab=info)
        if not out_file.is_file():
            return {
                "ok": False,
                "error": "MATLAB produced no result file",
                "stderr": proc.stderr[-2000:],
                "stdout": proc.stdout[-2000:],
                "matlab": str(info.executable),
            }
        result = json.loads(out_file.read_text(encoding="utf-8"))
        result["matlab"] = str(info.executable)
        result["matlab_source"] = info.source
        return result


def run_batch(jobs: list[dict], *, timeout: int = 3600) -> list[dict]:
    """Run many jobs in a single MATLAB process (one cold start, not N)."""
    info = find_matlab()
    if not info.ok:
        return [{"ok": False, "error": "MATLAB not found; set MATLAB_EXE"}]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        jobs_file = tmp_path / "jobs.json"
        out_file = tmp_path / "results.jsonl"
        jobs_file.write_text(json.dumps(jobs), encoding="utf-8")
        code = (
            f"addpath('{MATLAB_DIR.as_posix()}'); "
            f"jev_tune_batch('{jobs_file.as_posix()}','{out_file.as_posix()}');"
        )
        proc = run_matlab(code, timeout=timeout, matlab=info)
        if not out_file.is_file():
            return [{
                "ok": False,
                "error": "batch produced no results",
                "stderr": proc.stderr[-2000:],
            }]
        results = [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in results:
        r.setdefault("matlab", str(info.executable))
    return results


def probe(*, timeout: int = 180) -> dict:
    info = find_matlab()
    if not info.ok:
        return {"ok": False, "error": "MATLAB not found", "matlab": None}
    with tempfile.TemporaryDirectory() as tmp:
        out_file = Path(tmp) / "probe.json"
        code = (
            f"addpath('{MATLAB_DIR.as_posix()}'); "
            f"jev_tune_probe('{out_file.as_posix()}');"
        )
        proc = run_matlab(code, timeout=timeout, matlab=info)
        if not out_file.is_file():
            return {
                "ok": False,
                "error": "probe failed",
                "stderr": proc.stderr[-1500:],
                "matlab": str(info.executable),
            }
        data = json.loads(out_file.read_text(encoding="utf-8"))
        data["matlab"] = str(info.executable)
        data["matlab_source"] = info.source
        return data
