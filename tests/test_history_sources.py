"""Actual partial Git object import; no scientific tests or historical data payloads."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import zipfile
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('historical_source_proof_test',ROOT/'scripts/history_sources.py')
history=importlib.util.module_from_spec(spec);spec.loader.exec_module(history)


def commit(root,message):
    history.git(root,'add','.')
    history.git(root,'-c','user.name=Public fixture','-c','user.email=public@example.invalid','commit','-qm',message)
    return history.git(root,'rev-parse','HEAD').decode().strip()


def fixture(tmp_path):
    original=tmp_path/'original';original.mkdir();history.git(original,'init','-q')
    (original/'scripts').mkdir();(original/'research/results').mkdir(parents=True)
    (original/'.gitattributes').write_bytes(b'scripts/proof.py -text\n')
    (original/'scripts/proof.py').write_bytes(b'print("original source")\n')
    (original/'research/results/private.slx').write_bytes(b'PRIVATE MODEL NEVER INCLUDE')
    old=commit(original,'original metadata retained')
    # Unrelated new real history has no old refs or objects.
    clean=tmp_path/'clean';clean.mkdir();history.git(clean,'init','-q');(clean/'README.md').write_text('clean current source')
    commit(clean,'new public root')
    requirements={old:['scripts/proof.py']};capsule=tmp_path/'sources.zip'
    result=history.build(original,requirements,capsule)
    return original,clean,old,requirements,capsule,result


def test_real_original_git_show_and_explicit_archive_after_partial_import(tmp_path):
    original,clean,old,requirements,capsule,result=fixture(tmp_path)
    with pytest.raises(ValueError):history.git(clean,'show',old+':scripts/proof.py')
    before=history.git(clean,'log','--format=%H')
    restored=history.restore(clean,capsule,expected_sha256=result['sha256'],requirements=requirements)
    assert restored['ok'] and restored['source_paths']==1 and restored['objective_evaluations']==0
    assert history.git(clean,'show',old+':scripts/proof.py')==b'print("original source")\n'
    archive=history.git(clean,'-c','core.autocrlf=false','archive','--format=zip',old,'--','scripts/proof.py')
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:assert zipped.read('scripts/proof.py')==b'print("original source")\n'
    with pytest.raises(ValueError):history.git(clean,'show',old+':research/results/private.slx')
    assert history.git(clean,'log','--format=%H')==before
    assert list((clean/'.git/objects/pack').glob('*.promisor'))
    blob_types=[row['type'] for row in result['manifest']['objects'].values()]
    assert blob_types.count('blob')==2


@pytest.mark.parametrize('mode',['wrong_pin','unknown_commit','missing_path','tamper','extra_blob'])
def test_fake_missing_tampered_or_extra_objects_never_pass(tmp_path,mode):
    original,clean,old,requirements,capsule,result=fixture(tmp_path)
    pin=result['sha256']
    if mode=='wrong_pin':pin='0'*64
    elif mode=='unknown_commit':requirements={'0'*40:['scripts/proof.py']}
    elif mode=='missing_path':requirements={old:['scripts/absent.py']}
    else:
        with zipfile.ZipFile(capsule) as archive:
            manifest=json.loads(archive.read('manifest.json'));pack=archive.read('sources.pack')
        if mode=='tamper':pack=pack[:-1]+bytes([pack[-1]^1])
        else:
            extra=history.git(original,'hash-object','-w','--stdin',data=b'PRIVATE payload') .decode().strip()
            identities=sorted(set(manifest['objects'])|{extra})
            pack=history.git(original,'pack-objects','--stdout',data=('\n'.join(identities)+'\n').encode())
            manifest['pack_sha256']=history.sha(pack)
            manifest['objects'][extra]={'type':'blob','size':len(b'PRIVATE payload'),'sha256':history.sha(b'PRIVATE payload')}
        with zipfile.ZipFile(capsule,'w') as archive:
            archive.writestr('manifest.json',json.dumps(manifest));archive.writestr('sources.pack',pack)
        pin=history.sha(capsule.read_bytes())
    with pytest.raises(ValueError):history.restore(clean,capsule,expected_sha256=pin,requirements=requirements)
    with pytest.raises(ValueError):history.git(clean,'show',old+':scripts/proof.py')


def test_forbidden_data_path_cannot_be_packaged(tmp_path):
    original,_,old,_,_,_=fixture(tmp_path)
    with pytest.raises(ValueError):history.build(original,{old:['research/results/private.slx']},tmp_path/'forbidden.zip')


def test_pinned_offline_restore_and_missing_asset(tmp_path):
    _,clean,_,requirements,capsule,result=fixture(tmp_path)
    assets=tmp_path/'assets';assets.mkdir();(assets/history.ASSET).write_bytes(capsule.read_bytes())
    config={'schema_version':1,'asset':history.ASSET,'url':history.URL,'size_bytes':capsule.stat().st_size,
            'sha256':result['sha256'],'requirements':requirements,'paths':result['manifest']['paths']}
    path=clean/history.PINNED_MANIFEST;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(config))
    assert history.restore_pinned(clean,assets)['offline'] is True
    (assets/history.ASSET).unlink()
    with pytest.raises(ValueError):history.restore_pinned(clean,assets)


def test_original_data_origin_oid_proof_needs_no_data_blob(tmp_path):
    original,clean,old,requirements,capsule,result=fixture(tmp_path)
    path=clean/history.PINNED_MANIFEST;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'schema_version':1,'asset':history.ASSET,'url':history.URL,'size_bytes':capsule.stat().st_size,
        'sha256':result['sha256'],'requirements':requirements}))
    history.restore(clean,capsule,expected_sha256=result['sha256'],requirements=requirements)
    identity=history.git(original,'rev-parse',old+':research/results/private.slx').decode().strip()
    manifest={'groups':{'evidence':{'files':[{'path':'research/results/private.slx','source':{'kind':'git_blob','revision':old,'oid':identity}}]}}}
    assert history.verify_origin_paths(clean,manifest)['origin_paths']==1
    with pytest.raises(ValueError):history.git(clean,'cat-file','blob',identity)
    manifest['groups']['evidence']['files'][0]['source']['oid']='0'*40
    with pytest.raises(ValueError,match='identity differs'):history.verify_origin_paths(clean,manifest)


def metadata_origin_fixture(tmp_path):
    original,clean,old,requirements,capsule,result=fixture(tmp_path)
    path=clean/history.PINNED_MANIFEST;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'schema_version':1,'asset':history.ASSET,'url':history.URL,
        'size_bytes':capsule.stat().st_size,'sha256':result['sha256'],'requirements':requirements}))
    history.restore(clean,capsule,expected_sha256=result['sha256'],requirements=requirements)
    original_oid=history.git(original,'rev-parse',old+':research/results/private.slx').decode().strip()
    published_oid=history.oid('blob',b'generic metadata derivative; dynamics unchanged')
    source={'kind':'deidentified_git_blob','revision':old,'oid':published_oid,'original_oid':original_oid,
        'transformation':'metadata_only_deidentification'}
    manifest={'groups':{'evidence':{'files':[{'path':'research/results/private.slx','source':source}]}}}
    return clean,old,original_oid,published_oid,manifest,source


def test_derivative_origin_proof_uses_authentic_original_tree_and_keeps_public_oid_separate(tmp_path):
    clean,old,original_oid,published_oid,manifest,source=metadata_origin_fixture(tmp_path)
    before=(history.git(clean,'rev-parse','HEAD'),history.git(clean,'for-each-ref'))
    assert original_oid != published_oid
    assert history.verify_origin_paths(clean,manifest)['origin_paths']==1
    assert history.git(clean,'ls-tree',old,'--','research/results/private.slx').decode().split()[2]==original_oid
    assert source['oid']==published_oid and source['original_oid']==original_oid
    for identity in (original_oid,published_oid):
        with pytest.raises(ValueError):history.git(clean,'cat-file','blob',identity)
    assert before==(history.git(clean,'rev-parse','HEAD'),history.git(clean,'for-each-ref'))
    assert not (clean/'research/results/private.slx').exists()


@pytest.mark.parametrize('tamper',['wrong_original','missing_original','fallback_to_original_as_public','plain_blob_override','malformed_public'])
def test_derivative_origin_cannot_fall_back_or_override_authentic_tree_oid(tmp_path,tamper):
    clean,_,original_oid,_,manifest,source=metadata_origin_fixture(tmp_path)
    if tamper=='wrong_original':source['original_oid']='0'*40
    elif tamper in {'missing_original','fallback_to_original_as_public'}:
        source.pop('original_oid')
        if tamper=='fallback_to_original_as_public':source['oid']=original_oid
    elif tamper=='plain_blob_override':
        source['kind']='git_blob';source['oid']='0'*40
        source['original_oid']=original_oid  # A plain blob must be checked by oid, not this override.
    else:source['oid']='invalid-public-identity'
    before=(history.git(clean,'rev-parse','HEAD'),history.git(clean,'for-each-ref'))
    with pytest.raises(ValueError):history.verify_origin_paths(clean,manifest)
    assert before==(history.git(clean,'rev-parse','HEAD'),history.git(clean,'for-each-ref'))
    assert not (clean/'research/results/private.slx').exists()
