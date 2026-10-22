function T = test_discover(workRoot, varargin)
%TEST_DISCOVER  Self-check for jev_discover and the auto-discover path.
%
%   T = test_discover(workRoot)
%   T = test_discover(workRoot, 'tune', true)
%
%   Builds the demo variants, runs discovery on each and checks that the
%   blocks, the measured signal and the reference are the ones the fixture was
%   wired with.  Nothing here uses block names to decide anything: the fixture
%   names are deliberately unhelpful ("alpha", "beta", "gamma") and the checks
%   compare *identities*, not labels.
%
%   Returns a struct with one row per case: name, pass, and a detail string.
%   Used by tests/test_matlab_integration.py, and runnable on its own:
%
%       matlab -batch "addpath('matlab'); test_discover(tempname)"

if nargin < 1 || isempty(workRoot), workRoot = tempname; end
doTune = any(strcmp(varargin, 'tune'));
if ~isfolder(workRoot), mkdir(workRoot); end

cases = {};
cases{end+1} = check_gains(workRoot);
cases{end+1} = check_nested(workRoot);
cases{end+1} = check_pid_block(workRoot);
if doTune
    cases{end+1} = check_autotune(workRoot);
end

T = struct('ok', all(cellfun(@(c) c.pass, cases)), 'cases', {cases}, ...
    'work_root', workRoot);
fprintf('\n=== discover self-check: %d/%d passed ===\n', ...
    sum(cellfun(@(c) c.pass, cases)), numel(cases));
for k = 1:numel(cases)
    fprintf('  [%s] %-16s %s\n', ternary(cases{k}.pass, 'ok', 'FAIL'), ...
        cases{k}.name, cases{k}.detail);
end
end

% -------------------------------------------------------------------------
function c = check_gains(workRoot)
% Three Gain blocks at the top level with meaningless names: the classifier
% has to use the Integrator/Derivative paths, not the labels.
c = struct('name', 'gains', 'pass', false, 'detail', '');
make_demo_model(workRoot, 'gains', struct('name', 'tc_gains'));
D = jev_discover(fullfile(workRoot, 'tc_gains.slx'), ...
    struct('work_dir', fullfile(workRoot, 'wd_gains')));
want = {'alpha', 'beta', 'gamma'};
got = {D.controller.kp_block, D.controller.ki_block, D.controller.kd_block};
c.pass = D.ok && strcmp(D.confidence, 'high') && isequal(got, want) && ...
    abs(D.reference - 1) < 1e-9 && strcmp(D.measure_block, 'Delay');
c.detail = sprintf('kp=%s ki=%s kd=%s ref=%.3g measure=%s', ...
    got{1}, got{2}, got{3}, D.reference, D.measure_block);
end

function c = check_nested(workRoot)
% The same controller inside an unmasked subsystem, with a saturation and an
% anti-windup gain that must NOT be mistaken for Kp, and no Scope at all.
c = struct('name', 'nested', 'pass', false, 'detail', '');
make_demo_model(workRoot, 'nested', struct('name', 'tc_nested'));
D = jev_discover(fullfile(workRoot, 'tc_nested.slx'), ...
    struct('work_dir', fullfile(workRoot, 'wd_nested')));
want = {'Ctrl/alpha', 'Ctrl/beta', 'Ctrl/gamma'};
got = {D.controller.kp_block, D.controller.ki_block, D.controller.kd_block};
c.pass = D.ok && isequal(got, want) && strcmp(D.measure_block, 'Delay') && ...
    isfield(D, 'cfg') && isfield(D.cfg, 'instrument_block');
c.detail = sprintf('kp=%s ki=%s kd=%s measure=%s tap=%s', got{1}, got{2}, got{3}, ...
    D.measure_block, getfield_default(D.cfg, 'instrument_block', '-'));
end

function c = check_pid_block(workRoot)
% A masked PID Controller block in the Ideal form: I and D are times there, so
% the discovered gains must be convertible to the parallel form.
c = struct('name', 'ideal_pid', 'pass', false, 'detail', '');
make_demo_model(workRoot, 'ideal_pid', struct('name', 'tc_ideal'));
D = jev_discover(fullfile(workRoot, 'tc_ideal.slx'), ...
    struct('work_dir', fullfile(workRoot, 'wd_ideal')));
blk = getfield_default(D.controller, 'block', '');
form = getfield_default(D.controller, 'form', '');
c.pass = D.ok && strcmp(D.controller.kind, 'pid_block') && ...
    strcmp(blk, 'PID Controller') && strcmpi(form, 'Ideal');
c.detail = sprintf('kind=%s block=%s form=%s', D.controller.kind, blk, form);
end

function c = check_autotune(workRoot)
% End to end: --auto on an unfamiliar model must find the blocks, tune, and
% never return a gain set worse than the one it started from.
c = struct('name', 'autotune', 'pass', false, 'detail', '');
mdl = fullfile(workRoot, 'tc_nested.slx');
if ~isfile(mdl)
    make_demo_model(workRoot, 'nested', struct('name', 'tc_nested'));
end
cfg = struct('model', mdl, 'work_dir', fullfile(workRoot, 'wd_tune'), ...
    'iters', 8, 'auto_discover', true);
fid = fopen(fullfile(workRoot, 'tune_job.json'), 'w');
fwrite(fid, jsonencode(cfg), 'char');
fclose(fid);
R = jev_tune_json(fullfile(workRoot, 'tune_job.json'), fullfile(workRoot, 'tune_out.json'));
if ~R.ok
    c.detail = ['tuning failed: ' R.error];
    return
end
start = R.history(1).J;
c.pass = R.final_J <= start + 1e-6 && R.discovery.ok;
c.detail = sprintf('J %.3f -> %.3f in %d experiments', start, R.final_J, R.n_experiments);
end

% -------------------------------------------------------------------------
function v = getfield_default(s, name, default)
if isstruct(s) && isfield(s, name) && ~isempty(s.(name))
    v = s.(name);
else
    v = default;
end
end

function out = ternary(cond, a, b)
if cond, out = a; else, out = b; end
end
