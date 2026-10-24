"""Real tiny release ZIPs restore original bytes, never Git objects or simulations."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import zipfile
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('historical_data_restore_test',ROOT/'scripts/64_restore_historical_data.py')
history=importlib.util.module_from_spec(spec);spec.loader.exec_module(history)
data=history.library(ROOT)


def zip_contract(directory,asset,payloads,legacy=False):
    target=directory/asset;rows=[]
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,value in payloads.items():
            info=zipfile.ZipInfo(name);info.create_system=3;info.external_attr=(stat.S_IFREG|0o644)<<16
            archive.writestr(info,value)
            rows.append({'path':name,'size_bytes':len(value),'sha256':hashlib.sha256(value).hexdigest(),
                'install':False if legacy else name.startswith('research/results/'),
                'source':{'kind':'git_blob','revision':'1'*40,'oid':history.blob_oid(value)}})
    return {'asset':asset,'url':history.URL if legacy else data._expected_url('evidence',asset),
        'size_bytes':target.stat().st_size,'sha256':data.digest(target),'files':rows}


def fixture(tmp_path):
    assets=tmp_path/'assets';assets.mkdir();revision='1'*40
    current=b'{"current":2}\n';old=b'{"old":1}\n';old_oid=history.blob_oid(old);current_oid=history.blob_oid(current)
    metadata={'LICENSE':b'license\n','NOTICE.md':b'notice\n'}
    current_contract=zip_contract(assets,'research_evidence_v0.10.1.zip',{**metadata,'research/results/current.json':current})
    legacy=zip_contract(assets,history.ASSET,{**metadata,'objects/'+old_oid:old},True)
    manifest={'schema_version':1,'version':'0.10.1','repository':data.REPOSITORY,'hash_scope':'exact_bytes','source_revision':revision,
        'groups':{'evidence':current_contract}}
    index={'schema_version':1,'version':'0.10.1','asset':legacy,'tags':{'v-old':revision},
        'commits':{revision:{'research/results/current.json':current_oid,'research/results/old.json':old_oid}},
        'blobs':{current_oid:{'kind':'research_data','paths':['research/results/current.json'],'group':'evidence','member':'research/results/current.json',
                'size_bytes':len(current),'sha256':hashlib.sha256(current).hexdigest()},
            old_oid:{'kind':'legacy_archive','paths':['research/results/old.json'],'member':'objects/'+old_oid,
                'size_bytes':len(old),'sha256':hashlib.sha256(old).hexdigest()}}}
    return assets,manifest,index


def restore(tmp_path,assets,manifest,index,commit='v-old'):
    return history.restore(ROOT,commit,tmp_path/'restored',assets,index=index,data_manifest=manifest)


def test_real_zip_roundtrip_tag_and_original_blob_oids(tmp_path):
    assets,manifest,index=fixture(tmp_path)
    result=restore(tmp_path,assets,manifest,index)
    assert result['ok'] and result['file_count']==2 and result['objective_evaluations']==result['gradient_steps']==0
    assert (tmp_path/'restored/research/results/old.json').read_bytes()==b'{"old":1}\n'
    for row in result['files']:
        assert history.blob_oid((tmp_path/'restored'/row['path']).read_bytes())==row['oid']
    with pytest.raises(ValueError,match='already exists'):restore(tmp_path,assets,manifest,index)


@pytest.mark.parametrize('mode',['whole_corrupt','wrong_oid','traversal','formal','unknown_commit','unknown_url'])
def test_corrupt_identity_path_commit_and_url_fail_without_destination(tmp_path,mode):
    assets,manifest,index=fixture(tmp_path);commit='v-old'
    if mode=='whole_corrupt':
        path=assets/history.ASSET;path.write_bytes(path.read_bytes()+b'corrupt')
    elif mode=='wrong_oid':
        old=index['commits']['1'*40]['research/results/current.json'];row=index['blobs'].pop(old)
        index['blobs']['0'*40]=row
        index['commits']['1'*40]['research/results/current.json']='0'*40
    elif mode in {'traversal','formal'}:
        entries=index['commits']['1'*40];old=entries.pop('research/results/old.json')
        name='../outside.json' if mode=='traversal' else 'research/results/nonpid_transfer/model_101.json'
        entries[name]=old;index['blobs'][old]['paths']=[name]
    elif mode=='unknown_commit':commit='2'*40
    else:index['asset']['url']='https://example.invalid/archive.zip'
    with pytest.raises(ValueError):restore(tmp_path,assets,manifest,index,commit)
    assert not (tmp_path/'restored').exists()


def test_all_members_verified_even_unselected_license_and_no_partial_output(tmp_path):
    assets,manifest,index=fixture(tmp_path)
    index['asset']['files'][0]['sha256']='0'*64
    with pytest.raises(ValueError,match='Member SHA'):restore(tmp_path,assets,manifest,index)
    assert not (tmp_path/'restored').exists()


def test_download_fixed_url_and_redirect_host_boundary(tmp_path):
    assets,_,index=fixture(tmp_path);payload=(assets/history.ASSET).read_bytes();seen=[]
    class Response(io.BytesIO):
        headers={}
        def geturl(self):return 'https://release-assets.githubusercontent.com/public/fixed'
    class Opener:
        def open(self,request,timeout):seen.append(request.full_url);return Response(payload)
    target=tmp_path/'download.zip'
    history.download_legacy(index['asset'],target,data,Opener())
    assert seen==[history.URL] and target.read_bytes()==payload
    bad=copy.deepcopy(index['asset']);bad['url']='http://localhost/private'
    with pytest.raises(ValueError):history.download_legacy(bad,tmp_path/'never.zip',data,Opener())
    class BadResponse(Response):
        def geturl(self):return 'https://example.invalid/redirect'
    class BadOpener:
        def open(self,request,timeout):return BadResponse(payload)
    with pytest.raises(ValueError):history.download_legacy(index['asset'],tmp_path/'bad.zip',data,BadOpener())


def metadata_derivative_fixture(tmp_path):
    assets,manifest,index=fixture(tmp_path)
    name='research/results/current.json';revision='1'*40
    original=b'{"J":1.25,"input":[0,1,1],"gains":[2,3,4],"metadata":{"path":"C:/fixtures/plant.slx"}}\n'
    published=original.replace(b'C:/fixtures/plant.slx',b'benchmark/plant.slx')
    original_oid=history.blob_oid(original);public_oid=history.blob_oid(published)
    old_key=index['commits'][revision][name];index['blobs'].pop(old_key)
    contract=zip_contract(assets,'research_evidence_v0.10.1.zip',
        {'LICENSE':b'license\n','NOTICE.md':b'notice\n',name:published})
    member=next(row for row in contract['files'] if row['path']==name)
    member['source'].update(kind='deidentified_git_blob',original_oid=original_oid,
        transformation='metadata_only_deidentification')
    manifest['groups']['evidence']=contract
    index['commits'][revision][name]=original_oid
    index['blobs'][original_oid]={'kind':'research_data','paths':[name],'group':'evidence','member':name,
        'size_bytes':len(published),'sha256':hashlib.sha256(published).hexdigest(),'public_oid':public_oid}
    return assets,manifest,index,name,original,published,original_oid,public_oid


def test_historical_derivative_restores_new_metadata_bytes_and_reports_old_and_public_oids(tmp_path):
    assets,manifest,index,name,original,published,original_oid,public_oid=metadata_derivative_fixture(tmp_path)
    result=restore(tmp_path,assets,manifest,index)
    assert (tmp_path/'restored'/name).read_bytes()==published
    record=next(row for row in result['files'] if row['path']==name)
    assert record['oid']==public_oid and record['original_oid']==original_oid and record['deidentified']
    assert history.blob_oid(published)==public_oid != history.blob_oid(original)
    left,right=json.loads(original),json.loads(published)
    left.pop('metadata');right.pop('metadata')
    assert left==right=={'J':1.25,'input':[0,1,1],'gains':[2,3,4]}
    assert (tmp_path/'restored/research/results/old.json').read_bytes()==b'{"old":1}\n'


@pytest.mark.parametrize('tamper',['public_oid','missing_public_oid','contract_public_oid','missing_original_oid','wrong_original_oid'])
def test_historical_derivative_false_public_or_original_identity_leaves_no_output(tmp_path,tamper):
    assets,manifest,index,name,_,_,original_oid,public_oid=metadata_derivative_fixture(tmp_path)
    source=next(row for row in manifest['groups']['evidence']['files'] if row['path']==name)['source']
    if tamper=='public_oid':index['blobs'][original_oid]['public_oid']='0'*40
    elif tamper=='missing_public_oid':index['blobs'][original_oid].pop('public_oid')
    elif tamper=='contract_public_oid':source['oid']='0'*40
    elif tamper=='missing_original_oid':source.pop('original_oid')
    else:
        # Correct ZIP/member/public pins must not authorize a fabricated original tree identity.
        index['commits']['1'*40][name]='0'*40
        index['blobs']['0'*40]=index['blobs'].pop(original_oid)
    with pytest.raises(ValueError):restore(tmp_path,assets,manifest,index)
    assert not (tmp_path/'restored').exists()
    assert not list(tmp_path.glob('.historical-data-stage-*'))


def legacy_metadata_derivative_fixture(tmp_path):
    assets,manifest,index=fixture(tmp_path)
    name='research/results/old.json';revision='1'*40
    original=b'{"J":1.25,"input":[0,1],"metadata":{"path":"C:/fixtures/legacy.slx"}}\n'
    published=original.replace(b'C:/fixtures/legacy.slx',b'benchmark/legacy.slx')
    original_oid=history.blob_oid(original);public_oid=history.blob_oid(published)
    index['blobs'].pop(index['commits'][revision][name])
    member='objects/'+original_oid
    contract=zip_contract(assets,history.ASSET,{'LICENSE':b'license\n','NOTICE.md':b'notice\n',member:published},True)
    binding=next(row for row in contract['files'] if row['path']==member)
    binding.update(original_oid=original_oid,public_oid=public_oid)
    index['asset']=contract;index['commits'][revision][name]=original_oid
    index['blobs'][original_oid]={'kind':'legacy_archive','paths':[name],'member':member,
        'size_bytes':len(published),'sha256':hashlib.sha256(published).hexdigest(),'public_oid':public_oid}
    return assets,manifest,index,name,original,published,original_oid,public_oid,binding


def test_legacy_metadata_derivative_has_explicit_original_and_public_binding(tmp_path):
    assets,manifest,index,name,original,published,original_oid,public_oid,_=legacy_metadata_derivative_fixture(tmp_path)
    result=restore(tmp_path,assets,manifest,index)
    record=next(row for row in result['files'] if row['path']==name)
    assert record['original_oid']==original_oid and record['oid']==public_oid and record['deidentified']
    assert (tmp_path/'restored'/name).read_bytes()==published
    left,right=json.loads(original),json.loads(published)
    left.pop('metadata');right.pop('metadata')
    assert left==right=={'J':1.25,'input':[0,1]}
    assert (tmp_path/'restored/research/results/current.json').read_bytes()==b'{"current":2}\n'


@pytest.mark.parametrize('tamper',['missing_original','wrong_original','wrong_public','missing_public'])
def test_legacy_derivative_missing_or_false_member_binding_has_no_output(tmp_path,tamper):
    assets,manifest,index,_,_,_,_,_,binding=legacy_metadata_derivative_fixture(tmp_path)
    if tamper=='missing_original':binding.pop('original_oid')
    elif tamper=='wrong_original':binding['original_oid']='0'*40
    elif tamper=='missing_public':binding.pop('public_oid')
    else:binding['public_oid']='0'*40
    with pytest.raises(ValueError,match='binding differs'):restore(tmp_path,assets,manifest,index)
    assert not (tmp_path/'restored').exists()
    assert not list(tmp_path.glob('.historical-data-stage-*'))
