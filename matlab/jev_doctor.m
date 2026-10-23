function out = jev_doctor(mdlPath, outPath, opts)
%JEV_DOCTOR  Say why a model can or cannot be tuned, in nine checks.
%
%   out = jev_doctor('C:/work/Motor.slx', 'doctor.json')
%   out = jev_doctor(mdlPath, outPath, struct('discover', false))
%
%   Discovery answers "which blocks?"; this answers "why did it fail?" without
%   making the user guess.  Every check is cheap except the last one, which runs
%   discovery itself (skipped when the model does not compile, because there is
%   nothing to simulate).
%
%   Checks, in the order a problem usually appears:
%     file        the path exists
%     loads       Simulink can open it
%     referenced  Model blocks: their contents are in another file
%     protected   .slxp blocks
%     stateflow   charts (not tuned, but they can hold the controller)
%     compiles    set_param update: this is what names a missing variable
%     solver      variable vs fixed step, StopTime
%     signals     anything to log from (Scope / To Workspace / Outport)
%     tunable     one loop, several, or refused - from jev_discover
%
%   `out.next` is the one action worth taking, written for a human.

if nargin < 2 || isempty(outPath), outPath = 'jev_doctor.json'; end
if nargin < 3, opts = struct(); end
if ~isfield(opts, 'discover'), opts.discover = true; end
if ~isfield(opts, 'work_dir'), opts.work_dir = fullfile(tempdir, 'jev_doctor'); end

out = struct('ok', false, 'model', mdlPath, 'checks', {{}}, 'next', '', ...
    'verdict', '', 'matlab', version('-release'));
if ~isfolder(opts.work_dir), mkdir(opts.work_dir); end

% ---------------------------------------------------------------- file
if ~isfile(mdlPath)
    out.checks{end+1} = check_('file', false, 'no such file', ...
        'check the path; jev-tune discover -h shows the expected form');
    out.next = 'the file does not exist';
    finish(out, outPath);
    return
end
info = dir(mdlPath);
out.checks{end+1} = check_('file', true, ...
    sprintf('%s (%.0f KB)', mdlPath, info.bytes / 1024), '');

% ---------------------------------------------------------------- loads
tmpDir = fullfile(opts.work_dir, 'copy');
if ~isfolder(tmpDir), mkdir(tmpDir); end
[~, ~, ext] = fileparts(mdlPath);
copyPath = fullfile(tmpDir, ['jev_doctor_model' ext]);
jev_assert_distinct_paths(mdlPath, copyPath);
if isfile(copyPath), delete(copyPath); end
copyfile(mdlPath, copyPath);
srcDir = fileparts(mdlPath);
if isfolder(fullfile(srcDir, 'images'))
    copyfile(fullfile(srcDir, 'images'), fullfile(tmpDir, 'images'));
end
mdl = 'jev_doctor_model';
cleanup = onCleanup(@() close_quiet(mdl)); %#ok<NASGU>
try
    load_system(copyPath);
catch err
    out.checks{end+1} = check_('loads', false, short(err.message), ...
        'the model needs a newer release, a missing toolbox, or a library that is not on the path');
    out.next = 'Simulink cannot open this file at all';
    finish(out, outPath);
    return
end
out.checks{end+1} = check_('loads', true, sprintf('MATLAB %s', version('-release')), '');
warning('off', 'all');

% ---------------------------------------------------------------- blocks
blocks = find_system(mdl, 'SearchDepth', 1, 'LookUnderMasks', 'none', ...
    'FollowLinks', 'off');
blocks = blocks(~strcmp(blocks, mdl));

refs = {}; protected = {}; charts = {}; gains = 0; sums = 0;
scopes = 0; workspaces = 0; outports = 0;
for k = 1:numel(blocks)
    b = blocks{k};
    bt = get_param(b, 'BlockType');
    switch bt
        case 'ModelReference'
            name = safe(b, 'ModelName', '?');
            if endsWith(lower(name), '.slxp')
                protected{end+1} = strrep(b, [mdl '/'], ''); %#ok<AGROW>
            else
                refs{end+1} = sprintf('%s -> %s', strrep(b, [mdl '/'], ''), name); %#ok<AGROW>
            end
        case 'SubSystem'
            mt = lower(safe(b, 'MaskType', ''));
            if contains(mt, 'stateflow')
                charts{end+1} = strrep(b, [mdl '/'], ''); %#ok<AGROW>
            end
        case 'Gain'
            gains = gains + 1;
        case 'Sum'
            sums = sums + 1;
        case 'Scope'
            scopes = scopes + 1;
        case 'ToWorkspace'
            workspaces = workspaces + 1;
        case 'Outport'
            outports = outports + 1;
    end
end

out.checks{end+1} = check_('referenced', isempty(refs), ...
    text_or_list(refs, 'none'), ...
    'open the referenced model itself, or flatten it (Convert to Subsystem)');
out.checks{end+1} = check_('protected', isempty(protected), ...
    text_or_list(protected, 'none'), ...
    'a protected model cannot be read; tune the source model instead');
out.checks{end+1} = check_('stateflow', isempty(charts), ...
    text_or_list(charts, 'none'), ...
    'charts are opaque to discovery; if the controller lives in one, tune the blocks around it');

% ---------------------------------------------------------------- compiles
[okC, msg] = compiles(mdl);
out.checks{end+1} = check_('compiles', okC, msg, ...
    'define the variables the model asks for (often a setup script or a .mat), then run it once in Simulink');
if ~okC
    out.next = sprintf('fix the compile error first: %s', msg);
    out.verdict = 'Simulink cannot compile this model, so nothing can be tuned yet';
    finish(out, outPath);
    return
end

% ---------------------------------------------------------------- solver
solver = safe(mdl, 'Solver', '?');
fixedStep = safe(mdl, 'FixedStep', 'auto');
stopTime = safe(mdl, 'StopTime', '?');
stNum = str2double(stopTime);
varStep = strncmpi(solver, 'ode', 3) || strcmpi(solver, 'VariableStepAuto');
detail = sprintf('%s, %s, StopTime %s', solver, ...
    ternary(varStep, 'variable step', ['fixed step ' fixedStep]), stopTime);
fix = '';
if varStep
    fix = 'a fixed step (ode4, 1 ms) makes repeated experiments faster and deterministic';
end
out.checks{end+1} = check_('solver', isfinite(stNum) && stNum > 0, detail, fix);
if ~isfinite(stNum)
    out.next = 'StopTime is not a number; the model needs its workspace variables first';
end

% ---------------------------------------------------------------- signals
nSig = scopes + workspaces + outports;
out.checks{end+1} = check_('signals', true, ...
    sprintf('%d scopes, %d To Workspace, %d outports', scopes, workspaces, outports), ...
    ternary(nSig == 0, ...
        'nothing logs today; discovery adds its own Scope on a copy, so this is fine', ...
        ''));

out.n = struct('blocks', numel(blocks), 'gains', gains, 'sums', sums);

% ---------------------------------------------------------------- tunable
if opts.discover
    D = jev_discover(mdlPath, struct('probe', false, 'all_loops', true, ...
        'work_dir', fullfile(opts.work_dir, 'discover')));
    if D.ok
        c = D.controller;
        if strcmp(c.kind, 'pid_block')
            what = sprintf('PID block %s (form %s)', c.block, c.form);
        else
            what = sprintf('Kp=%s Ki=%s Kd=%s', c.kp_block, c.ki_block, c.kd_block);
        end
        nLoops = sum([D.loops.verified]);
        out.checks{end+1} = check_('tunable', true, ...
            sprintf('%d verified loop(s); %s', nLoops, what), '');
        out.verdict = sprintf('%d loop(s) found, confidence %s', nLoops, D.confidence);
        out.next = 'jev-tune matlab --model <this> --auto --plot before_after.png';
        out.ok = true;
    else
        hint = '';
        if isfield(D, 'candidates') && ~isempty(D.candidates)
            hint = strjoin(D.candidates(1:min(3, numel(D.candidates))), ' | ');
        end
        out.checks{end+1} = check_('tunable', false, ...
            sprintf('%s%s', D.code, ternary(isempty(hint), '', ['  (' hint ')'])), ...
            first_of(D.warnings));
        out.verdict = sprintf('discovery refused: %s', D.code);
        out.next = first_of(D.warnings);
    end
    out.discovery = struct('ok', D.ok, 'confidence', D.confidence, ...
        'code', getif(D, 'code', ''), 'loops', numel(getif(D, 'loops', {{}})), ...
        'measurements', D.measurements, 'n_total_simulations', D.n_total_simulations);
    out.n_total_simulations = D.n_total_simulations;
end

finish(out, outPath);
end

% -------------------------------------------------------------------------
function c = check_(name, ok, detail, fix)
c = struct('name', name, 'ok', logical(ok), 'detail', detail, 'fix', fix);
end

function [ok, msg] = compiles(mdl)
ok = true;
msg = 'compiles';
try
    set_param(mdl, 'SimulationCommand', 'update');
catch err
    ok = false;
    causes = {};
    for k = 1:numel(err.cause)
        m = short(err.cause{k}.message);
        if ~any(strcmp(causes, m)), causes{end+1} = m; end %#ok<AGROW>
    end
    if isempty(causes), causes{1} = short(err.message); end
    msg = strjoin(causes(1:min(3, numel(causes))), ' | ');
    try, set_param(mdl, 'SimulationCommand', 'stop'); catch, end
end
end

function s = text_or_list(items, empty)
if isempty(items)
    s = empty;
else
    s = strjoin(items(1:min(3, numel(items))), ', ');
    if numel(items) > 3, s = sprintf('%s (+%d more)', s, numel(items) - 3); end
end
end

function v = first_of(c)
v = '';
if isempty(c), return; end
if iscell(c), v = c{1}; else, v = c(1); end
end

function v = getif(s, name, default)
if isfield(s, name) && ~isempty(s.(name)), v = s.(name); else, v = default; end
end

function v = safe(blk, param, default)
v = default;
try
    v = get_param(blk, param);
catch
end
if isempty(v), v = default; end
end

function s = short(msg)
s = regexprep(char(msg), '<a href="[^"]*">', '');
s = regexprep(s, '</a>', '');
if numel(s) > 160, s = [s(1:157) '...']; end
end

function out = ternary(cond, a, b)
if cond, out = a; else, out = b; end
end

function finish(out, outPath)
tmp = [outPath '.tmp'];
fid = fopen(tmp, 'w');
if fid < 0, error('jev:io', 'cannot write %s', tmp); end
fwrite(fid, jsonencode(out), 'char');
fclose(fid);
movefile(tmp, outPath, 'f');
if nargout == 0 || true
    fprintf('\n%-11s %-5s %s\n', 'check', 'ok?', 'detail');
    for k = 1:numel(out.checks)
        c = out.checks{k};
        fprintf('%-11s %-5s %s\n', c.name, ternary(c.ok, 'ok', 'FAIL'), c.detail);
    end
    if ~isempty(out.verdict), fprintf('\nverdict: %s\n', out.verdict); end
    if ~isempty(out.next), fprintf('next:    %s\n', out.next); end
end
end

function close_quiet(mdl)
try
    if bdIsLoaded(mdl)
        try, set_param(mdl, 'SimulationCommand', 'stop'); catch, end
        try, set_param(mdl, 'FastRestart', 'off'); catch, end
        close_system(mdl, 0);
    end
catch
end
end
