"""Small real ZIP/Git fixtures; no experiment data or ML dependencies."""
from __future__ import annotations
import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/59_research_data.py"
spec = importlib.util.spec_from_file_location("research_data_test", SCRIPT)
data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


def regular(archive, name, payload, mode=stat.S_IFREG | 0o644):
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = mode << 16
    archive.writestr(info, payload)


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "Research data fixture")
    paths = {
        ".gitignore": b".local-audit/\n",
        "LICENSE": b"fixture license\n",
        "NOTICE.md": b"fixture notice\n",
        "models/keep.json": b'{"formal_weight":"not_optional"}\n',
        "research/results/nonpid_transfer/raw.json.gz": gzip.compress(b'{"original":"current"}', mtime=0),
        "research/results/trajectory_risk_raw/train.json.gz": gzip.compress(b'{"original":"historical"}', mtime=0),
        "research/results/primary.json": b'{"result":"negative_stop"}\n',
        "research/results/preserved.log": b"Original benchmark path C:/motor-valve benchmark/model.slx is log text, not a model payload.\n",
    }
    for name, payload in paths.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    git(root, "add", ".")
    git(root, "commit", "-qm", "Small original-byte research fixture")
    packages = root / ".local-audit/packages"
    manifest = data.build_manifest(root, packages)
    target = root / data.MANIFEST
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(manifest), encoding="utf-8")
    return root, manifest, packages, paths


def installed_rows(manifest):
    return [row for group in manifest["groups"].values() for row in group["files"] if row["install"]]


def remove_optional(root, manifest):
    for row in installed_rows(manifest):
        (root / row["path"]).unlink()


def rewrite_archive(packages, manifest, group, transform):
    contract = manifest["groups"][group]
    target = packages / contract["asset"]
    with zipfile.ZipFile(target) as archive:
        entries = [(info.filename, archive.read(info), info.external_attr >> 16) for info in archive.infolist()]
    entries = transform(entries)
    with zipfile.ZipFile(target, "w") as archive:
        for name, payload, mode in entries:
            regular(archive, name, payload, mode)
    contract["size_bytes"] = target.stat().st_size
    contract["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()


def test_real_git_provenance_groups_compression_and_no_model_capture(repository):
    root, manifest, packages, original = repository
    assert set(manifest["groups"]) == {"historical", "current", "evidence"}
    expected = {name for name in original if name.startswith("research/results/")}
    assert {row["path"] for row in installed_rows(manifest)} == expected
    assert not any(row["path"].startswith("models/") for row in installed_rows(manifest))
    for group, contract in manifest["groups"].items():
        with zipfile.ZipFile(packages / contract["asset"]) as archive:
            assert set(archive.namelist()) == {row["path"] for row in contract["files"]}
            assert all(info.compress_type == (zipfile.ZIP_DEFLATED if group == "evidence" else zipfile.ZIP_STORED)
                       for info in archive.infolist())
            for row in contract["files"]:
                assert archive.read(row["path"]) == git(root, "show", manifest["source_revision"] + ":" + row["path"])
                assert row["source"]["oid"] == git(root, "rev-parse", manifest["source_revision"] + ":" + row["path"]).decode().strip()
    assert data.check(root)["ok"]


def test_all_groups_restore_original_paths_idempotently_without_replacing_notice(repository):
    root, manifest, packages, original = repository
    remove_optional(root, manifest)
    (root / "NOTICE.md").write_bytes(b"Newer local notice must not be replaced")
    assert set(data.check(root)["missing"]) == {row["path"] for row in installed_rows(manifest)}
    restored = data.fetch(root, from_dir=packages)
    assert restored["ok"] and restored["offline"] and len(restored["installed_files"]) == 4
    assert data.check(root)["ok"]
    for name in restored["installed_files"]:
        assert (root / name).read_bytes() == original[name]
    assert (root / "NOTICE.md").read_bytes() == b"Newer local notice must not be replaced"
    assert not (root / "research/results/open_source_inventory_v0100.json").exists()
    repeated = data.fetch(root, from_dir=root / "nonexistent-package-dir")
    assert repeated["installed_files"] == [] and len(repeated["already_present_files"]) == 4
    assert repeated["downloaded_archives"] == []
    assert not list(root.glob(".jev-research-data-*"))


def test_group_selection_preserves_unselected_missing_data(repository):
    root, manifest, packages, original = repository
    remove_optional(root, manifest)
    result = data.fetch(root, groups="current", from_dir=packages)
    assert result["installed_files"] == ["research/results/nonpid_transfer/raw.json.gz"]
    assert data.check(root, groups="current")["ok"]
    assert not data.check(root)["ok"]
    assert not (root / "research/results/primary.json").exists()


def test_wrong_whole_zip_and_member_hash_never_publish_earlier_group(repository):
    root, manifest, packages, original = repository
    remove_optional(root, manifest)
    bad = copy.deepcopy(manifest)
    bad["groups"]["historical"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Whole ZIP"):
        data.fetch(root, bad, from_dir=packages)
    assert all(not (root / row["path"]).exists() for row in installed_rows(manifest))
    bad = copy.deepcopy(manifest)
    next(row for row in bad["groups"]["historical"]["files"] if row["install"])["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Member SHA-256"):
        data.fetch(root, bad, from_dir=packages)
    assert all(not (root / row["path"]).exists() for row in installed_rows(manifest))


@pytest.mark.parametrize("name", ["../escape.gz", "/absolute.gz", "C:/drive.gz", "x\\evil.gz", ".git/config", "x/../evil.gz", "a/NUL.txt", "a/file:ads"])
def test_zip_path_attacks_are_rejected_after_whole_zip_hash_matches(repository, name):
    root, manifest, packages, original = repository
    remove_optional(root, manifest)
    rewrite_archive(packages, manifest, "current", lambda rows: rows + [(name, b"attack", stat.S_IFREG | 0o644)])
    with pytest.raises(ValueError, match="path|Traversal|Reserved|Unknown"):
        data.fetch(root, manifest, from_dir=packages)
    assert all(not (root / row["path"]).exists() for row in installed_rows(manifest))
    assert not (root.parent / "escape.gz").exists()


@pytest.mark.parametrize("mode", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFDIR])
def test_nonregular_archive_members_are_rejected(repository, mode):
    root, manifest, packages, original = repository
    remove_optional(root, manifest)
    rewrite_archive(packages, manifest, "current", lambda rows: [(n, p, mode | 0o644) for n, p, _ in rows])
    with pytest.raises(ValueError, match="symlink/FIFO/socket/device/directory"):
        data.fetch(root, manifest, from_dir=packages)
    assert all(not (root / row["path"]).exists() for row in installed_rows(manifest))


@pytest.mark.parametrize("change", ["duplicate", "case", "unknown", "missing"])
def test_duplicate_case_unknown_and_missing_members(repository, change):
    root, manifest, packages, original = repository
    remove_optional(root, manifest)
    def alter(rows):
        if change == "missing":
            return rows[:-1]
        name, payload, mode = rows[-1]
        if change == "case":
            name = name.upper()
        elif change == "unknown":
            name = "models/unregistered.pt"
        return rows + [(name, payload, mode)]
    with pytest.warns(UserWarning, match="Duplicate name") if change == "duplicate" else _no_warning_context():
        rewrite_archive(packages, manifest, "current", alter)
    with pytest.raises(ValueError, match="Duplicate|colliding|Unknown|Missing"):
        data.fetch(root, manifest, from_dir=packages)
    assert not (root / "models/unregistered.pt").exists()


def _no_warning_context():
    from contextlib import nullcontext
    return nullcontext()


def test_existing_conflict_is_not_overwritten_or_hidden(repository, monkeypatch):
    root, manifest, packages, original = repository
    name = "research/results/primary.json"
    (root / name).write_bytes(b"User's modified evidence")
    monkeypatch.setattr(data, "download", lambda *args, **kwargs: pytest.fail("Conflict must precede download"))
    assert data.check(root)["conflicts"] == [name]
    with pytest.raises(ValueError, match="Refuse to overwrite"):
        data.fetch(root)
    assert (root / name).read_bytes() == b"User's modified evidence"


def test_atomic_publish_failure_rolls_back_only_new_data(repository, monkeypatch):
    root, manifest, packages, original = repository
    remove_optional(root, manifest)
    real_link, calls = data.os.link, []
    def failing_link(source, target):
        calls.append(str(target))
        if len(calls) == 2:
            raise OSError("simulated publication failure")
        return real_link(source, target)
    monkeypatch.setattr(data.os, "link", failing_link)
    with pytest.raises(OSError, match="publication failure"):
        data.fetch(root, from_dir=packages)
    assert len(calls) == 2
    assert all(not (root / row["path"]).exists() for row in installed_rows(manifest))
    assert (root / "models/keep.json").read_bytes() == original["models/keep.json"]
    assert not list(root.glob(".jev-research-data-*"))


def test_network_failure_and_missing_offline_archive_are_not_partial_success(repository, monkeypatch):
    root, manifest, packages, original = repository
    remove_optional(root, manifest)
    class FailedOpener:
        def open(self, request, timeout):
            raise ConnectionError("actual transport failure fixture")
    opener = FailedOpener()
    monkeypatch.setattr(data.urllib.request, "build_opener", lambda *args: opener)
    with pytest.raises(ConnectionError, match="transport failure"):
        data.fetch(root)
    assert all(not (root / row["path"]).exists() for row in installed_rows(manifest))
    with pytest.raises(ValueError, match="Missing/nonregular archive"):
        data.fetch(root, from_dir=root / "missing-offline-archives")
    assert not list(root.glob(".jev-research-data-*"))


def test_network_urls_and_response_limits_are_restricted(repository, tmp_path):
    root, manifest, packages, original = repository
    contract = manifest["groups"]["current"]
    class Response(io.BytesIO):
        headers = {}
        def geturl(self):
            return contract["url"]
    class Opener:
        def __init__(self, payload):
            self.payload, self.calls = payload, 0
        def open(self, request, timeout):
            assert request.full_url == contract["url"] and timeout == data.HTTP_TIMEOUT
            self.calls += 1
            return Response(self.payload)
    payload = (packages / contract["asset"]).read_bytes()
    for index, bad in enumerate((payload[:-1], payload + b"extra")):
        with pytest.raises(ValueError, match="Incomplete|byte/time limit"):
            data.download(contract, tmp_path / str(index), opener=Opener(bad))
    opener = Opener(payload)
    bad = {**contract, "url": "file:///private/file"}
    with pytest.raises(ValueError, match="outside fixed"):
        data.download(bad, tmp_path / "never", opener=opener)
    assert opener.calls == 0
    with pytest.raises(ValueError, match="Unsafe release download redirect"):
        data._ReleaseRedirects().redirect_request(None, None, 302, "redirect", {}, "https://untrusted.invalid/payload")


def test_repackage_is_exact_and_output_must_be_ignored(repository):
    root, manifest, packages, original = repository
    result = data.package(root / ".local-audit/repackaged", root)
    assert result["ok"]
    for path in result["archives"]:
        path = Path(path)
        assert path.read_bytes() == (packages / path.name).read_bytes()
    with pytest.raises(ValueError, match="not ignored"):
        data.package(root / "public_packages", root)
    bad = copy.deepcopy(manifest)
    bad["groups"]["current"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Whole ZIP"):
        data.package(root / ".local-audit/repackaged", root, bad)


def test_source_blob_mutation_rejected_by_builder(repository):
    root, manifest, packages, original = repository
    (root / "research/results/nonpid_transfer/raw.json.gz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="differ from committed blob"):
        data.build_manifest(root, root / ".local-audit/new-build")


def test_pinned_pid_reuse_restores_all_four_without_runtime_inventory(repository, monkeypatch):
    root, manifest, packages, original = repository
    source = root / ".local-audit/original-pid"
    source.mkdir()
    payloads = {name: ("independent tiny PID file: " + name).encode() for name in sorted(data.PID_PATHS)}
    pins = {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()}
    calibration = {"artifacts": {"training_data_sha256": pins["data/expert_train.npz"], "calibration_data_files": {
        Path(name).stem: {"path": name, "sha256": digest} for name, digest in pins.items() if name != "data/expert_train.npz"}}}
    (root / "models/calibration.json").write_text(json.dumps(calibration), encoding="utf-8")
    pid = source / data.PID_ASSET
    with zipfile.ZipFile(pid, "w") as archive:
        for name, payload in payloads.items():
            regular(archive, name, payload)
        regular(archive, "LICENSE", b"old release license")
        regular(archive, "NOTICE.md", b"old release notice")
        regular(archive, data.PID_INVENTORY, b'{"old_inventory":"metadata only"}')
    monkeypatch.setattr(data, "PID_SIZE", pid.stat().st_size)
    monkeypatch.setattr(data, "PID_SHA256", hashlib.sha256(pid.read_bytes()).hexdigest())
    output = root / ".local-audit/all-four-groups"
    combined = data.build_manifest(root, output, pid_archive=pid)
    assert set(combined["groups"]) == {"current", "historical", "evidence", "pid"}
    assert (output / data.PID_ASSET).read_bytes() == pid.read_bytes()
    # Neither the old inventory nor calibration metadata is a runtime input.
    (root / "models/calibration.json").unlink()
    assert not (root / data.PID_INVENTORY).exists()
    remove_optional(root, manifest)
    result = data.fetch(root, combined, from_dir=output)
    assert set(data.PID_PATHS) <= set(result["installed_files"])
    assert data.check(root, combined)["ok"]
    assert all((root / name).read_bytes() == payload for name, payload in payloads.items())
    assert not (root / data.PID_INVENTORY).exists()
    assert (root / "NOTICE.md").read_bytes() == original["NOTICE.md"]
    repackaged = data.package(root / ".local-audit/reused-pid", root, combined, groups="pid", from_dir=source)
    assert Path(repackaged["archives"][0]).read_bytes() == pid.read_bytes()


def test_pid_wrong_original_archive_is_rejected(repository, tmp_path):
    root, manifest, packages, original = repository
    bad = tmp_path / data.PID_ASSET
    bad.write_bytes(b"not the pinned old release archive")
    with pytest.raises(ValueError, match="PID release ZIP identity differs"):
        data.build_manifest(root, root / ".local-audit/wrong-pid", pid_archive=bad)


def test_cli_works_from_unrelated_cwd_with_only_manifest_and_stdlib(repository, tmp_path):
    root, manifest, packages, original = repository
    script = root / "scripts/59_research_data.py"
    script.parent.mkdir()
    shutil.copyfile(SCRIPT, script)
    elsewhere = tmp_path / "different-cwd"
    elsewhere.mkdir()
    remove_optional(root, manifest)
    command = [sys.executable, str(script)]
    missing = subprocess.run(command + ["--check"], cwd=elsewhere, capture_output=True, text=True)
    assert missing.returncode == 1 and json.loads(missing.stdout)["missing"]
    restored = subprocess.run(command + ["--fetch", "all", "--from-dir", str(packages)],
                              cwd=elsewhere, capture_output=True, text=True)
    assert restored.returncode == 0, restored.stderr + restored.stdout
    result = json.loads(restored.stdout)
    assert result["ok"] and set(result["groups"]) == {"current", "historical", "evidence"}
    checked = subprocess.run(command + ["--root", str(root), "--check", "evidence"],
                             cwd=elsewhere, capture_output=True, text=True)
    assert checked.returncode == 0 and json.loads(checked.stdout)["ok"]


@pytest.mark.parametrize("mutation", ["url", "group_path", "duplicate", "traversal", "unknown_metadata"])
def test_invalid_manifest_is_rejected_before_io(repository, mutation):
    root, manifest, packages, original = repository
    bad = copy.deepcopy(manifest)
    group = bad["groups"]["current"]
    if mutation == "url":
        group["url"] = "https://github.com/another/repository/releases/download/v0.10.1/anything.zip"
    elif mutation == "group_path":
        next(row for row in group["files"] if row["install"])["path"] = "models/jev_head.pt"
    elif mutation == "duplicate":
        group["files"].append(copy.deepcopy(group["files"][-1]))
    elif mutation == "traversal":
        group["files"][0]["path"] = "../LICENSE"
    else:
        next(row for row in group["files"] if not row["install"])["path"] = "private.slx"
    with pytest.raises(ValueError):
        data.fetch(root, bad, from_dir=packages)
