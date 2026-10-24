"""Full-check identity cannot be replaced by a nonempty subset of passing rows."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


spec = importlib.util.spec_from_file_location('claims_contract', Path(__file__).parents[1] / 'scripts/16_check_claims.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_contract_rejects_missing_extra_and_duplicate_checks():
    rows = [{'id': identifier} for identifier in module.expected_ids()]
    assert module.complete_roster(rows)
    assert not module.complete_roster(rows[:-1])
    assert not module.complete_roster(rows + [rows[0]])
    assert not module.complete_roster(rows + [{'id': 'invented:passing_check'}])


def test_duplicate_registry_fails_instead_of_deduplicating(tmp_path, monkeypatch):
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/claims.json').write_text(json.dumps({'claims': [{'id': 'same'}, {'id': 'same'}]}))
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='Duplicate'):
        module.expected_ids()


def test_list_ids_never_runs_an_audit(monkeypatch, capsys):
    def forbidden():
        raise AssertionError('Listing IDs must not execute experiments')
    monkeypatch.setattr(module, 'trajectory_evidence', forbidden)
    monkeypatch.setattr(module, 'transfer_shell_evidence', forbidden)
    monkeypatch.setattr(sys, 'argv', ['16_check_claims.py', '--list-ids'])
    assert module.main() == 0
    assert json.loads(capsys.readouterr().out) == module.expected_ids()


def test_light_archive_missing_evidence_is_an_explicit_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(sys, 'argv', ['16_check_claims.py', '--json'])
    assert module.main() == 2
    assert '59_research_data.py --fetch all' in capsys.readouterr().err
