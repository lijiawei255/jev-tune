function out = jev_tune_json(cfgPath, outPath)
%JEV_TUNE_JSON  Run the tuner from a JSON config and write a JSON result.
%
%   jev_tune_json('job.json', 'result.json')
%
%   job.json keys (all optional except model):
%     model            full path to the .slx / .mdl
%     work_dir         scratch folder (default: tempdir)
%     iters            maximum tuning-loop measurements (default 20); discovery,
%                      sweep, own-gain probe and final verification are additional
%     stop_time        simulation horizon in seconds (default: model StopTime)
%     step_gain        trust-region multiplier (default 1.0)
%     auto_discover    find the blocks, the measured signal and the reference
%                      first, instead of relying on default names
%     kp_block / ki_block / kd_block          gain block names (paths allowed)
%     controller       'gains' (three blocks) or 'pid_block'
%     pid_block        masked PID block name
%     measure_scope / input_scope             logging scope names
%     measure_element / input_element         explicit Dataset element index/name
%     instrument_block tap this block with a Scope on the working copy
%     ref_source       'auto' or a number
%     u_max            actuator limit used for the saturation feature
%     cp_mode          'monitor' (default) or explicit 'hard_hold'
%     stop_on_no_action true (default): stop on unchanged gains; false retains
%                      repeated observations for noise/dynamic monitoring
%
%   Explicit keys always win over what discovery proposes: the user (or the
%   agent acting for them) has the last word.
%
%   This is the bridge the Python CLI and the MCP server call; it keeps the
%   MATLAB side free of any argument parsing.

if nargin < 2 || isempty(outPath), outPath = 'jev_result.json'; end
cfg = jsondecode(fileread(cfgPath));

workDir = getfield_default(cfg, 'work_dir', tempdir());
iters = getfield_default(cfg, 'iters', 20);
stepGain = getfield_default(cfg, 'step_gain', 1.0);
stopTime = getfield_default(cfg, 'stop_time', []);
autoDiscover = logical(getfield_default(cfg, 'auto_discover', false));

mcfg = cfg;
mcfg = rmfield_safe(mcfg, {'model', 'work_dir', 'iters', 'stop_time', ...
    'step_gain', 'auto_discover'});
ledger = containers.Map('KeyType', 'char', 'ValueType', 'double');
mcfg.simulation_ledger = ledger;

t0 = tic;
discovery = struct('used', false);
try
    if autoDiscover
        [discovery, mcfg, stopTime] = discover_first(cfg.model, mcfg, stopTime, workDir);
        if ~discovery.ok
            out = struct('ok', false, 'code', discovery.code, ...
                'error', discovery.error, 'warnings', {discovery.warnings}, ...
                'discovery', discovery, 'wall_s', toc(t0));
            [out.measurements, out.n_total_simulations] = jev_simulation_counts(ledger);
            write_json(out, outPath);
            return
        end
    end

    % stopTime stays empty on purpose: jev_tune_model reads it from the model
    % it has already loaded, so this wrapper never pays a second load_system
    R = jev_tune_model(cfg.model, workDir, iters, stopTime, stepGain, mcfg);
    out = struct();
    out.ok = true;
    out.code = '';
    out.model = cfg.model;
    out.final_gains = R.final_gains(:).';
    out.final_J = R.final_J;
    out.reference = R.ref;
    out.stop_time = R.stopTime;
    out.ku = R.ku;
    out.tu = R.tu;
    out.zn_start = R.gzn(:).';
    if isfield(R, 'own_gains')
        out.own_gains = R.own_gains(:).';
        out.own_J = R.own_J;
    end
    out.n_rollbacks = R.n_rollbacks;
    out.n_escalations = R.n_escalations;
    out.decision_policy = R.decision_policy;
    out.cache_policy = R.cache_policy;
    out.n_experiments = R.n_recorded_measurements;
    out.n_history_records = numel(R.hist);
    % Includes loop/final measurement attempts, excluding cached final rows;
    % the own-gain probe and Ku/Tu sweep precede this recorded history.
    out.n_recorded_measurements = R.n_recorded_measurements;
    out.n_no_action_stops = R.n_no_action_stops;
    out.stop_reason = R.stop_reason;
    [out.measurements, out.n_total_simulations] = jev_simulation_counts(ledger);
    out.measurement_budget_scope = 'iters limits tuning-loop measurements; total includes discovery and setup';
    out.warnings = {};
    if isfield(R, 'stopTime') && abs(R.stopTime - 10) / 10 > 0.5
        out.warnings{end+1} = sprintf(['stopTime %.2f s is far from the 10 s training horizon; ' ...
            'the response features may be out of distribution (retrain or rescale the metrics)'], R.stopTime);
    end
    if discovery.used
        out.discovery = discovery;
        out.warnings = [out.warnings, discovery.warnings];
    end
    if isfield(R, 'timings'), out.timings = R.timings; end
    out.history = history_struct(R.hist);
    out.trace = trace_struct(R);
    out.wall_s = toc(t0);
catch err
    out = struct();
    out.ok = false;
    out.error = err.message;
    out.identifier = err.identifier;
    out.code = error_code(err.identifier);
    out.hint = error_hint(out.code);
    if discovery.used, out.discovery = discovery; end
    out.wall_s = toc(t0);
    [out.measurements, out.n_total_simulations] = jev_simulation_counts(ledger);
end

write_json(out, outPath);
end

% --------------------------------------------------------------------------- %
function [discovery, mcfg, stopTime] = discover_first(mdlPath, mcfg, stopTime, workDir)
%DISCOVER_FIRST  Ask jev_discover what the model looks like, then merge.
D = jev_discover(mdlPath, struct('probe', true, ...
    'work_dir', fullfile(workDir, 'discover'), 'simulation_ledger', mcfg.simulation_ledger));

discovery = struct('used', true, 'ok', D.ok, 'confidence', D.confidence, ...
    'warnings', {D.warnings}, 'evidence', {D.evidence}, ...
    'measurements', D.measurements, 'n_total_simulations', D.n_total_simulations);
if isfield(D, 'code'), discovery.code = D.code; else, discovery.code = ''; end
if ~D.ok
    discovery.error = D.error;
    return
end
discovery.error = '';
discovery.error_junction = getfield_default(D, 'error_junction', '');
discovery.measure_block = getfield_default(D, 'measure_block', '');
discovery.reference = getfield_default(D, 'reference', NaN);
discovery.reference_source = getfield_default(D, 'reference_source', '');
if isfield(D, 'controller')
    c = D.controller;
    discovery.controller_kind = c.kind;
    if strcmp(c.kind, 'pid_block')
        discovery.pid_block = c.block;
        discovery.pid_form = c.form;
    else
        discovery.kp_block = c.kp_block;
        discovery.ki_block = c.ki_block;
        discovery.kd_block = c.kd_block;
    end
end
if isfield(D, 'probe')
    discovery.probe = D.probe;
end

% Explicit keys win: only fill in what the caller did not set.
if isfield(D, 'cfg')
    names = fieldnames(D.cfg);
    for k = 1:numel(names)
        if strcmp(names{k}, 'model'), continue; end
        if strcmp(names{k}, 'stop_time')
            if isempty(stopTime), stopTime = D.cfg.stop_time; end
        elseif ~isfield(mcfg, names{k}) || isempty(mcfg.(names{k}))
            mcfg.(names{k}) = D.cfg.(names{k});
        end
    end
end
end

function code = error_code(identifier)
code = 'tune_failed';
if isempty(identifier), return; end
switch identifier
    case 'jev:no_signal', code = 'no_signal';
    case 'jev:wide_signal', code = 'wide_signal';
    case 'jev:signal_element', code = 'invalid_signal';
    case 'jev:invalid_signal', code = 'invalid_signal';
    case 'jev:source_overwrite', code = 'source_overwrite';
    case 'jev:unsupported_pid_configuration', code = 'unsupported_pid_configuration';
    case 'jev:pid_form', code = 'unsupported_pid_configuration';
    case 'jev:no_gains', code = 'no_gains';
    case 'jev:instrument', code = 'instrument_failed';
    case 'jev:ref', code = 'no_reference';
    otherwise
        if startsWith(identifier, 'Simulink:'), code = 'model_error'; end
end
end

function hint = error_hint(code)
switch code
    case 'no_signal'
        hint = ['nothing was logged as the measurement: run "jev-tune discover" ' ...
            'to find the right block, or pass measure_scope/instrument_block'];
    case 'wide_signal'
        hint = ['that Scope logs several signals; pass --auto so the tuner taps ' ...
            'the feedback signal itself, or name a single-signal Scope'];
    case 'no_gains'
        hint = ['the gain blocks named in the config do not exist: run "jev-tune ' ...
            'discover" and reuse its config, or pass kp_block/ki_block/kd_block'];
    case 'instrument_failed'
        hint = ['could not attach a logging Scope; pass measure_scope with the ' ...
            'name of an existing Scope or To Workspace block'];
    case 'no_reference'
        hint = 'pass ref_source with the numeric reference value';
    case 'model_error'
        hint = ['Simulink refused the model: check that it compiles and that ' ...
            'the workspace variables it needs are defined'];
    otherwise
        hint = 'see the error message; the model may not be supported (cascade, MIMO)';
end
end

function write_json(out, outPath)
jev_write_json_atomic(out, outPath);
end

function s = getfield_default(s, name, default)
if isfield(s, name) && ~isempty(s.(name))
    s = s.(name);
else
    s = default;
end
end

function s = rmfield_safe(s, names)
for i = 1:numel(names)
    if isfield(s, names{i})
        s = rmfield(s, names{i});
    end
end
end

function tr = trace_struct(R)
% The plot needs the shape of the response, not the whole recording: two traces
% downsampled to a few hundred points keep the JSON small enough to print.
tr = struct('reference', R.ref);
if ~isempty(R.best_t) && ~isempty(R.best_y)
    tr.best = thin(R.best_t, R.best_y, R.final_J);
end
if ~isempty(R.hist) && ~isempty(R.hist(1).t)
    tr.start = thin(R.hist(1).t, R.hist(1).y, R.hist(1).J);
end
end

function s = thin(t, y, J)
t = t(:).'; y = y(:).';
n = numel(t);
keep = max(2, round(n / 600));
idx = 1:keep:n;
s = struct('t', t(idx), 'y', y(idx), 'J', J);
end

function h = history_struct(hist)
n = numel(hist);
h = repmat(struct('J', 0, 'gains', [], 'step', [], 'event', ''), 1, n);
for i = 1:n
    h(i).J = hist(i).J;
    h(i).gains = hist(i).gains(:).';
    h(i).step = hist(i).step(:).';
    h(i).event = char(hist(i).event);
    for name = {'next_gains', 'proposed', 'held', 'escalate', 'reason', 'set_size', ...
            'conformal_would_hold', 'conformal_reason'}
        h(i).(name{1}) = hist(i).(name{1})(:).';
    end
    h(i).conformal_set = hist(i).conformal_set.'; % JSON axes x vocabulary
    h(i).conformal_applied = hist(i).conformal_applied;
    h(i).conformal_mode = hist(i).conformal_mode;
    h(i).measurement_reused = hist(i).measurement_reused;
end
end
