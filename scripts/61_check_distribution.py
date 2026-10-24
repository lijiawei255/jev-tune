"""Read-only verification of a small source archive and complete release-data coverage."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

MANIFEST = 'research/distribution/research_data_v0101.json'
SOURCEZIP_BUDGET_BYTES = 5_000_000
RETAINED_NONPID = {f'research/results/nonpid_transfer/{kind}_{seed}.json' for kind in ('model','calibration') for seed in (101,202,303)}
PID = {'data/expert_train.npz', *('data/calibration/'+name+'.npz' for name in ('temperature_fit','cp_fit','empirical_eval'))}


def require(condition, message):
    if not condition: raise ValueError(message)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checkout_equal(name, local, original):
    if local == original:
        return True
    if Path(name).suffix.lower() in {'.pt', '.onnx', '.mat', '.npz', '.gz', '.png', '.gif', '.jpg', '.zip'}:
        return False
    if b'\0' in local or b'\0' in original:
        return False
    try:
        local.decode('utf-8')
        original.decode('utf-8')
    except UnicodeDecodeError:
        return False
    return local.replace(b'\r\n', b'\n') == original.replace(b'\r\n', b'\n')


def stream_identity(stream):
    hashed, size = hashlib.sha256(), 0
    while True:
        chunk = stream.read(1024*1024)
        if not chunk: break
        hashed.update(chunk); size += len(chunk)
    return hashed.hexdigest(), size


def check(root, ref='HEAD'):
    root = Path(root).resolve()
    revision = git(root, 'rev-parse', ref+'^{commit}').decode().strip()
    tree = git(root, 'ls-tree', '-rz', '--full-tree', revision)
    blobs = {}
    for row in tree.split(b'\0'):
        if not row: continue
        meta, name = row.split(b'\t', 1); mode, kind, oid = meta.decode().split()
        name = name.decode('utf-8')
        require(kind == 'blob' and mode in {'100644','100755'}, 'Unsupported nonregular tracked payload: '+name)
        blobs[name] = oid
    require(MANIFEST in blobs and '.gitattributes' in blobs, 'Missing committed distribution manifest/attributes')
    def blob(name): return git(root, 'cat-file', 'blob', blobs[name])
    manifest = json.loads(blob(MANIFEST))
    groups, installs = {}, {}
    for group, contract in manifest['groups'].items():
        rows = contract['files']
        groups[group] = {'asset': contract['asset'], 'archive_size_bytes': contract['size_bytes'],
                         'expanded_size_bytes': sum(row['size_bytes'] for row in rows), 'installed_files': 0}
        for row in rows:
            require(type(row['install']) is bool, 'Missing explicit install flag')
            if not row['install']: continue
            name = row['path']
            require(name not in installs, 'Duplicate installed data: '+name)
            installs[name] = row
            groups[group]['installed_files'] += 1
            if name in PID:
                require(name not in blobs, 'PID attachment unexpectedly tracked: '+name)
                continue
            require(name.startswith('research/results/'), 'Formal source/model cannot be exported as data: '+name)
            require(name in blobs, 'Manifest install absent from ref: '+name)
            process = subprocess.Popen(['git','-C',str(root),'cat-file','blob',blobs[name]], stdout=subprocess.PIPE)
            with process.stdout as stream: hashed, size = stream_identity(stream)
            require(process.wait() == 0, 'Cannot read data Git blob: '+name)
            require(size == row['size_bytes'] and hashed == row['sha256'], 'Data Git-blob identity differs: '+name)
            local = root/name
            if local.exists():
                require(local.is_file() and not local.is_symlink(), 'Invalid local data type: '+name)
                with local.open('rb') as stream:
                    hashed, size = stream_identity(stream)
                require(hashed == row['sha256'], 'Local data bytes differ: '+name)
    data_names = set(installs)-PID-RETAINED_NONPID
    results = {name for name in blobs if name.startswith('research/results/')}
    require(results <= set(installs), 'Tracked research results missing from manifest: '+repr(sorted(results-set(installs))))
    attributes = blob('.gitattributes').decode('utf-8').splitlines()
    explicit = {line.split()[0] for line in attributes if line.strip() and not line.lstrip().startswith('#')
                and 'export-ignore' in line.split()[1:]}
    require(data_names <= explicit, 'Data lacks explicit export-ignore: '+repr(sorted(data_names-explicit)))
    # Compare current source with the selected Git revision, allowing only text checkout EOL conversion.
    for name in set(blobs)-data_names:
        local = root/name
        require(local.is_file() and not local.is_symlink(), 'Missing local source: '+name)
        require(checkout_equal(name, local.read_bytes(), blob(name)), 'Local source differs from ref: '+name)
    source = git(root, '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'archive', '--format=zip', revision)
    require(len(source) <= SOURCEZIP_BUDGET_BYTES, 'Source ZIP exceeds fixed 5000000-byte budget: '+str(len(source)))
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        entries = {}
        for entry in archive.infolist():
            if entry.is_dir(): continue
            name = entry.filename
            require(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,
                    'Unsafe source archive member: '+name)
            require(name not in entries and name in blobs, 'Unexpected/duplicate archive member: '+name)
            entries[name] = digest(archive.read(entry))
    require(set(entries) == set(blobs)-data_names, 'Source archive roster differs (data leak or excluded source): '+repr(sorted(set(entries) ^ (set(blobs)-data_names))))
    for name, hashed in entries.items(): require(hashed == digest(blob(name)), 'Source archive differs from Git blob: '+name)
    require(all(name in entries for name in ('README.md','NOTICE.md','LICENSE',MANIFEST)), 'Missing formal source/distribution contracts')
    return {'schema_version':1, 'ok':True, 'ref':ref, 'actual_commit':revision,
            'source_archive_budget_bytes':SOURCEZIP_BUDGET_BYTES, 'source_archive_size_bytes':len(source), 'source_archive_sha256':digest(source),
            'archive_format':'git archive --format=zip', 'source_archive_files':len(entries),
            'tracked_research_result_files':len(results), 'exported_data_files':len(data_names), 'groups':groups,
            'objective_evaluations':0, 'gradient_steps':0, 'scope':'Current selected tree only; original data retained in Git and hash-bound release attachments'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--ref',default='HEAD')
    args=parser.parse_args()
    try: result=check(args.root,args.ref)
    except (ValueError,KeyError,OSError,subprocess.CalledProcessError) as exc:
        print(json.dumps({'ok':False,'error':type(exc).__name__+': '+str(exc)}));raise SystemExit(1)
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
