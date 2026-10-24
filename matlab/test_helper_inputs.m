function R = test_helper_inputs()
%TEST_HELPER_INPUTS Real missing-input checks, before any Simulink operation.
helpers = {@bench_iter, @sens_lab, @cmp_gains, @save_demo_traces};
for i = 1:numel(helpers)
    expect_error(@() helpers{i}(), 'jev:helperInputs');
end
work = tempname; mkdir(work);
cleanup = onCleanup(@() rmdir(work, 's')); %#ok<NASGU>
missing = fullfile(work, 'not_supplied.slx');
output = fullfile(work, 'responses.mat');
expect_error(@() bench_iter(missing, work, output, struct()), 'jev:helperMissingInput');
expect_error(@() sens_lab(missing, work, output, struct()), 'jev:helperMissingInput');
expect_error(@() cmp_gains(missing, fullfile(work, 'missing.mat'), output, work, struct()), 'jev:helperMissingInput');
expect_error(@() save_demo_traces(missing, '', output, work, struct()), 'jev:helperMissingInput');
% A present placeholder proves missing result/config are rejected before load_system.
placeholder = fullfile(work, 'placeholder.slx');
fid = fopen(placeholder, 'w'); fclose(fid);
expect_error(@() cmp_gains(placeholder, fullfile(work, 'missing.mat'), output, work, struct()), 'jev:helperMissingInput');
expect_error(@() save_demo_traces(placeholder, '', output, work, struct()), 'jev:helperConfig');
assert(~isfile(output), 'Missing inputs must not create output');
% Use only our generated model, from an unrelated current directory.
model = 'helper_portable_plant';
make_demo_model(work, 'gains', struct('name', model));
modelPath = fullfile(work, [model '.slx']);
load_system(modelPath);
add_block('simulink/Sinks/To Workspace', [model '/HelperLog'], ...
    'VariableName', 'helper_response', 'SaveFormat', 'Timeseries');
add_line(model, 'Delay/1', 'HelperLog/1', 'autorouting', 'on');
save_system(model, modelPath); close_system(model, 0);
before = bytes(modelPath);
unrelated = fullfile(work, 'unrelated'); mkdir(unrelated);
originalDir = pwd; restoreDir = onCleanup(@() cd(originalDir)); %#ok<NASGU>
cd(unrelated);
cfg = struct('gain_blocks', {{'alpha','beta','gamma'}}, ...
    'gain_sets', [2 3 .05; 1 2 .02], 'ref', 1, 'horizon', 2, ...
    'output_variable', 'helper_response');
R = struct('gain_sets', cfg.gain_sets);
resultPath = fullfile(work, 'gain_sets.mat'); save(resultPath, 'R');
results = cell(1,4);
results{1} = bench_iter(modelPath, work, fullfile(work,'bench.mat'), cfg);
results{2} = sens_lab(modelPath, work, fullfile(work,'sensitivity.mat'), cfg);
results{3} = cmp_gains(modelPath, resultPath, fullfile(work,'compare.mat'), work, cfg);
results{4} = save_demo_traces(modelPath, '', fullfile(work,'traces.mat'), work, cfg);
for k = 1:numel(results)
    assert(numel(results{k}) == 2 && all(isfinite([results{k}.wall_seconds])));
    assert(numel(results{k}(1).t) > 1 && all(isfinite(results{k}(1).y)));
end
assert(strcmp(pwd, unrelated) && ~bdIsLoaded(model));
assert(isequal(before, bytes(modelPath)), 'Source model changed');
expect_error(@() bench_iter(modelPath, work, fullfile(work,'bench.mat'), cfg), 'jev:helperOutputExists');
% Multiple channels must never be silently reduced to the first one.
wide = Simulink.SimulationOutput;
wide.helper_response = timeseries([1 2; 3 4], [0; 1]);
expect_error(@() jev_read_signal(wide, 'helper_response'), 'jev:wide_signal');
dataset = Simulink.SimulationData.Dataset;
dataset = dataset.addElement(timeseries([1; 2], [0; 1]), 'a');
dataset = dataset.addElement(timeseries([3; 4], [0; 1]), 'b');
wide.helper_response = dataset;
expect_error(@() jev_read_signal(wide, 'helper_response'), 'jev:wide_signal');
R = struct('ok', true, 'helpers', 4, 'simulations', 8, ...
    'source_unchanged', true, 'outside_cwd', true, 'ambiguous_signals_rejected', true);
cd(originalDir);
fprintf('helper input and portable execution checks passed\n');
end

function data = bytes(path)
fid = fopen(path, 'rb'); assert(fid >= 0);
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
data = fread(fid, inf, '*uint8');
end

function expect_error(call, identifier)
try
    call();
catch exc
    assert(strcmp(exc.identifier, identifier), 'Unexpected error: %s', exc.identifier);
    return;
end
error('jev:test', 'Expected missing-input error %s', identifier);
end
