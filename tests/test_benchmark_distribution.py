"""Tiny pinned ZIP fixtures exercise optional benchmark restore without MATLAB."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/65_restore_benchmark.py"
spec = importlib.util.spec_from_file_location("benchmark_distribution_test", SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def write_zip(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content, mode in entries:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)


@pytest.fixture
def package(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    packages = tmp_path / "packages"
    packages.mkdir()
    payload = {name: ("fixture bytes for " + name).encode() for name in sorted(benchmark.MEMBERS)}
    entries = [(name, content, stat.S_IFREG | 0o644) for name, content in payload.items()]
    archive = packages / benchmark.ASSET
    write_zip(archive, entries)
    manifest = {"schema_version": 1, "version": "0.10.1", "repository": "lijiawei255/jev-tune",
                "hash_scope": "exact_bytes", "archive": {
                    "asset": benchmark.ASSET, "url": benchmark.URL, "size_bytes": archive.stat().st_size,
                    "sha256": benchmark.data.digest(archive), "files": [
                        {"path": name, "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                         "install": True} for name, content in payload.items()]}}
    return root, packages, archive, manifest, payload, entries


def repin(archive, manifest):
    manifest["archive"].update(size_bytes=archive.stat().st_size, sha256=benchmark.data.digest(archive))


def test_offline_atomic_restore_exact_roster_and_idempotence(package, monkeypatch):
    root, packages, archive, manifest, payload, _ = package
    monkeypatch.setattr(benchmark, "_download", lambda *_: pytest.fail("Offline restore contacted network"))
    target = root / benchmark.DEFAULT_DESTINATION
    publish = benchmark._publish
    def checked_publish(stage, destination):
        assert not destination.exists()
        assert benchmark._installed(stage, manifest["archive"])
        publish(stage, destination)
    monkeypatch.setattr(benchmark, "_publish", checked_publish)
    result = benchmark.restore(root, from_dir=packages, manifest=manifest)
    assert result["ok"] and result["offline"] and len(result["installed_files"]) == 18
    for name, content in payload.items():
        assert (target / name.removeprefix(benchmark.PREFIX)).read_bytes() == content
    assert benchmark.check(root, manifest=manifest)["ok"]
    archive.unlink()
    repeated = benchmark.restore(root, from_dir=packages, manifest=manifest)
    assert repeated["installed_files"] == [] and repeated["already_present_files"] == 18
    assert not list(root.rglob(".jev-benchmark-*"))
    assert result["objective_evaluations"] == result["gradient_steps"] == 0


def test_explicit_destination_and_tracked_manifest_loading(package):
    root, packages, _, manifest, _, _ = package
    path = root / benchmark.MANIFEST
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    target = root.parent / "separate destination"
    assert benchmark.restore(root, destination=target, from_dir=packages)["ok"]
    assert (target / "jev_lab_model.slx").is_file()
    assert not (root / benchmark.DEFAULT_DESTINATION).exists()


@pytest.mark.parametrize("bad_hash", ["archive", "member"])
def test_wrong_archive_or_member_hash_never_installs(package, bad_hash):
    root, packages, _, manifest, _, _ = package
    bad = copy.deepcopy(manifest)
    if bad_hash == "archive":
        bad["archive"]["sha256"] = "0" * 64
    else:
        bad["archive"]["files"][-1]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        benchmark.restore(root, from_dir=packages, manifest=bad)
    assert not (root / "benchmarks").exists()
    assert not list(root.glob(".jev-benchmark-*"))


@pytest.mark.parametrize("attack", ["traversal", "absolute", "symlink", "duplicate", "case", "missing", "unknown"])
def test_untrusted_headers_rejected_even_with_matching_whole_zip_hash(package, attack):
    root, packages, archive, manifest, payload, entries = package
    name, content, mode = entries[-1]
    if attack == "traversal":
        entries[-1] = ("../escaped.mat", content, mode)
    elif attack == "absolute":
        entries[-1] = ("C:/Users/private/model.slx", content, mode)
    elif attack == "symlink":
        entries[-1] = (name, content, stat.S_IFLNK | 0o777)
    elif attack == "duplicate":
        entries.append(entries[-1])
    elif attack == "case":
        entries.append((name.upper(), content, mode))
    elif attack == "missing":
        entries.pop()
    elif attack == "unknown":
        entries[-1] = (benchmark.PREFIX + "unexpected.mat", content, mode)
    with pytest.warns(UserWarning, match="Duplicate name") if attack == "duplicate" else _no_warning_context():
        write_zip(archive, entries)
    repin(archive, manifest)
    with pytest.raises(ValueError, match="path|Traversal|Unknown|Missing|Duplicate|symlink"):
        benchmark.restore(root, from_dir=packages, manifest=manifest)
    assert not (root / "benchmarks").exists()
    assert not (root.parent / "escaped.mat").exists()


def _no_warning_context():
    from contextlib import nullcontext
    return nullcontext()


@pytest.mark.parametrize("conflict", ["changed_file", "extra_file", "missing_file", "empty_dir"])
def test_existing_conflicts_are_not_overwritten_or_repaired(package, conflict):
    root, packages, _, manifest, _, _ = package
    benchmark.restore(root, from_dir=packages, manifest=manifest)
    target = root / benchmark.DEFAULT_DESTINATION
    model = target / "jev_lab_model.slx"
    if conflict == "changed_file":
        model.write_bytes(b"user model")
    elif conflict == "extra_file":
        (target / "user.txt").write_bytes(b"keep")
    elif conflict == "missing_file":
        model.unlink()
    else:
        (target / "user-directory").mkdir()
    before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="conflict|extra directories"):
        benchmark.restore(root, from_dir=packages, manifest=manifest)
    assert before == {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    if conflict == "empty_dir":
        assert (target / "user-directory").is_dir()


def test_destination_symlink_or_reparse_is_rejected(package, monkeypatch):
    root, packages, _, manifest, _, _ = package
    actual_is_link = benchmark.data._is_link
    # Reparse detection must run before Path.resolve could erase this component.
    forbidden = root / "benchmarks"
    monkeypatch.setattr(benchmark.data, "_is_link", lambda p: Path(p) == forbidden or actual_is_link(p))
    with pytest.raises(ValueError, match="Symlink/reparse"):
        benchmark.restore(root, from_dir=packages, manifest=manifest)
    assert not forbidden.exists()


@pytest.mark.parametrize("with_user_file", [False, True])
def test_publication_race_does_not_overwrite_user_directory(package, monkeypatch, with_user_file):
    root, packages, _, manifest, _, _ = package
    publish = benchmark._publish
    def concurrent_writer(stage, destination):
        destination.mkdir()
        if with_user_file:
            (destination / "user.txt").write_bytes(b"created during restore")
        publish(stage, destination)
    monkeypatch.setattr(benchmark, "_publish", concurrent_writer)
    with pytest.raises(OSError):
        benchmark.restore(root, from_dir=packages, manifest=manifest)
    target = root / benchmark.DEFAULT_DESTINATION
    assert target.is_dir()
    if with_user_file:
        assert (target / "user.txt").read_bytes() == b"created during restore"
    assert not (target / "jev_lab_model.slx").exists()
    assert not list(root.rglob(".jev-benchmark-*"))


def test_manifest_pins_exact_roster_and_project_url(package):
    _, _, _, manifest, _, _ = package
    for mutation in [lambda m: m["archive"].update(url="https://example.invalid/data.zip"),
                     lambda m: m["archive"]["files"].pop(),
                     lambda m: m["archive"]["files"][0].update(path="../escape")]:
        bad = copy.deepcopy(manifest)
        mutation(bad)
        with pytest.raises(ValueError):
            benchmark.validate_manifest(bad)


def test_committed_manifest_has_the_real_pinned_asset():
    manifest = benchmark.load_manifest()
    contract = manifest["archive"]
    assert contract["sha256"] == "7d82dcefee629af3981bf8304e7ceb27dfcab9e4b225a4340da749aa250fc103"
    assert contract["size_bytes"] == 2667111 and len(contract["files"]) == 18
    assert {row["path"] for row in contract["files"]} == benchmark.MEMBERS
