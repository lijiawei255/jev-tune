"""Documentation and citation metadata stay self-consistent."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docs_relink", ROOT / "scripts/docs_relink.py")
relink = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relink)
DOI = "10.5281/zenodo.23624699"


def test_every_relative_documentation_link_resolves():
    assert relink.unresolved(ROOT) == []


def test_citation_metadata_carries_orcid_and_concept_doi():
    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert 'orcid: "https://orcid.org/0009-0002-8322-4474"' in cff
    assert f'value: "{DOI}"' in cff and "type: doi" in cff


def test_readmes_show_doi_badge_quickstart_and_how_to_cite():
    for name, heading in (("README.md", "## How to cite"), ("README.zh-CN.md", "## 如何引用")):
        text = (ROOT / name).read_text(encoding="utf-8")
        first_screen = text[: text.index("\n## ")]
        assert f"https://zenodo.org/badge/DOI/{DOI}.svg" in first_screen
        assert first_screen.count("\n```") == 2 and "pip install -e ." in first_screen
        assert heading in text and DOI in text[text.index(heading):] and "CITATION.cff" in text
        assert "BOUNDARIES" in first_screen and "negative_stop" not in first_screen
