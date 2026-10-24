"""Tiny real Git clones and synthetic command fixtures; no scientific objective runs."""
import importlib.util
import json
import hashlib
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_reproducer_test', ROOT/'scripts/60_reproduce_release.py')
reproducer = importlib.util.module_from_spec(spec); spec.loader.exec_module(reproducer)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def tiny_repo(tmp_path, *, restore='pass', tests='pass', claims='pass', history_cleaned=False, history_restore='pass'):
    root = tmp_path/'source'; root.mkdir(); (root/'scripts').mkdir(); (root/'src').mkdir()
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    (root/'tracked.txt').write_text('untouched')
    (root/'.gitignore').write_text('.local-audit/\n__pycache__/\n')
    distribution=root/'research/distribution';distribution.mkdir(parents=True)
    (distribution/'research_data_v0101.json').write_text(json.dumps({'history_cleaned':history_cleaned}))
    code = "import json, pathlib, sys\n"
    if restore == 'fail': code += "print(json.dumps({'ok':False}));sys.exit(3)\n"
    elif restore == 'mutation': code += "pathlib.Path('tracked.txt').write_text('changed')\nprint(json.dumps({'ok':True}))\n"
    else: code += "pathlib.Path('.local-audit/data-restored.marker').write_text('true')\nprint(json.dumps({'ok':True,'objective_evaluations':0,'gradient_steps':0}))\n"
    (root/'scripts/59_research_data.py').write_text(code)
    if history_cleaned:
        (distribution/'historical_sources_v0101.json').write_text(json.dumps({'sha256':'c'*64}))
        code="import json,pathlib,os,sys,subprocess\nassert pathlib.Path('.local-audit/data-restored.marker').is_file()\nassert os.environ['GIT_NO_LAZY_FETCH']=='1' and os.environ['GIT_NO_REPLACE_OBJECTS']=='1'\n"
        if history_restore=='fail':code+="print(json.dumps({'ok':False}));sys.exit(5)\n"
        elif history_restore=='mutation':code+="pathlib.Path('tracked.txt').write_text('historical restore source mutation')\n"
        elif history_restore=='refs':code+="subprocess.check_call(['git','update-ref','refs/tags/unexpected', 'HEAD'])\n"
        code+="print(json.dumps({'ok':True,'capsule_sha256':"+repr('0'*64 if history_restore=='hash' else 'c'*64)+",'objects':4,'source_paths':2,'objective_evaluations':0,'gradient_steps':"+('1' if history_restore=='gradient' else '0')+"}))\n"
        (root/'scripts/history_sources.py').write_text(code)
    code = "import pathlib,sys\nassert pathlib.Path.cwd().joinpath('tracked.txt').is_file()\n"
    code += "assert __import__('os').environ['PYTHONPATH']==str(pathlib.Path.cwd()/'src')\n"
    code += "p=next(a.split('=',1)[1] for a in sys.argv if a.startswith('--junitxml='))\n"
    code += "pathlib.Path(p).write_text('<testsuites><testsuite tests=\"7\" failures=\"0\" errors=\"0\" skipped=\"0\"/></testsuites>')\nprint('Total coverage: 77.25%')\n"
    if tests == 'fail': code += 'sys.exit(4)\n'
    (root/'pytest.py').write_text(code)
    (root/'research/protocols').mkdir(parents=True)
    (root/'research/results/nonpid_transfer').mkdir(parents=True)
    (root/'research/results/calibration_runtime_sources').mkdir(parents=True)
    (root/'research/protocols/recorded_evidence_audit_v0100.json').write_text(json.dumps({'source_hashes': {}}))
    (root/'research/results/nonpid_transfer/report.json').write_text(json.dumps({'study_id':'synthetic','artifacts':{},'raw_sha256':hashlib.sha256(b'raw').hexdigest(), 'accounting':{'actual_objective_evaluations':13},'acceptance':{}}))
    rawpath = root/'research/results/nonpid_transfer/raw.json.gz';rawpath.write_bytes(b'raw')
    reportpath = root/'research/results/nonpid_transfer/report.json'
    inputs={'research/results/nonpid_transfer/report.json': hashlib.sha256(reportpath.read_bytes()).hexdigest(),
            'research/results/nonpid_transfer/raw.json.gz': hashlib.sha256(b'raw').hexdigest()}
    for name in ('original_machine_arrays.json','small_sample_arrays.json'):
        archive='research/results/calibration_runtime_sources/'+name+'.npz'
        (root/archive).write_bytes(b'fixture arrays')
        (root/'research/results/calibration_runtime_sources'/name).write_text(json.dumps({'input_hashes':inputs,'archive':archive,
            'archive_sha256':hashlib.sha256(b'fixture arrays').hexdigest(),'primary_archive_sha256':hashlib.sha256(b'fixture arrays').hexdigest()}))
    code = "import json,pathlib,sys,subprocess,hashlib\nfrom datetime import datetime,timezone\nif '--list-ids' in sys.argv:\n print(json.dumps(['synthetic:claims']));sys.exit(0)\n"
    code += "protocol='research/protocols/recorded_evidence_audit_v0100.json'\nsources={protocol:hashlib.sha256(pathlib.Path(protocol).read_bytes().replace(b'\\r\\n',b'\\n')).hexdigest()}\nrevision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()\n"
    code += "for directory,key in [('recorded_transfer_verification','original_numeric_manifest'),('recorded_recalibration_verification','original_supplement_manifest')]:\n p=pathlib.Path('.local-audit')/directory;p.mkdir(parents=True,exist_ok=True)\n r={'started_utc':datetime.now(timezone.utc).isoformat(),'status':'passed','ok':True,'strict_cpu_replay_proven':False,'audit_execution':{'git_revision':revision,'source_hashes':sources},key:json.loads(pathlib.Path('research/results/calibration_runtime_sources/'+('original_machine_arrays.json' if 'transfer' in directory else 'small_sample_arrays.json')).read_text()),'audit_type':'original_recorded_evidence' if 'transfer' in directory else 'original_recorded_recalibration_evidence','study_id':'synthetic','rows':9,'recorded_timings_preserved':True,'gradient_steps':0,'additional_verification_objective_evaluations':13 if 'transfer' in directory else 0,'raw_sha256':hashlib.sha256(b'raw').hexdigest(),'accounting':{'actual_objective_evaluations':13},'acceptance':{}}\n p.joinpath('fixture.json').write_text(json.dumps(r))\n"
    code += "print(json.dumps([{'id':'synthetic:claims','ok':"+('False' if claims == 'fail' else 'True')+"}]))\n"
    (root/'scripts/16_check_claims.py').write_text(code)
    git(root, 'add', '.'); git(root, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'tiny fixture')
    git(root, 'tag', 'fixture')
    return root


def args(root, destination, **kwargs):
    return SimpleNamespace(destination=destination, source=root, ref='fixture', report=None,
                           from_dir=None, verify=kwargs.get('verify', False))


def test_prepare_real_full_clone_refuses_existing_destination(tmp_path):
    source = tiny_repo(tmp_path); destination = tmp_path/'new'
    result = reproducer.reproduce(args(source, destination))
    assert result['ok'] and result['prepared'] and not result['verified']
    assert result['actual_HEAD'] == git(source, 'rev-parse', 'HEAD')
    assert git(destination, 'rev-parse', '--is-shallow-repository') == 'false'
    assert result['tracked_content_unchanged'] and result['verification_accounting']['additional_objective_evaluations'] == 0
    assert result['commands'][-1]['argv'][1:] == ['scripts/59_research_data.py','--root', str(destination), '--fetch','all']
    with pytest.raises(ValueError, match='already exists'): reproducer.reproduce(args(source, destination))
    assert (source/'tracked.txt').read_text() == 'untouched'


def test_cleaned_prepare_restores_data_before_pinned_history_without_changing_refs(tmp_path):
    source=tiny_repo(tmp_path,history_cleaned=True);destination=tmp_path/'cleaned_prepare'
    result=reproducer.reproduce(args(source,destination))
    assert result['ok'] and result['prepared'] and result['history_cleaned']
    assert result['historical_sources']['capsule_sha256']=='c'*64
    assert result['historical_source_refs_unchanged'] and result['tracked_content_unchanged']
    assert result['commands'][-2]['argv'][1]==reproducer.RESTORE
    assert result['commands'][-1]['argv'][1]==reproducer.HISTORY_RESTORE
    assert result['verification_accounting']['additional_objective_evaluations']==0


@pytest.mark.parametrize('failure',['fail','hash','gradient','mutation','refs'])
def test_cleaned_history_failure_blocks_tests_claims_and_prepared_state(tmp_path,failure):
    source=tiny_repo(tmp_path,history_cleaned=True,history_restore=failure)
    result=reproducer.reproduce(args(source,tmp_path/'bad_history',verify=True))
    assert result['ok'] is False and result['prepared'] is False and result['verified'] is False
    assert not any('pytest' in row['argv'] or 'scripts/16_check_claims.py' in row['argv'] for row in result['commands'])
    assert result['verification_accounting']['additional_objective_evaluations']==0


def test_cleaned_verify_keeps_all_existing_receipt_bindings(tmp_path):
    source=tiny_repo(tmp_path,history_cleaned=True)
    result=reproducer.reproduce(args(source,tmp_path/'cleaned_verified',verify=True))
    assert result['ok'] and result['verified'] and result['historical_source_refs_unchanged']
    assert result['pytest']['tests']==7 and result['claims']['total']==1
    assert result['verification_accounting']['additional_objective_evaluations']==13


def test_verify_records_actual_synthetic_counts_logs_and_receipts(tmp_path):
    source = tiny_repo(tmp_path); destination = tmp_path/'verified'
    result = reproducer.reproduce(args(source, destination, verify=True))
    assert result['ok'] and result['verified'] and result['status'] == 'verified'
    assert result['pytest']['tests'] == 7 and result['pytest']['coverage_percent'] == 77.25
    assert result['claims']['total'] == 1 and result['verification_accounting']['additional_objective_evaluations'] == 13
    assert all(row['returncode'] == 0 for row in result['commands'])
    assert json.loads((destination/'.local-audit/reproduction_v0101.json').read_text())['verified']


@pytest.mark.parametrize('stage', ['restore','tests','claims','mutation'])
def test_failures_never_become_pass_or_skip(tmp_path, stage):
    source = tiny_repo(tmp_path, restore='mutation' if stage == 'mutation' else ('fail' if stage == 'restore' else 'pass'),
                       tests='fail' if stage == 'tests' else 'pass', claims='fail' if stage == 'claims' else 'pass')
    result = reproducer.reproduce(args(source, tmp_path/'failure', verify=True))
    assert result['ok'] is False and result['verified'] is False and result['status'] == 'failed'
    if stage == 'mutation': assert result['tracked_content_unchanged'] is False


def test_report_cannot_overwrite_checkout_and_remote_ref_is_fixed(tmp_path):
    source = tiny_repo(tmp_path)
    value = args(source, tmp_path/'new'); value.report = tmp_path/'new/.git/config'
    with pytest.raises(ValueError, match='under .local-audit'): reproducer.reproduce(value)
    value = args(source, tmp_path/'new'); value.source = None
    with pytest.raises(ValueError, match='requires explicit local'): reproducer.reproduce(value)


def test_junit_counts_require_no_skips_and_real_coverage(tmp_path):
    xml = tmp_path/'test.xml'; xml.write_text('<testsuites><testsuite tests="3" skipped="1"/></testsuites>')
    with pytest.raises(ValueError): reproducer.pytest_results(xml, 'Total coverage: 90%')
    xml.write_text('<testsuites><testsuite tests="3"/></testsuites>')
    with pytest.raises(ValueError): reproducer.pytest_results(xml, '...')


def test_real_pytest_selector_environment_is_cleared(tmp_path, monkeypatch):
    source = tiny_repo(tmp_path)
    (source/'pytest.py').unlink()
    (source/'tests').mkdir()
    (source/'src/fixture_subject.py').write_text('def value():\n    return 7\n')
    (source/'tests/test_two.py').write_text('from fixture_subject import value\ndef test_one():\n    assert value()==7\ndef test_two():\n    assert value()==7\n')
    git(source, 'add', '-A'); git(source, '-c','user.name=Fixture','-c','user.email=test@example.invalid','commit','-qm','real pytest pair')
    git(source, 'tag', '-f', 'fixture')
    monkeypatch.setenv('PYTEST_ADDOPTS', '-k test_one')
    monkeypatch.setenv('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
    result = reproducer.reproduce(args(source, tmp_path/'real_tests', verify=True))
    assert result['ok'], result.get('error', result.get('finalization_error'))
    assert result['pytest']['tests'] == 2
    assert 'PYTEST_ADDOPTS' in result['removed_environment_variable_names']
    assert 'PYTEST_DISABLE_PLUGIN_AUTOLOAD' in result['removed_environment_variable_names']


def test_receipt_failure_missing_kind_and_raw_mutation_rejected(tmp_path):
    source=tiny_repo(tmp_path);destination=tmp_path/'receipt_contract'
    result=reproducer.reproduce(args(source,destination,verify=True))
    assert result['ok']
    receipts=result['verification_accounting']['receipts']
    with pytest.raises(ValueError,match='Missing complete'):
        reproducer.verify_receipt_bindings(destination,receipts[:1],result['actual_HEAD'],result['started_utc'])
    main=next(row for row in receipts if '/recorded_transfer_verification/' in row['path'])
    path=destination/main['path'];original=path.read_bytes()
    for field,value in [('ok',False),('raw_sha256','0'*64),('audit_type','wrong')]:
        modified=json.loads(original);modified[field]=value;path.write_text(json.dumps(modified))
        current=reproducer.receipt_costs(destination,{})['receipts']
        with pytest.raises(ValueError):
            reproducer.verify_receipt_bindings(destination,current,result['actual_HEAD'],result['started_utc'])
        path.write_bytes(original)


def test_source_change_after_receipts_preserves_failed_run_accounting(tmp_path):
    source=tiny_repo(tmp_path)
    script=source/'scripts/16_check_claims.py'
    with script.open('a') as stream:
        stream.write("pathlib.Path('tracked.txt').write_text('changed after charged audit')\n")
    git(source,'add','.')
    git(source,'-c','user.name=Fixture','-c','user.email=test@example.invalid','commit','-qm','charged audit mutates source')
    git(source,'tag','-f','fixture')
    result=reproducer.reproduce(args(source,tmp_path/'charged_failure',verify=True))
    assert result['status']=='failed' and result['ok'] is False and result['verified'] is False
    assert result['tracked_content_unchanged'] is False
    assert result['verification_accounting']['additional_objective_evaluations']==13
    assert len(result['verification_accounting']['receipts'])==2
    saved=json.loads((tmp_path/'charged_failure/.local-audit/reproduction_v0101.json').read_text())
    assert saved['verification_accounting']['additional_objective_evaluations']==13
