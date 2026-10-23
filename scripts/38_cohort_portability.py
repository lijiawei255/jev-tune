"""Preserve and reconstruct the observed cross-platform cohort audit failure.

All measured values come from committed CI logs or the exported Windows cohort.
This script never samples, simulates, changes tolerances, or reruns acceptance.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCES = Path('research/results/cohort_portability_sources')
RESULT = Path('research/results/cohort_portability.json')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def build_report(root=ROOT):
    root = Path(root)
    paths = {name: root/SOURCES/name for name in
             ('linux_evidence_log.txt', 'linux_job.json', 'linux_run.json', 'windows_train_cohort.json')}
    data = {name: path.read_bytes().replace(b'\r\n', b'\n') for name, path in paths.items()}
    log = data['linux_evidence_log.txt'].decode('utf-8-sig')
    lines = [re.sub(r'^\S+Z ', '', line) for line in log.splitlines()]
    job = json.loads(data['linux_job.json'])
    run = json.loads(data['linux_run.json'])
    reference = json.loads(data['windows_train_cohort.json'])
    study_path = root/'research/results/trajectory_risk.json'
    study = json.loads(study_path.read_text(encoding='utf-8'))
    require(job['status'] == 'completed' and job['conclusion'] == 'failure', 'source job was not the recorded failure')
    require(job['head_sha'] == run['headSha'] and str(job['run_id']) == run['url'].rsplit('/', 1)[-1],
            'run/job provenance differs')
    require(job['head_sha'] in log and job['html_url'].startswith(run['url'] + '/job/'),
            'checkout log/job URL does not bind the recorded run')
    # GitHub masks checkout credentials. Refuse common unmasked token formats;
    # retain the public job log rather than copying local credentials or envs.
    require(not re.search(r'(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})', log),
            'source log contains an unmasked token pattern')
    for line in lines:
        if 'AUTHORIZATION:' in line or re.match(r'\s+token:', line):
            require('***' in line, 'source log contains an unmasked authorization field')
    needle = 'ValueError: cohort regeneration differs from prescribed seed: '
    errors = [line.split(needle, 1)[1] for line in lines if needle in line]
    require(len(errors) == 1, 'expected one detailed cohort failure')
    raw_path, encoded = errors[0].split('; ', 1)
    comparison = json.loads(encoded)
    require(comparison['gains_rtol'] == comparison['gains_atol'] == 1e-12,
            'source failure used a different tolerance')
    require(comparison['identity_exact_match'] is False and comparison['gains_within_tolerance'] is True,
            'source failure classification changed')
    installed = {}
    for line in lines:
        if line.startswith('Successfully installed '):
            for token in line.split('Successfully installed ', 1)[1].split():
                name, version = token.rsplit('-', 1)
                installed[name] = version
    expected_packages = study['manifest']['packages']
    observed_packages = {name: installed.get(name) for name in expected_packages}
    python_versions = [re.search(r'CPython \(([^)]+)\)', line).group(1) for line in lines
                       if 'Successfully set up CPython (' in line]
    require(len(python_versions) == 1, 'missing/ambiguous logged Python version')

    def group(name):
        begin = lines.index('##[group]' + name) + 1
        end = next(index for index in range(begin, len(lines)) if lines[index] == '##[endgroup]')
        return lines[begin:end]

    summaries = [re.fullmatch(r'(\d+) automatic matches, (\d+) failures, (\d+) unverified manual claims', line)
                 for line in lines]
    summaries = [match for match in summaries if match]
    require(len(summaries) == 1, 'claims summary missing/ambiguous')
    train = study['training']['datasets']['train']
    require(raw_path == train['raw_file'], 'failure was not the recorded training cohort')
    raw_entry = next(entry for entry in study['raw_files'] if entry['path'] == raw_path)
    raw_bytes = (root/raw_path).read_bytes()
    require(hashlib.sha256(raw_bytes).hexdigest() == raw_entry['sha256'], 'original training raw changed')
    raw = json.loads(gzip.decompress(raw_bytes))
    require(reference['seed'] == train['seed'] and reference['n_plants'] == train['n_plants'],
            'exported Windows reference uses another cohort')
    plants = reference['plants']
    require(len(plants) == train['n_plants'], 'exported Windows cohort size differs')
    # Independently reconstruct the identity hash from fixed physical floats.
    # This validates the exported reference; it does NOT regenerate on this OS.
    for index, plant in enumerate(plants):
        require(plant['index'] == index, 'exported reference order differs')
        digest = hashlib.blake2b(digest_size=8, person=b'jev-noise')
        for name in ('num', 'den'):
            values = list(plant[name])
            while values and values[0] == 0:
                values.pop(0)
            digest.update(struct.pack('<Q', len(values)))
            digest.update(struct.pack('<' + 'd' * len(values), *values))
        digest.update(struct.pack('<5d', plant['delay_s'], plant['u_min'], plant['u_max'], 0., 0.))
        require(int.from_bytes(digest.digest(), 'little') == plant['identity'],
                'exported physical-cohort identity hash differs')
    spec = importlib.util.spec_from_file_location('cohort_portability_verifier',
                                                 root/'scripts/32_verify_trajectory_risk.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    reference_comparison = verifier.cohort_comparison(raw['per_plant'],
        [plant['identity'] for plant in plants], [plant['initial_gains'] for plant in plants])
    require(reference_comparison == reference['comparison'], 'exported Windows comparison is stale')
    require(reference_comparison['identity_exact_match'] and reference_comparison['gains_within_tolerance'],
            'exported Windows reference disagrees with original raw')
    require(comparison['recorded_identity_count'] == len(raw['per_plant']) and
            comparison['first_identity_mismatch']['recorded'] ==
            raw['per_plant'][comparison['first_identity_mismatch']['plant_index']]['plant_identity'],
            'logged comparison does not refer to original recorded identities')
    return {
        'schema_version': 1,
        'status': 'observed_linux_exact_cohort_regeneration_failure',
        'source_hash_policy': 'SHA-256 of committed text after CRLF-to-LF conversion only',
        'sources': {name: {'path': paths[name].relative_to(root).as_posix(),
                           'sha256_lf': hashlib.sha256(blob).hexdigest()} for name, blob in data.items()},
        'study_canonical_sha256': canonical_hash(study),
        'raw_training': {'path': raw_path, 'sha256': raw_entry['sha256'],
                         'seed': train['seed'], 'n_plants': train['n_plants']},
        'ci': {'run_id': job['run_id'], 'run_url': run['url'], 'head_sha': job['head_sha'],
               'job_id': job['id'], 'job_url': job['html_url'], 'job_name': job['name'],
               'job_conclusion': job['conclusion'], 'started_at': job['started_at'],
               'completed_at': job['completed_at']},
        'environment': {'operating_system_log': group('Operating System'),
                        'runner_image_log': group('Runner Image'), 'python': python_versions[0],
                        'scientific_packages_expected': expected_packages,
                        'scientific_packages_installed_from_log': observed_packages,
                        'all_scientific_package_versions_match': observed_packages == expected_packages},
        'strict_comparison': comparison,
        'other_claims_log_summary': dict(zip(('automatic_matches', 'failures', 'unverified_manual_claims'),
                                            map(int, summaries[0].groups()))),
        'windows_exported_reference_comparison': reference_comparison,
        'additional_simulations': 0, 'thresholds_changed': False, 'acceptance_recomputed': False,
        'linux_exact_cohort_regeneration_established': False,
        'interpretation': (
            'This Linux job failed exact physical-byte noise-stream identity regeneration in the first training cohort. '
            'Every initial-gain comparison passed the unchanged tolerance. The log does not isolate the responsible '
            'operation, library, or CPU instruction. Identity hashes are not independent sampling seeds, and a hash '
            'mismatch count is not evidence of a changed number of independent objects. Subsequent v2 reconstruction '
            'checks were not reached in this Linux job. The stored Windows cohort is independently checked against '
            'original raw and its physical-byte hashes; this metadata check does not regenerate it on the current OS. '
            'Reference-platform evidence verification and Linux runtime/C99 compatibility have separate scopes; '
            'neither establishes cross-platform bitwise study reproduction or the missing statistical premises.')}


def check(root=ROOT, report_path=None):
    root = Path(root)
    report_path = root/RESULT if report_path is None else Path(report_path)
    report = json.loads(report_path.read_text(encoding='utf-8'))
    require(report == build_report(root), 'cohort portability report differs from committed sources')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='read-only reconstruction from committed sources')
    args = parser.parse_args()
    try:
        if args.check:
            report = check()
        else:
            report = build_report()
            (ROOT/RESULT).write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        print(json.dumps({'ok': True, 'artifact': RESULT.as_posix(), 'status': report['status']}, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': f'{type(exc).__name__}: {exc}'}, indent=2))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
