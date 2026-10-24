"""Restore pinned optional research data. / 恢复固定哈希的按需研究数据。

The Git-distributed manifest is the trust root. Archives contain no manifest;
whole-ZIP and every member hash are checked before any dataset is installed.
This module collects no experiments, trains no models and imports no ML stack.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "research/distribution/research_data_v0101.json"
VERSION = "0.10.1"
REPOSITORY = "lijiawei255/jev-tune"
RELEASE_BASE = "https://github.com/" + REPOSITORY + "/releases/download/"
PID_ASSET = "pid_synthetic_data_v0.10.0.zip"
PID_SHA256 = "64816b2c2267b5847c76201949714aae4c57c3161a07d6526b88e00eb7ee6f3d"
PID_SIZE = 21047270
PID_PATHS = {"data/expert_train.npz", "data/calibration/temperature_fit.npz",
             "data/calibration/cp_fit.npz", "data/calibration/empirical_eval.npz"}
PID_INVENTORY = "research/results/open_source_inventory_v0100.json"
GROUPS = {"current", "historical", "evidence", "pid"}
MAX_ARCHIVE_BYTES = 1024 ** 3
MAX_EXPANDED_BYTES = 1024 ** 3
CHUNK = 1024 ** 2
HTTP_TIMEOUT = 30
DOWNLOAD_DEADLINE = 600
STAMP = (2026, 1, 1, 0, 0, 0)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(data):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + value)))


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            result.update(block)
    return result.hexdigest()


def safe_path(name):
    require(isinstance(name, str) and name and "\x00" not in name and "\\" not in name and ":" not in name,
            "Unsafe archive path: " + repr(name))
    require(not PurePosixPath(name).is_absolute() and not PureWindowsPath(name).drive and not name.endswith("/"),
            "Absolute/directory archive path: " + name)
    parts = name.split("/")
    require(all(part not in {"", ".", ".."} and part.casefold() != ".git" and not part.endswith((".", " ")) for part in parts),
            "Traversal/Git/noncanonical archive path: " + name)
    require(all(not re.fullmatch(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part, re.I) for part in parts),
            "Reserved archive path: " + name)
    return name


def _is_link(path):
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except FileNotFoundError:
        return False


def destination(root, name):
    root = Path(root).resolve()
    parts = safe_path(name).split("/")
    current = root
    for index, part in enumerate(parts):
        current = current / part
        require(not _is_link(current), "Symlink/reparse destination: " + name)
        if current.exists():
            mode = stat.S_IFMT(current.lstat().st_mode)
            require(mode == (stat.S_IFREG if index == len(parts) - 1 else stat.S_IFDIR),
                    "Nonregular/conflicting destination: " + name)
    return current


def _identity(path, row):
    return path.is_file() and path.stat().st_size == row["size_bytes"] and digest(path) == row["sha256"]


def _data_path(name, group):
    if group == "pid":
        return name in PID_PATHS
    if group == "evidence":
        return name.startswith("research/results/") and PurePosixPath(name).suffix not in {".gz", ".npz"}
    raw = name.startswith("research/") and PurePosixPath(name).suffix in {".gz", ".npz"}
    current = name.startswith(("research/results/nonpid_transfer/", "research/results/calibration_runtime_sources/"))
    return raw and current == (group == "current")


def _expected_url(group, asset):
    expected_asset = PID_ASSET if group == "pid" else "research_" + group + "_v0.10.1.zip"
    require(asset == expected_asset, "Unexpected release asset for group: " + group)
    return RELEASE_BASE + ("v0.10.0/" if group == "pid" else "v0.10.1/") + asset


def validate_manifest(manifest):
    require(isinstance(manifest, dict) and manifest.get("schema_version") == 1 and manifest.get("version") == VERSION,
            "Unsupported research-data manifest")
    require(manifest.get("repository") == REPOSITORY and manifest.get("hash_scope") == "exact_bytes", "Manifest repository/hash scope differs")
    require(type(manifest.get("history_cleaned", False)) is bool, "history_cleaned must be an explicit boolean when present")
    require(re.fullmatch(r"[0-9a-f]{40}", manifest.get("source_revision", "")), "Manifest needs full source revision")
    groups = manifest.get("groups")
    require(isinstance(groups, dict) and groups and set(groups) <= GROUPS, "Invalid data groups")
    all_installs = set()
    for group, archive in groups.items():
        require(archive.get("url") == _expected_url(group, archive.get("asset")), "Only fixed project HTTPS release URLs are allowed")
        require(type(archive.get("size_bytes")) is int and 0 < archive["size_bytes"] <= MAX_ARCHIVE_BYTES, "Invalid archive byte limit")
        require(re.fullmatch(r"[0-9a-f]{64}", archive.get("sha256", "")), "Invalid archive SHA-256")
        files = archive.get("files")
        require(isinstance(files, list) and files, "Empty archive file contract")
        names = set()
        for row in files:
            name = safe_path(row.get("path"))
            require(name.casefold() not in names, "Duplicate/case-colliding manifest path: " + name)
            names.add(name.casefold())
            require(type(row.get("size_bytes")) is int and 0 <= row["size_bytes"] <= MAX_EXPANDED_BYTES, "Invalid member size")
            require(re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")), "Invalid member hash")
            require(type(row.get("install")) is bool, "Missing explicit install flag")
            require(isinstance(row.get("source"), dict), "Missing member provenance")
            source = row["source"]
            if group == "pid":
                require(source.get("kind") == "pinned_pid_release" and source.get("release") == "v0.10.0"
                        and source.get("archive_sha256") == archive["sha256"], "PID provenance differs")
            else:
                require(source.get("kind") in {"git_blob", "deidentified_git_blob"} and source.get("revision") == manifest["source_revision"]
                        and re.fullmatch(r"[0-9a-f]{40}", source.get("oid", "")), "Committed Git blob provenance required")
                if source["kind"] == "deidentified_git_blob":
                    require(re.fullmatch(r"[0-9a-f]{40}", source.get("original_oid", "")) is not None
                            and source.get("transformation") == "metadata_only_deidentification",
                            "Deidentified member needs original identity and explicit transformation")
            if row["install"]:
                require(_data_path(name, group) and name.casefold() not in all_installs, "Invalid/duplicate install path: " + name)
                require((name in PID_PATHS) == (group == "pid"), "Data path/group mismatch: " + name)
                all_installs.add(name.casefold())
            else:
                require(name in {"LICENSE", "NOTICE.md"} | ({PID_INVENTORY} if group == "pid" else set()), "Unknown metadata member: " + name)
        require(sum(row["size_bytes"] for row in files) <= MAX_EXPANDED_BYTES, "Expanded group exceeds byte limit")
        require({row["path"] for row in files if not row["install"]} == {"LICENSE", "NOTICE.md"} | ({PID_INVENTORY} if group == "pid" else set()), "Incomplete license/notice contract")
        require(any(row["install"] for row in files), "No data in group")
        if group == "pid":
            require({row["path"] for row in files if row["install"]} == PID_PATHS, "PID member roster differs")
    return manifest


def load_manifest(root=ROOT):
    return validate_manifest(read_json((Path(root) / MANIFEST).read_bytes()))


def _select(manifest, groups):
    selected = sorted(manifest["groups"]) if groups == "all" else ([groups] if isinstance(groups, str) else list(groups))
    require(selected and len(set(selected)) == len(selected) and set(selected) <= manifest["groups"].keys(), "Unknown/duplicate requested group")
    return selected


def check(root=ROOT, manifest=None, groups="all"):
    root = Path(root).resolve()
    manifest = load_manifest(root) if manifest is None else validate_manifest(manifest)
    selected = _select(manifest, groups)
    present, missing, conflicts = [], [], []
    for group in selected:
        for row in manifest["groups"][group]["files"]:
            if not row["install"]:
                continue
            try:
                target = destination(root, row["path"])
                if not target.exists():
                    missing.append(row["path"])
                elif _identity(target, row):
                    present.append(row["path"])
                else:
                    conflicts.append(row["path"])
            except ValueError:
                conflicts.append(row["path"])
    return {"ok": not missing and not conflicts, "operation": "check", "groups": selected,
            "present_files": present, "missing": missing, "conflicts": conflicts,
            "objective_evaluations": 0, "gradient_steps": 0}


def _archive_headers(archive, contract):
    expected = {row["path"]: row for row in contract["files"]}
    seen, headers = set(), {}
    for info in archive.infolist():
        name = safe_path(info.filename)
        require(name.casefold() not in seen, "Duplicate/case-colliding ZIP member: " + name)
        seen.add(name.casefold())
        require(name in expected, "Unknown ZIP member: " + name)
        kind = stat.S_IFMT(info.external_attr >> 16)
        require(kind == stat.S_IFREG or kind == 0 and info.create_system == 0, "ZIP symlink/FIFO/socket/device/directory: " + name)
        require(not info.is_dir() and not info.flag_bits & 1, "Directory/encrypted ZIP member: " + name)
        require(info.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}, "Unsupported ZIP compression")
        require(info.file_size == expected[name]["size_bytes"], "ZIP member size differs: " + name)
        headers[name] = info
    require(set(headers) == set(expected), "Missing ZIP members")
    return headers


def verify_archive(path, contract, stage=None):
    path = Path(path)
    require(path.is_file() and not _is_link(path), "Missing/nonregular archive: " + str(path))
    require(path.stat().st_size == contract["size_bytes"] and digest(path) == contract["sha256"], "Whole ZIP size/SHA-256 differs: " + contract["asset"])
    staged = {}
    with zipfile.ZipFile(path) as archive:
        headers = _archive_headers(archive, contract)
        for row in contract["files"]:
            name, hasher, count = row["path"], hashlib.sha256(), 0
            source=row.get("source",{})
            git_hasher=(hashlib.sha1(b"blob "+str(row["size_bytes"]).encode("ascii")+b"\0")
                        if source.get("kind") in {"git_blob","deidentified_git_blob"} else None)
            target = None if stage is None or not row["install"] else Path(stage) / name
            if target is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
            with ExitStack() as stack:
                stream = stack.enter_context(archive.open(headers[name]))
                writer = stack.enter_context(target.open("xb")) if target is not None else None
                for block in iter(lambda: stream.read(CHUNK), b""):
                    count += len(block)
                    require(count <= row["size_bytes"], "Expanded member exceeds expected bytes: " + name)
                    hasher.update(block)
                    if git_hasher is not None:git_hasher.update(block)
                    if writer is not None:
                        writer.write(block)
            require(count == row["size_bytes"] and hasher.hexdigest() == row["sha256"], "Member SHA-256 differs: " + name)
            if git_hasher is not None:
                require(git_hasher.hexdigest()==source["oid"],"Published Git blob identity differs: "+name)
            if target is not None:
                staged[name] = target
    return staged


class _ReleaseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urllib.parse.urlsplit(newurl)
        require(url.scheme == "https" and url.hostname in {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
                and url.port in {None, 443} and url.username is None and url.password is None, "Unsafe release download redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(contract, target, *, opener=None):
    # validate_manifest has already pinned the exact initial URL. Never accept a
    # caller-supplied arbitrary file/http endpoint, including in an API call.
    require(any(contract.get("url") == _expected_url(group, contract.get("asset")) for group in GROUPS
                if contract.get("asset") == (PID_ASSET if group == "pid" else "research_" + group + "_v0.10.1.zip")),
            "Download URL is outside fixed project releases")
    opener = urllib.request.build_opener(_ReleaseRedirects()) if opener is None else opener
    started, count = time.monotonic(), 0
    request = urllib.request.Request(contract["url"], headers={"User-Agent": "jev-tune-research-data/0.10.1"})
    with opener.open(request, timeout=HTTP_TIMEOUT) as response, Path(target).open("xb") as output:
        final = urllib.parse.urlsplit(response.geturl())
        require(final.scheme == "https" and final.hostname in {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
                and final.port in {None, 443} and final.username is None and final.password is None, "Unsafe final download URL")
        length = response.headers.get("Content-Length")
        require(length is None or int(length) == contract["size_bytes"], "HTTP Content-Length differs")
        for block in iter(lambda: response.read(CHUNK), b""):
            count += len(block)
            require(count <= contract["size_bytes"] and time.monotonic() - started <= DOWNLOAD_DEADLINE, "Download byte/time limit exceeded")
            output.write(block)
    require(count == contract["size_bytes"], "Incomplete download")
    require(digest(target) == contract["sha256"], "Downloaded ZIP SHA-256 differs")


def fetch(root=ROOT, manifest=None, groups="all", from_dir=None):
    root = Path(root).resolve()
    manifest = load_manifest(root) if manifest is None else validate_manifest(manifest)
    selected = _select(manifest, groups)
    before = check(root, manifest, selected)
    require(not before["conflicts"], "Refuse to overwrite conflicting data: " + ", ".join(before["conflicts"]))
    missing = set(before["missing"])
    installed, downloaded, created_dirs = [], [], []
    with tempfile.TemporaryDirectory(prefix=".jev-research-data-", dir=root) as temporary:
        stage, staged = Path(temporary), {}
        for group in selected:
            contract = manifest["groups"][group]
            if not any(row["path"] in missing for row in contract["files"] if row["install"]):
                continue
            if from_dir is None:
                archive = stage / contract["asset"]
                download(contract, archive)
                downloaded.append(contract["asset"])
            else:
                archive = Path(from_dir).resolve() / contract["asset"]
            staged.update(verify_archive(archive, contract, stage / ("verified_" + group)))
        # No dataset has been written until every required archive and member
        # from every selected group has passed the complete byte contract.
        try:
            for group in selected:
                for row in manifest["groups"][group]["files"]:
                    if not row["install"] or row["path"] not in missing:
                        continue
                    target = destination(root, row["path"])
                    parents = []
                    parent = target.parent
                    while parent != root and not parent.exists():
                        parents.append(parent)
                        parent = parent.parent
                    for parent in reversed(parents):
                        parent.mkdir()
                        created_dirs.append(parent)
                    target = destination(root, row["path"])
                    if target.exists():
                        require(_identity(target, row), "Destination changed during restore: " + row["path"])
                        continue
                    # Same-filesystem hard-link publication is atomic and
                    # refuses existing destinations on both Windows and POSIX.
                    os.link(staged[row["path"]], target)
                    installed.append((row["path"], target, staged[row["path"]]))
            after = check(root, manifest, selected)
            require(after["ok"], "Restored data did not pass its complete final check")
        except BaseException:
            for name, target, original in reversed(installed):
                if target.exists() and not _is_link(target) and os.path.samefile(target, original):
                    target.unlink()
            for directory in reversed(created_dirs):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            raise
    return {"ok": True, "operation": "fetch", "groups": selected,
            "installed_files": [row[0] for row in installed], "already_present_files": before["present_files"],
            "downloaded_archives": downloaded, "offline": from_dir is not None,
            "objective_evaluations": 0, "gradient_steps": 0}


def _git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


def _ignored_output(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    require(output.is_relative_to(root) and output != root, "Package output must be inside the repository's ignored area")
    name = (output / "distribution-probe.tmp").relative_to(root).as_posix()
    result = subprocess.run(["git", "check-ignore", "-q", "--", name], cwd=root, capture_output=True)
    require(result.returncode == 0, "Package output is not ignored: " + str(output))
    output.mkdir(parents=True, exist_ok=True)
    require(not _is_link(output), "Package output may not be a link")
    return output


def _row(name, data, install, source):
    return {"path": safe_path(name), "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "install": install, "source": source}


def _write_zip(target, rows, providers):
    require(not Path(target).exists(), "Refuse to overwrite package: " + str(target))
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_STORED) as archive:
        for row in sorted(rows, key=lambda item: item["path"]):
            info = zipfile.ZipInfo(row["path"], date_time=STAMP)
            info.create_system, info.external_attr = 3, 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED if target.name == "research_evidence_v0.10.1.zip" else zipfile.ZIP_STORED
            with archive.open(info, "w", force_zip64=True) as writer:
                provider = providers[row["path"]]
                with provider() as stream:
                    shutil.copyfileobj(stream, writer, CHUNK)


def build_manifest(root, output_dir, *, revision="HEAD", pid_archive=None, from_dir=None):
    """Build real deterministic ZIPs; caller freezes the returned external JSON.

    Research members are exact committed Git blob bytes. Optional PID members
    come from the immutable, already released v0.10.0 ZIP and calibration pins.
    No manifest is written, no data is modified, and no network is contacted.
    """
    import io
    root = Path(root).resolve()
    # A cleaned tree cannot rediscover the removed dataset roster from Git.
    # Preserve the frozen external contract, including original OIDs strictly
    # as archived provenance, and reconstruct only the pinned existing bytes.
    if (root / MANIFEST).is_file():
        frozen = load_manifest(root)
        if frozen.get("history_cleaned") is True:
            package(output_dir, root, frozen, from_dir=from_dir)
            return frozen
    output = _ignored_output(root, output_dir)
    revision = _git(root, "rev-parse", revision + "^{commit}").decode().strip()
    tree = _git(root, "ls-tree", "-rz", "--full-tree", revision, "--", "research").split(b"\0")
    groups, providers = {"current": [], "historical": [], "evidence": []}, {}
    for entry in tree:
        if not entry:
            continue
        header, encoded = entry.split(b"\t", 1)
        mode, kind, oid = header.decode().split()
        name = encoded.decode("utf-8")
        raw = PurePosixPath(name).suffix in {".gz", ".npz"}
        if not raw and not name.startswith("research/results/"):
            continue
        require(mode in {"100644", "100755"} and kind == "blob", "Nonregular committed research data: " + name)
        if not raw:
            # EOL-sensitive machine evidence is distributed as the committed
            # blob, never silently rewritten by a platform's checkout filters.
            data = _git(root, "cat-file", "blob", oid)
            groups["evidence"].append(_row(name, data, True, {"kind": "git_blob", "revision": revision, "oid": oid}))
            providers[name] = lambda oid=oid: io.BytesIO(_git(root, "cat-file", "blob", oid))
            continue
        target = destination(root, name)
        require(target.is_file(), "Committed research data missing locally: " + name)
        # Git's blob identity checks all raw bytes without a second 464 MB
        # subprocess capture; source provenance remains bound to the tree OID.
        blob_hash = hashlib.sha1()
        size = target.stat().st_size
        blob_hash.update(b"blob " + str(size).encode("ascii") + b"\0")
        sha256 = hashlib.sha256()
        with target.open("rb") as stream:
            for block in iter(lambda: stream.read(CHUNK), b""):
                blob_hash.update(block)
                sha256.update(block)
        require(blob_hash.hexdigest() == oid, "Working research bytes differ from committed blob: " + name)
        group = "current" if name.startswith(("research/results/nonpid_transfer/", "research/results/calibration_runtime_sources/")) else "historical"
        groups[group].append({"path": name, "size_bytes": size, "sha256": sha256.hexdigest(), "install": True,
                              "source": {"kind": "git_blob", "revision": revision, "oid": oid}})
        providers[name] = lambda target=target: target.open("rb")
    licenses = []
    for name in ("LICENSE", "NOTICE.md"):
        data = _git(root, "show", revision + ":" + name)
        oid = _git(root, "rev-parse", revision + ":" + name).decode().strip()
        licenses.append(_row(name, data, False, {"kind": "git_blob", "revision": revision, "oid": oid}))
        providers[name] = lambda data=data: io.BytesIO(data)
    manifest = {"schema_version": 1, "version": VERSION, "repository": REPOSITORY, "history_cleaned": False,
                "source_revision": revision, "hash_scope": "exact_bytes", "groups": {}}
    for group, rows in groups.items():
        if not rows:
            continue
        rows = sorted(rows + licenses, key=lambda item: item["path"])
        asset = "research_" + group + "_v0.10.1.zip"
        target = output / asset
        _write_zip(target, rows, providers)
        contract = {"asset": asset, "url": _expected_url(group, asset), "size_bytes": target.stat().st_size,
                    "sha256": digest(target), "files": rows}
        verify_archive(target, contract)
        manifest["groups"][group] = contract
    if pid_archive is not None:
        archive_path = Path(pid_archive).resolve()
        require(archive_path.stat().st_size == PID_SIZE and digest(archive_path) == PID_SHA256, "Original v0.10.0 PID release ZIP identity differs")
        calibration = read_json((root / "models/calibration.json").read_bytes())["artifacts"]
        pins = {"data/expert_train.npz": calibration["training_data_sha256"]}
        pins.update({entry["path"].replace("\\", "/"): entry["sha256"] for entry in calibration["calibration_data_files"].values()})
        require(set(pins) == PID_PATHS, "Four calibration PID pins required")
        rows = []
        with zipfile.ZipFile(archive_path) as archive:
            require(set(archive.namelist()) == PID_PATHS | {"LICENSE", "NOTICE.md", PID_INVENTORY}, "Original PID release members differ")
            for info in archive.infolist():
                data = archive.read(info)
                row = _row(info.filename, data, info.filename in PID_PATHS,
                           {"kind": "pinned_pid_release", "release": "v0.10.0", "archive_sha256": PID_SHA256})
                if row["install"]:
                    require(row["sha256"] == pins[row["path"]], "PID calibration pin differs")
                rows.append(row)
        contract = {"asset": PID_ASSET, "url": _expected_url("pid", PID_ASSET), "size_bytes": PID_SIZE,
                    "sha256": PID_SHA256, "files": sorted(rows, key=lambda item: item["path"])}
        verify_archive(archive_path, contract)
        target = output / PID_ASSET
        require(not target.exists(), "Refuse to overwrite PID release copy")
        shutil.copyfile(archive_path, target)
        require(digest(target) == PID_SHA256, "PID release copy changed")
        manifest["groups"]["pid"] = contract
    return validate_manifest(manifest)


def package(output_dir, root=ROOT, manifest=None, groups="all", from_dir=None):
    """Repackage only bytes matching the already frozen external contract."""
    import io
    root = Path(root).resolve()
    manifest = load_manifest(root) if manifest is None else validate_manifest(manifest)
    selected, results = _select(manifest, groups), []
    output = _ignored_output(root, output_dir)
    for group in selected:
        contract = manifest["groups"][group]
        target = output / contract["asset"]
        if target.exists():
            verify_archive(target, contract)
            results.append(str(target))
            continue
        with tempfile.TemporaryDirectory(prefix=".package-stage-", dir=output) as temporary:
            staged = Path(temporary) / contract["asset"]
            if group == "pid":
                require(from_dir is not None, "PID packaging must reuse --from-dir original release ZIP")
                source = Path(from_dir).resolve() / contract["asset"]
                verify_archive(source, contract)
                shutil.copyfile(source, staged)
            else:
                # All installable members must have been restored first.
                # Original source_revision/OIDs are archival provenance and
                # never a requirement to retain old data blobs in Git.
                with ExitStack() as stack:
                    providers, metadata_archive = {}, None
                    for row in contract["files"]:
                        path = destination(root, row["path"])
                        if _identity(path, row):
                            providers[row["path"]] = lambda path=path: path.open("rb")
                        elif row["install"]:
                            raise ValueError("Package source missing/changed: " + row["path"] + "; restore with 59_research_data.py --fetch " + group)
                        else:
                            require(from_dir is not None, "Pinned original LICENSE/NOTICE bytes require --from-dir release ZIPs")
                            if metadata_archive is None:
                                original = Path(from_dir).resolve() / contract["asset"]
                                verify_archive(original, contract)
                                metadata_archive = stack.enter_context(zipfile.ZipFile(original))
                            providers[row["path"]] = lambda name=row["path"], archive=metadata_archive: archive.open(name)
                    _write_zip(staged, contract["files"], providers)
            verify_archive(staged, contract)
            os.link(staged, target)
            results.append(str(target))
    return {"ok": True, "operation": "package", "groups": selected, "archives": results,
            "objective_evaluations": 0, "gradient_steps": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument("--check", nargs="?", const="all", metavar="GROUP")
    flags.add_argument("--fetch", nargs="?", const="all", metavar="GROUP")
    flags.add_argument("--package", type=Path, metavar="IGNORED_OUTPUT_DIR")
    parser.add_argument("--group", default="all", help="current/historical/evidence/pid/all for --package; default all")
    parser.add_argument("--from-dir", type=Path, help="Offline directory containing exact release ZIP filenames")
    args = parser.parse_args()
    operation = "check" if args.check else "fetch" if args.fetch else "package"
    try:
        if args.check:
            result = check(args.root, groups=args.check)
        elif args.fetch:
            result = fetch(args.root, groups=args.fetch, from_dir=args.from_dir)
        else:
            result = package(args.package, args.root, groups=args.group, from_dir=args.from_dir)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as exc:
        result = {"ok": False, "operation": operation, "error": str(exc), "objective_evaluations": 0, "gradient_steps": 0}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
