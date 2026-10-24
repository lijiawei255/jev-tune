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
import gzip
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Explicit acceptance roster: --list-ids performs no experiment/audit.  The
# actual run must still return every registered check exactly once.
ARTIFACT_CHECK_IDS = (
    'table:jev_head', 'table:bo', 'table:jev_head_swept', 'table:shrunk_zn',
    'table:identify+pidtune_PID', 'table:swept_zn', 'table:vocab_hill',
    'table:cmaes', 'table:simplex', 'table:zn_classic',
    'table_thermal_deadtime:vocab_hill', 'table_thermal_deadtime:jev_head_swept',
    'table_thermal_deadtime:jev_head', 'table_thermal_deadtime:bo',
    'table_thermal_deadtime:cmaes', 'table_thermal_deadtime:identify+pidtune_PID',
    'table_thermal_deadtime:zn_classic', 'table_thermal_deadtime:swept_zn',
    'table_thermal_deadtime:shrunk_zn', 'table_thermal_deadtime:simplex',
    'generated:ABLATION.md', 'generated:ABSTENTION.md', 'generated:COMPUTE.md',
    'generated:CALIBRATE_ONLY.md', 'generated:JOINT_RISK.md',
    'generated:CP_DIAGNOSIS.md', 'generated:JOINT_RISK_ROLLOUT.md',
    'generated:ROLLOUT_DIAGNOSIS.md', 'generated:TRAJECTORY_RISK.md',
    'generated:CONFORMAL.md', 'generated:rollout_readmes',
    'generated:APPLICABILITY.md', 'generated:trajectory_summaries',
    'raw:joint_risk', 'raw:monitor_equivalence', 'raw:joint_risk_rollout',
    'raw:cp_performance_diagnosis', 'evidence:rollout_diagnosis.json',
    'evidence:trajectory_risk.json', 'evidence:trajectory_risk_reproduction.json',
    'evidence:cohort_portability.json', 'practical:43_verify_practical_budget',
    'practical:40_verify_model_adaptation', 'practical:41_sync_practical_docs',
    'practical:42_release_practical', 'shell:recorded_transfer',
    'shell:recorded_recalibration', 'shell:runtime_boundary',
    'shell:recorded_audit_summary', 'shell:49_sync_shell_docs',
    'shell:50_open_source_inventory', 'shell:distribution',
)


def expected_ids():
    claims = json.loads((ROOT / 'docs/claims.json').read_text(encoding='utf-8'))['claims']
    identifiers = [row['id'] for row in claims] + list(ARTIFACT_CHECK_IDS)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('Duplicate registered claim/check IDs')
    return identifiers


def complete_roster(rows):
    identifiers = [row['id'] for row in rows]
    expected = expected_ids()
    return len(identifiers) == len(set(identifiers)) and set(identifiers) == set(expected)


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
    def generator(number):
        spec=importlib.util.spec_from_file_location(number,ROOT/'scripts'/(number+'.py'))
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    def checked(identifier,title,source,evaluate,success,stale):
        try:
            ok=bool(evaluate()); detail=success if ok else stale
        except Exception as exc:
            ok=False; detail=f'render failed: {type(exc).__name__}: {exc}'
        rows.append({'id':identifier,'text':title,'ok':ok,'value':None,'source':source,'detail':detail})
    def compare_document(number,artifact,doc):
        module=generator(number)
        payload=json.loads((ROOT/'research/results'/artifact).read_text(encoding='utf-8'))
        render=getattr(module,'_doc',None) or module.render
        return render(payload).strip()==(ROOT/'docs'/doc).read_text(encoding='utf-8').strip()
    for number, artifact, doc in [("17_ablation","ablation.json","ABLATION.md"),
                                  ("20_abstention","abstention.json","ABSTENTION.md"),
                                  ("21_hardware","hardware_v0100.json","COMPUTE.md"),
                                  ("22_calibrate_only","calibrate_only.json","CALIBRATE_ONLY.md"),
                                  ("25_joint_risk","joint_risk.json","JOINT_RISK.md"),
                                  ("26_cp_diagnosis","cp_diagnosis.json","CP_DIAGNOSIS.md"),
                                  ("29_joint_risk_rollout","joint_risk_rollout.json","JOINT_RISK_ROLLOUT.md"),
                                  ("30_rollout_diagnosis","rollout_diagnosis.json","ROLLOUT_DIAGNOSIS.md"),
                                  ("31_trajectory_risk","trajectory_risk.json","TRAJECTORY_RISK.md")]:
        source=f"research/results/{artifact}"
        checked('generated:'+doc,'Full bilingual document rendered from JSON',source,
                lambda:compare_document(number,artifact,doc),
                'complete generated document matches','stale document: rerun its generator')
    checked('generated:CONFORMAL.md','Complete CP evidence and bilingual conclusions',
            'models/calibration.json + research/results/ablation.json',
            lambda:generator('23_sync_reference_docs').conformal_document(write=False).strip()==(ROOT/'docs/CONFORMAL.md').read_text(encoding='utf-8').strip(),
            'complete CP document matches','stale CP document')
    def compare_readmes():
        module=generator('23_sync_reference_docs')
        rollout=json.loads((ROOT/'research/results/joint_risk_rollout.json').read_text(encoding='utf-8'))
        return all(module.rollout_readme_section(rollout,chinese) in (ROOT/name).read_text(encoding='utf-8')
                   for name,chinese in [('README.md',False),('README.zh-CN.md',True)])
    checked('generated:rollout_readmes','Bilingual rollout numbers and acceptance conclusion',
            'research/results/joint_risk_rollout.json',compare_readmes,
            'both rollout README sections match','stale rollout README conclusion')
    def compare_applicability():
        module=generator('23_sync_reference_docs')
        robust=json.loads((ROOT/'research/results/robustness.json').read_text(encoding='utf-8'))
        body=(ROOT/'docs/APPLICABILITY.md').read_text(encoding='utf-8')
        return all(section.strip() in body for section in module.applicability_sections(robust))
    checked('generated:APPLICABILITY.md','Bilingual robustness data and narrative',
            'research/results/robustness.json',compare_applicability,
            'both robustness sections match','stale robustness table/narrative')
    checked('generated:trajectory_summaries','Complete bilingual trajectory sections and claim sources',
            'research/results/trajectory_risk.json + research/results/rollout_diagnosis.json',
            lambda:not generator('33_sync_trajectory_docs').check_generated_sections(ROOT),
            'all generated trajectory sections and source definitions match',
            'stale trajectory section or missing registered source; run scripts/33_sync_trajectory_docs.py --check')
    return rows


def trajectory_evidence() -> list[dict]:
    """Recompute retrospective diagnosis and verify prospective raw study."""
    rows=[]
    historical = None
    historical_error = None
    historical_attempted = False
    for name,artifact,function in [('30_rollout_diagnosis','rollout_diagnosis.json','diagnosis'),
                                   ('32_verify_trajectory_risk','trajectory_risk.json','study'),
                                   ('34_reproduce_trajectory_evaluation','trajectory_risk_reproduction.json','reproduction')]:
        source='research/results/'+artifact
        try:
            if function=='diagnosis':
                spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
                module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                payload=json.loads((ROOT/source).read_text(encoding='utf-8'))
                ok=module.same_evidence(payload,module.build_diagnosis(ROOT))
                detail='retrospective evidence recomputed from original raw' if ok else 'diagnosis differs from original raw'
            else:
                # Build the historical source view once for both verifiers.
                # The live runtime retains the separately checked v0.9 fixes.
                if not historical_attempted:
                    historical_attempted = True
                    try:
                        spec=importlib.util.spec_from_file_location('historical_research',ROOT/'scripts/44_verify_historical_research.py')
                        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                        historical=module.check(root=ROOT)
                    except Exception as exc:
                        historical_error=exc
                if historical_error is not None:
                    raise ValueError(f'Isolated historical audit failed: {historical_error}') from historical_error
                result=historical['checks'][function]
                ok=result['ok'] is True
                detail='isolated v0.8 source view: '+result['detail']
        except Exception as exc:
            ok=False; detail=f'{type(exc).__name__}: {exc}'
        rows.append({'id':'evidence:'+artifact,'text':'Independent evidence reconstruction',
                     'ok':ok,'value':None,'source':source,'detail':detail})
    return rows


def cohort_portability_evidence() -> list[dict]:
    """Keep the observed Linux failure auditable without local regeneration."""
    source = 'research/results/cohort_portability.json'
    try:
        spec = importlib.util.spec_from_file_location('cohort_portability', ROOT/'scripts/38_cohort_portability.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        report = module.check(root=ROOT)
        ok = (report['additional_simulations'] == 0 and report['thresholds_changed'] is False
              and report['linux_exact_cohort_regeneration_established'] is False)
        detail = 'observed Linux cohort failure preserved from source logs; reference export matches raw' if ok else 'invalid portability evidence status'
    except Exception as exc:
        ok = False; detail = f'{type(exc).__name__}: {exc}'
    return [{'id': 'evidence:cohort_portability.json', 'text': 'Preserved cross-platform reproducibility limitation',
             'ok': ok, 'value': None, 'source': source, 'detail': detail}]


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


def same_evidence(actual, expected):
    """Exact structure/counts, ULP-scale tolerance for cross-platform recomputation."""
    if isinstance(expected, dict):
        return isinstance(actual,dict) and actual.keys()==expected.keys() and all(same_evidence(actual[k],v) for k,v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual,list) and len(actual)==len(expected) and all(same_evidence(a,b) for a,b in zip(actual,expected))
    if isinstance(expected,float):
        return isinstance(actual,(float,int)) and math.isfinite(actual) and math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-12)
    return actual==expected


def source_hash_matches(path, expected, *, text_file=False):
    """Permit Git checkout EOL conversion, never text/content normalization."""
    data=Path(path).read_bytes()
    candidates={data}
    if text_file:
        lf=data.replace(b'\r\n',b'\n')
        candidates.update((lf,lf.replace(b'\n',b'\r\n')))
    return any(hashlib.sha256(blob).hexdigest()==expected for blob in candidates)


def performance_diagnosis_evidence() -> list[dict]:
    """Recompute both harm definitions and paired comparisons from E1/E2."""
    import numpy as np
    from jev_tune.evaluate import HARM_METRIC
    source='research/results/cp_performance_diagnosis.json'
    try:
        payload=json.loads((ROOT/source).read_text(encoding='utf-8'))
        inputs={name:json.loads((ROOT/f'research/results/{name}.json').read_text(encoding='utf-8'))
                for name in ('ablation','abstention')}
        assert HARM_METRIC['version']==2 and payload.get('harm_metric')==HARM_METRIC, 'diagnosis must use harm metric v2'
        for name,data in inputs.items():
            assert data.get('harm_metric')==HARM_METRIC, f'{name} must use harm metric v2'
            assert source_hash_matches(ROOT/f'research/results/{name}.json',payload['source_sha256'][name],text_file=True), f'stale {name} source hash'
        sys.path.insert(0,str(ROOT/'scripts'))
        spec=importlib.util.spec_from_file_location('performance_diagnosis',ROOT/'scripts/27_cp_performance_diagnosis.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        ab={r['variant']:r for r in inputs['ablation']['rows']}
        validation=inputs['abstention']['validation']
        expected={'E1':{},'E2':{},'exposure':{'E1':{},'E2':{}}}
        for left,right in [('C3_temperature_CP','C2_temperature_only'),('C2_temperature_only','C1_uncalibrated'),('C3_temperature_CP','C0_MLP_regression')]:
            expected['E1'][left+' minus '+right]=module.differences(module.array(ab[left]),module.array(ab[right]))
        for name in ('C0_MLP_regression','C1_uncalibrated','C2_temperature_only','C3_temperature_CP'):
            reports=[draw['decision_report'] for draw in ab[name]['per_draw']]
            expected['exposure']['E1'][name]=module.exposure(reports)
        for left,right in [('temperature_CP','CP_random_hold'),('temperature_CP','no_abstention'),('CP_random_hold','no_abstention')]:
            lr=[row for row in validation if row['policy']==left]
            rr=[row for row in validation if row['policy']==right]
            assert [r['draw_seed'] for r in lr]==[r['draw_seed'] for r in rr], 'E2 pairing changed'
            expected['E2'][left+' minus '+right]={
                'combined':module.differences(np.asarray([r['per_plant'] for r in lr]).ravel(),np.asarray([r['per_plant'] for r in rr]).ravel()),
                'by_draw':{str(l['draw_seed']):module.differences(l['per_plant'],r['per_plant']) for l,r in zip(lr,rr)}}
        for name in ('temperature_CP','CP_random_hold','no_abstention'):
            expected['exposure']['E2'][name]=module.exposure([r for r in validation if r['policy']==name])
        keys=('draw','median','p90','coverage','harmful_rate','harmful_gt_2pct_rate','rollbacks')
        expected['E1_primary_by_draw']={name:[{key:draw[key] for key in keys} for draw in ab[name]['per_draw']]
            for name in ('C1_uncalibrated','C2_temperature_only','C3_temperature_CP')}
        assert all(same_evidence(payload[key],value) for key,value in expected.items()), 'paired/exposure fields differ from current E1/E2'
        ok=True;detail='v2 source hashes, paired costs and exact zero-tolerance/>2% exposure counts match'
    except Exception as exc:
        ok=False;detail=f'performance diagnosis mismatch: {type(exc).__name__}: {exc}'
    return [{'id':'raw:cp_performance_diagnosis','text':'Current E1/E2 paired diagnosis and distinct harm definitions',
             'ok':ok,'value':None,'source':source,'detail':detail}]


def verify_rollout_run(result, model, qhats, *, collect_step=None):
    """Rebuild measurements, decisions and best history from each raw run."""
    import numpy as np
    from jev_tune.decode import apply_step

    plants, transitions = result['per_plant'], result['transitions']
    n = result['n_plants']
    assert len(plants) == n and [p['plant_index'] for p in plants] == list(range(n))
    assert len({p['plant_identity'] for p in plants}) == n
    by_plant = {i: [] for i in range(n)}
    for row in transitions:
        by_plant[row['plant_index']].append(row)
    total = {k:0 for k in ('operating_initial','executed','diagnostic_rejected','diagnostic_collected')}
    collected = {key:[] for key in ('features','labels','current_cost','proposed_cost','plant_index','plant_identity','stage')}
    for plant in plants:
        i = plant['plant_index']; rows = by_plant[i]
        assert [r['stage'] for r in rows] == list(range(len(rows)))
        assert len(rows) <= result['horizon']
        counts = {key:0 for key in total}; counts['operating_initial'] = 1
        current, gains = plant['initial_J'], plant['initial_gains']
        assert current is not None and math.isfinite(current) and plant['best_valid']
        history = [{'stage':-1,'gains':gains,'cost':current,'observed_finite':True}]
        any_harm = False; any_harm2 = False; stop = False
        for row in rows:
            assert not stop and row['plant_identity'] == plant['plant_identity']
            assert row['gains_before'] == gains and row['cost_before'] == current
            stage = row['stage']
            if row['proposal_valid']:
                proposed = np.asarray(row['gains_proposed'])
                assert np.allclose(proposed,apply_step(np.asarray(gains),row['proposed_step']),rtol=1e-12,atol=1e-12)
                assert np.allclose(row['applied_step'],np.log10(proposed/np.asarray(gains)),rtol=0,atol=1e-14)
                assert np.array_equal(row['features'][20:23],row['applied_step'])
                assert np.array_equal(row['features'][23:],np.asarray(row['choice_probabilities']).ravel())
                changed = not np.array_equal(proposed,gains)
                assert changed or (row['reason']=='no_action' and not row['measured'] and not row['executed'])
                if row['prediction_set'] is not None:
                    probabilities = np.asarray(row['probabilities'])
                    assert np.allclose(probabilities,model.probabilities(np.asarray([row['features']]))[0],rtol=0,atol=1e-12)
                    expected = (1-probabilities <= qhats[stage]).tolist()
                    assert row['prediction_set'] == expected and row['qhat'] == qhats[stage]
                    assert row['accepted'] == (expected == [True,False])
                    assert row['qhat_full_set'] == (qhats[stage] >= 1)
                    if result['mode'] != 'monitor':
                        assert row['executed'] == row['accepted']
                else:
                    assert not row['executed']
                    assert not changed or (result['mode']=='collect' and stage==collect_step)
            else:
                assert not row['executed'] and not row['measured'] and row['prediction_set'] is None
            if row['measured']:
                assert row['observed_finite'] and row['cost_after'] is not None and math.isfinite(row['cost_after'])
                label = int(row['cost_after'] > current)
                harm2 = row['cost_after'] > current*1.02
                assert row['label'] == label and row['harmful'] == bool(label) and row['harmful_gt2pct'] == harm2
                bucket = row['measurement_kind']; counts[bucket] += 1
                assert (bucket == 'executed') == row['executed']
                if bucket == 'diagnostic_collected':
                    assert result['mode']=='collect' and stage==collect_step
                    for key,value in {'features':row['features'],'labels':label,'current_cost':current,
                        'proposed_cost':row['cost_after'],'plant_index':i,'plant_identity':plant['plant_identity'],'stage':stage}.items():
                        collected[key].append(value)
                if row['executed']:
                    if result['mode'] != 'monitor':
                        assert row['prediction_set'] == [True,False]
                        assert not label or not row['prediction_set'][label]
                    current, gains = row['cost_after'],row['gains_proposed']
                    history.append({'stage':stage,'gains':gains,'cost':current,'observed_finite':True})
                    any_harm |= bool(label); any_harm2 |= harm2
            else:
                assert row['cost_after'] is None and row['measurement_kind'] is None
            stop = row['reason'] not in {'executed','proposal'}
        assert history == plant['operating_history']
        best = min(history,key=lambda x:x['cost'])
        assert plant['best_J']==best['cost'] and plant['best_gains']==best['gains']
        assert plant['current_J']==current and plant['current_gains']==gains
        assert plant['any_harm']==any_harm and plant['any_harm_gt2pct']==any_harm2
        expected_counts = {**counts,'operating':counts['operating_initial']+counts['executed'],'total':sum(counts.values())}
        assert plant['simulation_counts']==expected_counts
        for key in total:
            total[key] += counts[key]
    total.update(operating=total['operating_initial']+total['executed'],total=sum(total.values()))
    assert result['simulation_counts']==total
    # Collection is emitted in plant order at a single target stage.
    assert collected==result['collected']
    return True


def rollout_evidence() -> list[dict]:
    """Verify frozen calibration and raw trajectories independently of summaries."""
    import numpy as np
    from jev_tune.risk import JointRiskModel
    from jev_tune.sequential_risk import stage_calibration, summarize_rollout, acceptance_checks
    source = 'research/results/joint_risk_rollout.json'
    try:
        payload = json.loads((ROOT/source).read_text(encoding='utf-8'))
        protocol_path = ROOT/'research/protocols/joint_risk_rollout_v1.json'
        protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
        assert protocol==payload['protocol']
        assert source_hash_matches(protocol_path,payload['protocol_sha256'],text_file=True)
        spec = protocol['specification']
        raw_path = ROOT/payload['raw_file']; raw_bytes = raw_path.read_bytes()
        assert hashlib.sha256(raw_bytes).hexdigest()==payload['raw_sha256']
        raw = json.loads(gzip.decompress(raw_bytes))
        initial = json.loads((ROOT/'research/results/joint_risk.json').read_text(encoding='utf-8'))
        model_data = initial['risk_model']
        canonical = lambda value: hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        assert canonical(model_data)==payload['risk_model_sha256']==spec['frozen_risk_model_sha256']
        assert spec['frozen_proposal']==initial['protocol']['specification']['proposal']
        assert source_hash_matches(ROOT/'models/calibration.json',spec['calibration_file_sha256'],text_file=True)
        assert source_hash_matches(ROOT/'models/jev_head.pt',spec['frozen_proposal']['checkpoint_sha256'])
        source_hashes={name.replace('\\','/'):value for name,value in payload['manifest']['file_sha256'].items()}
        # The experiment renderer/checker can evolve independently; numerical
        # rollout dependencies must still match the run, modulo checkout EOLs.
        for name in ('joint_rollout','sequential_risk','risk','decode','decision','state','plants','metrics','primitives'):
            relative=f'src/jev_tune/{name}.py'
            assert source_hash_matches(ROOT/relative,source_hashes[relative],text_file=True)
        model = JointRiskModel(np.asarray(model_data['mean']),np.asarray(model_data['scale']),
            np.asarray(model_data['coefficient']),model_data['intercept'],model_data['temperature'])
        horizon=spec['horizon']; qhats=payload['qhats']
        assert len(qhats)==len(payload['stages'])==len(raw['calibration'])==horizon
        assert math.fsum(spec['alpha_per_stage'])==payload['union_bound']<=spec['trajectory_alpha']
        identities=set(initial['per_plant']['plant_identity'])
        for t,(stage,run) in enumerate(zip(payload['stages'],raw['calibration'])):
            assert run['mode']=='collect' and run['horizon']==horizon
            assert run['n_plants']==stage['n_initial']==spec['calibration']['n_initial_per_stage']
            ids={p['plant_identity'] for p in run['per_plant']}
            assert not identities.intersection(ids); identities.update(ids)
            verify_rollout_run(run,model,qhats,collect_step=t)
            collected=run['collected']; x=np.asarray(collected['features']).reshape(-1,44)
            probs=model.probabilities(x) if len(x) else np.empty((0,2))
            recalculated=stage_calibration(probs,collected['labels'],spec['alpha_per_stage'][t])
            assert all(same_evidence(stage[key],value) for key,value in recalculated.items())
            assert stage['stage']==t and stage['seed']==spec['calibration']['seeds'][t]
            assert stage['prefix_qhats']==qhats[:t] and stage['qhat']==qhats[t]
            assert stage['collected_sha256']==canonical(collected)
            assert stage['simulation_counts']==run['simulation_counts']
        eval_ids=None
        for mode,run in raw['evaluation'].items():
            assert run['mode']==mode and run['horizon']==horizon and run['n_plants']==spec['evaluation']['n_plants']
            ids=[p['plant_identity'] for p in run['per_plant']]
            assert not identities.intersection(ids)
            assert eval_ids is None or ids==eval_ids
            eval_ids=ids
            verify_rollout_run(run,model,qhats)
        evaluation={mode:summarize_rollout(run) for mode,run in raw['evaluation'].items()}
        assert same_evidence(evaluation,payload['evaluation'])
        acceptance=acceptance_checks(evaluation['monitor'],evaluation['gated'],all(payload['integrity'].values()),
            trajectory_alpha=spec['acceptance']['trajectory_risk_upper_max'],
            minimum_execution=spec['acceptance']['first_stage_execution_lower_min'])
        assert acceptance==payload['acceptance']
        deployment=payload['deployment']
        assert deployment['enabled']==acceptance['passed'] and not deployment['generic_python_c_matlab_enabled']
        assert deployment['scope']==spec['scope'] and deployment['failed_criteria']==acceptance['failed']
        assert deployment['status']==('validated_research_scope_only' if acceptance['passed'] else 'research_only')
        cal_total=sum(run['simulation_counts']['total'] for run in raw['calibration'])
        eval_total=sum(run['simulation_counts']['total'] for run in raw['evaluation'].values())
        assert payload['simulation_counts']=={'calibration_total':cal_total,'evaluation_total':eval_total,'total':cal_total+eval_total}
        detail='raw histories/actions, frozen stages/hashes, observed IDs, counts and acceptance reproduce'
        ok=True
    except Exception as exc:
        ok=False; detail=f'raw rollout evidence mismatch: {type(exc).__name__}: {exc}'
    return [{'id':'raw:joint_risk_rollout','text':'Raw sequential CP calibration and full rollout acceptance',
             'ok':ok,'value':None,'source':source,'detail':detail}]


def practical_evidence() -> list[dict]:
    """Check adapter provenance, actual trial ledgers and retained research."""
    rows = []
    for name, artifact, function in (
        ('43_verify_practical_budget', 'research/results/practical_budget.json', 'check'),
        ('40_verify_model_adaptation', 'research/results/model_adaptation.json', 'check'),
        ('41_sync_practical_docs', 'docs/MODEL_ADAPTATION.md', 'check'),
        ('42_release_practical', 'research/protocols/research_pause_v090.json', 'check_preserved'),
    ):
        try:
            spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            result = getattr(module, function)(root=ROOT)
            assert result, str(result)
            ok, detail = True, 'source-bound evidence / generated bilingual text verified'
        except Exception as exc:
            ok, detail = False, f'{type(exc).__name__}: {exc}'
        rows.append({'id': 'practical:' + name, 'text': 'Practical mainline evidence and preservation',
                     'ok': ok, 'value': None, 'source': artifact, 'detail': detail})
    return rows


def transfer_shell_evidence() -> list[dict]:
    """Audit original recorded evidence; strict cross-CPU refit is a separate failure.

    The post-incident obligation is specified in 52 and its frozen protocol.
    A pass here never reclassifies retained 46/48/54 failures as passing.
    """
    rows = []
    for identifier, name, entry, source in (
        ('recorded_transfer', '52_verify_recorded_transfer', 'check', 'research/results/nonpid_transfer/report.json'),
        ('recorded_recalibration', '52_verify_recorded_transfer', 'check_recalibration', 'research/results/recalibration_benchmark.json'),
        ('runtime_boundary', '58_verify_runtime_observations', 'check', 'research/results/calibration_runtime_observations_v0100.json'),
        ('recorded_audit_summary', '56_summarize_recorded_evidence', 'check', 'research/results/recorded_evidence_audit_v0100.json'),
        ('49_sync_shell_docs', '49_sync_shell_docs', 'check', 'docs/SAFETY_SHELL.md'),
        ('50_open_source_inventory', '50_open_source_inventory', 'check', 'research/results/open_source_inventory_v0100.json'),
        ('distribution', '61_check_distribution', 'check', 'research/distribution/research_data_v0101.json'),
    ):
        try:
            spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/(name+'.py'))
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            result = getattr(module, entry)(root=ROOT)
            assert result and result['ok'] is True
            extra = result.get('additional_verification_objective_evaluations', 0)
            ok, detail = True, f'independent evidence verified; additional_verification_objective_evaluations={extra}'
        except Exception as exc:
            ok, detail = False, f'{type(exc).__name__}: {exc}'
        rows.append({'id':'shell:'+identifier, 'text':'Recorded shell evidence; original strict CPU refit failure remains retained',
                     'ok':ok, 'value':None, 'source':source, 'detail':detail})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list-ids", action="store_true", help="Print the complete acceptance roster without running audits")
    args = ap.parse_args()

    if args.list_ids:
        print(json.dumps(expected_ids(), indent=2, ensure_ascii=False))
        return 0
    if not (ROOT / 'research/results/open_source_inventory_v0100.json').is_file():
        print('Optional research evidence is missing. Restore with: python scripts/59_research_data.py --fetch all. '
              'For full verification including historical Git objects, use: '
              'python scripts/60_reproduce_release.py --destination NEW_DIRECTORY --verify', file=sys.stderr)
        return 2

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
    for checker in (benchmark_tables,generated_documents,decision_evidence,rollout_evidence,performance_diagnosis_evidence,trajectory_evidence,cohort_portability_evidence,practical_evidence,transfer_shell_evidence):
        try:
            checked_rows=checker()
        except Exception as exc:
            checked_rows=[{'id':'check:'+checker.__name__,'text':'Artifact check must remain diagnosable on stale input',
                'ok':False,'value':None,'source':'repository artifacts','detail':f'{type(exc).__name__}: {exc}'}]
        for row in checked_rows:
            rows.append(row)
            failed += not row["ok"]

    if not complete_roster(rows):
        failed += 1
        rows.append({'id': 'check:complete_roster', 'text': 'Every registered acceptance check must execute exactly once',
                     'ok': False, 'value': None, 'source': 'docs/claims.json + ARTIFACT_CHECK_IDS',
                     'detail': 'Missing, unexpected or duplicate acceptance check ID'})
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
