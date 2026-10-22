from pathlib import Path

p = Path(r"C:\workspace\jev-tune\matlab\test_discover.m")
s = p.read_text(encoding="utf-8")


def sub(old, new):
    global s
    assert old in s, old[:80]
    s = s.replace(old, new, 1)


sub(
    """cases{end+1} = check_cascade_refused(workRoot);
cases{end+1} = check_doctor(workRoot);""",
    """cases{end+1} = check_cascade_refused(workRoot);
cases{end+1} = check_doctor(workRoot);
cases{end+1} = check_own_gains(workRoot);""",
)

sub(
    """function c = check_doctor(workRoot)""",
    """function c = check_own_gains(workRoot)
% The promise is that the tuner never hands back something worse than what the
% model already runs.  Tune the fixture once, write the result into its gain
% blocks, and run again: the second run must not lose to the first.
c = struct('name', 'own_gains', 'pass', false, 'detail', '');
make_demo_model(workRoot, 'gains', struct('name', 'tc_own'));
mdl = fullfile(workRoot, 'tc_own.slx');

j1 = tune_once(workRoot, 'tc_own', 'wd_own1');
if ~isfinite(j1)
    c.detail = 'first run failed';
    return
end
cfg = struct('model', mdl, 'work_dir', fullfile(workRoot, 'wd_own1'), ...
    'iters', 6, 'auto_discover', true);
job = fullfile(workRoot, 'own_job.json');
fid = fopen(job, 'w');
fwrite(fid, jsonencode(cfg), 'char');
fclose(fid);
R1 = jev_tune_json(job, fullfile(workRoot, 'own_out1.json'));
g = R1.final_gains;

% those gains become the model's own
load_system(mdl);
set_param([R1.model_name_placeholder_if_any], 'Gain', '1'); %#ok<*NASGU>
bdclose('jev_lab_model');

set_param('tc_own/Gain_Kp', 'Gain', num2str(g(1)));
set_param('tc_own/Gain_Ki', 'Gain', num2str(g(2)));
set_param('tc_own/Gain_Kd', 'Gain', num2str(g(3)));
save_system('tc_own');
bdclose('tc_own');

j2 = tune_once(workRoot, 'tc_own', 'wd_own2');
c.pass = isfinite(j2) && j2 <= j1 + 1e-6;
c.detail = sprintf('tuned J=%.3f, re-run from those gains J=%.3f', j1, j2);
end

function c = check_doctor(workRoot)""",
)
p.write_text(s, encoding="utf-8")
print("self-check: own gains invariant added")
