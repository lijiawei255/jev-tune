"""Restore the optional motor/valve benchmark. / 恢复可选电机/阀门基准。

The tracked manifest pins the complete ZIP and every one of its 18 members.
Installation publishes a verified staging directory atomically and never
replaces an existing conflicting destination. No simulations or training run.
固定清单核验完整 ZIP 和全部 18 个成员；暂存核验后原子安装，不覆盖冲突目录。
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "research/distribution/motor_valve_benchmark_v0101.json"
ASSET = "motor_valve_benchmark_v0.10.1.zip"
URL = "https://github.com/lijiawei255/jev-tune/releases/download/v0.10.1/" + ASSET
PREFIX = "motor_valve_benchmark/"
DEFAULT_DESTINATION = "benchmarks/motor_valve"
EVIDENCE = {
    "archive-equivalence.public.json", "mxarray-inspection.public.json",
    "native-mat-inspection.public.json", "numeric-equivalence.public.json",
    "numeric-mat-preservation.public.json", "payload-privacy.public.json",
    "same-input-cost.public.json",
}
MEMBERS = {PREFIX + name for name in {
    "jev_lab_model.slx", "images/80mm_Butterfly_valve.STL", "images/valve_icon.jpg",
    "README.md", "MANIFEST.json",
    *("evidence/" + name for name in EVIDENCE),
    *(f"runs/run_{index:02d}/tune_result.mat" for index in range(1, 7)),
}}
MAX_BYTES = 64 * 1024 ** 2

_spec = importlib.util.spec_from_file_location("jev_benchmark_research_data", ROOT / "scripts/59_research_data.py")
data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(data)


def validate_manifest(manifest):
    data.require(isinstance(manifest, dict) and manifest.get("schema_version") == 1
                 and manifest.get("version") == "0.10.1", "Unsupported benchmark manifest")
    data.require(manifest.get("repository") == "lijiawei255/jev-tune"
                 and manifest.get("hash_scope") == "exact_bytes", "Benchmark trust root differs")
    contract = manifest.get("archive")
    data.require(isinstance(contract, dict) and contract.get("asset") == ASSET
                 and contract.get("url") == URL, "Only the pinned project benchmark release URL is allowed")
    data.require(type(contract.get("size_bytes")) is int and 0 < contract["size_bytes"] <= MAX_BYTES,
                 "Invalid benchmark archive size")
    data.require(re.fullmatch(r"[0-9a-f]{64}", contract.get("sha256", "")), "Invalid benchmark archive hash")
    rows = contract.get("files")
    data.require(isinstance(rows, list) and len(rows) == 18, "Benchmark must have exactly 18 members")
    seen = set()
    for row in rows:
        data.require(isinstance(row, dict), "Invalid benchmark member")
        name = data.safe_path(row.get("path"))
        data.require(name in MEMBERS and name.casefold() not in seen, "Unknown/duplicate benchmark member: " + name)
        seen.add(name.casefold())
        data.require(type(row.get("size_bytes")) is int and 0 <= row["size_bytes"] <= MAX_BYTES,
                     "Invalid benchmark member size")
        data.require(re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")), "Invalid benchmark member hash")
        data.require(row.get("install") is True, "All benchmark members must be installed")
    data.require({row["path"] for row in rows} == MEMBERS, "Benchmark member roster differs")
    data.require(sum(row["size_bytes"] for row in rows) <= MAX_BYTES, "Expanded benchmark exceeds byte limit")
    return manifest


def load_manifest(root=ROOT):
    return validate_manifest(data.read_json((Path(root) / MANIFEST).read_bytes()))


def _target(root, destination=None):
    root = Path(root).absolute()
    path = Path(root) / DEFAULT_DESTINATION if destination is None else Path(destination).expanduser()
    if not path.is_absolute():
        path = Path(root) / path
    data.require(".." not in path.parts, "Noncanonical benchmark destination")
    path = path.absolute()
    # Do not resolve away symlinks or Windows reparse points before checking.
    for parent in [*reversed(path.parents), path]:
        data.require(not data._is_link(parent), "Symlink/reparse benchmark destination: " + str(parent))
        data.require(not parent.exists() or parent.is_dir(), "Nondirectory benchmark destination: " + str(parent))
    data.require(path != Path(path.anchor), "Refuse filesystem root as benchmark destination")
    return path


def _installed(target, contract):
    expected = {row["path"][len(PREFIX):]: row for row in contract["files"]}
    if not target.exists():
        return False
    seen = set()
    for folder, directories, filenames in os.walk(target, followlinks=False):
        for name in directories + filenames:
            entry = Path(folder) / name
            data.require(not data._is_link(entry), "Symlink/reparse installed benchmark member")
        for name in filenames:
            entry = Path(folder) / name
            relative = entry.relative_to(target).as_posix()
            data.safe_path(relative)
            data.require(relative in expected and data._identity(entry, expected[relative]),
                         "Refuse conflicting benchmark file: " + relative)
            seen.add(relative)
    data.require(seen == set(expected), "Refuse incomplete/conflicting existing benchmark destination")
    # Extra empty directories are also user-owned content, not ours to replace.
    expected_dirs = {str(Path(name).parent).replace("\\", "/") for name in expected}
    expected_dirs |= {str(parent).replace("\\", "/") for name in expected
                      for parent in Path(name).parents if str(parent) != "."}
    actual_dirs = {Path(folder).relative_to(target).as_posix() for folder, _, _ in os.walk(target)
                   if Path(folder) != target}
    data.require(actual_dirs <= expected_dirs, "Refuse extra directories in benchmark destination")
    return True


def check(root=ROOT, *, destination=None, manifest=None):
    manifest = load_manifest(root) if manifest is None else validate_manifest(manifest)
    target = _target(root, destination)
    present = _installed(target, manifest["archive"])
    return {"ok": present, "operation": "check", "destination": str(target),
            "member_count": 18 if present else 0, "objective_evaluations": 0, "gradient_steps": 0}


def _download(contract, target):
    # validate_manifest pins the initial URL; reuse script 59's HTTPS redirect policy.
    data.require(contract["url"] == URL, "Unexpected benchmark download URL")
    opener = urllib.request.build_opener(data._ReleaseRedirects())
    started, count = time.monotonic(), 0
    request = urllib.request.Request(URL, headers={"User-Agent": "jev-tune-benchmark/0.10.1"})
    with opener.open(request, timeout=data.HTTP_TIMEOUT) as response, target.open("xb") as output:
        final = urllib.parse.urlsplit(response.geturl())
        data.require(final.scheme == "https" and final.hostname in {
            "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
            and final.port in {None, 443} and final.username is None and final.password is None,
            "Unsafe final benchmark download URL")
        length = response.headers.get("Content-Length")
        data.require(length is None or int(length) == contract["size_bytes"], "HTTP Content-Length differs")
        for block in iter(lambda: response.read(data.CHUNK), b""):
            count += len(block)
            data.require(count <= contract["size_bytes"] and time.monotonic() - started <= data.DOWNLOAD_DEADLINE,
                         "Benchmark download byte/time limit exceeded")
            output.write(block)
    data.require(count == contract["size_bytes"], "Incomplete benchmark download")


def _publish(stage, target):
    """Atomic directory publication with no replacement, including an empty racer."""
    if os.name == "nt":
        os.rename(stage, target)  # Windows rename refuses every existing target.
        return
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        rename = library.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(-100, os.fsencode(stage), -100, os.fsencode(target), 1)  # RENAME_NOREPLACE
    elif sys.platform == "darwin" and hasattr(library, "renamex_np"):
        rename = library.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(os.fsencode(stage), os.fsencode(target), 4)  # RENAME_EXCL
    else:
        raise OSError(errno.ENOTSUP, "Atomic no-replacement directory publication is unavailable")
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(target))


def restore(root=ROOT, *, destination=None, from_dir=None, manifest=None):
    root = Path(root).absolute()
    manifest = load_manifest(root) if manifest is None else validate_manifest(manifest)
    contract = manifest["archive"]
    target = _target(root, destination)
    if _installed(target, contract):
        return {"ok": True, "operation": "restore", "destination": str(target), "installed_files": [],
                "already_present_files": 18, "offline": from_dir is not None,
                "objective_evaluations": 0, "gradient_steps": 0}
    ancestor = target.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    created = []
    with tempfile.TemporaryDirectory(prefix=".jev-benchmark-", dir=ancestor) as temporary:
        stage = Path(temporary)
        archive = stage / ASSET if from_dir is None else Path(from_dir).absolute() / ASSET
        if from_dir is None:
            _download(contract, archive)
        data.verify_archive(archive, contract, stage / "verified")
        # All member data and headers are verified before target parents exist.
        staged_target = stage / "verified" / PREFIX.rstrip("/")
        data.require(_installed(staged_target, contract), "Staged benchmark check failed")
        try:
            _target(root, destination)
            missing = []
            parent = target.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for parent in reversed(missing):
                parent.mkdir()
                created.append(parent)
            _target(root, destination)
            data.require(not target.exists(), "Destination changed during benchmark restore")
            _publish(staged_target, target)
        except BaseException:
            for parent in reversed(created):
                try:
                    parent.rmdir()
                except OSError:
                    pass
            raise
    return {"ok": True, "operation": "restore", "destination": str(target),
            "installed_files": sorted(name[len(PREFIX):] for name in MEMBERS), "already_present_files": 0,
            "offline": from_dir is not None, "objective_evaluations": 0, "gradient_steps": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", help="Install directory / 安装目录（默认 benchmarks/motor_valve）")
    parser.add_argument("--from-dir", help="Offline directory containing the pinned ZIP / 固定 ZIP 所在离线目录")
    parser.add_argument("--check", action="store_true", help="Check installed bytes without downloading / 只核验已安装文件")
    parser.add_argument("--json", action="store_true", help="Print JSON (also the default) / 输出 JSON（也是默认格式）")
    args = parser.parse_args(argv)
    try:
        result = check(destination=args.destination) if args.check else restore(
            destination=args.destination, from_dir=args.from_dir)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        result = {"ok": False, "error": str(error), "objective_evaluations": 0, "gradient_steps": 0}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
