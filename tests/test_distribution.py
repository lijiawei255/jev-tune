"""Real tiny Git archives prove source/data separation and identity checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('distribution_check_test',ROOT/'scripts/61_check_distribution.py')
verify=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify)


@pytest.mark.parametrize('name,language',[('README.md','en'),('README.zh-CN.md','zh')])
def test_readme_distribution_intro_preserves_generated_summary(name,language):
    source=ROOT/'scripts/49_sync_shell_docs.py'
    summary_spec=importlib.util.spec_from_file_location('distribution_shell_summary',source)
    summary=importlib.util.module_from_spec(summary_spec);summary_spec.loader.exec_module(summary)
    body=(ROOT/name).read_text(encoding='utf-8')
    rendered=summary.documents(ROOT)[name]
    start=f'<!-- transfer-shell:{language}:start -->'
    end=f'<!-- transfer-shell:{language}:end -->'
    observed_block=body.split(start,1)[1].split(end,1)[0]
    expected_block=rendered.split(start,1)[1].split(end,1)[0]
    assert observed_block==expected_block, 'Distribution edits changed recorded scientific summary'
    assert body==rendered, 'Distribution intro violates generated README layout'


def test_binary_weights_cannot_use_text_checkout_exception():
    for name in ('models/head.pt', 'models/head.mat', 'models/head.onnx', 'assets/view.png', 'unknown.bin'):
        assert not verify.checkout_equal(name, b'raw\r\n\0tail', b'raw\n\0tail')
    assert not verify.checkout_equal('models/head.pt', b'raw\r\ntail', b'raw\ntail')
    assert verify.checkout_equal('scripts/source.py', b'line\r\n', b'line\n')
    assert not verify.checkout_equal('scripts/source.py', b'changed\r\n', b'line\n')


def commit(root):
    subprocess.run(['git','-C',str(root),'add','.'],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=test@example.invalid','commit','-qm','fixture'],check=True)


def fixture(tmp_path, defect=None, *, history_cleaned=False):
    root=tmp_path/'git';root.mkdir();subprocess.run(['git','init','-q',str(root)],check=True)
    for name in ('README.md','NOTICE.md','LICENSE','scripts/code.py','models/formal.pt','research/protocols/study.json'):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'formal public source\n')
    data={'research/results/raw.npz':b'fake numeric binary\0','research/results/report.json':b'{"measured":3}\n',
          'research/results/nonpid_transfer/model_101.json': b'{"formal_weight":1}\n'}
    if history_cleaned:
        for name in verify.RETAINED_NONPID:
            data.setdefault(name, (json.dumps({'formal':name})+'\n').encode())
    rows=[]
    for name,value in data.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
        rows.append({'path':name,'install':True,'size_bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()})
    if defect=='manifest': rows.pop(1)
    attrs=[name+' export-ignore' for name in data if name not in verify.RETAINED_NONPID]
    if defect=='exclude':attrs.pop()
    if defect=='formal':attrs.append('models/formal.pt export-ignore')
    if defect=='nonpid':attrs.append('research/results/nonpid_transfer/model_101.json export-ignore')
    (root/'.gitattributes').write_text('\n'.join(attrs)+'\n')
    if history_cleaned:
        # Preserve authentic original trees as dangling proof objects, while
        # the only reachable branch contains source and the six formal files.
        commit(root)
        original=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        old_branch=subprocess.check_output(['git','-C',str(root),'symbolic-ref','--short','HEAD'],text=True).strip()
        for row in rows:
            oid=subprocess.check_output(['git','-C',str(root),'rev-parse',original+':'+row['path']],text=True).strip()
            row['source']={'kind':'git_blob','revision':original,'oid':oid}
        subprocess.run(['git','-C',str(root),'checkout','--orphan','cleaned'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(root),'rm','-r','--cached','.'],check=True,capture_output=True)
        (root/'.gitignore').write_text('\n'.join(name for name in data if name not in verify.RETAINED_NONPID)+'\n')
        historical=root/'research/distribution/historical_sources_v0101.json'
        historical.parent.mkdir(parents=True,exist_ok=True)
        historical.write_text(json.dumps({'schema_version':1,'asset':'historical_sources_v0.10.1.zip',
            'url':'https://github.com/lijiawei255/jev-tune/releases/download/v0.10.1/historical_sources_v0.10.1.zip',
            'size_bytes':1,'sha256':'0'*64,'requirements':{original:['LICENSE','NOTICE.md']}}))
    manifest=root/verify.MANIFEST;manifest.parent.mkdir(parents=True,exist_ok=True)
    descriptor={'history_cleaned':history_cleaned,'groups':{'evidence':{'asset':'fixture.zip','size_bytes':123,'files':rows}}}
    if history_cleaned:descriptor['source_revision']=original
    manifest.write_text(json.dumps(descriptor))
    commit(root)
    if history_cleaned:
        subprocess.run(['git','-C',str(root),'branch','-D',old_branch],check=True,capture_output=True)
    return root


def test_real_git_archive_is_small_and_keeps_formal_sources(tmp_path):
    root=fixture(tmp_path)
    result=verify.check(root)
    assert result['ok'] and result['tracked_research_result_files']==3 and result['exported_data_files']==2
    assert result['source_archive_files']==9 and result['source_archive_size_bytes']>0
    assert result['groups']['evidence']['archive_size_bytes']==123
    assert result['objective_evaluations']==0
    subprocess.run(['git','-C',str(root),'tag','candidate'],check=True)
    assert verify.check(root,'candidate')['actual_commit']==result['actual_commit']


@pytest.mark.parametrize('defect',['manifest','exclude','formal','nonpid'])
def test_missing_contract_or_formal_source_exclusion_fails(tmp_path,defect):
    root=fixture(tmp_path,defect)
    with pytest.raises(ValueError):verify.check(root)


@pytest.mark.parametrize('path',['scripts/code.py','research/results/raw.npz'])
def test_worktree_numeric_or_source_mutation_fails(tmp_path,path):
    root=fixture(tmp_path);(root/path).write_bytes(b'mutation')
    with pytest.raises(ValueError):verify.check(root)


def test_committed_data_mutation_without_repin_fails(tmp_path):
    root=fixture(tmp_path);(root/'research/results/raw.npz').write_bytes(b'mutation');commit(root)
    with pytest.raises(ValueError,match='Git-blob identity'):verify.check(root)


def test_fixed_source_zip_budget_is_enforced_on_actual_bytes(tmp_path):
    import random
    root=fixture(tmp_path)
    (root/'models/formal.pt').write_bytes(random.Random(774).randbytes(5_000_001))
    commit(root)
    with pytest.raises(ValueError,match='5000000-byte budget'):verify.check(root)


def test_manifest_cannot_hide_formal_code_as_data(tmp_path):
    root=fixture(tmp_path)
    path=root/verify.MANIFEST;value=json.loads(path.read_text())
    code=(root/'scripts/code.py').read_bytes()
    value['groups']['evidence']['files'].append({'path':'scripts/code.py','install':True,'size_bytes':len(code),'sha256':hashlib.sha256(code).hexdigest()})
    path.write_text(json.dumps(value))
    with (root/'.gitattributes').open('a') as stream:stream.write('scripts/code.py export-ignore\n')
    commit(root)
    with pytest.raises(ValueError,match='Formal source/model'):verify.check(root)


def test_cleaned_source_history_keeps_six_formal_files_without_optional_git_blobs(tmp_path):
    root=fixture(tmp_path,history_cleaned=True)
    result=verify.check(root)
    assert result['history_cleaned'] is True and result['tracked_research_result_files']==6
    assert result['reachable_history_commits_checked']==1 and result['exported_data_files']==2
    assert result['original_tree_provenance']['ok'] and result['payloads_verified']
    assert subprocess.run(['git','-C',str(root),'cat-file','-e','HEAD:research/results/raw.npz'],capture_output=True).returncode!=0
    (root/'research/results/raw.npz').unlink()
    (root/'research/results/report.json').unlink()
    checked=verify.check(root)
    assert checked['ok'] and checked['payloads_verified'] is False  # Missing optional data is not missing source.
    assert set(checked['missing_optional_payload_files'])=={'research/results/raw.npz','research/results/report.json'}


@pytest.mark.parametrize('stage',['index','head','historical'])
def test_cleaned_mode_rejects_external_data_in_index_head_or_reachable_history(tmp_path,stage):
    root=fixture(tmp_path,history_cleaned=True)
    subprocess.run(['git','-C',str(root),'add','-f','research/results/raw.npz'],check=True)
    if stage!='index':
        commit(root)
    if stage=='historical':
        subprocess.run(['git','-C',str(root),'rm','--cached','research/results/raw.npz'],check=True)
        commit(root)
    with pytest.raises(ValueError,match='remains tracked|reachable history'):
        verify.check(root)


def test_cleaned_mode_formal_json_bytes_are_still_exactly_pinned(tmp_path):
    root=fixture(tmp_path,history_cleaned=True)
    (root/'research/results/nonpid_transfer/model_101.json').write_bytes(b'{"formal_weight":2}\n')
    with pytest.raises(ValueError,match='Local data bytes'):
        verify.check(root)


def test_cleaned_mode_requires_all_six_formal_members(tmp_path):
    root=fixture(tmp_path,history_cleaned=True)
    path=root/verify.MANIFEST;value=json.loads(path.read_text())
    value['groups']['evidence']['files']=[row for row in value['groups']['evidence']['files'] if row['path']!='research/results/nonpid_transfer/model_101.json']
    path.write_text(json.dumps(value));commit(root)
    with pytest.raises(ValueError,match='missing from manifest|six formal'):
        verify.check(root)


@pytest.mark.parametrize('repin_oid',[False,True])
def test_cleaned_restored_bytes_and_sha256_repin_cannot_fake_original_tree_oid(tmp_path,repin_oid):
    root=fixture(tmp_path,history_cleaned=True)
    changed=b'changed restored payload, with self-consistent SHA256'
    (root/'research/results/raw.npz').write_bytes(changed)
    path=root/verify.MANIFEST;value=json.loads(path.read_text())
    row=next(row for row in value['groups']['evidence']['files'] if row['path']=='research/results/raw.npz')
    row.update(size_bytes=len(changed),sha256=hashlib.sha256(changed).hexdigest())
    if repin_oid:
        row['source']['oid']=hashlib.sha1(b'blob '+str(len(changed)).encode()+b'\0'+changed).hexdigest()
    path.write_text(json.dumps(value));commit(root)
    with pytest.raises(ValueError,match='Git-blob OID|Origin tree/blob identity'):
        verify.check(root)
