"""Clone the fixed official release and reproduce it using the current Python environment."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

OFFICIAL = 'https://github.com/lijiawei255/jev-tune.git'
RELEASE_REF = 'v0.10.1'
RESTORE = 'scripts/59_research_data.py'
DATA_MANIFEST = 'research/distribution/research_data_v0101.json'
HISTORY_RESTORE = 'scripts/history_sources.py'
HISTORY_MANIFEST = 'research/distribution/historical_sources_v0101.json'


def now():
    return datetime.now(timezone.utc).isoformat()


def tracked_hashes(root):
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).split(b'\0')
    result = {}
    for value in names:
        if not value: continue
        name = value.decode('utf-8')
        path = root/name
        if path.is_symlink():
            data = os.readlink(path).encode('utf-8')
        elif path.is_file():
            data = path.read_bytes()
        else:
            raise ValueError('Tracked file missing: '+name)
        result[name] = hashlib.sha256(data).hexdigest()
    return result


def receipt_snapshot(root):
    result = {}
    for dirname in ('recorded_transfer_verification', 'recorded_recalibration_verification'):
        for path in sorted((root/'.local-audit'/dirname).glob('*.json')):
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def receipt_costs(root, before):
    after = receipt_snapshot(root)
    if any(after.get(name) != digest for name, digest in before.items()):
        raise ValueError('Existing verification receipt changed or disappeared')
    rows = []
    for name, digest in after.items():
        if name in before: continue
        value = json.loads((root/name).read_text(encoding='utf-8'))
        count = value.get('additional_verification_objective_evaluations', value.get('additional_objective_evaluations'))
        if type(count) is not int or count < 0:
            raise ValueError('Receipt has no valid objective accounting: '+name)
        rows.append({'path': name, 'sha256': digest, 'status': value.get('status'),
                     'ok': value.get('ok'), 'additional_objective_evaluations': count})
    return {'receipts': rows, 'additional_objective_evaluations': sum(row['additional_objective_evaluations'] for row in rows),
            'scope': 'Recorded-evidence audit receipts only, including failures; not independent samples. Unit-test and demo work is outside this objective ledger.'}



def verify_receipt_bindings(root, receipts, revision, started_utc):
    protocol_name = 'research/protocols/recorded_evidence_audit_v0100.json'
    protocol = json.loads((root/protocol_name).read_text(encoding='utf-8'))
    sources = dict(protocol['source_hashes'])
    normalized = lambda path: hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    sources[protocol_name] = normalized(root/protocol_name)
    for name, expected in sources.items():
        if normalized(root/name) != expected: raise ValueError('Receipt source pin differs: '+name)
    primary = json.loads((root/'research/results/nonpid_transfer/report.json').read_text(encoding='utf-8'))
    inputs = {'research/results/nonpid_transfer/report.json': normalized(root/'research/results/nonpid_transfer/report.json'),
              'research/results/nonpid_transfer/raw.json.gz': primary['raw_sha256']}
    raw = root/'research/results/nonpid_transfer/raw.json.gz'
    if hashlib.sha256(raw.read_bytes()).hexdigest() != primary['raw_sha256']:
        raise ValueError('Primary raw bytes differ')
    for name, expected in primary['artifacts'].items():
        path = 'research/results/nonpid_transfer/'+name
        if normalized(root/path) != expected: raise ValueError('Primary model/calibration pin differs')
        inputs[path] = expected
    expected_manifests = {
        'recorded_transfer_verification': ('original_numeric_manifest', 'original_machine_arrays.json'),
        'recorded_recalibration_verification': ('original_supplement_manifest', 'small_sample_arrays.json')}
    found = set()
    for row in receipts:
        name = row['path']; category = Path(name).parts[-2]
        if category not in expected_manifests: raise ValueError('Unexpected receipt category')
        receipt_bytes = (root/name).read_bytes()
        if hashlib.sha256(receipt_bytes).hexdigest() != row['sha256']:
            raise ValueError('New receipt changed during finalization: '+name)
        value = json.loads(receipt_bytes)
        began = datetime.fromisoformat(value['started_utc'])
        if not datetime.fromisoformat(started_utc) <= began <= datetime.now(timezone.utc):
            raise ValueError('New receipt timestamp outside this reproduction: '+name)
        if value.get('ok') is not True or value.get('status') != 'passed' or value.get('strict_cpu_replay_proven') is not False:
            raise ValueError('New verification receipt failed or has wrong scope: '+name)
        if value['audit_execution']['git_revision'] != revision or value['audit_execution']['source_hashes'] != sources:
            raise ValueError('New receipt source/revision differs: '+name)
        key, manifest_name = expected_manifests[category]
        manifest = json.loads((root/'research/results/calibration_runtime_sources'/manifest_name).read_text(encoding='utf-8'))
        if value[key] != manifest or manifest['input_hashes'] != inputs:
            raise ValueError('New receipt numeric archive binding differs: '+name)
        if hashlib.sha256((root/manifest['archive']).read_bytes()).hexdigest() != manifest['archive_sha256']:
            raise ValueError('Numeric archive bytes differ')
        if category == 'recorded_recalibration_verification':
            main_manifest = json.loads((root/'research/results/calibration_runtime_sources/original_machine_arrays.json').read_text(encoding='utf-8'))
            if manifest['primary_archive_sha256'] != main_manifest['archive_sha256']:
                raise ValueError('Supplement archive parent differs')
        if category == 'recorded_transfer_verification':
            if value.get('audit_type') != 'original_recorded_evidence' or value.get('study_id') != primary['study_id']:
                raise ValueError('Main receipt study/type differs')
            if any(value[key] != primary[key] for key in ('raw_sha256','accounting','acceptance')):
                raise ValueError('New receipt primary binding differs: '+name)
            if row['additional_objective_evaluations'] != primary['accounting']['actual_objective_evaluations']:
                raise ValueError('New receipt objective accounting differs: '+name)
        elif (value.get('audit_type') != 'original_recorded_recalibration_evidence' or value.get('rows') != 9
              or value.get('recorded_timings_preserved') is not True or value.get('gradient_steps') != 0
              or row['additional_objective_evaluations'] != 0):
            raise ValueError('Supplemental receipt objective accounting differs')
        found.add(category)
    if found != set(expected_manifests): raise ValueError('Missing complete passing main/supplement verification receipts')


def pytest_results(xml_path, log, *, validate=True):
    suites = list(ET.parse(xml_path).getroot().iter('testsuite'))
    counts = {name: sum(int(s.attrib.get(name, 0)) for s in suites)
              for name in ('tests', 'failures', 'errors', 'skipped')}
    coverage = re.findall(r'Total coverage:\s*([\d.]+)%', log)
    if not suites or counts['tests'] <= 0 or not coverage:
        raise ValueError('Missing actual JUnit tests or coverage')
    counts['coverage_percent'] = float(coverage[-1])
    if validate and (counts['failures'] or counts['errors'] or counts['skipped'] or counts['coverage_percent'] < 66):
        raise ValueError('Full suite requires zero failures/errors/skips and coverage >=66')
    return counts


def reproduce(args):
    destination = Path(args.destination).expanduser().resolve()
    if destination.exists():
        raise ValueError('Destination already exists; refuse to reuse, delete or reset: '+str(destination))
    source = OFFICIAL
    ref = RELEASE_REF
    if args.source is not None:
        source_path = Path(args.source).expanduser().resolve()
        if not source_path.is_dir(): raise ValueError('--source must be an existing local Git directory')
        subprocess.check_output(['git', '-C', str(source_path), 'rev-parse', '--git-dir'])
        source, ref = str(source_path), args.ref or RELEASE_REF
    elif args.ref is not None:
        raise ValueError('--ref requires explicit local --source; official release is fixed')
    report_path = Path(args.report).expanduser().resolve() if args.report else destination/'.local-audit/reproduction_v0101.json'
    if report_path.exists(): raise ValueError('Report already exists; refuse overwrite: '+str(report_path))
    if report_path.is_relative_to(destination) and not report_path.is_relative_to(destination/'.local-audit'):
        raise ValueError('Reports inside destination must be under .local-audit')
    report = {'schema_version': 1, 'ok': False, 'status': 'running', 'started_utc': now(),
              'destination': str(destination), 'source': source, 'requested_ref': ref, 'actual_HEAD': None,
              'mode': 'verify' if args.verify else 'prepare', 'prepared': False, 'verified': False,
              'dependency_environment': {'scope': 'Reuses the current Python/dependency environment; not a clean dependency installation',
                                         'python_executable': sys.executable, 'python_version': sys.version},
              'commands': []}
    before = receipts_before = None
    try:
        # Ordinary clone: in cleaned mode all reachable commits contain source
        # only. Original verifier source objects are an explicit pinned restore.
        clone = ['git', 'clone', '-c', 'core.autocrlf=false', '--no-local', '--', source, str(destination)]
        row = {'argv': clone, 'cwd': str(destination.parent), 'started_utc': now()}
        report['commands'].append(row)
        result = subprocess.run(clone, cwd=destination.parent, capture_output=True, text=True, encoding='utf-8', errors='replace')
        row.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr, completed_utc=now())
        if result.returncode: raise RuntimeError('Git clone failed')
        audit = destination/'.local-audit'; audit.mkdir(exist_ok=True)
        env = os.environ.copy(); env['PYTHONPATH'] = str(destination/'src')
        env['GIT_NO_LAZY_FETCH'] = '1'
        env['GIT_NO_REPLACE_OBJECTS'] = '1'
        removed = sorted(name for name in env if name.startswith('PYTEST_'))
        for name in removed: env.pop(name)
        report['removed_environment_variable_names'] = removed
        def run(command, name, *, require_success=True):
            record = {'argv': command, 'cwd': str(destination), 'started_utc': now(),
                      'PYTHONPATH': env['PYTHONPATH']}
            report['commands'].append(record)
            completed = subprocess.run(command, cwd=destination, env=env, capture_output=True,
                                       text=True, encoding='utf-8', errors='replace')
            log_path = audit/(name+'.log')
            log_path.write_text(completed.stdout+'\n'+completed.stderr, encoding='utf-8')
            record.update(returncode=completed.returncode, completed_utc=now(), log=str(log_path),
                          log_sha256=hashlib.sha256(log_path.read_bytes()).hexdigest())
            if completed.returncode and require_success: raise RuntimeError(name+' failed with exit '+str(completed.returncode))
            return completed.stdout, log_path
        run(['git', 'checkout', '--detach', ref], 'checkout')
        report['actual_HEAD'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=destination, text=True).strip()
        if subprocess.check_output(['git', 'rev-parse', '--is-shallow-repository'], cwd=destination, text=True).strip() != 'false':
            raise ValueError('Full Git history is required')
        manifest = json.loads((destination/DATA_MANIFEST).read_text(encoding='utf-8'))
        history_cleaned = manifest.get('history_cleaned', False)
        if type(history_cleaned) is not bool:
            raise ValueError('Committed history_cleaned mode must be boolean')
        report['history_cleaned'] = history_cleaned
        before = tracked_hashes(destination); report['tracked_hashes_before'] = before
        if report_path.is_relative_to(destination) and report_path.relative_to(destination).as_posix() in before:
            raise ValueError('Report would overwrite tracked source')
        receipts_before = receipt_snapshot(destination)
        restore = [sys.executable, RESTORE, '--root', str(destination), '--fetch', 'all']
        if args.from_dir: restore += ['--from-dir', str(Path(args.from_dir).expanduser().resolve())]
        restore_output, _ = run(restore, 'restore_release_data')
        report['restoration'] = json.loads(restore_output)
        if report['restoration'].get('ok') is not True:
            raise ValueError('Data restoration did not report success')
        if tracked_hashes(destination) != before: raise ValueError('Restore changed tracked content')
        if history_cleaned:
            if HISTORY_RESTORE not in before or HISTORY_MANIFEST not in before:
                raise ValueError('Cleaned release lacks committed historical-source restore/pins')
            pins = json.loads((destination/HISTORY_MANIFEST).read_text(encoding='utf-8'))
            refs_before = subprocess.check_output(['git','show-ref'], cwd=destination, env=env)
            history = [sys.executable, HISTORY_RESTORE, '--root', str(destination), '--restore-pinned']
            if args.from_dir:
                history += ['--from-dir', str(Path(args.from_dir).expanduser().resolve())]
            output, _ = run(history, 'restore_historical_sources')
            value = json.loads(output)
            report['historical_sources'] = value
            if (value.get('ok') is not True or value.get('capsule_sha256') != pins['sha256']
                    or type(value.get('objective_evaluations')) is not int or value['objective_evaluations'] != 0
                    or type(value.get('gradient_steps')) is not int or value['gradient_steps'] != 0):
                raise ValueError('Pinned historical-source restoration did not report valid success/accounting')
            refs_after = subprocess.check_output(['git','show-ref'], cwd=destination, env=env)
            report['historical_source_refs_unchanged'] = refs_before == refs_after
            if refs_before != refs_after:
                raise ValueError('Historical-source restore changed refs/tags/HEAD')
            if subprocess.check_output(['git','rev-parse','HEAD'], cwd=destination, text=True, env=env).strip() != report['actual_HEAD']:
                raise ValueError('Historical-source restore changed HEAD')
            if tracked_hashes(destination) != before:
                raise ValueError('Historical-source restore changed tracked content')
        else:
            report['historical_sources'] = {'required':False, 'scope':'Legacy full-history release; explicit cleaned mode not enabled'}
        report['prepared'] = True
        if args.verify:
            junit = audit/'reproduction_pytest.xml'
            output, log_path = run([sys.executable, '-m', 'pytest', 'tests', '-q', '--cov', '--cov-report=term',
                                   '--cov-fail-under=66', '--junitxml='+str(junit)], 'reproduction_pytest', require_success=False)
            report['pytest'] = pytest_results(junit, log_path.read_text(encoding='utf-8'), validate=False)
            report['pytest']['junit_sha256'] = hashlib.sha256(junit.read_bytes()).hexdigest()
            if report['commands'][-1]['returncode']:
                raise RuntimeError('pytest failed with exit '+str(report['commands'][-1]['returncode']))
            pytest_results(junit, log_path.read_text(encoding='utf-8'))
            if tracked_hashes(destination) != before: raise ValueError('Tests changed tracked content')
            expected_output, _ = run([sys.executable, 'scripts/16_check_claims.py', '--list-ids'], 'claims_id_contract')
            expected_ids = json.loads(expected_output)
            if not isinstance(expected_ids, list) or not expected_ids or len(expected_ids) != len(set(expected_ids)):
                raise ValueError('Invalid complete claims ID contract')
            report['claims_expected_ids'] = expected_ids
            output, _ = run([sys.executable, 'scripts/16_check_claims.py', '--json'], 'reproduction_claims', require_success=False)
            claims = json.loads(output)
            if isinstance(claims, list):
                report['claims'] = {'total': len(claims), 'passed': sum(row.get('ok') is True for row in claims),
                    'failed': sum(row.get('ok') is False for row in claims),
                    'unverified': sum(row.get('ok') is None for row in claims), 'rows': claims}
            if report['commands'][-1]['returncode']:
                raise RuntimeError('claims failed with exit '+str(report['commands'][-1]['returncode']))
            if (not isinstance(claims, list) or not claims or any(row.get('ok') is not True for row in claims)
                    or len({row['id'] for row in claims}) != len(claims)
                    or {row['id'] for row in claims} != set(expected_ids)):
                raise ValueError('Claims missing, duplicated, failed or unverified')
            report['claims'] = {'total': len(claims), 'passed': len(claims), 'failed': 0, 'unverified': 0, 'rows': claims}
            report['verified'] = True
        report['status'] = 'verified' if args.verify else 'prepared'
        report['ok'] = True
    except Exception as exc:
        report.update(status='failed', ok=False, verified=False, error=type(exc).__name__+': '+str(exc))
    finally:
        if before is not None:
            try:
                report['tracked_hashes_after'] = tracked_hashes(destination)
                report['tracked_content_unchanged'] = report['tracked_hashes_after'] == before
                if not report['tracked_content_unchanged']: raise ValueError('Tracked content changed during reproduction')
            except Exception as exc:
                report.update(status='failed', ok=False, verified=False, finalization_error=type(exc).__name__+': '+str(exc))
            # Source-integrity failure must never short-circuit spent-work accounting.
            try:
                report['verification_accounting'] = receipt_costs(destination, receipts_before)
                if report['ok'] and args.verify:
                    verify_receipt_bindings(destination, report['verification_accounting']['receipts'], report['actual_HEAD'], report['started_utc'])
            except Exception as exc:
                report.update(status='failed', ok=False, verified=False, accounting_error=type(exc).__name__+': '+str(exc))
        report['completed_utc'] = now()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--verify', action='store_true')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--ref')
    parser.add_argument('--from-dir', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        result = reproduce(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, str(exc)+'\n')
    print(json.dumps({'ok': result['ok'], 'status': result['status'], 'actual_HEAD': result['actual_HEAD']}))
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
