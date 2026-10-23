"""Run the frozen CP-decoupling study and record real subprocess outcomes."""
from __future__ import annotations
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = [
    ['scripts/17_ablation.py'], ['scripts/20_abstention.py'],
    ['scripts/03_evaluate.py', '--plants', '120', '--budget', '20'],
    ['scripts/03_evaluate.py', '--family', 'thermal_deadtime', '--plants', '120', '--budget', '20'],
    ['scripts/22_calibrate_only.py'], ['scripts/08_generalize.py'],
    ['scripts/11_robustness.py'], ['scripts/12_make_race.py'],
    ['scripts/10_specialize.py', '--scenario', 'valve_dead_zone', '--plants', '120', '--name', 'valve', '--report', 'research/results/specialization.json'],
    ['scripts/13_tracking_demo.py'], ['scripts/26_cp_diagnosis.py'],
    ['scripts/27_cp_performance_diagnosis.py'],
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', action='store_true', help='keep successful runs and retry failed/incomplete commands')
    args_cli = parser.parse_args()
    logdir = ROOT / '.local-audit/reproduce_v060'
    logdir.mkdir(parents=True, exist_ok=True)
    record = {'protocol': 'research/protocols/cp_decoupling.json', 'runs': []}
    destination = ROOT / 'research/results/reproduction.json'
    if args_cli.resume and destination.exists():
        record = json.loads(destination.read_text(encoding='utf-8'))
        failed = [r for r in record['runs'] if r['returncode']]
        record.setdefault('failed_attempts', []).extend(failed)
        record['runs'] = [r for r in record['runs'] if not r['returncode']]
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTHONUNBUFFERED='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    for args in COMMANDS:
        if any(r['command'][1:] == args for r in record['runs']):
            continue
        name = Path(args[0]).stem + ('_thermal' if 'thermal_deadtime' in args else '')
        print('RUN ' + ' '.join(args), flush=True)
        start = time.time()
        logpath = logdir / (name + '.log')
        attempt = 1
        while logpath.exists():
            attempt += 1
            logpath = logdir / (name + f'.attempt{attempt}.log')
        with logpath.open('w', encoding='utf-8') as log:
            p = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        record['runs'].append({'command': [sys.executable, *args], 'returncode': p.returncode,
            'elapsed_s': time.time() - start, 'log_sha256': hashlib.sha256(logpath.read_bytes()).hexdigest(),
            'script_sha256': hashlib.sha256((ROOT / args[0]).read_bytes()).hexdigest()})
        destination.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        print(f'DONE {name}: {p.returncode}', flush=True)
        if p.returncode:
            print(logpath.read_text(encoding='utf-8')[-8000:])
            raise SystemExit(p.returncode)


if __name__ == '__main__':
    main()
