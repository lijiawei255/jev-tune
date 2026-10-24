"""Exercise real Git history and ignore rules, including add-then-remove data."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('payload_guard', ROOT/'scripts/63_check_git_payload.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def command(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.STDOUT)


def setup(tmp_path):
    command(tmp_path, 'init', '-q')
    command(tmp_path, 'config', 'user.name', 'Fixture')
    command(tmp_path, 'config', 'user.email', 'fixture@example.invalid')
    (tmp_path/'README.md').write_text('source\n')
    commit(tmp_path)
    return tmp_path


def commit(root):
    command(root, 'add', '.')
    command(root, 'commit', '-qm', 'fixture')


def test_small_source_history_passes(tmp_path):
    root = setup(tmp_path)
    result = guard.check(root)
    assert result['ok'] and result['commit_count'] == 1


def test_oversized_blob_removed_from_head_still_fails(tmp_path):
    root = setup(tmp_path)
    (root/'temporary.bin').write_bytes(b'x'*(guard.MAX_BLOB_BYTES+1))
    commit(root)
    command(root, 'rm', 'temporary.bin')
    command(root, 'commit', '-qm', 'remove temporary binary')
    with pytest.raises(ValueError, match='oversized_blobs'):
        guard.check(root)


def test_reused_small_blob_at_data_path_still_fails(tmp_path):
    root = setup(tmp_path)
    target = root/'research/results/report.json'
    target.parent.mkdir(parents=True)
    target.write_bytes((root/'README.md').read_bytes())
    commit(root)
    with pytest.raises(ValueError, match='report.json'):
        guard.check(root)


def test_old_tag_cannot_hide_forbidden_data(tmp_path):
    root = setup(tmp_path)
    target = root/'research/results/old.json'
    target.parent.mkdir(parents=True)
    target.write_text('{}')
    commit(root)
    command(root, 'tag', 'old-data')
    command(root, 'reset', '--hard', 'HEAD~1')
    with pytest.raises(ValueError, match='old.json'):
        guard.check(root)


def test_formal_nonpid_weights_are_allowed(tmp_path):
    root = setup(tmp_path)
    for name in guard.FORMAL_NONPID:
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"formal":true}')
    commit(root)
    assert guard.check(root)['ok']


def test_replace_refs_cannot_hide_real_large_history(tmp_path, monkeypatch):
    root = setup(tmp_path)
    clean = command(root, 'rev-parse', 'HEAD').decode().strip()
    monkeypatch.setattr(guard, 'MAX_BLOB_BYTES', 1000)
    (root/'temporary.bin').write_bytes(b'x'*1001)
    commit(root)
    dirty = command(root, 'rev-parse', 'HEAD').decode().strip()
    command(root, 'rm', 'temporary.bin')
    command(root, 'commit', '-qm', 'remove temporary binary')
    command(root, 'replace', dirty, clean)
    with pytest.raises(ValueError, match='oversized_blobs'):
        guard.check(root)


def test_project_ignore_rules_keep_only_formal_artifacts(tmp_path):
    setup(tmp_path)
    (tmp_path/'.gitignore').write_bytes((ROOT/'.gitignore').read_bytes())
    excluded = ['research/results/new.json', 'research/results/nonpid_transfer/raw.json.gz',
                'research/results/new_folder/data.npz', '.local-audit/receipt.json',
                'data/expert_train.npz', 'models/unbound.pt', 'models/specialized/head.pt']
    included = sorted(guard.FORMAL_NONPID) + ['src/jev_tune/primitives.py', 'scripts/59_research_data.py',
        'models/jev_head.pt', 'models/jev_head.onnx', 'models/jev_head_weights.mat',
        'models/meta.json', 'models/calibration.json', 'models/ablation_a0.pt', 'models/ablation_a0.manifest.json']
    for name in excluded + included:
        result = subprocess.run(['git', '-C', str(tmp_path), 'check-ignore', '--no-index', '--quiet', name])
        assert result.returncode == (0 if name in excluded else 1), name
