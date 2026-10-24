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
