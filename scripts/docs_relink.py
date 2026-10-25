"""Point documentation at the frozen archive and remove generator markers.

Every relative reference in README*.md, AGENTS.md, CONTRIBUTING.md, NOTICE.md,
c/README.md and docs/*.md either resolves in this checkout or is rewritten to
the immutable ``v0.10.2-archive`` tag. Numbers inside former generator blocks
are kept verbatim; only the markers go. ``--check`` changes nothing and exits 1
on any unresolved relative reference.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG_URL = "https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/"
RELEASE_URL = "https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1"
FILES = ["README.md", "README.zh-CN.md", "AGENTS.md", "CONTRIBUTING.md", "NOTICE.md", "c/README.md"]
LINK = re.compile(r"\]\((?!https?://|mailto:|#)([^)#\s]+)(#[^)\s]*)?\)")
CODE = re.compile(r"`((?:scripts|research|examples|docs)/[^`\s]+)`")
MOVED = {  # v0.10.2 path -> current path
    "src/jev_tune/primitives.py": "src/jev_tune/core/primitives.py",
    "src/jev_tune/calibration.py": "src/jev_tune/core/calibration.py",
    "src/jev_tune/decode.py": "src/jev_tune/core/policy.py",
    "examples/linear_decoder_shell/README.md": "src/jev_tune/domains/light/README.md",
    "examples/linear_decoder_shell/run.py": "src/jev_tune/domains/light/linear_shell.py",
    "examples/linear_decoder_shell": "src/jev_tune/domains/light",
    **{f"src/jev_tune/{m}.py": f"src/jev_tune/domains/pid/{m}.py" for m in (
        "decision", "evaluate", "plants", "metrics", "state", "expert", "baselines", "model",
        "train", "scenarios", "identified", "matlab_runner", "matlab_worker", "matlab_baseline", "plot")},
}
MARKER = re.compile(r"<!-- (?:/?claim(?::[^>]*)?|[a-z0-9-]+(?::[a-z-]+)?:(?:start|end)) -->")


def documents(root: Path) -> list[Path]:
    return [root / f for f in FILES if (root / f).is_file()] + sorted((root / "docs").glob("*.md"))


def target(doc: Path, ref: str, root: Path) -> Path:
    return (doc.parent / ref).resolve() if not ref.startswith("/") else (root / ref[1:]).resolve()


def moved(doc: Path, ref: str, root: Path) -> str | None:
    rel = target(doc, ref, root).relative_to(root).as_posix().rstrip("/")
    new = MOVED.get(rel)
    return None if new is None else Path(os.path.relpath(root / new, doc.parent)).as_posix()


def archived(doc: Path, ref: str, root: Path) -> str:
    rel = target(doc, ref, root).relative_to(root).as_posix()
    return RELEASE_URL if rel.startswith("research/results") else TAG_URL + rel


def rewrite(doc: Path, root: Path) -> str:
    text = doc.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^[ \t]*" + MARKER.pattern + r"[ \t]*\n", "", text)
    text = MARKER.sub("", text)

    def link(m):
        ref, anchor = m.group(1), m.group(2) or ""
        if target(doc, ref, root).exists():
            return m.group(0)
        if moved(doc, ref, root):
            return f"]({moved(doc, ref, root)}{anchor})"
        return f"]({archived(doc, ref, root)}{anchor if 'releases' not in archived(doc, ref, root) else ''})"

    def code(m):
        ref = m.group(1)
        if (root / ref).exists() or "*" in ref or "<" in ref or not re.search(r"\.\w+$|/$", ref):
            return m.group(0)
        if ref.rstrip("/") in MOVED:
            return f"`{MOVED[ref.rstrip('/')]}`"
        return f"[`{ref}`]({archived(root / 'README.md', ref, root)})"

    return CODE.sub(code, LINK.sub(link, text))


def unresolved(root: Path) -> list[str]:
    bad = []
    for doc in documents(root):
        for m in LINK.finditer(doc.read_text(encoding="utf-8")):
            if not target(doc, m.group(1), root).exists():
                bad.append(f"{doc.relative_to(root)} -> {m.group(1)}")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if not args.check:
        for doc in documents(ROOT):
            new = rewrite(doc, ROOT)
            if new != doc.read_text(encoding="utf-8"):
                doc.write_text(new, encoding="utf-8")
    bad = unresolved(ROOT)
    print("\n".join(bad) if bad else "all relative documentation links resolve")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
