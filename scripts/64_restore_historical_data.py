"""Restore one original experimental-data version to a new directory, without Git writes."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
INDEX='research/distribution/historical_data_v0101.json'
ASSET='historical_data_variants_v0.10.1.zip'
URL='https://github.com/lijiawei255/jev-tune/releases/download/v0.10.1/'+ASSET
FORMAL={f'research/results/nonpid_transfer/{kind}_{seed}.json' for kind in ('model','calibration') for seed in (101,202,303)}


def library(root):
    spec=importlib.util.spec_from_file_location('historical_data_release_library',Path(root)/'scripts/59_research_data.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def require(condition,message):
    if not condition:raise ValueError(message)


def blob_oid(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def validate_legacy(contract,data):
    require(contract.get('asset')==ASSET and contract.get('url')==URL,'Legacy asset is outside fixed official release')
    require(type(contract.get('size_bytes')) is int and 0<contract['size_bytes']<=data.MAX_ARCHIVE_BYTES,'Invalid legacy archive size')
    require(re.fullmatch('[0-9a-f]{64}',contract.get('sha256','')) is not None,'Invalid legacy archive hash')
    rows=contract.get('files');require(isinstance(rows,list) and rows,'Missing complete legacy member contract')
    names=set()
    for row in rows:
        name=data.safe_path(row['path']);require(name.casefold() not in names,'Duplicate legacy member');names.add(name.casefold())
        require(name in {'LICENSE','NOTICE.md'} or re.fullmatch('objects/[0-9a-f]{40}',name) is not None,'Unexpected legacy member')
        require(row.get('install') is False and type(row.get('size_bytes')) is int and 0<=row['size_bytes']<=data.MAX_EXPANDED_BYTES
                and re.fullmatch('[0-9a-f]{64}',row.get('sha256','')) is not None,'Invalid legacy member identity')
    require({'license','notice.md'}<=names and sum(row['size_bytes'] for row in rows)<=data.MAX_EXPANDED_BYTES,'Missing license/notice or oversized legacy group')
    return contract


def download_legacy(contract,target,data,opener=None):
    validate_legacy(contract,data)
    opener=urllib.request.build_opener(data._ReleaseRedirects()) if opener is None else opener
    request=urllib.request.Request(URL,headers={'User-Agent':'jev-tune-historical-data/0.10.1'})
    count=0;started=time.monotonic()
    with opener.open(request,timeout=data.HTTP_TIMEOUT) as response,Path(target).open('xb') as stream:
        final=urllib.parse.urlsplit(response.geturl())
        require(final.scheme=='https' and final.hostname in {'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}
                and final.port in {None,443} and final.username is None and final.password is None,'Unsafe final release URL')
        length=response.headers.get('Content-Length');require(length is None or int(length)==contract['size_bytes'],'HTTP length differs')
        for chunk in iter(lambda:response.read(data.CHUNK),b''):
            count+=len(chunk);require(count<=contract['size_bytes'] and time.monotonic()-started<=data.DOWNLOAD_DEADLINE,'Download bound exceeded');stream.write(chunk)
    require(count==contract['size_bytes'] and data.digest(target)==contract['sha256'],'Downloaded legacy ZIP identity differs')


def restore(root,commit,destination,from_dir=None,*,index=None,data_manifest=None,opener=None):
    root=Path(root).resolve();destination=Path(destination).resolve()
    require(not destination.exists(),'Destination already exists; refuse overwrite')
    require(destination.parent.is_dir(),'Destination parent must already exist')
    data=library(root)
    index=json.loads((root/INDEX).read_text(encoding='utf-8')) if index is None else index
    require(index.get('schema_version')==1 and index.get('version')=='0.10.1','Unsupported historical data index')
    revision=index['tags'].get(commit,commit)
    require(re.fullmatch('[0-9a-f]{40}',revision) is not None and revision in index['commits'],'Unknown original commit/tag')
    manifest=data.load_manifest(root) if data_manifest is None else data.validate_manifest(data_manifest)
    selections=[];contracts={};folded=set()
    for name,identity in index['commits'][revision].items():
        data.safe_path(name)
        require(name.startswith('research/results/') and name not in FORMAL,'Destination is not an experimental record: '+name)
        require(name.casefold() not in folded,'Case-colliding restore destination');folded.add(name.casefold())
        require(re.fullmatch('[0-9a-f]{40}',identity) is not None and identity in index['blobs'],'Unknown original blob')
        row=index['blobs'][identity];require(name in row['paths'],'Historical blob/path contract differs')
        if row['kind']=='research_data':
            group=row['group'];require(group in {'current','historical','evidence'} and group in manifest['groups'],'Unknown current release-data group')
            contract=manifest['groups'][group]
        else:
            require(row['kind']=='legacy_archive' and row['member']=='objects/'+identity,'Unknown legacy blob kind/member')
            group='legacy';contract=validate_legacy(index['asset'],data)
        member=row['member'];data.safe_path(member)
        matches=[entry for entry in contract['files'] if entry['path']==member]
        require(len(matches)==1 and matches[0]['size_bytes']==row['size_bytes'] and matches[0]['sha256']==row['sha256'],'Historical/current member pin differs')
        contracts[group]=contract;selections.append((name,identity,row,group))
    require(selections,'Original commit has no removed experimental records')
    # Temporary sibling staging is private; destination appears only after all ZIPs and all selected OIDs pass.
    with tempfile.TemporaryDirectory(prefix='.historical-data-stage-',dir=destination.parent) as temporary:
        stage=Path(temporary);archives={}
        for group,contract in contracts.items():
            archive=Path(from_dir).resolve()/contract['asset'] if from_dir is not None else stage/contract['asset']
            if from_dir is None:
                download_legacy(contract,archive,data,opener) if group=='legacy' else data.download(contract,archive,opener=opener)
            data.verify_archive(archive,contract);archives[group]=archive
        output=stage/'restored';output.mkdir();records=[]
        for name,identity,row,group in selections:
            target=data.destination(output,name);target.parent.mkdir(parents=True,exist_ok=True)
            hashed=hashlib.sha256();git_hash=hashlib.sha1(b'blob '+str(row['size_bytes']).encode()+b'\0');size=0
            with zipfile.ZipFile(archives[group]) as archive,archive.open(row['member']) as source,target.open('xb') as writer:
                for chunk in iter(lambda:source.read(data.CHUNK),b''):
                    size+=len(chunk);require(size<=row['size_bytes'],'Expanded original blob exceeds size')
                    hashed.update(chunk);git_hash.update(chunk);writer.write(chunk)
            require(size==row['size_bytes'] and hashed.hexdigest()==row['sha256'] and git_hash.hexdigest()==identity,'Restored original Git blob identity differs: '+name)
            records.append({'path':name,'oid':identity,'sha256':hashed.hexdigest(),'size_bytes':size})
        require(not destination.exists(),'Destination appeared during restore; refuse overwrite')
        output.rename(destination)
    return {'ok':True,'operation':'restore_historical_data','requested_commit':commit,'original_commit':revision,
            'destination':str(destination),'files':records,'file_count':len(records),'total_bytes':sum(row['size_bytes'] for row in records),
            'verified_archives':{contract['asset']:contract['sha256'] for contract in contracts.values()},'offline':from_dir is not None,
            'objective_evaluations':0,'gradient_steps':0,'scope':'Original experimental files restored outside Git; no model execution, refs or Git object writes'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--from-dir',type=Path)
    args=parser.parse_args()
    try:result=restore(args.root,args.commit,args.destination,args.from_dir)
    except (ValueError,KeyError,OSError,zipfile.BadZipFile) as exc:
        print(json.dumps({'ok':False,'error':type(exc).__name__+': '+str(exc),'objective_evaluations':0,'gradient_steps':0}));raise SystemExit(1)
    print(json.dumps(result,indent=2))
