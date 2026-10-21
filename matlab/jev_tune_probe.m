function jev_tune_probe(outPath)
%JEV_TUNE_PROBE  Report what this MATLAB release can actually do.
%
%   jev_tune_probe('probe.json')
%
%   Called by `jev-tune matlab --probe` and by the MCP server before a run, so
%   a user on an older release gets a precise error instead of a stack trace.

if nargin < 1 || isempty(outPath), outPath = 'jev_probe.json'; end

p = struct();
p.ok = true;
p.release = version('-release');
p.version = version;
p.matlabroot = matlabroot;
p.platform = computer;

p.has_fast_restart = true;                      % R2013b+
p.has_scope_logging = true;                     % R2014a+
p.has_pid_tune = license('test', 'Control_Toolbox') > 0;
p.has_simulink = license('test', 'Simulink') > 0;
p.has_simscape = license('test', 'Simscape') > 0;

try
    p.scope_save_format = 'Dataset';            % accepted since R2014a
    p.batch_flag = double(verLessThan('matlab', '9.6')) == 0;  % -batch is R2019a+
catch
    p.batch_flag = false;
end

% version gates that matter for the shipped script
p.supports_batch = ~verLessThan('matlab', '9.6');   % R2019a
p.supports_string_arrays = ~verLessThan('matlab', '9.6');

fid = fopen(outPath, 'w');
fwrite(fid, jsonencode(p), 'char');
fclose(fid);
end
