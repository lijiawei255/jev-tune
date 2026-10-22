function out = jev_tune_all(cfgPath, outPath)
%JEV_TUNE_ALL  Tune every independent loop of a model, one after another.
%
%   out = jev_tune_all('job.json', 'result.json')
%
%   job.json: {"model": "...", "work_dir": "...", "iters": 20, "out_dir": "...",
%              "suffix": "_tuned"}
%
%   For a model with several *independent* loops (a gantry with four axes, an
%   oven with three zones) the honest answer is not "tune the model", it is
%   "tune each loop".  This runs discovery once, then tunes each verified loop,
%   carrying the gains forward: loop k starts from the file loop k-1 wrote, so
%   the last copy has all of them.  A cascade is refused by discovery before any
%   of this starts.
%
%   The result is the ledger: per loop, the junction it was tuned against, the
%   cost before and after, the experiments it took, and the gains.  Numbers come
%   from jev_tune_json; nothing is recomputed here.

if nargin < 2 || isempty(outPath), outPath = 'jev_tune_all.json'; end
cfg = jsondecode(fileread(cfgPath));
workDir = getfield_default(cfg, 'work_dir', fullfile(tempdir, 'jev_all'));
if ~isfolder(workDir), mkdir(workDir); end
iters = getfield_default(cfg, 'iters', 20);
stopTime = getfield_default(cfg, 'stop_time', []);
stepGain = getfield_default(cfg, 'step_gain', 1.0);

t0 = tic;
out = struct('ok', false, 'model', cfg.model, 'loops', {{}}, 'wall_s', 0);

% ---- discovery once, on the original file
D = jev_discover(cfg.model, struct('probe', true, 'all_loops', true, ...
    'work_dir', fullfile(workDir, 'discover')));
if ~D.ok
    out.code = D.code;
    out.error = D.error;
    out.warnings = D.warnings;
    out.discovery = summarise_discovery(D);
    out = finish(out, outPath, t0);
    return
end

valid = [D.loops.verified];
loops = D.loops(valid);
if numel(loops) < 2
    out.code = 'single_loop';
    out.error = 'only one verified loop was found; use the normal tune path';
    out.discovery = summarise_discovery(D);
    out = finish(out, outPath, t0);
    return
end

% ---- chain: each loop starts from the file the previous one wrote
[srcDir, stem, ext] = fileparts(cfg.model);
outDir = getfield_default(cfg, 'out_dir', srcDir);
suffix = getfield_default(cfg, 'suffix', '_tuned');
if ~isfolder(outDir), mkdir(outDir); end
target = fullfile(outDir, [stem suffix ext]);
current = cfg.model;
records = {};

for k = 1:numel(loops)
    fprintf('\n[all] loop %d/%d: %s\n', k, numel(loops), loops(k).junction);
    tLoop = tic;
    Dl = jev_discover(current, struct('probe', true, 'all_loops', true, ...
        'loop_junction', loops(k).junction, 'work_dir', ...
        fullfile(workDir, sprintf('discover_%d', k))));
    tDisc = toc(tLoop);
    rec = struct('junction', loops(k).junction, 'measure', loops(k).measure, ...
        'reference', loops(k).reference, 'ok', false, 'code', '', ...
        'start_J', NaN, 'final_J', NaN, 'n_experiments', 0, 'gains', []);
    if ~Dl.ok
        rec.code = Dl.code;
        rec.error = Dl.error;
        records{end+1} = rec; %#ok<AGROW>
        fprintf('[all]   skipped: %s\n', Dl.code);
        continue
    end
    jobCfg = merge_cfg(Dl.cfg, cfg);
    job = fullfile(workDir, sprintf('job_%d.json', k));
    resPath = fullfile(workDir, sprintf('res_%d.json', k));
    % jev_tune_json takes the flattened form
    flat = jobCfg;
    flat.model = current;
    flat.work_dir = fullfile(workDir, sprintf('run_%d', k));
    flat.iters = iters;
    if ~isempty(stopTime), flat.stop_time = stopTime; end
    flat.step_gain = stepGain;
    write_json(flat, job);
    tTune = tic;
    R = jev_tune_json(job, resPath);
    tTune = toc(tTune);
    rec.ok = R.ok;
    rec.code = getfield_default(R, 'code', '');
    if R.ok
        rec.start_J = R.history(1).J;
        rec.final_J = R.final_J;
        rec.n_experiments = R.n_experiments;
        rec.gains = R.final_gains;
        wbCfg = struct('controller', getfield_default(jobCfg, 'controller', 'gains'), ...
            'kp_block', getfield_default(jobCfg, 'kp_block', ''), ...
            'ki_block', getfield_default(jobCfg, 'ki_block', ''), ...
            'kd_block', getfield_default(jobCfg, 'kd_block', ''), ...
            'pid_block', getfield_default(jobCfg, 'pid_block', ''), ...
            'target', target);
        W = jev_writeback(current, R.final_gains, wbCfg, ...
            fullfile(workDir, sprintf('wb_%d.json', k)));
        rec.written = W.ok;
        if ~W.ok
            rec.ok = false;
            rec.error = W.error;
        else
            current = target;
        end
        fprintf('[all]   J %.3f -> %.3f in %d experiments (discover %.1fs, tune %.1fs)\n', ...
            rec.start_J, rec.final_J, rec.n_experiments, tDisc, tTune);
    else
        rec.error = R.error;
        fprintf('[all]   failed: %s\n', R.error);
    end
    records{end+1} = rec; %#ok<AGROW>
end

out.loops = records;
out.n_loops = numel(records);
out.n_tuned = sum(cellfun(@(r) r.ok, records));
out.target = target;
out.total_experiments = sum(cellfun(@(r) r.n_experiments, records));
out.ok = out.n_tuned > 0 && isfile(target);
out.code = '';
out.discovery = summarise_discovery(D);
out = finish(out, outPath, t0);
end

% -------------------------------------------------------------------------
function flat = merge_cfg(base, user)
% Explicit user keys win over what discovery proposed.
flat = base;
names = fieldnames(user);
for k = 1:numel(names)
    if any(strcmp(names{k}, {'model', 'work_dir', 'iters', 'stop_time', 'step_gain'}))
        continue
    end
    flat.(names{k}) = user.(names{k});
end
end

function s = summarise_discovery(D)
s = struct('ok', D.ok, 'confidence', D.confidence, ...
    'error_junction', getfield_default(D, 'error_junction', ''), ...
    'measure_block', getfield_default(D, 'measure_block', ''), ...
    'warnings', {getfield_default(D, 'warnings', {{}})});
end

function v = getfield_default(s, name, default)
if isstruct(s) && isfield(s, name) && ~isempty(s.(name))
    v = s.(name);
else
    v = default;
end
end

function write_json(out, path)
tmp = [path '.tmp'];
fid = fopen(tmp, 'w');
if fid < 0, error('jev:io', 'cannot write %s', tmp); end
fwrite(fid, jsonencode(out), 'char');
fclose(fid);
movefile(tmp, path, 'f');
end

function out = finish(out, outPath, t0)
out.wall_s = toc(t0);
write_json(out, outPath);
end
