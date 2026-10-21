"""A warm MATLAB worker, driven through a queue directory.

Cold start is ~50 s and a model compile ~10 s on the reference machine, while a
whole tuning run costs ~2 s.  Spawning one MATLAB per job therefore throws away
the throughput advantage; this keeps a single session alive and feeds it jobs
through files (no sockets, no toolboxes, survives a client restart).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from .matlab_runner import MATLAB_DIR, find_matlab


class MatlabWorker:
    def __init__(self, timeout: float = 300.0, startup_timeout: float = 180.0):
        self.queue_dir = Path(tempfile.mkdtemp(prefix="jev_queue_"))
        self.stop_file = self.queue_dir / "stop.flag"
        self.timeout = timeout
        self.startup_timeout = startup_timeout
        self._proc: subprocess.Popen | None = None
        self._ready = False

    # ------------------------------------------------------------------ life
    def start(self) -> None:
        info = find_matlab()
        if not info.ok:
            raise RuntimeError("MATLAB not found; set MATLAB_EXE or add it to PATH")
        code = (
            f"addpath('{MATLAB_DIR.as_posix()}'); "
            f"jev_tune_worker('{self.queue_dir.as_posix()}','{self.stop_file.as_posix()}',0.05);"
        )
        exe = str(info.executable)
        self._proc = subprocess.Popen(
            [exe, "-batch", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(self.queue_dir),
        )
        # the worker writes ready.flag once its session is initialised
        ready = self.queue_dir / "ready.flag"
        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if ready.is_file():
                self._ready = True
                return
            if self._proc.poll() is not None:
                raise RuntimeError(f"worker exited during startup:\n{self._tail()}")
            time.sleep(0.2)
        raise TimeoutError(f"MATLAB worker did not become ready in {self.startup_timeout:.0f}s")

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            self.stop_file.write_text("stop", encoding="utf-8")
            self._proc.wait(timeout=30)
        except Exception:
            self._proc.kill()
        finally:
            self._proc = None
            self._ready = False

    def _tail(self) -> str:
        if self._proc is None or self._proc.stdout is None:
            return ""
        try:
            return self._proc.stdout.read()[-2000:]
        except Exception:
            return ""

    # ------------------------------------------------------------------ jobs
    def run(self, cfg: dict) -> dict:
        if not self._ready:
            self.start()
        job_id = uuid.uuid4().hex[:8]
        job_path = self.queue_dir / f"job_{job_id}.json"
        res_path = self.queue_dir / f"res_{job_id}.json"
        job_path.write_text(json.dumps(cfg), encoding="utf-8")

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if res_path.is_file():
                try:
                    data = json.loads(res_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    time.sleep(0.05)
                try:
                    res_path.unlink()
                except OSError:
                    pass
                return data
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError(f"worker died while running a job:\n{self._tail()}")
            time.sleep(0.05)
        raise TimeoutError(f"job {job_id} did not finish in {self.timeout:.0f}s")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()


_WORKER: MatlabWorker | None = None


def get_worker() -> MatlabWorker:
    """Process-wide singleton so repeated MCP calls reuse the warm session."""
    global _WORKER
    if _WORKER is None:
        _WORKER = MatlabWorker()
    return _WORKER


def tune_with_worker(cfg: dict, *, timeout: float = 300.0) -> dict:
    worker = get_worker()
    worker.timeout = timeout
    return worker.run(cfg)
