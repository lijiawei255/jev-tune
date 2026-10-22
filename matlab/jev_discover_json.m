function out = jev_discover_json(cfgPath, outPath)
%JEV_DISCOVER_JSON  Run jev_discover from a JSON config and write JSON.
%
%   jev_discover_json('job.json', 'result.json')
%
%   job.json: {"model": "...", "work_dir": "...", "probe": true}
%
%   The output is shaped for a caller that is not MATLAB: block paths as
%   strings, a short human-readable evidence list, and the config that
%   jev_tune_json accepts directly.

if nargin < 2 || isempty(outPath), outPath = 'jev_discover.json'; end
cfg = jsondecode(fileread(cfgPath));
opts = struct('probe', getfield_default(cfg, 'probe', true), ...
    'work_dir', getfield_default(cfg, 'work_dir', fullfile(tempdir, 'jev_discover')));

out = struct('ok', false, 'model', cfg.model, 'confidence', 'low');
try
    D = jev_discover(cfg.model, opts);
catch err
    out.code = 'discover_failed';
    out.error = err.message;
    write_json(out, outPath);
    return
end

out.ok = D.ok;
out.confidence = D.confidence;
out.evidence = D.evidence;
out.warnings = D.warnings;
if isfield(D, 'code'), out.code = D.code; else, out.code = ''; end
if ~D.ok
    out.error = D.error;
    if isfield(D, 'candidates'), out.candidates = D.candidates; end
    write_json(out, outPath);
    return
end
out.error = '';

out.error_junction = getfield_default(D, 'error_junction', '');
out.reference = struct('value', getfield_default(D, 'reference', NaN), ...
    'source', getfield_default(D, 'reference_source', ''));
out.measure = struct('block', getfield_default(D, 'measure_block', ''), ...
    'port', getfield_default(D, 'measure_port', 1));
out.stop_time = D.stop_time;

c = D.controller;
out.controller = struct('kind', c.kind);
if strcmp(c.kind, 'pid_block')
    out.controller.block = c.block;
    out.controller.form = c.form;
    out.controller.p = c.p;
    out.controller.i = c.i;
    out.controller.d = c.d;
    out.controller.variant = getfield_default(c, 'controller', 'PID');
    if strcmpi(c.form, 'Parallel')
        out.controller.parallel_gains = [c.p c.i c.d];
    elseif all(isfinite([c.p c.i c.d])) && abs(c.p) > 0
        % Ideal/Standard store I and D as times: Ki = P/I, Kd = P*D
        ki = c.p / c.i; if ~isfinite(ki), ki = 0; end
        out.controller.parallel_gains = [c.p ki c.p * c.d];
    end
else
    out.controller.kp_block = c.kp_block;
    out.controller.ki_block = c.ki_block;
    out.controller.kd_block = c.kd_block;
    out.controller.candidates = c.candidates;
    out.controller.classes = c.classes;
end
if isfield(D, 'probe')
    out.probe = D.probe;
end
if isfield(D, 'effects')
    out.effects = D.effects(:).';
end
if isfield(D, 'junction_scan')
    scan = D.junction_scan;
    for k = 1:numel(scan)
        scan(k).fwd = numel(scan(k).fwd);
    end
    out.junction_scan = scan;
end
out.config = D.cfg;
if isfield(out.config, 'model'), out.config = rmfield(out.config, 'model'); end

write_json(out, outPath);
end

% -------------------------------------------------------------------------
function v = getfield_default(s, name, default)
if isfield(s, name) && ~isempty(s.(name))
    v = s.(name);
else
    v = default;
end
end

function write_json(out, outPath)
tmpPath = [outPath '.tmp'];
fid = fopen(tmpPath, 'w');
if fid < 0, error('jev:io', 'cannot write %s', tmpPath); end
fwrite(fid, jsonencode(out), 'char');
fclose(fid);
movefile(tmpPath, outPath, 'f');
end
