"""Selected-path original Git source proofs, never a complete historical repository.

Promisor marks omitted parents/side branches as deliberately absent, not available
from a server. No refs, remotes, replacements or worktree files are installed.
Commit/tree metadata can contain original names/emails/file names; it is retained
as identity evidence and requires the publisher's separate metadata review.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile

MAX_BLOB = 1_000_000
MAX_PACK = 20_000_000
PREFIXES = ('scripts/','src/','tests/','matlab/','c/','research/protocols/','examples/denoise_transfer/')
SUFFIXES = {'.py','.m','.c','.h','.json','.md','.yml','.yaml'}
SCOPE = 'Selected-path original source proof only; not complete old history or complete fsck proof. Omitted objects are unavailable, with lazy fetch disabled. Original commit/tree metadata is retained.'


def require(condition, message):
    if not condition: raise ValueError(message)


def sha(data): return hashlib.sha256(data).hexdigest()


def git(root, *args, data=None):
    env=os.environ.copy();env['GIT_NO_LAZY_FETCH']='1';env['GIT_NO_REPLACE_OBJECTS']='1'
    completed=subprocess.run(['git','-C',str(root),*args],input=data,capture_output=True,env=env)
    require(completed.returncode==0, 'Git operation failed: '+repr(args)+' '+completed.stderr.decode('utf-8',errors='replace'))
    return completed.stdout


def source_path(name):
    p=PurePosixPath(name)
    require(isinstance(name,str) and (name.startswith(PREFIXES) or name in {'LICENSE','NOTICE.md'}) and '\\' not in name and ':' not in name
            and not p.is_absolute() and all(x not in {'','.','..','.git'} for x in name.split('/'))
            and (p.suffix.lower() in SUFFIXES or name=='LICENSE') and not name.startswith('research/results/'), 'Forbidden source path: '+str(name))
    return name


def oid(kind,data): return hashlib.sha1(kind.encode()+b' '+str(len(data)).encode()+b'\0'+data).hexdigest()


def tree_entries(data):
    result={};position=0
    while position<len(data):
        end=data.index(b' ',position);mode=data[position:end].decode('ascii')
        zero=data.index(b'\0',end);name=data[end+1:zero].decode('utf-8')
        require(name not in result and '/' not in name and name not in {'.','..'}, 'Invalid tree member')
        target=data[zero+1:zero+21];require(len(target)==20,'Truncated tree object')
        result[name]=(mode,target.hex());position=zero+21
    return result


def selected_closure(requirements, getter):
    needed=set();paths={}
    for revision,names in requirements.items():
        require(re.fullmatch('[0-9a-f]{40}',revision) is not None and isinstance(names,list) and names
                and names==sorted(set(names)), 'Invalid commit/path contract')
        kind,commit=getter(revision);require(kind=='commit' and len(commit)<=MAX_BLOB and oid(kind,commit)==revision,'Commit identity differs')
        require(commit.startswith(b'tree '),'Missing original root tree')
        tree=commit.split(b'\n',1)[0][5:].decode();needed.add(revision)
        def include_trees(identity):
            if identity in needed: return
            kind,data=getter(identity);require(kind=='tree' and len(data)<=MAX_BLOB,'Original tree topology missing/oversized');needed.add(identity)
            for tree_name,(mode,target) in tree_entries(data).items():
                if mode=='40000': include_trees(target)
                elif tree_name=='.gitattributes':
                    kind,attributes=getter(target)
                    require(mode in {'100644','100755'} and kind=='blob' and len(attributes)<=MAX_BLOB and b'\0' not in attributes,
                            'Invalid historical Git attributes')
                    attributes.decode('utf-8-sig');needed.add(target)
        include_trees(tree)
        paths[revision]={}
        for name in names:
            source_path(name);current=tree;parts=name.split('/')
            for index,part in enumerate(parts):
                kind,data=getter(current);require(kind=='tree','Missing original tree chain');needed.add(current)
                entries=tree_entries(data);require(part in entries,'Source path absent from original tree: '+name)
                mode,target=entries[part]
                if index<len(parts)-1:
                    require(mode=='40000','Non-tree ancestor: '+name);current=target
                else:
                    require(mode in {'100644','100755'},'Source path is not a regular file: '+name)
                    kind,value=getter(target);require(kind=='blob' and len(value)<=MAX_BLOB and b'\0' not in value,'Non-source/oversized blob: '+name)
                    value.decode('utf-8-sig');needed.add(target);paths[revision][name]={'oid':target,'sha256':sha(value),'size':len(value)}
    return needed,paths


def build(root,requirements,output):
    root,output=Path(root).resolve(),Path(output).resolve()
    require(not output.exists(),'Refuse to overwrite source capsule')
    requirements={key:sorted(set(value)) for key,value in sorted(requirements.items())}
    objects={}
    def getter(identity):
        if identity not in objects:
            kind=git(root,'cat-file','-t',identity).decode().strip()
            data=git(root,'cat-file',kind,identity)
            require(oid(kind,data)==identity,'Original object identity mismatch')
            objects[identity]=(kind,data)
        return objects[identity]
    needed,paths=selected_closure(requirements,getter)
    require(set(objects)==needed,'Unexpected object traversal')
    pack=git(root,'pack-objects','--stdout','--no-reuse-delta','--no-reuse-object',data=('\n'.join(sorted(needed))+'\n').encode())
    require(len(pack)<=MAX_PACK,'Oversized source capsule')
    manifest={'schema_version':1,'scope':SCOPE,'requirements':requirements,'paths':paths,'pack_sha256':sha(pack),
        'objects':{key:{'type':kind,'size':len(data),'sha256':sha(data)} for key,(kind,data) in sorted(objects.items())},
        'metadata_inventory':{'commits':sorted(key for key,(kind,_) in objects.items() if kind=='commit'),
                              'trees':sorted(key for key,(kind,_) in objects.items() if kind=='tree'),
                              'commit_headers':{key:data.split(b'\n\n',1)[0].decode('utf-8',errors='replace') for key,(kind,data) in objects.items() if kind=='commit'},
                              'tree_entry_names':sorted({name for kind,data in objects.values() if kind=='tree' for name in tree_entries(data)}),
                              'scope':'Original commit messages, author/committer names/emails and tree names remain; no non-source blob payloads'}}
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',json.dumps(manifest,sort_keys=True,indent=2)+'\n')
        archive.writestr('sources.pack',pack)
    return {'ok':True,'sha256':sha(output.read_bytes()),'size_bytes':output.stat().st_size,'manifest':manifest}


def verified_capsule(capsule,expected_sha256,requirements):
    payload=Path(capsule).read_bytes();require(len(payload)<=MAX_PACK and sha(payload)==expected_sha256,'Source capsule SHA256 differs')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        require(archive.namelist()==['manifest.json','sources.pack'],'Unexpected/duplicate capsule member')
        require(sum(info.file_size for info in archive.infolist())<=2*MAX_PACK,'Oversized capsule members')
        manifest=json.loads(archive.read('manifest.json'));pack=archive.read('sources.pack')
    require(manifest['schema_version']==1 and manifest['scope']==SCOPE and manifest['requirements']==requirements,
            'Capsule requirements/scope differ from pinned contract')
    require(sha(pack)==manifest['pack_sha256'],'Source pack bytes changed')
    with tempfile.TemporaryDirectory(prefix='source-proof-check-') as directory:
        repo=Path(directory);git(repo,'init','-q')
        packid=git(repo,'index-pack','--stdin','--promisor',data=pack).decode().split()[-1]
        idx=repo/'.git/objects/pack'/('pack-'+packid+'.idx')
        inventory={}
        for line in git(repo,'verify-pack','-v',str(idx)).decode().splitlines():
            fields=line.split()
            if fields and re.fullmatch('[0-9a-f]{40}',fields[0]):
                require(fields[1] in {'commit','tree','blob'},'Unexpected packed object type')
                inventory[fields[0]]=fields[1]
        require(set(inventory)==set(manifest['objects']),'Pack object roster differs')
        objects={}
        for identity,kind in inventory.items():
            data=git(repo,'cat-file',kind,identity);entry=manifest['objects'][identity]
            require(oid(kind,data)==identity and entry=={'type':kind,'size':len(data),'sha256':sha(data)},'Packed object identity differs')
            objects[identity]=(kind,data)
        def getter(identity):
            require(identity in objects,'Missing required source-proof object: '+identity)
            return objects[identity]
        needed,paths=selected_closure(requirements,getter)
        require(needed==set(objects) and paths==manifest['paths'],'Extra object or path proof differs')
        for revision,names in requirements.items():
            for name in names:
                require(sha(git(repo,'show',revision+':'+name))==paths[revision][name]['sha256'],'Real Git source lookup differs')
    return manifest,pack


def restore(root,capsule,*,expected_sha256,requirements):
    root=Path(root).resolve()
    git(root,'rev-parse','--git-dir')
    before_refs=git(root,'for-each-ref','--format=%(refname) %(objectname)')
    before_head=git(root,'rev-parse','HEAD')
    manifest,pack=verified_capsule(capsule,expected_sha256,requirements)
    git(root,'index-pack','--stdin','--promisor',data=pack)
    for revision,names in requirements.items():
        for name in names:
            require(sha(git(root,'show',revision+':'+name))==manifest['paths'][revision][name]['sha256'],'Imported source lookup differs')
    require(git(root,'for-each-ref','--format=%(refname) %(objectname)')==before_refs and git(root,'rev-parse','HEAD')==before_head,
            'Source import changed refs/HEAD')
    return {'ok':True,'scope':SCOPE,'objects':len(manifest['objects']),'source_paths':sum(map(len,requirements.values())),
            'capsule_sha256':expected_sha256,'objective_evaluations':0,'gradient_steps':0}


PINNED_MANIFEST = 'research/distribution/historical_sources_v0101.json'
ASSET = 'historical_sources_v0.10.1.zip'
URL = 'https://github.com/lijiawei255/jev-tune/releases/download/v0.10.1/'+ASSET


def pinned_contract(root):
    contract=json.loads((Path(root)/PINNED_MANIFEST).read_text(encoding='utf-8'))
    require(contract['schema_version']==1 and contract['asset']==ASSET and contract['url']==URL,
            'Historical source release identity differs')
    require(type(contract['size_bytes']) is int and 0<contract['size_bytes']<=MAX_PACK
            and re.fullmatch('[0-9a-f]{64}',contract['sha256']) is not None,'Invalid capsule size/SHA pin')
    return contract


def verify_origin_paths(root,data_manifest):
    """Bind release member origin OIDs to authentic old trees without reading data blobs."""
    root=Path(root).resolve();contract=pinned_contract(root);checked={}
    for group in data_manifest['groups'].values():
        for row in group['files']:
            source=row['source']
            if source['kind'] not in {'git_blob','deidentified_git_blob'}: continue
            revision,name=source['revision'],row['path']
            expected=source['oid']
            if source['kind']=='deidentified_git_blob':
                expected=source.get('original_oid','')
                require(source.get('transformation')=='metadata_only_deidentification'
                        and re.fullmatch('[0-9a-f]{40}',source['oid']) is not None
                        and re.fullmatch('[0-9a-f]{40}',expected) is not None,
                        'Missing published derivative identity')
            require(revision in contract['requirements'] and re.fullmatch('[0-9a-f]{40}',revision) is not None,
                    'Origin revision outside pinned source proof')
            parts=name.split('/')
            require(not name.startswith('/') and '\\' not in name and ':' not in name
                    and all(part not in {'','.','..','.git'} for part in parts),'Unsafe origin path')
            require(re.fullmatch('[0-9a-f]{40}',expected) is not None,'Invalid origin blob OID')
            key=(revision,name)
            require(key not in checked or checked[key]==expected,'Conflicting origin identity')
            output=git(root,'ls-tree','--full-tree',revision,'--',name).decode('utf-8').strip()
            require(output and '\t' in output,'Origin path absent from original tree: '+name)
            meta,actual_name=output.split('\t',1);mode,kind,identity=meta.split()
            require(actual_name==name and kind=='blob' and mode in {'100644','100755'} and identity==expected,
                    'Origin tree/blob identity differs: '+name)
            checked[key]=expected
    require(checked,'No original Git origin paths checked')
    return {'ok':True,'origin_paths':len(checked),'objective_evaluations':0,'gradient_steps':0,
            'scope':'Original commit/tree path-to-blob-OID proof; data payload identity is independently pinned by the release-data manifest'}


def restore_pinned(root,from_dir=None):
    root=Path(root).resolve();contract=pinned_contract(root)
    if from_dir is not None:
        capsule=Path(from_dir).resolve()/ASSET
        require(capsule.is_file() and capsule.stat().st_size==contract['size_bytes'],'Missing/wrong-sized offline source capsule')
        result=restore(root,capsule,expected_sha256=contract['sha256'],requirements=contract['requirements'])
    else:
        import urllib.request
        with tempfile.TemporaryDirectory(prefix='historical-source-download-') as directory:
            capsule=Path(directory)/ASSET
            with urllib.request.urlopen(URL,timeout=60) as response, capsule.open('wb') as stream:
                size=0
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk: break
                    size+=len(chunk);require(size<=contract['size_bytes'],'Oversized downloaded source capsule')
                    stream.write(chunk)
            require(capsule.stat().st_size==contract['size_bytes'],'Downloaded source capsule size differs')
            result=restore(root,capsule,expected_sha256=contract['sha256'],requirements=contract['requirements'])
    result['offline']=from_dir is not None
    return result


if __name__=='__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--requirements',type=Path)
    parser.add_argument('--build',type=Path)
    parser.add_argument('--restore',type=Path)
    parser.add_argument('--restore-pinned',action='store_true')
    parser.add_argument('--from-dir',type=Path)
    parser.add_argument('--sha256')
    args=parser.parse_args()
    try:
        require(sum(map(bool,(args.build,args.restore,args.restore_pinned)))==1,'Choose exactly one operation')
        if args.restore_pinned:
            result=restore_pinned(args.root,args.from_dir)
        else:
            require(args.requirements is not None,'Explicit requirements needed')
            contract=json.loads(args.requirements.read_text(encoding='utf-8'))
            result=build(args.root,contract,args.build) if args.build else restore(args.root,args.restore,expected_sha256=args.sha256,requirements=contract)
        print(json.dumps(result,indent=2))
    except (ValueError,KeyError,OSError,zipfile.BadZipFile) as exc:
        print(json.dumps({'ok':False,'error':type(exc).__name__+': '+str(exc)}));raise SystemExit(1)
