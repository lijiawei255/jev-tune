function R = jev_tune_model(mdlPath, workDir, iters, stopTime, stepGain, cfg)
%JEV_TUNE_MODEL  Tune a Simulink PID loop with the Jev decision head.
%
%   R = jev_tune_model(mdlPath, workDir, iters, stopTime)
%
%   Everything runs inside MATLAB: Simulink Fast Restart for the plant, a
%   hand-written forward pass for the head (jev_head_forward), no Python and
%   no IPC.
%
%   The loop is wrapped in a deterministic safety gate:
%     * the best gain set seen so far is always remembered and returned;
%     * if a step makes the cost blow up (unstable / saturated / diverged) the
%       tuner rolls back to `best * 0.6` instead of trusting the head.  `noul`
%       is advisory only -- the veto lives in ordinary code.

if nargin < 3 || isempty(iters), iters = 20; end
if nargin < 4, stopTime = []; end
if nargin < 5 || isempty(stepGain), stepGain = 1.0; end
if nargin < 6 || isempty(cfg), cfg = struct(); end
cfg = with_defaults(cfg);
if nargin < 2 || isempty(workDir), workDir = tempdir; end

% ---------------------------------------------------------------- config
% Block and scope names are project conventions, not part of the method, so
% they are configurable: pass cfg.kp_block = 'MyController/Kp' etc.
function cfg = with_defaults(cfg)
defaults = struct( ...
    'kp_block', 'Gain_Kp', ...
    'ki_block', 'Gain_Ki', ...
    'kd_block', 'Gain_Kd', ...
    'measure_scope', 'Scope_Position', ...
    'input_scope', 'Scope_Current', ...
    'ref_source', 'auto', ...      % 'auto' = Step x Deg2Rad blocks, or a number
    'u_max', [], ...               % actuator limit for the saturation feature
    'step_blocks', {{'Step'}}, ...
    'scale_block', 'Deg2Rad', ...
    'controller', 'gains', ...     % 'gains' (three blocks) | 'pid_block'
    'pid_block', 'PID Controller', ...
    'instrument_block', '', ...    % tap this block on the working copy
    'instrument_port', 1, ...      % which output port to tap
    'keep_loaded', false);         % true => leave the model compiled for reuse
f = fieldnames(defaults);
for i = 1:numel(f)
    if ~isfield(cfg, f{i}), cfg.(f{i}) = defaults.(f{i}); end
end
% Caching a compiled model is only safe in a non-interactive session: in the
% desktop, a later close_system raises a modal "exit Fast Restart?" dialog that
% nobody can click when the session is driven by an agent.
if usejava('desktop')
    cfg.keep_loaded = false;
end
end

here = fileparts(mfilename('fullpath'));
addpath(here);
thisDir = fileparts(here);
W = load(fullfile(thisDir, 'models', 'jev_head_weights.mat'));

% ---------------------------------------------------------------- model copy
% A model compile costs ~10 s and a MATLAB cold start ~50 s, both far more
% than a 0.1 s simulation.  With keep_loaded the compiled model is cached and
% reused by the next job (that is what makes the warm-worker throughput real).
T = struct('setup', 0, 'sweep', 0, 'loop', 0, 'save', 0);
tSetup = tic;
if ~isfolder(workDir), mkdir(workDir); end
mdlName = 'jev_lab_model';
cacheKey = [mdlPath '|' workDir];

if cfg.keep_loaded && is_loaded(mdlName) && strcmp(cache_get(cacheKey), mdlName)
    reused = true;
    try, set_param(mdlName, 'FastRestart', 'on'); catch, end
    if isempty(stopTime)
        stopTime = str2double(get_param(mdlName, 'StopTime'));
    end
    set_param(mdlName, 'StopTime', num2str(stopTime));
else
    reused = false;
    dst = fullfile(workDir, [mdlName '.slx']);
    if isfile(dst), delete(dst); end
    copyfile(mdlPath, dst);
    srcDir = fileparts(mdlPath);
    if isfolder(fullfile(srcDir, 'images'))
        copyfile(fullfile(srcDir, 'images'), fullfile(workDir, 'images'));
    end
    load_system(dst);
    try, set_param(mdlName, 'SimMechanicsOpenEditorOnUpdate', 'off'); catch, end
    if isempty(stopTime)
        stopTime = str2double(get_param(mdlName, 'StopTime'));
    end
    set_param(mdlName, 'StopTime', num2str(stopTime));
    set_param(mdlName, 'FastRestart', 'on');
    cache_put(cacheKey, mdlName);
end

oldDir = pwd; cd(workDir);
restoreDir = onCleanup(@() cd(oldDir));
if ~(cfg.keep_loaded && reused)
    cleanupModel = onCleanup(@() maybe_close(mdlName, cfg.keep_loaded)); %#ok<NASGU>
end
warning('off', 'all');

scopes = get_param(find_system(mdlName, 'SearchDepth', 1, 'BlockType', 'Scope'), 'Name');
if ischar(scopes), scopes = {scopes}; end
if ~reused
    % logging is a structural setting: it must be applied before the model is
    % initialised, and it cannot be touched while Fast Restart holds it open
    for k = 1:numel(scopes)
        set_param([mdlName '/' scopes{k}], 'DataLogging', 'on', ...
            'DataLoggingVariableName', strrep(scopes{k}, '-', '_'), ...
            'DataLoggingSaveFormat', 'Dataset', 'DataLoggingLimitDataPoints', 'off');
    end
end

% ------------------------------------------------------------- instrument
% A model that logs nothing usable needs no manual edit: discovery reports
% which block carries the measured signal, and the tap is added to the copy
% (never to the user's file).  The copy is already loaded here, so the Scope
% exists before the model is initialised, which is what logging requires.
if ~reused && isfield(cfg, 'instrument_block') && ~isempty(cfg.instrument_block)
    tap = [mdlName '/' cfg.instrument_block];
    tapPort = 1;
    if isfield(cfg, 'instrument_port') && ~isempty(cfg.instrument_port)
        tapPort = cfg.instrument_port;
    end
    if ~jev_instrument(mdlName, tap, cfg.measure_scope, tapPort)
        warning('jev:instrument', ...
            'could not tap %s; pass measure_scope explicitly', cfg.instrument_block);
    end
    scopes = get_param(find_system(mdlName, 'SearchDepth', 1, 'BlockType', 'Scope'), 'Name');
    if ischar(scopes), scopes = {scopes}; end
end

% ------------------------------------------------------------- PID block form
% Ideal and Standard forms store I and D as *times*; a multiplicative step on
% the I parameter then means the opposite of what the head intends.  Switching
% the copy to the Parallel form with equivalent gains keeps the controller the
% same and makes the action space mean one thing everywhere.  The user's file is
% untouched, and jev_writeback does the same conversion when it saves.
if ~reused && strcmpi(cfg.controller, 'pid_block')
    blk = [mdlName '/' cfg.pid_block];
    form = get_param(blk, 'Form');
    if ~strcmpi(form, 'Parallel')
        [p0, i0, d0] = parallel_gains(blk);
        set_param(blk, 'Form', 'Parallel', 'P', num2str(p0), ...
            'I', num2str(i0), 'D', num2str(d0));
        fprintf('[jev] PID form %s -> Parallel: P=%g I=%g D=%g\n', form, p0, i0, d0);
    end
end

% ---------------------------------------------------------------- reference
refCmd = 1.0;
if isnumeric(cfg.ref_source) && isscalar(cfg.ref_source) && isfinite(cfg.ref_source)
    refCmd = abs(cfg.ref_source);
else
    try
        amp = str2num(get_param([mdlName '/' cfg.step_blocks{1}], 'After')); %#ok<ST2NM>
        gsc = 1.0;
        if ~isempty(cfg.scale_block)
            gsc = str2num(get_param([mdlName '/' cfg.scale_block], 'Gain')); %#ok<ST2NM>
        end
        if isfinite(amp) && isfinite(gsc) && abs(amp * gsc) > 1e-9
            refCmd = abs(amp * gsc);
        end
    catch
        warning('jev:ref', 'could not infer the reference; pass cfg.ref_source');
    end
end
fprintf('[jev] reference step = %.4f\n', refCmd);

apply = @(g) set_gains(mdlName, g, cfg);
runOnce = @() run_and_extract(mdlName, stopTime, cfg);
sweepOnce = @() run_and_extract(mdlName, min(stopTime, 4), cfg);

% ---------------------------------------------------------------- Ku / Tu
% The ultimate gain depends on the plant, not on the gains we start from, so a
% warm worker caches it: the Kp sweep is 7 deliberately unstable runs and costs
% more than the whole tuning loop.
T.setup = toc(tSetup);
tSweep = tic;
sweepKey = ['sweep|' cacheKey];
cache = cache_all();
if isKey(cache, sweepKey) && ~(isfield(cfg, 'force_sweep') && cfg.force_sweep)
    c = cache(sweepKey);
    ku = c.ku; tu = c.tu;
    fprintf('[jev] Ku~%.3g Tu~%.3g s (cached)\n', ku, tu);
else
    kpGrid = logspace(log10(0.5), log10(400), 7);
    oscScore = zeros(size(kpGrid));
    tuGuess = nan(size(kpGrid));
    for i = 1:numel(kpGrid)
        apply([kpGrid(i), 0, 0]);
        try
            [t, y, ~] = sweepOnce();
            [oscScore(i), tuGuess(i)] = oscillation_score(t, y);
        catch err
            % an unstable point may not integrate at all; that is still an
            % informative "no oscillation to measure here" answer
            fprintf('[jev] Ku sweep: Kp=%.3g did not simulate (%s)\n', ...
                kpGrid(i), short_msg(err.message));
            oscScore(i) = 0; tuGuess(i) = NaN;
        end
    end
    ok = find(oscScore >= 3, 1, 'last');
    if isempty(ok)
        ku = kpGrid(end) * 0.5; tu = stopTime / 4;
        fprintf('[jev] no sustained oscillation; Ku~%.3g Tu~%.3g\n', ku, tu);
    else
        ku = kpGrid(ok); tu = tuGuess(ok);
        fprintf('[jev] Ku~%.3g (grid point %d), Tu~%.3g s\n', ku, ok, tu);
    end
    cache(sweepKey) = struct('ku', ku, 'tu', tu);
end
gzn = [0.6 * ku, 1.2 * ku / tu, 0.075 * ku * tu];
T.sweep = toc(tSweep);
tLoop = tic;

% ---------------------------------------------------------------- tuning loop
gains = gzn;
bestGains = gains; bestJ = inf; bestY = []; bestT = []; bestU = [];
prevAction = zeros(1, 3);
prevCost = 0;
nRollbacks = 0;
stall = 0;
hist = struct('gains', {}, 'M', {}, 'J', {}, 't', {}, 'y', {}, 'u', {}, 'step', {}, 'event', {});

for it = 0:iters-1
    apply(gains);
    % A candidate gain set may simply not simulate: a divergent loop, a
    % singularity, an algebraic loop that only appears at high gain.  That is a
    % normal event in tuning, not a reason to abandon the run, so it is scored
    % as an infinitely bad candidate and handed to the safety gate.
    simOK = true;
    try
        [t, y, u] = runOnce();
        M = jev_metrics(t, y, u, refCmd, stopTime, cfg.u_max);
        J = jev_cost(M, stopTime, refCmd);
    catch err
        simOK = false;
        t = []; y = []; u = []; M = nan(1, 9); J = inf;
        fprintf('[jev] iter %2d  simulation failed (%s)\n', it, short_msg(err.message));
    end

    if J < bestJ - 1e-3
        bestJ = J; bestGains = gains; bestY = y; bestT = t; bestU = u;
        stall = 0;
    else
        stall = stall + 1;
    end
    if stall >= 5
        fprintf('[jev] early stop: no improvement for 5 iterations\n');
        break
    end

    % ---- deterministic safety gate (noul is advice, this is the veto)
    event = "step";
    if (J > max(3 * bestJ + 1, 8) || ~simOK) && nRollbacks < 4
        gains = max(bestGains * 0.6, 1e-4);
        nRollbacks = nRollbacks + 1;
        event = "rollback";
        fprintf('[jev] iter %2d  J=%.3f unstable -> rollback #%d to [%.3g %.3g %.3g]\n', ...
            it, J, nRollbacks, gains(1), gains(2), gains(3));
        hist(end+1).gains = gains; hist(end).M = M; hist(end).J = J; %#ok<AGROW>
        hist(end).t = t; hist(end).y = y; hist(end).u = u;
        hist(end).step = zeros(1, 3); hist(end).event = event;
        prevAction = zeros(1, 3); prevCost = J;
        continue
    end
    if ~simOK
        % the gate is exhausted and the model still will not run: stop instead
        % of feeding empty signals to the feature builder
        fprintf('[jev] stopping: the model does not simulate at these gains\n');
        break
    end

    [feats, curves] = jev_state(M, t, y, u, gains, gzn, ku, tu, ...
        prevAction, prevCost, J, it, stopTime, refCmd);
    out = jev_head_forward(W, feats, curves);

    step = zeros(1, 3);
    mult = [0.50, 0.70, 0.87, 1.00, 1.15, 1.43, 2.00];
    d = log10(mult);
    for ax = 1:3
        p = softmax_local(out.choice(:, ax, 1)).';
        mu = p * d.';
        v = max(p * (d.^2).' - mu^2, 0);
        gate = 1 / (1 + v / var(d));
        step(ax) = min(max(stepGain * mu * gate, -0.32), 0.32);
    end

    hist(end+1).gains = gains; hist(end).M = M; hist(end).J = J; %#ok<AGROW>
    hist(end).t = t; hist(end).y = y; hist(end).u = u;
    hist(end).step = step; hist(end).event = event;

    fprintf('[jev] iter %2d  J=%.3f  gains=[%.3g %.3g %.3g]  step=[%+.3f %+.3f %+.3f]\n', ...
        it, J, gains(1), gains(2), gains(3), step(1), step(2), step(3));

    prevAction = step;
    prevCost = J;
    gains = min(max(gains .* (10 .^ step), 1e-4), 1e3);
end

% ---------------------------------------------------------------- finish
apply(bestGains);
try
    [t, y, u] = runOnce();
    M = jev_metrics(t, y, u, refCmd, stopTime, cfg.u_max);
    J = jev_cost(M, stopTime, refCmd);
catch err
    % the best set is the one that ran before; keep its numbers rather than
    % failing at the very last step
    fprintf('[jev] re-running the best gains failed (%s); keeping the recorded result\n', ...
        short_msg(err.message));
    t = bestT; y = bestY; u = bestU; J = bestJ;
    M = jev_metrics(t, y, u, refCmd, stopTime, cfg.u_max);
end
if J < bestJ
    % we re-ran the best gains, so `gains` already equals bestGains
    bestJ = J; bestY = y; bestT = t; bestU = u;
end
hist(end+1).gains = bestGains; hist(end).M = M; hist(end).J = bestJ; %#ok<AGROW>
hist(end).t = t; hist(end).y = y; hist(end).u = u;
hist(end).step = zeros(1, 3); hist(end).event = "final";

T.loop = toc(tLoop);
tSave = tic;
R = struct('model', mdlName, 'stopTime', stopTime, 'iters', iters, ...
    'ku', ku, 'tu', tu, 'gzn', gzn, 'ref', refCmd, ...
    'final_gains', bestGains, 'final_J', bestJ, 'n_rollbacks', nRollbacks, 'stepGain', stepGain, ...
    'hist', hist, 'scopes', {scopes}, 'best_t', bestT, 'best_y', bestY, 'best_u', bestU);
R.timings = T;
save(fullfile(workDir, 'tune_result.mat'), 'R');
R.timings.save = toc(tSave);
fprintf('[jev] done. best J=%.3f  gains=[%.4g %.4g %.4g}  rollbacks=%d\n', ...
    bestJ, bestGains(1), bestGains(2), bestGains(3), nRollbacks);
fprintf('[jev] saved %s\n', fullfile(workDir, 'tune_result.mat'));
end

% --------------------------------------------------------------------------- %
function set_gains(mdlName, g, cfg)
if strcmpi(cfg.controller, 'pid_block')
    % Simulink "PID Controller" block: parallel form with P, I, D mask params
    blk = [mdlName '/' cfg.pid_block];
    set_param(blk, 'P', num2str(g(1)));
    set_param(blk, 'I', num2str(g(2)));
    set_param(blk, 'D', num2str(g(3)));
else
    set_param([mdlName '/' cfg.kp_block], 'Gain', num2str(g(1)));
    set_param([mdlName '/' cfg.ki_block], 'Gain', num2str(g(2)));
    set_param([mdlName '/' cfg.kd_block], 'Gain', num2str(g(3)));
end
end

function tf = is_loaded(name)
tf = ~isempty(find_system('SearchDepth', 0, 'Type', 'block_diagram', 'Name', name));
end

function maybe_close(name, keep)
try
    if keep
        % leave it compiled; the next job reuses it
        return
    end
    if is_loaded(name)
        try, set_param(name, 'FastRestart', 'off'); catch, end
        close_system(name, 0);
    end
catch
end
end

function v = cache_get(key)
v = cache('get', key, '');
end

function m = cache_all()
m = cache('map', '', []);
end

function cache_put(key, value)
cache('put', key, value); %#ok<NASGU>
end

function value = cache(action, key, payload)
% one persistent store shared by every caller (two separate `persistent`
% variables in two functions would be two different maps)
persistent STORE
if isempty(STORE), STORE = containers.Map(); end
switch action
    case 'get'
        if isKey(STORE, key), value = STORE(key); else, value = payload; end
    case 'put'
        STORE(key) = payload;
        value = payload;
    case 'map'
        value = STORE;
    otherwise
        value = [];
end
end

function [t, y, u] = run_and_extract(mdlName, stopTime, cfg)
out = sim(mdlName, 'StopTime', num2str(stopTime));
[t, y] = pick_signal(out, cfg.measure_scope);
if isempty(t)
    error('jev:no_signal', ...
        ['nothing was logged as "%s"; run jev-tune discover to find the right ' ...
         'block, or pass measure_scope / instrument_block'], cfg.measure_scope);
end
[~, u] = pick_signal(out, cfg.input_scope);
if isempty(u), u = zeros(size(t)); end
end

function [t, y] = pick_signal(out, name)
t = []; y = [];
if isprop(out, name) || isfield(out, name)
    ds = out.(name);
    if isa(ds, 'Simulink.SimulationData.Dataset')
        e = ds.getElement(1); y = e.Values.Data; t = e.Values.Time;
    elseif isstruct(ds)
        y = ds.signals.values; t = ds.time;
    end
end
if isempty(t), return; end
t = t(:); y = y(:, 1);
end

function [score, tu] = oscillation_score(t, y)
y = y(:); n = numel(y);
i0 = round(n * 0.4);
tail = y(i0:end);
if numel(tail) < 10, score = 0; tu = NaN; return; end
s = sign(tail - mean(tail));
cross = find(diff(s) ~= 0);
score = numel(cross);
if score >= 3
    tt = t(i0 + cross);
    tu = 2 * median(diff(tt));
else
    tu = NaN;
end
if ~isfinite(tu) || tu <= 0, tu = NaN; score = 0; end
end

function J = jev_cost(M, horizon, ref)
os_ = min(max(M(1), 0), 2);
ts_ = min(max(M(2), 0), 1);
st_ = min(max(M(3) / horizon, 0), 1);
ess_ = min(max(abs(M(4)), 0), 2);
itae = min(max(M(6) / (max(ref, 1e-9) * horizon^2), 0), 3);
sat_ = min(max(M(8), 0), 1);
over_ = min(max(M(9), 0), 3);
J = os_ + (0.5 * ts_ + st_) + 4 * ess_ + itae + sat_ + 0.5 * over_;
end

function [p, i, d] = parallel_gains(blk)
% Convert the mask parameters of a PID block to parallel-form gains.
p = num_of(blk, 'P');
it = num_of(blk, 'I');
dt = num_of(blk, 'D');
if ~isfinite(p), p = 0; end
if ~isfinite(it), it = 0; end
if ~isfinite(dt), dt = 0; end
% Ideal/Standard: P(1 + 1/(I s) + D s/(...))  =>  Kp = P, Ki = P/I, Kd = P*D
if abs(it) > 1e-12, i = p / it; else, i = 0; end
d = p * dt;
end

function v = num_of(blk, param)
% Mask parameters are often expressions (pi/180, 2*Kp), so str2double would
% silently return NaN.  str2num evaluates the way Simulink itself does.
v = str2num(get_param(blk, param)); %#ok<ST2NM>
if isempty(v) || ~isscalar(v) || ~isnumeric(v), v = NaN; end
end

function s = short_msg(msg)
% Simulink error messages carry a long hyperlink; keep the console readable.
s = regexprep(msg, '<a href="[^"]*">', '');
s = regexprep(s, '</a>', '');
if numel(s) > 160, s = [s(1:157) '...']; end
end

function p = softmax_local(z)
z = z(:) - max(z);
e = exp(z);
p = e / sum(e);
end

function close_model(mdlName)
try
    bd = find_system('SearchDepth', 0, 'Type', 'block_diagram', 'Name', mdlName);
    if ~isempty(bd)
        try, set_param(mdlName, 'FastRestart', 'off'); catch, end
        close_system(mdlName, 0);
    end
catch
end
end

