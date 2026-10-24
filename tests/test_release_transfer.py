"""Release packaging must reject prose, registry and input-evidence mutations."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('transfer_release_test', ROOT/'scripts/47_release_transfer.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.mark.parametrize('changed', ['README.md', 'docs/claims.json', 'research/results/latency.json'])
def test_package_rejects_changes_after_fresh_claims(tmp_path, monkeypatch, changed):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    for name in ('README.md', 'docs/claims.json', 'research/results/latency.json'):
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}\n', encoding='utf-8')
    monkeypatch.setattr(release, 'ROOT', tmp_path)
    monkeypatch.setattr(release, 'historical', lambda: SimpleNamespace(
        check_preserved=lambda: True,
        digest=lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()))
    monkeypatch.setattr(release, 'execution', lambda: ({}, {}, 83.))
    fixed = release.sources()
    assert {changed, 'README.md', 'docs/claims.json', 'research/results/latency.json'} <= set(fixed)
    payload = {'version':'0.10.0','ok':True,'framework_verified':True,'pytest_execution':{},
               'fresh_claims_execution':{'source_hashes':fixed}}
    (tmp_path/release.REPORT).write_text(json.dumps(payload), encoding='utf-8')
    (tmp_path/changed).write_text('changed after verification\n', encoding='utf-8')
    with pytest.raises(AssertionError):
        release.package()


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_primary_artifact_accepts_normalized_line_endings(tmp_path, monkeypatch, newline):
    canonical = b'{\n  "value": 12.5\n}\n'
    path = tmp_path / "model.json"
    path.write_bytes(canonical.replace(b"\n", newline))
    monkeypatch.setattr(release, "ROOT", tmp_path)
    expected = hashlib.sha256(canonical).hexdigest()
    release.verify_primary_artifact("model.json", expected)
    # Exact-byte release evidence deliberately distinguishes CRLF from LF.
    assert release.digest("model.json") == hashlib.sha256(path.read_bytes()).hexdigest()
    if newline == b"\r\n":
        assert release.digest("model.json") != expected


def test_primary_artifact_rejects_numeric_mutation(tmp_path, monkeypatch):
    canonical = b'{\n  "value": 12.5\n}\n'
    path = tmp_path / "model.json"
    path.write_bytes(canonical.replace(b"12.5", b"12.6").replace(b"\n", b"\r\n"))
    monkeypatch.setattr(release, "ROOT", tmp_path)
    with pytest.raises(AssertionError, match="Primary artifact changed"):
        release.verify_primary_artifact("model.json", hashlib.sha256(canonical).hexdigest())


def test_package_rejects_line_ending_change_even_when_sources_match(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    artifact = "research/results/model.json"
    path = tmp_path / artifact
    path.parent.mkdir(parents=True)
    canonical = b'{\n  "value": 12.5\n}\n'
    path.write_bytes(canonical)
    # Keep the real historical normalization and all production comparison
    # functions. Only preservation and pytest execution are unrelated here.
    history = release.historical()
    monkeypatch.setattr(history, "check_preserved", lambda: True)
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "historical", lambda: history)
    monkeypatch.setattr(release, "execution", lambda: ({}, {}, 83.))
    fixed = release.sources()
    payload = {
        "version": "0.10.0", "ok": True, "framework_verified": True,
        "pytest_execution": {}, "fresh_claims_execution": {"source_hashes": fixed},
        "evidence_hashes": {artifact: release.digest(artifact)}, "logs": {},
    }
    (tmp_path / release.REPORT).write_text(json.dumps(payload), encoding="utf-8")
    path.write_bytes(canonical.replace(b"\n", b"\r\n"))
    assert release.sources() == fixed
    with pytest.raises(AssertionError, match="Release evidence changed: " + artifact):
        release.package()
