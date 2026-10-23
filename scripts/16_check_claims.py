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
import math
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render_value(value, fmt=".3f"):
    return "null" if value is None else format(float(value), fmt)


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


def evaluate(claim: dict) -> tuple[bool | None, float | None, str]:
    src = ROOT / claim["source"]
    if not src.is_file():
        return False, None, f"missing artifact {claim['source']}"
    if claim.get("verified_by") == "manual":
        return None, claim.get("value"), "UNVERIFIED manual evidence (not an automatic pass)"

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

    want = claim["value"]
    tol = float(claim.get("tol", 0))
    ok = (got is None and want is None) if (got is None or want is None) else math.isfinite(float(got)) and abs(float(got) - float(want)) <= tol
    detail = f"{render_value(got,'.6g')} vs {render_value(want,'.6g')} (tol {tol:g})"
    for doc in claim.get("documents", []):
        path = ROOT / doc["file"]
        body = path.read_text(encoding="utf-8")
        marker = rf"<!-- claim:{re.escape(claim['id'])} -->(.*?)<!-- /claim -->"
        matches = re.findall(marker, body)
        rendered = render_value(got, doc.get("format", ".3f"))
        if not matches or any(m.strip() != rendered for m in matches):
            ok = False
            detail += f"; stale/missing prose in {doc['file']} (expected {rendered})"
    return ok, None if got is None else float(got), detail


def benchmark_tables() -> list[dict]:
    """Check both published benchmark tables and the compact README copies."""
    checks = []
    for suffix in ("", "_thermal_deadtime"):
        source = f"research/results/eval_{'thermal_deadtime' if suffix else 'heldout'}_120.json"
        data = json.loads((ROOT / source).read_text(encoding="utf-8"))
        table = ROOT / f"research/results/benchmark_table{suffix}.md"
        body = table.read_text(encoding="utf-8")
        for row in data["rows"]:
            method = row["method"]
            prefix = f"| `{method}` | {row['final_cost_median']:.3f} | {row['final_cost_p90']:.3f} |"
            tail = (f" {row['ratio_to_ref']:.2f} | {100 * row['success_rate']:.0f}% | "
                    f"{row['sims_to_target_median']:.1f} | {row['budget']} |")
            # Column names are stable artifacts of scripts/03_evaluate.py.
            ok = prefix + tail in body
            for doc in ("README.md", "README.zh-CN.md"):
                compact = prefix + f" {row['budget']:g} |"
                if compact not in (ROOT / doc).read_text(encoding="utf-8"):
                    ok = False
            checks.append({"id": f"table{suffix}:{method}", "text": "Benchmark and bilingual README row",
                           "ok": ok, "value": row["final_cost_median"], "source": source,
                           "detail": "table and README rows match" if ok else "stale/missing table or README row"})
    return checks


def generated_documents() -> list[dict]:
    """Render current experiment documents from JSON without rerunning models."""
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))
    rows=[]
    for number, artifact, doc in [("17_ablation","ablation.json","ABLATION.md"),
                                  ("20_abstention","abstention.json","ABSTENTION.md"),
                                  ("21_hardware","hardware.json","COMPUTE.md"),
                                  ("22_calibrate_only","calibrate_only.json","CALIBRATE_ONLY.md"),
                                  ("25_joint_risk","joint_risk.json","JOINT_RISK.md"),
                                  ("26_cp_diagnosis","cp_diagnosis.json","CP_DIAGNOSIS.md")]:
        spec=importlib.util.spec_from_file_location(number, ROOT / "scripts" / (number+".py"))
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source=f"research/results/{artifact}"
        payload=json.loads((ROOT/source).read_text(encoding="utf-8"))
        render = getattr(module, "_doc", None) or module.render
        expected=render(payload).strip()
        actual=(ROOT/"docs"/doc).read_text(encoding="utf-8").strip()
        ok=expected==actual
        rows.append({"id":"generated:"+doc,"text":"Full bilingual document rendered from JSON",
                     "ok":ok,"value":None,"source":source,
                     "detail":"complete generated document matches" if ok else "stale document: rerun its generator"})
    spec=importlib.util.spec_from_file_location("reference_docs",ROOT/"scripts/23_sync_reference_docs.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ok=module.conformal_document(write=False).strip()==(ROOT/"docs/CONFORMAL.md").read_text(encoding="utf-8").strip()
    rows.append({"id":"generated:CONFORMAL.md","text":"Complete CP evidence and bilingual conclusions",
                 "ok":ok,"value":None,"source":"models/calibration.json + research/results/ablation.json",
                 "detail":"complete CP document matches" if ok else "stale CP document"})
    robust=json.loads((ROOT/'research/results/robustness.json').read_text(encoding='utf-8'))
    body=(ROOT/'docs/APPLICABILITY.md').read_text(encoding='utf-8')
    ok=all(section.strip() in body for section in module.applicability_sections(robust))
    rows.append({"id":"generated:APPLICABILITY.md","text":"Bilingual robustness data and narrative",
                 "ok":ok,"value":None,"source":"research/results/robustness.json",
                 "detail":"both robustness sections match" if ok else "stale robustness table/narrative"})
    return rows


def decision_evidence() -> list[dict]:
    """Check raw paired actions and monitor equivalence, not only prose."""
    import numpy as np
    from jev_tune.risk import risk_report, select_joint_gains
    risk=json.loads((ROOT/'research/results/joint_risk.json').read_text(encoding='utf-8'))
    raw=risk['per_plant']
    report=risk_report(raw['probabilities'],raw['labels'],np.asarray(raw['prediction_set'],bool),raw['current_cost'],raw['proposed_cost'])
    selected=select_joint_gains(raw['current_gains'],raw['proposed_gains'],np.asarray(raw['prediction_set'],bool))
    ok=report==risk['evaluation'] and np.array_equal(selected,raw['selected_gains'])
    ok=bool(ok and np.array_equal(np.asarray(raw['prediction_set'])[:,0]&~np.asarray(raw['prediction_set'])[:,1],raw['accepted']))
    expected=np.where(raw['accepted'],raw['proposed_cost'],raw['current_cost'])
    ok=bool(ok and np.array_equal(expected,raw['selected_cost']))
    rows=[{'id':'raw:joint_risk','text':'Raw full-action admission and measured cost pairs','ok':ok,'value':None,
           'source':'research/results/joint_risk.json','detail':'raw admission, coverage and paired costs match' if ok else 'raw risk evidence mismatch'}]
    data=json.loads((ROOT/'research/results/ablation.json').read_text(encoding='utf-8'))
    by={r['variant']:r for r in data['rows']}
    ok=all(np.array_equal(a['per_plant'],b['per_plant']) for a,b in zip(by['C2_temperature_only']['per_draw'],by['C4_CP_monitor']['per_draw']))
    rows.append({'id':'raw:monitor_equivalence','text':'Frozen matched-draw monitor costs equal Temp Only','ok':ok,'value':None,
                 'source':'research/results/ablation.json','detail':'paired outcomes identical' if ok else 'monitor changed paired outcomes'})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    claims = json.loads((ROOT / "docs/claims.json").read_text(encoding="utf-8"))[
        "claims"
    ]
    rows, failed, unverified = [], 0, 0
    for claim in claims:
        try:
            ok, got, detail = evaluate(claim)
        except Exception as exc:  # noqa: BLE001 - report, never crash CI
            ok, got, detail = False, None, f"error: {exc}"
        if ok is None:
            unverified += 1
        elif not ok:
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
    for row in benchmark_tables()+generated_documents()+decision_evidence():
        rows.append(row)
        failed += not row["ok"]

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        width = max(len(r["id"]) for r in rows)
        for r in rows:
            tag = "SKIP" if r["ok"] is None else ("ok  " if r["ok"] else "FAIL")
            print(f"  [{tag}] {r['id']:<{width}}  {r['detail']}")
            if not r["ok"]:
                print(f"{'':<13}{r['text']}")
                print(f"{'':<13}source: {r['source']}")
        print(f"\n{len(rows) - failed - unverified} automatic matches, {failed} failures, {unverified} unverified manual claims")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
