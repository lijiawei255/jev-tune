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
validateattributes(iters, {'numeric'}, {'scalar', 'integer', 'positive', 'finite'});
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
    'tau_act', [], 'tau_esc', [], 'tau_noul', [], ... % optional policy overrides
    'cp_enabled', [], 'cp_qhat', [], 'cp_alpha', [], 'cp_k_max', [], 'cp_mode', [], ...
    'stop_on_no_action', true, ... % false for noisy/repeated or dynamic observations
    'keep_loaded', false);         % true => leave the model compiled for reuse
f = fieldnames(defaults);
for i = 1:numel(f)
    if ~isfield(cfg, f{i}), cfg.(f{i}) = defaults.(f{i}); end
end
validateattributes(cfg.stop_on_no_action, {'logical', 'numeric'}, {'scalar', 'finite'});
if ~ismember(cfg.stop_on_no_action, [0 1])
    error('jev:stop_on_no_action', 'stop_on_no_action must be true or false');
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
for policyName = {'tau_act', 'tau_esc', 'tau_noul', 'cp_enabled', 'cp_qhat', 'cp_alpha', 'cp_k_max', 'cp_mode'}
    if ~isempty(cfg.(policyName{1})), W.(policyName{1}) = cfg.(policyName{1}); end
end

% ---------------------------------------------------------------- model copy
% A model compile costs ~10 s and a MATLAB cold start ~50 s, both far more
% than a 0.1 s simulation.  With keep_loaded the compiled model is cached and
% reused by the next job (that is what makes the warm-worker throughput real).
T = struct('setup', 0, 'sweep', 0, 'loop', 0, 'save', 0);
measurements = struct('reference_probe', 0, 'sweep', 0, 'own_gain_probe', 0, ...
    'tuning', 0, 'final_verification', 0);
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
            'DataLoggingVariableName', matlab.lang.makeValidName(strrep(scopes{k}, '-', '_')), ...
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

apply = @(g) set_gains(mdlName, g, cfg);
runOnce = @() run_and_extract(mdlName, stopTime, cfg);
sweepOnce = @() run_and_extract(mdlName, min(stopTime, 4), cfg);
% captured before the sweep writes test gains into the model
gOwn = get_gains(mdlName, cfg);

% ---------------------------------------------------------------- reference
% Any Step block, not a block called "Step": the name is a convention of one
% model.  If even that fails, one run at the current gains gives the steady
% state, which is what a closed loop with integral action settles on.
refCmd = 1.0;
[refCmd, refSrc, refOK] = infer_reference(mdlName, cfg);
if ~refOK
    try
        measurements.reference_probe = measurements.reference_probe + 1;
        [t0, y0, ~] = runOnce();
        tail = y0(max(1, round(0.8 * numel(y0))):end);
        guess = abs(median(tail));
        if isfinite(guess) && guess > 1e-9
            refCmd = guess;
            refSrc = sprintf('steady state of a probe run (%.4g)', guess);
            refOK = true;
            warning('jev:ref', ...
                ['the reference could not be read from a Step block; using the ' ...
                 'steady state (%.4g). Pass ref_source if the loop has an offset'], ...
                guess);
        end
    catch
    end
end
if ~refOK
    warning('jev:ref', 'could not infer the reference; pass cfg.ref_source');
    refSrc = 'default 1.0';
end
fprintf('[jev] reference = %.4f  (%s)\n', refCmd, refSrc);

% Before touching anything: the blocks this run will write must exist.  Without
% this, a model with different names fails with "Invalid Simulink object name",
% which says nothing about what to do.
missing = {};
if strcmpi(cfg.controller, 'pid_block')
    if ~block_exists([mdlName '/' cfg.pid_block]), missing{end+1} = cfg.pid_block; end
else
    for nm = {cfg.kp_block, cfg.ki_block, cfg.kd_block}
        if ~block_exists([mdlName '/' nm{1}]), missing{end+1} = nm{1}; end %#ok<AGROW>
    end
end
if ~isempty(missing)
    error('jev:no_gains', ...
        ['these blocks do not exist in the model: %s. Run "jev-tune discover ' ...
         '--model <file>" to find the controller, or pass kp_block / ki_block / ' ...
         'kd_block'], strjoin(missing, ', '));
end

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
    % The range is a starting point, not an assumption: a plant whose ultimate
    % gain sits outside it gets a grid that is re-centred, because otherwise the
    % nominal gain handed to Ziegler-Nichols is a guess with no relation to the
    % plant.  Three rounds at most, so a model that never oscillates still ends.
    lo = 0.05; hi = 50;
    ku = NaN; tu = NaN;
    for attempt = 1:2
        kpGrid = logspace(log10(lo), log10(hi), 7);
        oscScore = zeros(size(kpGrid));
        tuGuess = nan(size(kpGrid));
        for i = 1:numel(kpGrid)
            apply([kpGrid(i), 0, 0]);
            try
                measurements.sweep = measurements.sweep + 1;
                [t, y, ~] = sweepOnce();
                [oscScore(i), tuGuess(i)] = oscillation_score(t, y);
            catch err
                % A gain at which the model will not integrate is past the
                % boundary, not "inconclusive": scoring it as zero made the sweep
                % widen into territory nothing can simulate.
                fprintf('[jev] Ku sweep: Kp=%.3g did not simulate\n', kpGrid(i));
                oscScore(i) = Inf; tuGuess(i) = NaN;
            end
        end
        lastOsc = find(oscScore > 0, 1, 'first');
        if isempty(lastOsc)
            % tolerates more gain than the top of the range
            if attempt < 2
                fprintf('[jev] Ku sweep: no oscillation up to Kp=%.3g, widening\n', hi);
                lo = kpGrid(end); hi = hi * 40;
                continue
            end
            ku = NaN;   % no boundary in reach: do not invent one
            break
        elseif lastOsc == 1
            % already unstable at the bottom of the range
            if attempt < 2
                fprintf('[jev] Ku sweep: oscillation at Kp=%.3g, narrowing\n', lo);
                hi = kpGrid(1); lo = max(lo / 100, 1e-4);
                continue
            end
            ku = kpGrid(1); tu = tuGuess(1);
            fprintf(['[jev] Ku sweep: oscillation at every trial gain; using an ' ...
                'upper bound Ku~%.3g Tu~%.3g (the start is aggressive)\n'], ku, tu);
            break
        else
            ku = kpGrid(lastOsc); tu = tuGuess(lastOsc);
            if lastOsc == numel(kpGrid)
                fprintf('[jev] Ku~%.3g (at the top of the range, a lower bound), Tu~%.3g s\n', ...
                    ku, tu);
            else
                fprintf('[jev] Ku~%.3g (between %.3g and %.3g), Tu~%.3g s\n', ...
                    ku, kpGrid(max(1, lastOsc - 1)), kpGrid(min(numel(kpGrid), lastOsc + 1)), tu);
            end
            if ~isfinite(tu) || tu <= 0 || tu > stopTime / 3
                fprintf(['[jev] Tu~%.3g s is close to the %.1f s sweep window; ' ...
                    'the period estimate may be short\n'], tu, min(stopTime, 4));
            end
            break
        end
    end
    cache(sweepKey) = struct('ku', ku, 'tu', tu);
end

if ~isfinite(ku) || ~isfinite(tu) || tu <= 0
    % Ziegler-Nichols has no answer for this plant (a first-order loop, or one
    % that stays marginally stable across the whole range).  Inventing a number
    % is how the old code produced a start that was really the top of its grid.
    % Start where the model already is instead, and keep the feature scaling
    % consistent with it.
    gzn = gOwn;
    ku = max(gOwn(1), 1e-6) / 0.6;
    tu = max(stopTime / 4, 1e-3);
    fprintf(['[jev] no ultimate gain in reach; starting from the model own ' ...
        'gains [%.4g %.4g %.4g]\n'], gOwn(1), gOwn(2), gOwn(3));
else
    gzn = [0.6 * ku, 1.2 * ku / tu, 0.075 * ku * tu];
end
T.sweep = toc(tSweep);
tLoop = tic;

% ------------------------------------------------- the gains the model already has
% The loop starts from Ziegler-Nichols, which says nothing about the controller
% the model shipped with.  Handing back something worse than what the user
% already runs is not help, so those gains are measured once and become the floor
% the safety gate defends.  One simulation, and the promise in the README stops
% depending on how the ZN start happens to compare.
%
% Acceptance (2026-10-22): on a model whose own gains are better than its ZN
% start, the returned cost must be at most the own-gains cost; on a model whose
% own gains are worse, the behaviour must be unchanged.
ownJ = inf; ownT = []; ownY = []; ownU = [];
if any(abs(gOwn - gzn) > 1e-9 * max(1, abs(gOwn)))
    apply(gOwn);
    try
        measurements.own_gain_probe = measurements.own_gain_probe + 1;
        [ownT, ownY, ownU] = runOnce();
        ownJ = jev_cost(jev_metrics(ownT, ownY, ownU, refCmd, stopTime, cfg.u_max), ...
            stopTime, refCmd);
        fprintf('[jev] the model own gains [%.4g %.4g %.4g] give J=%.3f\n', ...
            gOwn(1), gOwn(2), gOwn(3), ownJ);
    catch err
        fprintf('[jev] the model own gains do not simulate (%s); ignoring them\n', ...
            short_msg(err.message));
        ownJ = inf; ownT = []; ownY = []; ownU = [];
    end
end

% ---------------------------------------------------------------- tuning loop
gains = gzn;
bestGains = gains; bestJ = inf; bestY = []; bestT = []; bestU = [];
if ownJ < bestJ
    bestGains = gOwn; bestJ = ownJ;
    bestT = ownT; bestY = ownY; bestU = ownU;
end
prevAction = zeros(1, 3);
prevCost = 0;
nRollbacks = 0;
nEscalated = 0;
stoppedNoAction = false;
stopReason = 'budget';
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
        measurements.tuning = measurements.tuning + 1;
        [t, y, u] = runOnce();
        M = jev_metrics(t, y, u, refCmd, stopTime, cfg.u_max);
        J = jev_cost(M, stopTime, refCmd);
    catch err
        simOK = false;
        t = []; y = []; u = []; M = nan(1, 9); J = inf;
        fprintf('[jev] iter %2d  simulation failed (%s)\n', it, short_msg(err.message));
    end

    % Every row describes the gains that produced this measurement.  The next
    % proposal/rollback is stored separately, including on early exits.
    hist(end+1).gains = gains; hist(end).M = M; hist(end).J = J; %#ok<AGROW>
    hist(end).t = t; hist(end).y = y; hist(end).u = u;
    hist(end).step = zeros(1, 3); hist(end).event = "measured";
    hist(end).next_gains = gains;
    hist(end).held = false(1, 3); hist(end).escalate = false(1, 3);
    hist(end).proposed = zeros(1, 3); hist(end).reason = zeros(1, 3);
    hist(end).set_size = zeros(1, 3); hist(end).conformal_set = false(7, 3);
    hist(end).conformal_applied = false;
    hist(end).conformal_mode = 'off';
    hist(end).conformal_would_hold = false(1, 3); hist(end).conformal_reason = zeros(1, 3);
    hist(end).measurement_reused = false;

    if J < bestJ - 1e-3
        bestJ = J; bestGains = gains; bestY = y; bestT = t; bestU = u;
        stall = 0;
    else
        stall = stall + 1;
    end
    if stall >= 5
        hist(end).event = "stop";
        stopReason = 'early_stop';
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
        hist(end).next_gains = gains; hist(end).event = event;
        prevAction = zeros(1, 3); prevCost = J;
        if cfg.stop_on_no_action && isequal(gains, hist(end).gains)
            stoppedNoAction = true;
            stopReason = 'rollback_no_action';
            hist(end).event = "stop_rollback_no_action";
            fprintf('[jev] stopping: rollback would repeat the same gains\n');
            break
        end
        continue
    end
    if ~simOK
        hist(end).event = "simulation_failed";
        stopReason = 'simulation_failed';
        % the gate is exhausted and the model still will not run: stop instead
        % of feeding empty signals to the feature builder
        fprintf('[jev] stopping: the model does not simulate at these gains\n');
        break
    end
    if ~isfinite(bestJ) && nRollbacks >= 2
        stopReason = 'no_successful_simulation';
        fprintf('[jev] stopping: nothing has simulated successfully yet\n');
        break
    end

    [feats, curves] = jev_state(M, t, y, u, gains, gzn, ku, tu, ...
        prevAction, prevCost, J, it, stopTime, refCmd);
    out = jev_head_forward(W, feats, curves);

    decision = jev_decode(W, out, stepGain);
    step = decision.step;
    nEscalated = nEscalated + sum(decision.escalate);

    hist(end).step = step; hist(end).event = event;
    hist(end).held = decision.held; hist(end).escalate = decision.escalate;
    hist(end).proposed = decision.proposed; hist(end).reason = decision.reason;
    hist(end).set_size = decision.set_size; hist(end).conformal_set = decision.conformal_set;
    hist(end).conformal_applied = decision.conformal_applied;
    hist(end).conformal_mode = decision.conformal_mode;
    hist(end).conformal_would_hold = decision.conformal_would_hold;
    hist(end).conformal_reason = decision.conformal_reason;

    fprintf('[jev] iter %2d  J=%.3f  gains=[%.3g %.3g %.3g]  step=[%+.3f %+.3f %+.3f]\n', ...
        it, J, gains(1), gains(2), gains(3), step(1), step(2), step(3));

    prevAction = step;
    prevCost = J;
    gains = min(max(gains .* (10 .^ step), 1e-4), 1e3);
    hist(end).next_gains = gains;
    if cfg.stop_on_no_action && isequal(gains, hist(end).gains)
        % This offline simulation path can stop when no gain changes. It does
        % not certify a fixed point: history features or a new observation may
        % change a later decision. Set false for noise/dynamic monitoring.
        stoppedNoAction = true;
        stopReason = 'no_action';
        hist(end).event = "stop_no_action";
        fprintf('[jev] stopping: no actual gain change; repeated observations disabled\n');
        break
    end
end

% ---------------------------------------------------------------- finish
apply(bestGains);
% A no-action stop ends deterministic offline search. The best response was
% already measured (possibly by the own-gain probe), so reuse that trace.
finalReused = stoppedNoAction && ~isempty(bestY);
try
    if finalReused
        t = bestT; y = bestY; u = bestU;
    else
        measurements.final_verification = measurements.final_verification + 1;
        [t, y, u] = runOnce();
    end
    M = jev_metrics(t, y, u, refCmd, stopTime, cfg.u_max);
    J = jev_cost(M, stopTime, refCmd);
catch err
    % the best set is the one that ran before; keep its numbers rather than
    % failing at the very last step
    fprintf('[jev] re-running the best gains failed (%s); keeping the recorded result\n', ...
        short_msg(err.message));
    t = bestT; y = bestY; u = bestU; J = bestJ;
    if isempty(y)
        error('jev:no_signal', ...
            ['no experiment produced a usable response; the model did not ' ...
             'simulate at any gain set (last error: %s)'], short_msg(err.message));
    end
    M = jev_metrics(t, y, u, refCmd, stopTime, cfg.u_max);
end
if J < bestJ
    % we re-ran the best gains, so `gains` already equals bestGains
    bestJ = J; bestY = y; bestT = t; bestU = u;
end
hist(end+1).gains = bestGains; hist(end).M = M; hist(end).J = J; %#ok<AGROW>
hist(end).t = t; hist(end).y = y; hist(end).u = u;
hist(end).step = zeros(1, 3); hist(end).event = "final";
hist(end).next_gains = bestGains;
hist(end).held = false(1, 3); hist(end).escalate = false(1, 3);
hist(end).proposed = zeros(1, 3); hist(end).reason = zeros(1, 3);
hist(end).set_size = zeros(1, 3); hist(end).conformal_set = false(7, 3);
hist(end).conformal_applied = false;
hist(end).conformal_mode = 'off';
hist(end).conformal_would_hold = false(1, 3); hist(end).conformal_reason = zeros(1, 3);
hist(end).measurement_reused = finalReused;

T.loop = toc(tLoop);
tSave = tic;
R = struct('model', mdlName, 'stopTime', stopTime, 'iters', iters, ...
    'ku', ku, 'tu', tu, 'gzn', gzn, 'ref', refCmd, ...
    'own_gains', gOwn, 'own_J', ownJ, ...
    'final_gains', bestGains, 'final_J', bestJ, 'n_rollbacks', nRollbacks, 'stepGain', stepGain, ...
    'n_escalations', nEscalated, ...
    'n_no_action_stops', double(stoppedNoAction), ...
    'stop_reason', stopReason, 'measurements', measurements, ...
    'n_total_simulations', sum(cell2mat(struct2cell(measurements))), ...
    'n_recorded_measurements', measurements.tuning + measurements.final_verification, ...
    'hist', hist, 'scopes', {scopes}, 'best_t', bestT, 'best_y', bestY, 'best_u', bestU);
R.decision_policy = struct('step_gain', stepGain, 'stop_on_no_action', logical(cfg.stop_on_no_action));
for policyName = {'temperature', 'tau_act', 'tau_esc', 'tau_noul', ...
        'cp_enabled', 'cp_qhat', 'cp_alpha', 'cp_k_max', 'cp_mode', 'cp_n_calibration', ...
        'cp_quantile_rank', 'cp_method', 'model_sha256', 'calibration_sha256'}
    if isfield(W, policyName{1})
        R.decision_policy.(policyName{1}) = W.(policyName{1});
    end
end
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
    set_param(blk, 'P', num2str(g(1), 17));
    set_param(blk, 'I', num2str(g(2), 17));
    set_param(blk, 'D', num2str(g(3), 17));
else
    set_param([mdlName '/' cfg.kp_block], 'Gain', num2str(g(1), 17));
    set_param([mdlName '/' cfg.ki_block], 'Gain', num2str(g(2), 17));
    set_param([mdlName '/' cfg.kd_block], 'Gain', num2str(g(3), 17));
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
if size(y, 2) > 1
    error('jev:wide_signal', ...
        ['"%s" logs %d signals; the tuner needs one. Pass --auto so it taps the ' ...
         'feedback signal itself, or name a single-signal Scope'], ...
        cfg.measure_scope, size(y, 2));
end
[~, u] = pick_signal(out, cfg.input_scope);
if isempty(u), u = zeros(size(t)); end
end

function [t, y] = pick_signal(out, name)
% Return the logged signal as a matrix: the caller decides what to do with more
% than one column.  Silently taking column 1 is how a two-input Scope (reference
% *and* response) hands the tuner the reference as the measurement.
t = []; y = [];
var = matlab.lang.makeValidName(strrep(name, '-', '_'));
if isprop(out, var) || isfield(out, var)
    ds = out.(var);
    if isa(ds, 'Simulink.SimulationData.Dataset')
        e = ds.getElement(1); y = e.Values.Data; t = e.Values.Time;
    elseif isstruct(ds)
        y = ds.signals.values; t = ds.time;
    end
end
if isempty(t), return; end
t = t(:);
y = reshape(y, numel(t), []);
end

function [score, tu] = oscillation_score(t, y)
% A sustained oscillation is one whose peaks do not decay.  Counting mean
% crossings alone calls a damped second-order response "unstable" (its overshoot
% crosses the mean three or four times), and then the highest trial gain wins the
% sweep - which is how Ku always came out as the top of the grid.
score = 0; tu = NaN;
y = y(:); n = numel(y);
if n < 20, return; end
i0 = max(1, round(n * 0.35));
seg = y(i0:end) - mean(y(i0:end));
tt = t(i0:end);
up = find(seg(1:end-1) <= 0 & seg(2:end) > 0);
if numel(up) < 3, return; end              % three peaks at least, to judge decay
amps = zeros(1, numel(up) - 1);
for k = 1:numel(up) - 1
    amps(k) = max(seg(up(k):up(k+1)));
end
amps = amps(amps > 0.01 * max(amps));
if numel(amps) < 3, return; end
ratio = amps(end) / max(amps(end-1), eps);
tu = 2 * median(diff(tt(up)));
if ratio >= 0.9 && isfinite(tu) && tu > 0
    score = numel(amps);
end
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

function [ref, src, ok] = infer_reference(mdlName, cfg)
% Reference by block *type*, with the configured name only as a preference.
ref = NaN; src = 'none'; ok = false;
if isnumeric(cfg.ref_source) && isscalar(cfg.ref_source) && isfinite(cfg.ref_source)
    ref = abs(cfg.ref_source); src = 'given by the caller'; ok = true;
    return
end
steps = {};
for k = 1:numel(cfg.step_blocks)
    b = [mdlName '/' cfg.step_blocks{k}];
    if block_exists(b), steps{end+1} = b; end %#ok<AGROW>
end
if isempty(steps)
    steps = find_system(mdlName, 'SearchDepth', 1, 'LookUnderMasks', 'none', ...
        'FollowLinks', 'off', 'BlockType', 'Step');
end
if numel(steps) ~= 1
    if numel(steps) > 1
        src = sprintf('%d Step blocks, ambiguous', numel(steps));
    end
    return
end
amp = num_of(steps{1}, 'After');
if ~isfinite(amp), amp = num_of(steps{1}, 'Amplitude'); end
gsc = 1;
if ~isempty(cfg.scale_block) && block_exists([mdlName '/' cfg.scale_block])
    g = num_of([mdlName '/' cfg.scale_block], 'Gain');
    if isfinite(g), gsc = g; end
end
if isfinite(amp) && abs(amp * gsc) > 1e-12
    ref = abs(amp * gsc);
    src = sprintf('%s%s', strrep(steps{1}, [mdlName '/'], ''), ...
        ternary(abs(gsc - 1) > 1e-12, sprintf(' x %g', gsc), ''));
    ok = true;
end
end

function tf = block_exists(path)
tf = false;
try
    tf = ~isempty(get_param(path, 'Handle'));
catch
end
end

function out = ternary(cond, a, b)
if cond, out = a; else, out = b; end
end

function g = get_gains(mdlName, cfg)
% The controller as the model currently has it, whatever encodes it.
if strcmpi(cfg.controller, 'pid_block')
    blk = [mdlName '/' cfg.pid_block];
    g = [num_of(blk, 'P'), num_of(blk, 'I'), num_of(blk, 'D')];
    if strcmpi(safe_get(blk, 'Form', 'Parallel'), 'Parallel') == false
        g = parallel_gains(blk);
    end
else
    g = [num_of([mdlName '/' cfg.kp_block], 'Gain'), ...
         num_of([mdlName '/' cfg.ki_block], 'Gain'), ...
         num_of([mdlName '/' cfg.kd_block], 'Gain')];
end
g(~isfinite(g) | g < 1e-6) = 1e-3;
end

function v = safe_get(blk, param, fallback)
try
    v = get_param(blk, param);
catch
    v = fallback;
end
if isempty(v), v = fallback; end
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

