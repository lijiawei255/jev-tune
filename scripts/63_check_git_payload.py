"""Reject accidental experimental data and oversized blobs in advertised Git history."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

MAX_BLOB_BYTES = 5_000_000
FORMAL_NONPID = {f'research/results/nonpid_transfer/{kind}_{seed}.json'
                for kind in ('model', 'calibration') for seed in (101, 202, 303)}


def git(root, *args, input=None):
    env = os.environ.copy()
    env.update(GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1')
    return subprocess.check_output(['git', '-C', str(root), *args], input=input, env=env)


def check(root):
    root = Path(root).resolve()
    # --all includes branches and tags. A large file added and then removed
    # within the same push must still fail; checking only HEAD is insufficient.
    objects = git(root, 'rev-list', '--objects', '--all')
    rows = git(root, 'cat-file', '--batch-check=%(objectname) %(objecttype) %(objectsize) %(rest)', input=objects)
    oversized, blobs = [], 0
    for line in rows.decode('utf-8').splitlines():
        parts = line.split(' ', 3)
        if parts[1] != 'blob':
            continue
        blobs += 1
        if int(parts[2]) > MAX_BLOB_BYTES:
            oversized.append({'oid': parts[0], 'size_bytes': int(parts[2]), 'path': parts[3] if len(parts) > 3 else ''})
    # Inspect every historical tree: rev-list labels an object with only one
    # path, so it cannot alone detect the same blob added at a forbidden path.
    forbidden = []
    commits = git(root, 'rev-list', '--all').decode().splitlines()
    for revision in commits:
        paths = git(root, 'ls-tree', '-rz', '--name-only', revision, '--', 'research/results').split(b'\0')
        for value in paths:
            if value:
                name = value.decode('utf-8')
                if name not in FORMAL_NONPID:
                    forbidden.append({'commit': revision, 'path': name})
    if oversized or forbidden:
        raise ValueError(json.dumps({'oversized_blobs': oversized, 'release_only_history_paths': forbidden}, ensure_ascii=False))
    return {'ok': True, 'scope': 'All advertised local branches/tags, including intermediate commits',
            'commit_count': len(commits), 'blob_count': blobs, 'max_blob_bytes': MAX_BLOB_BYTES,
            'objective_evaluations': 0, 'gradient_steps': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = check(args.root)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
