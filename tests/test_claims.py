"""Check real artifact/prose drift, not only registry self-consistency."""
import importlib.util
import json
import copy
import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location("claim_check", Path(__file__).parents[1] / "scripts/16_check_claims.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_manual_is_unverified_and_missing_manual_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ROOT", tmp_path)
    claim = {"source": "evidence.json", "verified_by": "manual", "value": 1}
    assert module.evaluate(claim)[0] is False
    (tmp_path / "evidence.json").write_text("{}")
    assert module.evaluate(claim)[0] is None


def test_source_hash_tolerates_only_checkout_line_endings(tmp_path):
    path=tmp_path/'source.py'
    original=b'first\r\nsecond\r\n'
    expected=hashlib.sha256(original).hexdigest()
    path.write_bytes(b'first\nsecond\n')
    assert module.source_hash_matches(path,expected,text_file=True)
    assert not module.source_hash_matches(path,expected)
    path.write_bytes(b'first\nchanged\n')
    assert not module.source_hash_matches(path,expected,text_file=True)


def test_recomputed_evidence_tolerance_cannot_hide_changed_results():
    assert module.same_evidence({'events':2,'upper':.006}, {'events':2,'upper':.006+1e-15})
    assert not module.same_evidence({'events':1,'upper':.006}, {'events':2,'upper':.006})
    assert not module.same_evidence({'events':2,'upper':.006}, {'events':2,'upper':.0061})


def test_raw_claims_reject_diagnostic_cost_as_operating_best_and_count_drift():
    from jev_tune.decision import load_backend
    from jev_tune.joint_rollout import run_joint_rollout
    from jev_tune.plants import sample_plants

    class AlwaysAmbiguous:
        def probabilities(self, features):
            return np.full((len(features),2),.5)

    root=Path(__file__).parents[1]
    risk=AlwaysAmbiguous()
    run=run_joint_rollout(load_backend(root/'models'),risk,sample_plants(3,seed=85701),
                          [1.],horizon=1,mode='gated',diagnostic=True)
    assert module.verify_rollout_run(run,risk,[1.])
    stale=copy.deepcopy(run)
    stale['per_plant'][0]['best_J']=-1.
    with pytest.raises(AssertionError):
        module.verify_rollout_run(stale,risk,[1.])
    stale=copy.deepcopy(run)
    stale['simulation_counts']['operating']+=1
    with pytest.raises(AssertionError):
        module.verify_rollout_run(stale,risk,[1.])


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


def test_stale_renderer_is_structured_failure_in_json_mode(tmp_path, monkeypatch, capsys):
    (tmp_path/'scripts').mkdir();(tmp_path/'research/results').mkdir(parents=True)
    (tmp_path/'docs').mkdir()
    (tmp_path/'scripts/17_ablation.py').write_text("def _doc(payload):\n    raise ValueError('stale harm schema')\n")
    (tmp_path/'research/results/ablation.json').write_text('{}')
    # This test exercises renderer failures after the independent missing-data
    # preflight.  A separate contract test covers an un-restored source ZIP.
    (tmp_path/'research/results/open_source_inventory_v0100.json').write_text('{}')
    (tmp_path/'docs/claims.json').write_text('{"claims":[]}')
    monkeypatch.setattr(module,'ROOT',tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path/'scripts'))
    rows=module.generated_documents()
    row=next(r for r in rows if r['id']=='generated:ABLATION.md')
    assert row['ok'] is False and 'ValueError: stale harm schema' in row['detail']
    assert len(rows)==13 and all(r['ok'] is False for r in rows)
    monkeypatch.setattr(module,'generated_documents',lambda:rows)
    for name in ('benchmark_tables','decision_evidence','rollout_evidence','performance_diagnosis_evidence','trajectory_evidence','cohort_portability_evidence','practical_evidence','transfer_shell_evidence'):
        monkeypatch.setattr(module,name,lambda:[])
    monkeypatch.setattr(sys,'argv',['check_claims','--json'])
    assert module.main()==1
    parsed=json.loads(capsys.readouterr().out)
    assert parsed[:-1]==rows
    assert parsed[-1]['id']=='check:complete_roster' and parsed[-1]['ok'] is False


def test_new_shell_checker_reports_missing_evidence_as_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    rows = module.transfer_shell_evidence()
    assert len(rows) == 7 and all(row['ok'] is False for row in rows)
    assert {r['id'] for r in rows} == {'shell:recorded_transfer',
        'shell:recorded_recalibration', 'shell:runtime_boundary', 'shell:recorded_audit_summary', 'shell:49_sync_shell_docs',
        'shell:50_open_source_inventory', 'shell:distribution'}
    assert all('FileNotFoundError' in row['detail'] for row in rows)


def test_performance_diagnosis_recomputes_counts_and_requires_v2_sources(tmp_path, monkeypatch, capsys):
    from jev_tune.evaluate import HARM_METRIC
    root=Path(__file__).parents[1]
    (tmp_path/'scripts').mkdir();(tmp_path/'research/results').mkdir(parents=True)
    for name in ('27_cp_performance_diagnosis.py','_experiment_protocol.py'):
        (tmp_path/'scripts'/name).write_bytes((root/'scripts'/name).read_bytes())
    report={'harm_metric':dict(HARM_METRIC),'n_decisions':10,'n_executed':8,
            'n_harmful':3,'n_harmful_gt_2pct':1,'improvement_rate':.5,
            'partial_hold_rate':.1,'axis_coverage':.7,'n_rollbacks':0}
    draw={'draw':0,'per_plant':[1.,2.,3.],'median':2.,'p90':2.8,'coverage':.8,
          'harmful_rate':.375,'harmful_gt_2pct_rate':.125,'rollbacks':0,'decision_report':report}
    ablation={'harm_metric':dict(HARM_METRIC),'rows':[{'variant':name,'per_draw':[draw]}
        for name in ('C0_MLP_regression','C1_uncalibrated','C2_temperature_only','C3_temperature_CP')]}
    abstention={'harm_metric':dict(HARM_METRIC),'validation':[dict(report,policy=name,draw_seed=7,per_plant=[1.,2.,3.])
        for name in ('temperature_CP','CP_random_hold','no_abstention')]}
    for name,payload in [('ablation',ablation),('abstention',abstention)]:
        (tmp_path/f'research/results/{name}.json').write_text(json.dumps(payload))
    monkeypatch.syspath_prepend(str(tmp_path/'scripts'))
    helper_spec=importlib.util.spec_from_file_location('_experiment_protocol',root/'scripts/_experiment_protocol.py')
    helper=importlib.util.module_from_spec(helper_spec);helper_spec.loader.exec_module(helper)
    monkeypatch.setitem(sys.modules,'_experiment_protocol',helper)
    spec=importlib.util.spec_from_file_location('test_performance_generator',tmp_path/'scripts/27_cp_performance_diagnosis.py')
    generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
    generator.main();capsys.readouterr()
    monkeypatch.setattr(module,'ROOT',tmp_path)
    assert module.performance_diagnosis_evidence()[0]['ok'] is True
    result_path=tmp_path/'research/results/cp_performance_diagnosis.json'
    original=json.loads(result_path.read_text())
    changed=copy.deepcopy(original)
    changed['exposure']['E1']['C2_temperature_only']['harmful_count']+=1
    result_path.write_text(json.dumps(changed))
    assert module.performance_diagnosis_evidence()[0]['ok'] is False
    result_path.write_text(json.dumps(original))
    path=tmp_path/'research/results/ablation.json'
    path.write_text(path.read_text()+' ')
    assert 'source hash' in module.performance_diagnosis_evidence()[0]['detail']
    changed=copy.deepcopy(original);changed['harm_metric']['version']=1
    result_path.write_text(json.dumps(changed))
    assert 'metric v2' in module.performance_diagnosis_evidence()[0]['detail']


def test_reproduction_claims_require_equal_nonindependent_report_and_surface_errors(tmp_path, monkeypatch):
    (tmp_path/'scripts').mkdir(); (tmp_path/'research/results').mkdir(parents=True)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    # Exercise the real historical worker's report validation through the new
    # claims entry point. Archive/import isolation and exact metadata provenance
    # gates have separate tamper tests; this fixture replaces their setup only.
    # The real worker still checks replay schema, equality and evidence scope.
    root=Path(__file__).resolve().parents[1]
    worker_path=root/'scripts/44_verify_historical_research.py'
    # The real worker hashes its post-hoc sources even when setup is isolated.
    (tmp_path/'scripts/42_release_practical.py').write_bytes(
        (root/'scripts/42_release_practical.py').read_bytes())
    (tmp_path/'scripts/44_verify_historical_research.py').write_text(
        "import importlib.util\n"
        f"spec=importlib.util.spec_from_file_location('real_historical_worker',{str(worker_path)!r})\n"
        "worker=importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)\n"
        "worker.verify_archives=lambda root: ({'baseline_commit':'fixture'}, {})\n"
        "worker.imported_sources=lambda root: {}\n"
        "adapter_contexts=[]\n"
        "def fixture_adapter_setup(root, module, context, receipts):\n"
        "    assert context == 'trajectory_saved_replay'\n"
        "    assert worker.Path(module.__file__).resolve() == root/'scripts/34_reproduce_trajectory_evaluation.py'\n"
        "    adapter_contexts.append(context)\n"
        "    return {'context':context, 'fixture_setup_only':True}\n"
        "worker.install_metadata_predicate_adapter=fixture_adapter_setup\n"
        "def check(root):\n"
        "    adapter_contexts.clear()\n"
        "    result=worker.worker(root)\n"
        "    assert adapter_contexts == ['trajectory_saved_replay']\n"
        "    return result\n")
    (tmp_path/'research/results/trajectory_risk.json').write_text('{}')
    script=tmp_path/'scripts/34_reproduce_trajectory_evaluation.py'
    script.write_text("import json\ndef check(*, result_path, report_path):\n"
                      "    p=json.loads(report_path.read_text())\n"
                      "    if p.get('stale'): raise ValueError('replay source hash differs')\n"
                      "    return p\n")
    report_path=tmp_path/'research/results/trajectory_risk_reproduction.json'
    valid={'schema_version':1,'equal':True,'additional_independent_evidence':False,'acceptance_recomputed':False}
    monkeypatch.setattr(module,'ROOT',tmp_path)
    def row(value):
        report_path.write_text(json.dumps(value))
        return next(r for r in module.trajectory_evidence() if r['id']=='evidence:trajectory_risk_reproduction.json')
    passed=row(valid)
    assert passed['ok'] is True, passed['detail']
    assert row(dict(valid,schema_version=0))['ok'] is False
    assert row(dict(valid,equal=False))['ok'] is False
    assert row(dict(valid,additional_independent_evidence=True))['ok'] is False
    assert row(dict(valid,acceptance_recomputed=True))['ok'] is False
    failed=row(dict(valid,stale=True))
    assert failed['ok'] is False and 'ValueError: replay source hash differs' in failed['detail']
