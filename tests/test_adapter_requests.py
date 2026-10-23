"""User-request outcomes and file handoffs, without launching MATLAB."""
import json
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from jev_tune import cli, matlab_runner, matlab_worker


def test_worker_waits_for_complete_result_and_atomically_publishes_request(tmp_path, monkeypatch):
    monkeypatch.setattr(matlab_worker.tempfile, 'mkdtemp', lambda **kwargs: str(tmp_path))
    monkeypatch.setattr(matlab_worker.uuid, 'uuid4', lambda: SimpleNamespace(hex='abcd1234' * 4))
    worker = matlab_worker.MatlabWorker(timeout=1)
    worker._ready = True
    result_path = tmp_path/'res_abcd1234.json'
    result_path.write_text('{', encoding='utf-8')
    publish = Path.replace
    published = []

    def replace(source, destination):
        assert not list(tmp_path.glob('job_*.json'))
        published.append(json.loads(source.read_text(encoding='utf-8')))
        return publish(source, destination)

    def finish_result(seconds):
        assert result_path.exists(), 'a partial result must remain available to its writer'
        result_path.write_text('{"ok": true, "final_J": 0.5}', encoding='utf-8')

    monkeypatch.setattr(Path, 'replace', replace)
    monkeypatch.setattr(matlab_worker.time, 'sleep', finish_result)
    result = worker.run({'model': 'plant.slx', 'iters': 3})
    assert result == {'ok': True, 'final_J': .5}
    assert published[0]['model'] == 'plant.slx' and published[0]['iters'] == 3
    assert published[0]['keep_loaded'] is False
    assert not result_path.exists()
    assert not list(tmp_path.glob('*.tmp'))


def test_worker_keeps_invalid_result_until_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(matlab_worker.tempfile, 'mkdtemp', lambda **kwargs: str(tmp_path))
    monkeypatch.setattr(matlab_worker.uuid, 'uuid4', lambda: SimpleNamespace(hex='abcd1234' * 4))
    ticks = iter([0., 0., .5, 2.])
    monkeypatch.setattr(matlab_worker.time, 'time', lambda: next(ticks))
    monkeypatch.setattr(matlab_worker.time, 'sleep', lambda seconds: None)
    worker = matlab_worker.MatlabWorker(timeout=1)
    worker._ready = True
    result_path = tmp_path/'res_abcd1234.json'
    result_path.write_text('{', encoding='utf-8')
    with pytest.raises(TimeoutError, match='did not finish'):
        worker.run({'model': 'plant.slx'})
    assert result_path.read_text() == '{'


@pytest.mark.parametrize('all_loops', [False, True])
@pytest.mark.parametrize('explicit', [False, True])
def test_config_values_survive_defaults_and_explicit_flags_win(tmp_path, monkeypatch, capsys, all_loops, explicit):
    config = tmp_path/'config.json'
    config.write_text(json.dumps({'iters': 7, 'step_gain': .4, 'stop_time': 4., 'ref_source': '0.5236',
                                  'work_dir': 'configured-work', 'u_max': 1.6}), encoding='utf-8')
    received = []

    def run_job(cfg, **kwargs):
        received.append(cfg)
        return {'ok': False, 'error': 'mock stop after dispatch'}

    def run_all(model, **kwargs):
        assert kwargs['iters'] == kwargs['config']['iters']
        assert kwargs['work_dir'] == kwargs['config']['work_dir']
        return run_job(kwargs['config'])

    monkeypatch.setattr(matlab_runner, 'run_job', run_job)
    monkeypatch.setattr(matlab_runner, 'run_all_loops', run_all)
    args = ['matlab', '--model', 'plant.slx', '--config', str(config), '--json']
    if all_loops:
        args += ['--all-loops']
    if explicit:
        args += ['--iters', '9', '--step-gain', '.25', '--stop-time', '2', '--work-dir', 'explicit-work']
    assert cli.main(args) == 2
    capsys.readouterr()
    assert received == [{'model': 'plant.slx', 'iters': 9 if explicit else 7,
                         'step_gain': .25 if explicit else .4, 'stop_time': 2. if explicit else 4.,
                         'work_dir': 'explicit-work' if explicit else 'configured-work', 'u_max': 1.6,
                         'ref_source': .5236}]


@pytest.mark.parametrize('value, expected', [('auto', 'auto'), ('0.5236', .5236)])
def test_reference_flag_reaches_matlab_as_auto_or_number(monkeypatch, capsys, value, expected):
    received = []
    monkeypatch.setattr(matlab_runner, 'run_job', lambda cfg, **kw:
                        received.append(cfg) or {'ok': False, 'error': 'mock stop'})
    assert cli.main(['matlab', '--model', 'plant.slx', '--ref-source', value, '--json']) == 2
    capsys.readouterr()
    assert received[0]['ref_source'] == expected


@pytest.mark.parametrize('value', ['0', '-1', 'Inf', 'NaN', 'arbitrary'])
def test_unsupported_reference_flag_is_rejected_before_launch(monkeypatch, capsys, value):
    monkeypatch.setattr(matlab_runner, 'run_job', lambda *a, **kw: pytest.fail('must not launch'))
    with pytest.raises(SystemExit) as error:
        cli.main(['matlab', '--model', 'plant.slx', '--ref-source', value, '--json'])
    assert error.value.code == 2
    assert 'finite positive' in capsys.readouterr().err


@pytest.mark.parametrize('value', ['0', -1, 'Inf', 'NaN', True, None])
def test_unsupported_reference_in_config_is_a_structured_failure(tmp_path, monkeypatch, capsys, value):
    config = tmp_path/'config.json'
    config.write_text(json.dumps({'ref_source': value}), encoding='utf-8')
    monkeypatch.setattr(matlab_runner, 'run_job', lambda *a, **kw: pytest.fail('must not launch'))
    assert cli.main(['matlab', '--model', 'plant.slx', '--config', str(config), '--json']) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['ok'] is False and result['code'] == 'invalid_config'
    assert 'finite positive' in result['error']


def test_all_loops_runner_serializes_complete_config(tmp_path, monkeypatch):
    monkeypatch.setattr(matlab_runner, 'find_matlab', lambda: SimpleNamespace(
        ok=True, executable=Path('mock-matlab'), source='mock'))
    dispatched = []

    def run_matlab(code, **kwargs):
        match = re.search(r"jev_tune_all\('([^']+)','([^']+)'\)", code)
        dispatched.append(json.loads(Path(match[1]).read_text(encoding='utf-8')))
        Path(match[2]).write_text('{"ok": false}', encoding='utf-8')
        return subprocess.CompletedProcess([], 0, '', '')

    monkeypatch.setattr(matlab_runner, 'run_matlab', run_matlab)
    matlab_runner.run_all_loops(str(tmp_path/'plant.slx'), iters=9, work_dir='work',
        config={'stop_time': 2., 'step_gain': .25, 'u_max': 1.6})
    assert dispatched == [{'model': str((tmp_path/'plant.slx').resolve()), 'iters': 9,
                           'work_dir': 'work', 'stop_time': 2., 'step_gain': .25, 'u_max': 1.6}]


def test_all_loops_rejects_unsupported_plot_before_launch(monkeypatch, capsys):
    monkeypatch.setattr(matlab_runner, 'run_all_loops', lambda *a, **kw: pytest.fail('must not launch'))
    assert cli.main(['matlab', '--model', 'plant.slx', '--all-loops', '--plot', 'out.png', '--json']) == 2
    assert json.loads(capsys.readouterr().out)['code'] == 'unsupported_option'


@pytest.mark.parametrize('raises', [False, True])
def test_requested_writeback_failure_is_whole_request_failure(monkeypatch, capsys, raises):
    monkeypatch.setattr(matlab_runner, 'run_job', lambda *a, **kw:
        {'ok': True, 'final_J': .5, 'final_gains': [1., 2., 3.], 'history': [{'J': 1.}]})

    def writeback(*args, **kwargs):
        if raises:
            raise TimeoutError('mock writeback timeout')
        return {'ok': False, 'code': 'writeback_failed', 'error': 'mock disk failure'}

    monkeypatch.setattr(matlab_runner, 'run_writeback', writeback)
    assert cli.main(['matlab', '--model', 'plant.slx', '--write-back', '--json']) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['ok'] is False and result['tuning_ok'] is True
    assert result['code'] == 'writeback_failed'
    assert result['final_J'] == .5 and result['final_gains'] == [1., 2., 3.]
    assert result['write_back']['ok'] is False


def test_successful_writeback_remains_success(monkeypatch, capsys):
    monkeypatch.setattr(matlab_runner, 'run_job', lambda *a, **kw:
        {'ok': True, 'final_J': .5, 'final_gains': [1., 2., 3.]})
    monkeypatch.setattr(matlab_runner, 'run_writeback', lambda *a, **kw: {'ok': True, 'target': 'plant_tuned.slx'})
    assert cli.main(['matlab', '--model', 'plant.slx', '--write-back', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['ok'] is True


@pytest.mark.parametrize('json_output', [False, True])
def test_loop_reports_measured_simulations_separately_from_budget(monkeypatch, capsys, json_output):
    monkeypatch.setattr('jev_tune.plants.make_plant', lambda *a, **kw: SimpleNamespace(n=1))
    monkeypatch.setattr('jev_tune.plants.ultimate_gain', lambda p: (np.ones(1), np.ones(1)))
    monkeypatch.setattr('jev_tune.decision.load_backend', lambda *a, **kw: None)
    monkeypatch.setattr('jev_tune.evaluate.evaluate_head', lambda *a, **kw: SimpleNamespace(
        history=np.ones((1, 21)), best_j=np.ones(1), gains=np.ones((1, 3)),
        budget=21, actual_simulations=np.array([2]), stop_iter=np.array([2])))
    assert cli.main(['loop', '--iters', '20'] + (['--json'] if json_output else [])) == 0
    output = capsys.readouterr().out
    if json_output:
        result = json.loads(output)
        assert result['n_experiments'] == result['n_total_simulations'] == 2
        assert result['simulation_budget'] == 21 and len(result['hist']) == 21
        assert result['prior'] == {'method': 'analytic_ultimate_gain', 'simulations': 0}
    else:
        assert 'experiments 2  budget 21' in output
