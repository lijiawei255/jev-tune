"""Re-read every published number from its artifact and fail when they disagree.

The repository quotes numbers in prose (README, docs/*.md) that are produced by
scripts.  Prose drifts: a script is fixed, a model is retrained, and the sentence
still says the old figure.  `docs/claims.json` is the list of what is published
and where each number comes from; this walks it and compares.

    python scripts/16_check_claims.py          # table, exit 1 on drift
    python scripts/16_check_claims.py --json   # machine readable

Claims that need MATLAB are marked "verified_by": "manual" and are only reported,
never silently trusted.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def walk(obj, path: str):
    """Resolve `rows[method=jev_head].final_cost_median` against a JSON tree."""
    cur = obj
    for part in path.split("."):
        sel = re.fullmatch(r"(\w+)\[(\w+)=([^\]]+)\]", part)
        if sel:
            key, field, want = sel.groups()
            cur = cur[key]
            cur = next(r for r in cur if str(r[field]) == want)
            continue
        idx = re.fullmatch(r"(\w+)\[(-?\d+)\]", part)
        if idx:
            cur = cur[idx.group(1)][int(idx.group(2))]
            continue
        cur = cur[part]
    return cur


def evaluate(claim: dict) -> tuple[bool, float | None, str]:
    src = ROOT / claim["source"]
    if "verified_by" in claim and claim["verified_by"] == "manual":
        return True, claim.get("value"), "manual (not re-checked here)"
    if not src.is_file():
        return False, None, f"missing artifact {claim['source']}"

    if "regex" in claim:
        text = src.read_text(encoding="utf-8", errors="replace")
        m = re.search(claim["regex"], text)
        if not m:
            return False, None, f"pattern not found in {claim['source']}"
        got = float(m.group(1))
    else:
        data = json.loads(src.read_text(encoding="utf-8-sig"))
        got = walk(data, claim["path"])
        if "reduce" in claim:
            rows = got
            where = claim.get("where") or {}
            rows = [r for r in rows if all(r.get(k) == v for k, v in where.items())]
            field = claim["reduce"].split(":")[1]
            op = claim["reduce"].split(":")[0]
            values = [r[field] for r in rows]
            got = sum(values) if op == "sum" else len(values)
        if "all_equal" in claim:
            field, want = claim["all_equal"]
            bad = [r for r in got if r.get(field) != want]
            got = 1 if not bad else 0
            claim["value"] = 1

    want = float(claim["value"])
    tol = float(claim.get("tol", 0))
    ok = abs(float(got) - want) <= tol
    return ok, float(got), f"{got:.6g} vs {want:.6g} (tol {tol:g})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    claims = json.loads((ROOT / "docs/claims.json").read_text(encoding="utf-8"))[
        "claims"
    ]
    rows, failed = [], 0
    for claim in claims:
        try:
            ok, got, detail = evaluate(claim)
        except Exception as exc:  # noqa: BLE001 - report, never crash CI
            ok, got, detail = False, None, f"error: {exc}"
        if not ok:
            failed += 1
        rows.append(
            {
                "id": claim["id"],
                "text": claim["text"],
                "ok": ok,
                "value": got,
                "detail": detail,
                "source": claim["source"],
            }
        )

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        width = max(len(r["id"]) for r in rows)
        for r in rows:
            tag = "ok  " if r["ok"] else "FAIL"
            print(f"  [{tag}] {r['id']:<{width}}  {r['detail']}")
            if not r["ok"]:
                print(f"{'':<13}{r['text']}")
                print(f"{'':<13}source: {r['source']}")
        print(f"\n{len(rows) - failed}/{len(rows)} claims match their artifacts")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
