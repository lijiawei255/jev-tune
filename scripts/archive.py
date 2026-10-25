"""Recoverable entry to the frozen v0.10.2 research archive.

Main keeps the runtime shell. Frozen protocols, historical evidence, negative
results and their verifiers live unchanged at the Git tag below; their data
lives in the hash-pinned v0.10.0/v0.10.1 Release attachments. This script never edits the
current checkout: it opens the tag in a separate worktree and runs the
archived verifiers there, so hashes recorded by the frozen studies stay valid.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

TAG = "v0.10.2-archive"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / ".archive" / TAG
VERIFY = (
    ["scripts/59_research_data.py", "--fetch", "all"],
    ["scripts/history_sources.py", "--root", ".", "--restore-pinned"],
    ["scripts/16_check_claims.py", "--json"],
)


def git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def ensure_tag() -> str:
    if subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{TAG}"],
                      cwd=ROOT, capture_output=True).returncode != 0:
        git("fetch", "origin", "tag", TAG, "--no-tags")
    return git("rev-parse", f"{TAG}^{{commit}}")


def open_worktree(path: Path) -> Path:
    commit = ensure_tag()
    if not (path / ".git").exists():
        git("worktree", "add", "--detach", str(path), commit)
    if git("rev-parse", "HEAD", cwd=path) != commit:
        raise SystemExit(f"{path} is not at {TAG}; remove it and retry")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Open or verify the frozen research archive.")
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="worktree location")
    ap.add_argument("--verify", action="store_true",
                    help="restore pinned Release data and run the archived claim verifier")
    args = ap.parse_args(argv)
    path = open_worktree(args.dir.resolve())
    print(f"[archive] {TAG} at {path}")
    if not args.verify:
        return 0
    for cmd in VERIFY:
        print("[archive] python " + " ".join(cmd))
        code = subprocess.run([sys.executable, *cmd], cwd=path,
                              env={**os.environ, "PYTHONPATH": "src"}).returncode
        if code:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
