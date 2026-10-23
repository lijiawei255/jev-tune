"""Check real artifact/prose drift, not only registry self-consistency."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("claim_check", Path(__file__).parents[1] / "scripts/16_check_claims.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_manual_is_unverified_and_missing_manual_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ROOT", tmp_path)
    claim = {"source": "evidence.json", "verified_by": "manual", "value": 1}
    assert module.evaluate(claim)[0] is False
    (tmp_path / "evidence.json").write_text("{}")
    assert module.evaluate(claim)[0] is None


def test_prose_drift_is_not_hidden_by_correct_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "r.json").write_text(json.dumps({"cost": 1.2345}))
    doc = tmp_path / "doc.md"
    claim = {"id": "cost", "source": "r.json", "path": "cost", "value": 1.2345,
             "documents": [{"file": "doc.md", "format": ".3f"}]}
    doc.write_text("<!-- claim:cost -->0.900<!-- /claim -->")
    assert module.evaluate(claim)[0] is False
    doc.write_text("<!-- claim:cost -->1.234<!-- /claim -->")
    assert module.evaluate(claim)[0] is True
    doc.write_text("no registered number")
    assert module.evaluate(claim)[0] is False
