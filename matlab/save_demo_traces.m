function S = save_demo_traces(modelPath, resultPath, outputPath, workDir, config)
%SAVE_DEMO_TRACES Save responses to explicit gain sets; no private model assumed.
% Required config: gain_blocks (3 relative paths), gain_sets (N-by-3), ref,
% horizon, output_variable (a logged timeseries or single-signal Dataset).
% resultPath may be empty; otherwise load R.gain_sets from that external MAT.
% Paths may be absolute or relative to the repository containing this file.
% 显式提供模型、结果（可为空）、输出、工作目录和配置，不隐式读取外部文件。
if nargin < 5
    error('jev:helperInputs', 'Supply modelPath, resultPath, outputPath, workDir and config.');
end
repoRoot = fileparts(fileparts(mfilename('fullpath')));
modelPath = resolve_path(modelPath, repoRoot);
workDir = resolve_path(workDir, repoRoot);
outputPath = resolve_path(outputPath, repoRoot);
if ~isfile(modelPath), error('jev:helperMissingInput', 'Model not found: %s', modelPath); end
if ~isfolder(workDir), error('jev:helperMissingInput', 'Work directory not found: %s', workDir); end
if ~isfolder(fileparts(outputPath)), error('jev:helperMissingInput', 'Output parent not found: %s', outputPath); end
if isfile(outputPath), error('jev:helperOutputExists', 'Choose a new output file: %s', outputPath); end
if ~isstruct(config) || ~isscalar(config), error('jev:helperConfig', 'config must be a scalar struct.'); end
if ~isempty(resultPath)
    resultPath = resolve_path(resultPath, repoRoot);
    if ~isfile(resultPath), error('jev:helperMissingInput', 'Result file not found: %s', resultPath); end
    loaded = load(resultPath, 'R');
    if ~isfield(loaded, 'R') || ~isstruct(loaded.R) || ~isfield(loaded.R, 'gain_sets')
        error('jev:helperConfig', 'Result file must contain R.gain_sets.');
    end
    config.gain_sets = loaded.R.gain_sets;
end
required = {'gain_blocks', 'gain_sets', 'output_variable', 'ref', 'horizon'};
if ~all(isfield(config, required)), error('jev:helperConfig', 'Required config fields: %s', strjoin(required, ', ')); end
validateattributes(config.gain_sets, {'numeric'}, {'2d', 'ncols', 3, 'nonempty', 'finite', 'nonnegative'});
validateattributes(config.ref, {'numeric'}, {'scalar', 'finite', 'positive'});
validateattributes(config.horizon, {'numeric'}, {'scalar', 'finite', 'positive'});
blocks = cellstr(config.gain_blocks);
if numel(blocks) ~= 3 || any(cellfun(@isempty, blocks)), error('jev:helperConfig', 'Supply three relative gain block paths.'); end
variable = char(config.output_variable);
if isempty(variable), error('jev:helperConfig', 'output_variable must be explicit.'); end
oldDir = pwd;
dirCleanup = onCleanup(@() cd(oldDir)); %#ok<NASGU>
cd(workDir);
[~, model] = fileparts(modelPath);
if bdIsLoaded(model), error('jev:helperModelLoaded', 'Close model before running helper: %s', model); end
load_system(modelPath);
modelCleanup = onCleanup(@() close_loaded(model)); %#ok<NASGU>
S = struct('gains', {}, 't', {}, 'y', {}, 'metrics', {}, 'wall_seconds', {});
for i = 1:size(config.gain_sets, 1)
    in = Simulink.SimulationInput(model);
    for axis = 1:3
        in = in.setBlockParameter([model '/' blocks{axis}], 'Gain', num2str(config.gain_sets(i, axis), 17));
    end
    in = in.setModelParameter('StopTime', num2str(config.horizon, 17));
    started = tic; out = sim(in); elapsed = toc(started);
    element = [];
    if isfield(config, 'output_element'), element = config.output_element; end
    [t, y] = jev_read_signal(out, variable, element);
    if isempty(t)
        error('jev:helperSignal', 'Logged output not found: %s', variable);
    end
    metrics = jev_metrics(t, y, zeros(size(t)), config.ref, config.horizon, []);
    S(end+1) = struct('gains', config.gain_sets(i, :), 't', t, 'y', y, ...
        'metrics', metrics, 'wall_seconds', elapsed); %#ok<AGROW>
    fprintf('set %d: gains=[%g %g %g], wall=%g s\n', i, config.gain_sets(i, :), elapsed);
end
R = struct('gain_sets', config.gain_sets, 'config', config);
save(outputPath, 'S', 'R');
end

function path = resolve_path(value, repoRoot)
if ~(ischar(value) || (isstring(value) && isscalar(value))) || isempty(char(value))
    error('jev:helperInputs', 'Supply a nonempty explicit path.');
end
path = char(value);
if isempty(regexp(path, '^([A-Za-z]:[\\/]|[/\\])', 'once')), path = fullfile(repoRoot, path); end
end

function close_loaded(model)
if bdIsLoaded(model)
    try, set_param(model, 'FastRestart', 'off'); catch, end
    close_system(model, 0);
end
end
