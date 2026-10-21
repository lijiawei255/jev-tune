function out = jev_tune_json(cfgPath, outPath)
%JEV_TUNE_JSON  Run the tuner from a JSON config and write a JSON result.
%
%   jev_tune_json('job.json', 'result.json')
%
%   job.json keys (all optional except model):
%     model        full path to the .slx / .mdl
%     work_dir     scratch folder (default: tempdir)
%     iters        maximum experiments (default 20)
%     stop_time    simulation horizon in seconds (default: model StopTime)
%     step_gain    trust-region multiplier (default 1.0)
%     kp_block / ki_block / kd_block      root-level gain block names
%     measure_scope / input_scope         scope block names
%     ref_source   'auto' or a number
%     u_max        actuator limit used for the saturation feature
%
%   This is the bridge the Python CLI and the MCP server call; it keeps the
%   MATLAB side free of any argument parsing.

if nargin < 2 || isempty(outPath), outPath = 'jev_result.json'; end
cfg = jsondecode(fileread(cfgPath));

workDir = getfield_default(cfg, 'work_dir', tempdir());
iters = getfield_default(cfg, 'iters', 20);
stepGain = getfield_default(cfg, 'step_gain', 1.0);
stopTime = getfield_default(cfg, 'stop_time', []);

mcfg = cfg;
mcfg = rmfield_safe(mcfg, {'model', 'work_dir', 'iters', 'stop_time', 'step_gain'});

t0 = tic;
try
    if isempty(stopTime)
        load_system(cfg.model);
        stopTime = str2double(get_param(bdroot_name(cfg.model), 'StopTime'));
        close_system(bdroot_name(cfg.model), 0);
    end
    R = jev_tune_model(cfg.model, workDir, iters, stopTime, stepGain, mcfg);
    out = struct();
    out.ok = true;
    out.model = cfg.model;
    out.final_gains = R.final_gains(:).';
    out.final_J = R.final_J;
    out.reference = R.ref;
    out.stop_time = R.stopTime;
    out.ku = R.ku;
    out.tu = R.tu;
    out.zn_start = R.gzn(:).';
    out.n_rollbacks = R.n_rollbacks;
    out.n_experiments = numel(R.hist);
    out.history = history_struct(R.hist);
    out.wall_s = toc(t0);
catch err
    out = struct();
    out.ok = false;
    out.error = err.message;
    out.identifier = err.identifier;
    out.wall_s = toc(t0);
end

fid = fopen(outPath, 'w');
if fid < 0
    error('jev:io', 'cannot write %s', outPath);
end
fwrite(fid, jsonencode(out), 'char');
fclose(fid);
end

% --------------------------------------------------------------------------- %
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

function name = bdroot_name(path)
[~, name] = fileparts(path);
end

function h = history_struct(hist)
n = numel(hist);
h = repmat(struct('J', 0, 'gains', [], 'step', [], 'event', ''), 1, n);
for i = 1:n
    h(i).J = hist(i).J;
    h(i).gains = hist(i).gains(:).';
    h(i).step = hist(i).step(:).';
    h(i).event = char(hist(i).event);
end
end
