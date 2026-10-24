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


def test_binary_weights_cannot_use_text_checkout_exception():
    for name in ('models/head.pt', 'models/head.mat', 'models/head.onnx', 'assets/view.png', 'unknown.bin'):
        assert not verify.checkout_equal(name, b'raw\r\n\0tail', b'raw\n\0tail')
    assert not verify.checkout_equal('models/head.pt', b'raw\r\ntail', b'raw\ntail')
    assert verify.checkout_equal('scripts/source.py', b'line\r\n', b'line\n')
    assert not verify.checkout_equal('scripts/source.py', b'changed\r\n', b'line\n')


def commit(root):
    subprocess.run(['git','-C',str(root),'add','.'],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=test@example.invalid','commit','-qm','fixture'],check=True)


def fixture(tmp_path, defect=None):
    root=tmp_path/'git';root.mkdir();subprocess.run(['git','init','-q',str(root)],check=True)
    for name in ('README.md','NOTICE.md','LICENSE','scripts/code.py','models/formal.pt','research/protocols/study.json'):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'formal public source\n')
    data={'research/results/raw.npz':b'fake numeric binary\0','research/results/report.json':b'{"measured":3}\n',
          'research/results/nonpid_transfer/model_101.json': b'{"formal_weight":1}\n'}
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
    manifest=root/verify.MANIFEST;manifest.parent.mkdir(parents=True,exist_ok=True)
    manifest.write_text(json.dumps({'groups':{'evidence':{'asset':'fixture.zip','size_bytes':123,'files':rows}}}))
    commit(root)
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
