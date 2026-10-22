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
cases{end+1} = check_cascade_refused(workRoot);
if doTune
    cases{end+1} = check_autotune(workRoot);
    cases{end+1} = check_pid_form_equivalence(workRoot);
    cases{end+1} = check_two_loops(workRoot);
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

function c = check_pid_form_equivalence(workRoot)
% The same controller written twice: three Gain blocks, and a masked PID block
% in the Ideal form (where I and D are times).  Tuning both must land in the
% same place, otherwise the action space means different things per encoding.
c = struct('name', 'pid_form', 'pass', false, 'detail', '');
make_demo_model(workRoot, 'second_order', struct('name', 'tc_par'));
make_demo_model(workRoot, 'ideal_pid', struct('name', 'tc_ideal2'));
jPar = tune_once(workRoot, 'tc_par', 'wd_par');
jIdeal = tune_once(workRoot, 'tc_ideal2', 'wd_ideal2');
if ~isfinite(jPar) || ~isfinite(jIdeal)
    c.detail = sprintf('one of the runs failed (par=%g ideal=%g)', jPar, jIdeal);
    return
end
rel = abs(jIdeal - jPar) / max(abs(jPar), 1e-9);
c.pass = rel < 0.10;
c.detail = sprintf('parallel J=%.3f, ideal J=%.3f (%.1f%% apart)', jPar, jIdeal, 100 * rel);
end

function j = tune_once(workRoot, name, wd)
j = NaN;
cfg = struct('model', fullfile(workRoot, [name '.slx']), ...
    'work_dir', fullfile(workRoot, wd), 'iters', 8, 'auto_discover', true);
job = fullfile(workRoot, [name '_job.json']);
fid = fopen(job, 'w');
fwrite(fid, jsonencode(cfg), 'char');
fclose(fid);
R = jev_tune_json(job, fullfile(workRoot, [name '_out.json']));
if R.ok, j = R.final_J; end
end

function c = check_cascade_refused(workRoot)
% A hand-built cascade must be refused, not silently tuned as one loop.  This is
% the case the old code got wrong: it picked a junction and reported success.
c = struct('name', 'cascade', 'pass', false, 'detail', '');
make_demo_model(workRoot, 'cascade', struct('name', 'tc_cascade'));
D = jev_discover(fullfile(workRoot, 'tc_cascade.slx'), ...
    struct('work_dir', fullfile(workRoot, 'wd_cascade')));
c.pass = ~D.ok && strcmp(D.code, 'cascade_suspect');
detail = sprintf('ok=%d code=%s', D.ok, getfield_default(D, 'code', '-'));
if isfield(D, 'controller') && isfield(D.controller, 'n_integrators')
    detail = sprintf('%s (gains=%d, integrators=%d)', detail, ...
        D.controller.n_gains, D.controller.n_integrators);
end
c.detail = detail;
end

function c = check_two_loops(workRoot)
% Two independent loops: discovery must see both, and --all-loops must leave
% both gain sets in the final file.
c = struct('name', 'two_loops', 'pass', false, 'detail', '');
make_demo_model(workRoot, 'two_loops', struct('name', 'tc_two'));
D = jev_discover(fullfile(workRoot, 'tc_two.slx'), ...
    struct('probe', false, 'all_loops', true, 'work_dir', fullfile(workRoot, 'wd_two')));
nVerified = sum([D.loops.verified]);
if nVerified < 2
    c.detail = sprintf('%d verified loops', nVerified);
    return
end
cfg = struct('model', fullfile(workRoot, 'tc_two.slx'), ...
    'work_dir', fullfile(workRoot, 'wd_two_all'), 'iters', 4);
job = fullfile(workRoot, 'two_job.json');
fid = fopen(job, 'w');
fwrite(fid, jsonencode(cfg), 'char');
fclose(fid);
R = jev_tune_all(job, fullfile(workRoot, 'two_out.json'));
c.pass = R.ok && R.n_tuned == 2 && isfile(R.target);
% both loops' gains must be in the copy, not just the last one written
a1 = NaN; b1 = NaN;
try
    load_system(R.target);
    [~, nm] = fileparts(R.target);
    a1 = str2double(get_param([nm '/k_a_1'], 'Gain'));
    b1 = str2double(get_param([nm '/k_b_1'], 'Gain'));
    bdclose(nm);
catch
end
c.pass = c.pass && isfinite(a1) && isfinite(b1) && a1 ~= 2 && b1 ~= 2;
c.detail = sprintf('%d/%d tuned, %d experiments, k_a_1=%s k_b_1=%s', ...
    R.n_tuned, R.n_loops, R.total_experiments, num2str(a1), num2str(b1));
end

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
