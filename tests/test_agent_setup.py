"""Offline subprocess checks for environment selection and editable installation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECORDER = r'''
import base64,json,os,pathlib,shutil,sys
mode,selected,*args=sys.argv[1:]
if mode=='--native': args=[base64.b64decode(x).decode() for x in args]
with open(os.environ['SETUP_LOG'],'a',encoding='utf-8') as f:
 f.write(json.dumps({'selected':selected,'args':args,'pythonpath':os.environ.get('PYTHONPATH')})+'\n')
if args[:2]==['-m','venv']:
 target=pathlib.Path(args[2]); suffix='Scripts/python.exe' if os.name=='nt' and mode=='--native' else 'bin/python'
 destination=target/suffix;destination.parent.mkdir(parents=True,exist_ok=True)
 shutil.copyfile(selected,destination);destination.chmod(0o755);sys.exit(0)
if args[:3]==['-m','pip','install']:
 if os.environ.get('SETUP_FAIL_PIP')=='1': sys.exit(23)
 if '-e' in args:
  assert '--no-deps' in args and pathlib.Path(args[args.index('-e')+1]).resolve()==pathlib.Path(os.environ['SETUP_REPO']).resolve()
  pathlib.Path(os.environ['SETUP_INSTALLED']).write_text(selected)
 sys.exit(0)
if args[:2]==['-m','jev_tune.cli']:
 if not pathlib.Path(os.environ['SETUP_INSTALLED']).exists():sys.exit(9)
 print('{"ok":true,"fixture_only":true}');sys.exit(0)
raise SystemExit('Unexpected setup invocation: '+repr(args))
'''
NATIVE = r'''
using System;
using System.Diagnostics;
using System.Text;
public class SetupPython {
 public static int Main(string[] args) {
  var encoded=Array.ConvertAll(args,a=>Convert.ToBase64String(Encoding.UTF8.GetBytes(a)));
  var p=new ProcessStartInfo(Environment.GetEnvironmentVariable("SETUP_REAL_PYTHON"));
  p.UseShellExecute=false;
  p.Arguments="-I \""+Environment.GetEnvironmentVariable("SETUP_RECORDER")+"\" --native \""+Process.GetCurrentProcess().MainModule.FileName+"\" "+string.Join(" ",encoded);
  using(var child=Process.Start(p)){child.WaitForExit();return child.ExitCode;}
 }
}
'''


def bash_path(path):
    value = Path(path).resolve().as_posix()
    return "/" + value[0].lower() + value[2:] if os.name == "nt" else value


@pytest.fixture(scope="session")
def native_python(tmp_path_factory):
    if os.name != "nt":
        return None
    # Windows PowerShell's installed C# compiler creates a real native-command
    # fixture, so LASTEXITCODE is exercised instead of a mocked PS function.
    folder = tmp_path_factory.mktemp("setup native shim")
    source, target = folder / "shim.cs", folder / "python.exe"
    source.write_text(NATIVE, encoding="utf-8")
    compiler = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = "Add-Type -Path $args[0] -OutputAssembly $args[1] -OutputType ConsoleApplication"
    build = folder / "build.ps1"
    build.write_text(command, encoding="utf-8")
    subprocess.run([str(compiler), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                    "-File", str(build), str(source), str(target)], check=True, capture_output=True, timeout=60)
    return target


@pytest.fixture(params=["bash", "powershell"])
def setup_case(request, tmp_path, native_python):
    shell = request.param
    if shell == "bash":
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        executable = str(git_bash) if os.name == "nt" and git_bash.is_file() else shutil.which("bash")
    else:
        executable = (str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
                      if os.name == "nt" else None)
    if not executable:
        pytest.skip("This setup script's shell is not installed on this platform")
    repo, shims, base = (tmp_path / name for name in ("repository with spaces", "command shims", "conda home with spaces"))
    (repo / "scripts").mkdir(parents=True)
    shims.mkdir()
    suffix = ".sh" if shell == "bash" else ".ps1"
    script = repo / "scripts" / ("agent_setup" + suffix)
    shutil.copyfile(ROOT / "scripts" / script.name, script)
    recorder = tmp_path / "record calls.py"
    recorder.write_text(RECORDER, encoding="utf-8")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC",
                                            "HOME", "USERPROFILE", "LANG", "LC_ALL") if key in os.environ}
    env.update(SETUP_REAL_PYTHON=sys.executable, SETUP_RECORDER=str(recorder),
               SETUP_LOG=str(tmp_path / "calls.jsonl"), SETUP_INSTALLED=str(tmp_path / "editable marker"), SETUP_REPO=str(repo))
    if shell == "bash":
        # Expose only the actual utilities this script needs. In particular,
        # removing fake conda must never reveal a runner's /usr/bin/conda.
        env["PATH"] = bash_path(shims)
        for name in ("bash", "dirname", "grep"):
            utility = shims / name
            target = "/bin/bash" if name == "bash" else "/usr/bin/" + name
            utility.write_text('#!/bin/bash\nexec ' + target + ' "$@"\n', encoding="utf-8")
            utility.chmod(0o755)
        env["SETUP_FAKE_BASE"] = bash_path(base)
        selected = base / "envs/jev-tune/bin/python"
        shim = '#!/usr/bin/env bash\nexec "$SETUP_REAL_PYTHON" -I "$SETUP_RECORDER" --shell "$0" "$@"\n'
        bootstrap = shims / "python3"
        bootstrap.write_text(shim, encoding="utf-8"); bootstrap.chmod(0o755)
        conda = shims / "conda"
        conda.write_text('#!/usr/bin/env bash\nif [[ "$1 $2" == "env list" ]]; then printf "jev-tune fixture\\n"; else printf "%s\\n" "$SETUP_FAKE_BASE"; fi\n', encoding="utf-8")
        conda.chmod(0o755)
        selected.parent.mkdir(parents=True); shutil.copyfile(bootstrap, selected); selected.chmod(0o755)
        command = [executable, "--noprofile", "--norc", bash_path(script)]
    else:
        env["PATH"] = str(shims)
        env["SETUP_FAKE_BASE"] = str(base)
        selected = base / "envs/jev-tune/python.exe"
        conda = shims / "conda.cmd"
        conda.write_text('@echo off\nif "%1 %2"=="env list" (echo jev-tune fixture) else (echo %SETUP_FAKE_BASE%)\n', encoding="utf-8")
        shutil.copyfile(native_python, shims / "python.exe")
        selected.parent.mkdir(parents=True); shutil.copyfile(native_python, selected)
        command = [executable, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    def run():
        return subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    def calls():
        return [json.loads(line) for line in Path(env["SETUP_LOG"]).read_text(encoding="utf-8").splitlines()]
    return shell, repo, selected, conda, env, run, calls


def assert_install(calls, selected, repo):
    pip = [row for row in calls if row["args"][:2] == ["-m", "pip"]]
    assert len(pip) == 4
    assert all(Path(row["selected"]).resolve() == selected.resolve() for row in pip)
    assert pip[-1]["args"][:6] == ["-m", "pip", "install", "--quiet", "--no-deps", "-e"]
    assert len(pip[-1]["args"]) == 7 and Path(pip[-1]["args"][6]).resolve() == repo.resolve()
    assert pip[1]["args"][-2:] == ["--index-url", "https://download.pytorch.org/whl/cpu"]
    assert pip[2]["args"][4:] == ["numpy", "scipy", "scikit-learn", "pytest", "matplotlib", "onnx", "onnxruntime"]
    assert all(row["pythonpath"] is None for row in calls)


def test_setup_editable_install_uses_selected_python_and_fresh_child(setup_case, tmp_path):
    shell, repo, selected, _, env, run, calls = setup_case
    result = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert_install(calls(), selected, repo)
    assert "[setup] python:" in result.stdout and "[setup] activate:" in result.stdout
    assert "conda activate jev-tune" in result.stdout
    assert ("conda.sh" if shell == "bash" else "shell.powershell") in result.stdout
    assert (bash_path(selected) if shell == "bash" else str(selected)) in result.stdout
    command = [str(selected), "-m", "jev_tune.cli", "--help"]
    if shell == "bash" and os.name == "nt":
        command = ["C:/Program Files/Git/bin/bash.exe", "--noprofile", "--norc", bash_path(selected), *command[1:]]
    fresh = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert fresh.returncode == 0 and '"ok":true' in fresh.stdout
    assert calls()[-1]["args"] == ["-m", "jev_tune.cli", "--help"] and calls()[-1]["pythonpath"] is None


def test_setup_pip_failure_never_reports_ready(setup_case):
    _, _, _, _, env, run, calls = setup_case
    env["SETUP_FAIL_PIP"] = "1"
    result = run()
    assert result.returncode == 23
    assert "environment ready" not in result.stdout
    assert len(calls()) == 1 and calls()[0]["args"][:3] == ["-m", "pip", "install"]


def test_setup_venv_fallback_installs_with_its_python_and_prints_activation(setup_case):
    shell, repo, _, conda, _, run, calls = setup_case
    conda.unlink()
    result = run()
    assert result.returncode == 0, result.stdout + result.stderr
    selected = repo / (".venv/bin/python" if shell == "bash" else ".venv/Scripts/python.exe")
    assert_install(calls(), selected, repo)
    assert calls()[0]["args"][:2] == ["-m", "venv"]
    assert "[setup] activate:" in result.stdout
    assert ("/activate" if shell == "bash" else "Activate.ps1") in result.stdout


@pytest.mark.parametrize("script", ["archive.py"])
def test_restore_help_uses_utf8_without_pythonpath_under_legacy_encoding(script, tmp_path):
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--help"], cwd=tmp_path,
                            env=env, capture_output=True, timeout=30)
    stdout, stderr = result.stdout.decode("utf-8"), result.stderr.decode("utf-8")
    assert result.returncode == 0, stdout + stderr
    assert "usage:" in stdout and "--help" in stdout and "Traceback" not in stderr
