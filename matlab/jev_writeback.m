function out = jev_writeback(mdlPath, gains, cfg, outPath)
%JEV_WRITEBACK  Write tuned gains into a *copy* of the model.
%
%   out = jev_writeback('C:/work/Motor.slx', [91.5 172 14.1], cfg, 'w.json')
%
%   cfg (optional): controller ('gains' | 'pid_block'), kp_block, ki_block,
%   kd_block, pid_block, out_dir, suffix (default '_tuned').
%
%   The user's file is never modified: the result is
%   <out_dir>/<name><suffix>.slx.  A masked PID block whose Form is Ideal or
%   Standard stores I and D as *times*, so the copy is switched to the Parallel
%   form with the equivalent gains: same controller, one representation.
%
%   Call this only after the model is closed; it loads its own copy.

if nargin < 3 || isempty(cfg), cfg = struct(); end
if nargin < 4 || isempty(outPath), outPath = 'jev_writeback.json'; end
cfg = with_defaults(cfg);
gains = gains(:).';

out = struct('ok', false, 'source', mdlPath, 'gains', gains);
if ~isfile(mdlPath)
    out.code = 'model_not_found';
    out.error = sprintf('no such file: %s', mdlPath);
    write_json(out, outPath);
    return
end

[srcDir, stem, ext] = fileparts(mdlPath);
if isempty(cfg.out_dir), cfg.out_dir = srcDir; end
if ~isfolder(cfg.out_dir), mkdir(cfg.out_dir); end
if isfield(cfg, 'target') && ~isempty(cfg.target)
    % chained runs (jev_tune_all) name the file themselves
    target = cfg.target;
else
    target = fullfile(cfg.out_dir, [stem cfg.suffix ext]);
end
out.target = target;

tmpDir = tempname;
mkdir(tmpDir);
copyName = ['jev_wb' ext];
tmpPath = fullfile(tmpDir, copyName);
copyfile(mdlPath, tmpPath);
if isfolder(fullfile(srcDir, 'images'))
    copyfile(fullfile(srcDir, 'images'), fullfile(tmpDir, 'images'));
end

mdl = 'jev_wb';
cleanup = onCleanup(@() safe_close(mdl)); %#ok<NASGU>
try
    load_system(tmpPath);
catch err
    out.code = 'load_failed';
    out.error = err.message;
    write_json(out, outPath);
    return
end
warning('off', 'all');

try
    if strcmpi(cfg.controller, 'pid_block')
        blk = [mdl '/' cfg.pid_block];
        form = get_param(blk, 'Form');
        p = gains(1); i = gains(2); d = gains(3);
        if ~strcmpi(form, 'Parallel')
            % Ideal/Standard: I and D are times; P is still the gain.
            set_param(blk, 'Form', 'Parallel');
            out.converted_from = form;
        end
        set_param(blk, 'P', num2str(p, 17), 'I', num2str(i, 17), 'D', num2str(d, 17));
        out.written = {sprintf('%s.P', cfg.pid_block), ...
                       sprintf('%s.I', cfg.pid_block), ...
                       sprintf('%s.D', cfg.pid_block)};
    else
        set_param([mdl '/' cfg.kp_block], 'Gain', num2str(gains(1), 17));
        set_param([mdl '/' cfg.ki_block], 'Gain', num2str(gains(2), 17));
        set_param([mdl '/' cfg.kd_block], 'Gain', num2str(gains(3), 17));
        out.written = {cfg.kp_block, cfg.ki_block, cfg.kd_block};
    end
    set_param(mdl, 'FastRestart', 'off');
    if isfile(target), delete(target); end
    save_system(mdl, target);
    out.ok = true;
    out.code = '';
    % save_system may rename the in-memory model after the new file name; close
    % by name so a chained run does not leave the previous copy open and locked
    close_named(mdl);
    [~, targetStem] = fileparts(target);
    close_named(targetStem);
catch err
    out.code = 'writeback_failed';
    out.error = err.message;
end
safe_close(mdl);
write_json(out, outPath);
end

% -------------------------------------------------------------------------
function cfg = with_defaults(cfg)
d = struct('controller', 'gains', 'kp_block', 'Gain_Kp', ...
    'ki_block', 'Gain_Ki', 'kd_block', 'Gain_Kd', ...
    'pid_block', 'PID Controller', 'out_dir', '', 'suffix', '_tuned');
f = fieldnames(d);
for k = 1:numel(f)
    if ~isfield(cfg, f{k}) || isempty(cfg.(f{k}))
        cfg.(f{k}) = d.(f{k});
    end
end
end

function close_named(name)
try
    if bdIsLoaded(name)
        try, set_param(name, 'FastRestart', 'off'); catch, end
        close_system(name, 0);
    end
catch
end
end

function safe_close(mdl)
try
    if ~isempty(find_system('SearchDepth', 0, 'Type', 'block_diagram', 'Name', mdl))
        try, set_param(mdl, 'FastRestart', 'off'); catch, end
        close_system(mdl, 0);
    end
catch
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
