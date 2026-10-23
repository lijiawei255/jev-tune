function R = test_model_adaptation(workRoot)
%TEST_MODEL_ADAPTATION Real Simulink fixtures for the v0.9 adapter contracts.
% R contains independently counted simulation calls and measured differences;
% scripts/40_verify_model_adaptation.py retains this result and the source log.
if nargin < 1, workRoot = tempname; end
if ~isfolder(workRoot), mkdir(workRoot); end
originalWarnings = warning;
restoreWarnings = onCleanup(@() warning(originalWarnings)); %#ok<NASGU>
global JEV_ADAPTATION_SIM_CALLS
JEV_ADAPTATION_SIM_CALLS = 0;
R = struct('ok', false, 'matlab_release', version('-release'));

% Identical continuous response, different solver sample grids.
t1 = linspace(0, 10, 101).'; t2 = [0; .001; .002; .003; 10];
m1 = jev_metrics(t1, zeros(size(t1)), [], 1, 10, []);
m2 = jev_metrics(t2, zeros(size(t2)), [], 1, 10, []);
assert(max(abs(m1(5:6) - [10 50])) < 1e-12);
assert(max(abs(m1(5:6) - m2(5:6))) < 1e-12);
R.integration = struct('uniform_iae_itae', m1(5:6), ...
    'nonuniform_iae_itae', m2(5:6), 'max_difference', max(abs(m1(5:6) - m2(5:6))));
R.invalid_reference = capture(@() jev_metrics(t1, zeros(size(t1)), [], -1, 10, []));
assert(strcmp(R.invalid_reference, 'jev:ref'));
R.invalid_time = capture(@() jev_metrics([0; 2; 1], [0; 0; 0], [], 1, 2, []));
assert(strcmp(R.invalid_time, 'jev:invalid_signal'));

% A Dataset's second scalar element must never be silently discarded.
signals = Simulink.SimulationData.Dataset;
signals = signals.addElement(timeseries(ones(3, 1), [0; 1; 2]), 'reference');
signals = signals.addElement(timeseries(zeros(3, 1), [0; 1; 2]), 'response');
logged = struct('measurement', signals);
R.dataset_rejection = capture(@() jev_read_signal(logged, 'measurement'));
assert(strcmp(R.dataset_rejection, 'jev:wide_signal'));
[selectedT, selectedY] = jev_read_signal(logged, 'measurement', 'response');
assert(isequal(selectedT, [0; 1; 2]) && isequal(selectedY, zeros(3, 1)));
R.dataset_selected_response = selectedY.';

% Ideal and Parallel trajectories must agree before any optimization occurs.
name = 'tc_adaptation_ideal';
make_demo_model(workRoot, 'ideal_pid', struct('name', name));
source = fullfile(workRoot, [name '.slx']);
load_system(source);
closeIdeal = onCleanup(@() close_fixture(name)); %#ok<NASGU>
block = [name '/PID Controller'];
set_param(name, 'Solver', 'ode4', 'FixedStep', '0.001', 'StopTime', '3');
set_param(block, 'P', '2', 'I', '4', 'D', '0.5');
enable_scopes(name);
save_system(name, source);
sourceBytes = bytes(source);
jev_validate_pid_conversion(block);
g = jev_pid_parallel_gains('Ideal', [2 4 .5]);
assert(isequal(g, [2 8 1]));
before = sim(name, 'StopTime', '3');
[ti, yi] = jev_read_signal(before, 'Scope-Position');
set_param(block, 'Form', 'Parallel', 'P', num2str(g(1), 17), ...
    'I', num2str(g(2), 17), 'D', num2str(g(3), 17));
after = sim(name, 'StopTime', '3');
[tp, yp] = jev_read_signal(after, 'Scope-Position');
assert(isequal(ti, tp));
maxDifference = max(abs(yi - yp));
assert(maxDifference < 1e-10);
R.ideal = struct('parameters', [2 4 .5], 'parallel_gains', g, ...
    'max_trajectory_difference', maxDifference, 'samples', numel(ti), 'simulations', 2);
% Conversion outside the verified zero-state configuration is refused.
set_param(block, 'Form', 'Ideal', 'InitialConditionForIntegrator', '1');
R.ideal_nonzero_ic_rejection = capture(@() jev_validate_pid_conversion(block));
assert(strcmp(R.ideal_nonzero_ic_rejection, 'jev:unsupported_pid_configuration'));
set_param(block, 'InitialConditionForIntegrator', '0', 'TrackingMode', 'on');
R.ideal_tracking_rejection = capture(@() jev_validate_pid_conversion(block));
assert(strcmp(R.ideal_tracking_rejection, 'jev:unsupported_pid_configuration'));
close_fixture(name);
assert(isequal(sourceBytes, bytes(source)));

% Guards run before loading/deleting a same-path source file.
protect = fullfile(workRoot, 'protect'); mkdir(protect);
sourceTune = fullfile(protect, 'jev_lab_model.slx'); write_bytes(sourceTune, uint8('source fixture'));
sourceDiscover = fullfile(protect, 'jev_disc_model.slx'); write_bytes(sourceDiscover, uint8('source fixture'));
doctorDir = fullfile(protect, 'doctor'); mkdir(doctorDir); mkdir(fullfile(doctorDir, 'copy'));
sourceDoctor = fullfile(doctorDir, 'copy', 'jev_doctor_model.slx'); write_bytes(sourceDoctor, uint8('source fixture'));
R.path_rejections = struct( ...
    'tune', capture(@() jev_tune_model(sourceTune, protect, 1)), ...
    'discover', capture(@() jev_discover(sourceDiscover, struct('work_dir', protect))), ...
    'doctor', capture(@() jev_doctor(sourceDoctor, fullfile(protect, 'doctor.json'), struct('work_dir', doctorDir))), ...
    'writeback', capture(@() jev_writeback(sourceTune, [1 1 1], struct('target', sourceTune), fullfile(protect, 'wb.json'))));
assert(all(structfun(@(x) strcmp(x, 'jev:source_overwrite'), R.path_rejections)));
assert(isequal(bytes(sourceTune), uint8('source fixture').'));
assert(isequal(bytes(sourceDiscover), uint8('source fixture').'));
assert(isequal(bytes(sourceDoctor), uint8('source fixture').'));
R.original_files_preserved = true;

% The model callback is independent of the tuner's accounting implementation.
name = 'tc_adaptation_gains';
make_demo_model(workRoot, 'gains', struct('name', name));
source = fullfile(workRoot, [name '.slx']);
load_system(source);
set_param(name, 'Solver', 'ode4', 'FixedStep', '0.001', 'StopTime', '4', ...
    'StartFcn', 'global JEV_ADAPTATION_SIM_CALLS; JEV_ADAPTATION_SIM_CALLS=JEV_ADAPTATION_SIM_CALLS+1;');
save_system(name, source); close_fixture(name);
sourceBytes = bytes(source);
cfg = struct('model', source, 'work_dir', fullfile(workRoot, 'auto'), ...
    'auto_discover', true, 'iters', 1, 'stop_time', 4, 'keep_loaded', true);
JEV_ADAPTATION_SIM_CALLS = 0;
auto = tune_job(cfg, workRoot, 'auto');
assert(auto.ok);
assert(auto.n_total_simulations == JEV_ADAPTATION_SIM_CALLS);
assert(auto.discovery.n_total_simulations >= 5);
assert(auto.n_total_simulations == sum(cell2mat(struct2cell(auto.measurements))));
assert(isequal(sourceBytes, bytes(source)));
R.auto_ledger = struct('callback_count', JEV_ADAPTATION_SIM_CALLS, ...
    'reported_total', auto.n_total_simulations, 'measurements', auto.measurements, ...
    'discovery_total', auto.discovery.n_total_simulations, 'recorded_measurements', auto.n_experiments);

% A two-port Scope logs the reference first and the actual response second.
load_system(source);
scope = [name '/Scope-Position'];
set_param(scope, 'NumInputPorts', '2');
delete_line(name, 'Delay/1', 'Scope-Position/1');
add_line(name, 'Step/1', 'Scope-Position/1', 'autorouting', 'on');
add_line(name, 'Delay/1', 'Scope-Position/2', 'autorouting', 'on');
save_system(name, source); close_fixture(name);
explicit = struct('model', source, 'work_dir', fullfile(workRoot, 'ambiguous'), ...
    'iters', 1, 'stop_time', 4, 'kp_block', 'alpha', 'ki_block', 'beta', ...
    'kd_block', 'gamma', 'measure_scope', 'Scope-Position', ...
    'input_scope', 'Scope-Current', 'ref_source', '1');
JEV_ADAPTATION_SIM_CALLS = 0;
ambiguous = tune_job(explicit, workRoot, 'ambiguous');
assert(~ambiguous.ok && strcmp(ambiguous.code, 'wide_signal'));
assert(ambiguous.n_total_simulations == 1 && JEV_ADAPTATION_SIM_CALLS == 1);
R.ambiguous_scope = struct('code', ambiguous.code, ...
    'callback_count', JEV_ADAPTATION_SIM_CALLS, 'reported_total', ambiguous.n_total_simulations);
explicit.measure_element = 2;
explicit.work_dir = fullfile(workRoot, 'selected');
JEV_ADAPTATION_SIM_CALLS = 0;
selected = tune_job(explicit, workRoot, 'selected');
assert(selected.ok && selected.final_J > 0);
assert(selected.n_total_simulations == JEV_ADAPTATION_SIM_CALLS);
R.explicit_scope = struct('final_J', selected.final_J, ...
    'callback_count', JEV_ADAPTATION_SIM_CALLS, 'reported_total', selected.n_total_simulations);

% A second job on the same paths still reloads the source and repeats its scan.
JEV_ADAPTATION_SIM_CALLS = 0;
again = tune_job(explicit, workRoot, 'selected_again');
assert(again.ok && again.measurements.sweep > 0);
assert(again.n_total_simulations == JEV_ADAPTATION_SIM_CALLS);
assert(strcmp(again.cache_policy, 'fresh_model_per_job'));
R.repeat_job = struct('sweep_simulations', again.measurements.sweep, ...
    'callback_count', JEV_ADAPTATION_SIM_CALLS, 'reported_total', again.n_total_simulations);

% Every discovery round in the all-loops wrapper belongs to its total budget.
name = 'tc_adaptation_two';
make_demo_model(workRoot, 'two_loops', struct('name', name));
source = fullfile(workRoot, [name '.slx']);
load_system(source);
set_param(name, 'StopTime', '4', 'StartFcn', ...
    'global JEV_ADAPTATION_SIM_CALLS; JEV_ADAPTATION_SIM_CALLS=JEV_ADAPTATION_SIM_CALLS+1;');
save_system(name, source); close_fixture(name);
sourceBytes = bytes(source);
allCfg = struct('model', source, 'work_dir', fullfile(workRoot, 'all'), ...
    'iters', 1, 'stop_time', 4, 'step_gain', .5);
job = fullfile(workRoot, 'all_job.json'); jev_write_json_atomic(allCfg, job);
JEV_ADAPTATION_SIM_CALLS = 0;
allResult = jev_tune_all(job, fullfile(workRoot, 'all_result.json'));
assert(allResult.ok && allResult.n_tuned == allResult.n_loops && allResult.n_loops == 2);
assert(allResult.n_total_simulations == JEV_ADAPTATION_SIM_CALLS);
assert(isequal(sourceBytes, bytes(source)));
R.all_loops_ledger = struct('callback_count', JEV_ADAPTATION_SIM_CALLS, ...
    'reported_total', allResult.n_total_simulations, 'measurements', allResult.measurements, ...
    'n_tuned', allResult.n_tuned, 'n_loops', allResult.n_loops);

% Later chain paths must protect the original, not just the previous copy.
% Each named source is a real two-loop model. Preflight must reject all three
% aliases before a later iteration could delete that source file.
R.chain_path_rejections = struct();
collisionKinds = {'iteration', 'discovery', 'tuning'};
for k = 1:numel(collisionKinds)
    kind = collisionKinds{k};
    collisionDir = fullfile(workRoot, ['collision_' kind]); mkdir(collisionDir);
    if strcmp(kind, 'iteration')
        collisionSource = fullfile(collisionDir, 'loop_2_tuned.slx');
    elseif strcmp(kind, 'discovery')
        mkdir(fullfile(collisionDir, 'discover_2'));
        collisionSource = fullfile(collisionDir, 'discover_2', 'jev_disc_model.slx');
    else
        mkdir(fullfile(collisionDir, 'run_2'));
        collisionSource = fullfile(collisionDir, 'run_2', 'jev_lab_model.slx');
    end
    copyfile(source, collisionSource);
    beforeCollision = bytes(collisionSource);
    collisionCfg = struct('model', collisionSource, 'work_dir', collisionDir, ...
        'iters', 1, 'stop_time', 4);
    collisionJob = fullfile(collisionDir, 'job.json');
    jev_write_json_atomic(collisionCfg, collisionJob);
    JEV_ADAPTATION_SIM_CALLS = 0;
    rejected = jev_tune_all(collisionJob, fullfile(collisionDir, 'result.json'));
    assert(~rejected.ok && strcmp(rejected.code, 'source_overwrite'));
    assert(isequal(beforeCollision, bytes(collisionSource)));
    assert(rejected.n_total_simulations == JEV_ADAPTATION_SIM_CALLS);
    assert(rejected.measurements.loop_discovery == 0 && rejected.measurements.tuning_jobs == 0);
    R.chain_path_rejections.(kind) = struct('code', rejected.code, ...
        'original_bytes_preserved', true, 'callback_count', JEV_ADAPTATION_SIM_CALLS, ...
        'reported_total', rejected.n_total_simulations);
end

% Error responses use the same complete-file publication helper as successes.
atomicPath = fullfile(workRoot, 'atomic.json');
jev_write_json_atomic(struct('ok', false, 'error', 'fixture'), atomicPath);
published = jsondecode(fileread(atomicPath));
assert(~published.ok && strcmp(published.error, 'fixture') && ~isfile([atomicPath '.tmp']));
R.atomic_response_complete = true;
R.ok = true;
end

function result = tune_job(cfg, folder, tag)
job = fullfile(folder, [tag '_job.json']);
jev_write_json_atomic(cfg, job);
result = jev_tune_json(job, fullfile(folder, [tag '_result.json']));
end

function code = capture(callback)
code = '';
try
    callback();
catch err
    code = err.identifier;
end
assert(~isempty(code), 'expected an error but the call succeeded');
end

function enable_scopes(model)
for name = {'Scope-Position', 'Scope-Current'}
    set_param([model '/' name{1}], 'DataLogging', 'on', ...
        'DataLoggingVariableName', matlab.lang.makeValidName(strrep(name{1}, '-', '_')), ...
        'DataLoggingSaveFormat', 'Dataset', 'DataLoggingLimitDataPoints', 'off');
end
end

function value = bytes(path)
fid = fopen(path, 'rb'); assert(fid >= 0);
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
value = fread(fid, Inf, '*uint8');
end

function write_bytes(path, value)
fid = fopen(path, 'wb'); assert(fid >= 0);
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, value, 'uint8');
end

function close_fixture(name)
if bdIsLoaded(name)
    set_param(name, 'FastRestart', 'off');
    close_system(name, 0);
end
end
