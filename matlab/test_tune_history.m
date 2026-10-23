function R = test_tune_history(workRoot)
%TEST_TUNE_HISTORY End-to-end first-iteration fault and cumulative telemetry.
% The fixture deliberately rejects large integral gains at every simulation:
% P-only sweep and own gains run, the first Z-N candidate fails, and the final
% own-gain rerun succeeds. This exercises the former undefined-counter path.
if nargin < 1, workRoot = tempname; end
if ~isfolder(workRoot), mkdir(workRoot); end
mdl = 'tc_history';
make_demo_model(workRoot, 'second_order', struct('name', mdl));
source = fullfile(workRoot, [mdl '.slx']);
load_system(source);
set_param(mdl, 'StartFcn', [ ...
    'if str2double(get_param(''jev_lab_model/PID Controller'',''I'')) > 0.01; ' ...
    'error(''jev:fixture_fault'',''intentional integral-gain failure''); end']);
save_system(mdl, source); close_system(mdl, 0);
cfg = struct('controller', 'pid_block', 'pid_block', 'PID Controller', ...
    'measure_scope', 'Scope-Position', 'input_scope', 'Scope-Current', ...
    'ref_source', 1, 'keep_loaded', false);
failed = jev_tune_model(source, fullfile(workRoot, 'failed'), 1, 10, 1, cfg);
assert(failed.n_rollbacks == 1 && failed.n_escalations == 0);
assert(strcmp(failed.hist(1).event, 'rollback') && isinf(failed.hist(1).J));
assert(failed.hist(1).gains(2) > 0.01);
assert(all(failed.hist(1).next_gains == max(0.6 * failed.own_gains, 1e-4)));
assert(all(failed.final_gains == failed.own_gains));
assert(failed.final_J == failed.own_J);
% Remove the fault for an ordinary multi-iteration all-held run.
load_system(source); set_param(mdl, 'StartFcn', '');
save_system(mdl, source); close_system(mdl, 0);
cfg.tau_act = 1; cfg.tau_esc = 1;
cfg.model = source; cfg.work_dir = fullfile(workRoot, 'held');
cfg.iters = 4; cfg.stop_time = 10; cfg.step_gain = 1;
jobPath = fullfile(workRoot, 'job.json');
fid = fopen(jobPath, 'w'); assert(fid >= 0);
fprintf(fid, '%s', jsonencode(cfg)); fclose(fid);
resultPath = fullfile(workRoot, 'result.json');
held = jev_tune_json(jobPath, resultPath);
assert(held.ok);
onDisk = jsondecode(fileread(resultPath));
assert(onDisk.ok && onDisk.decision_policy.cp_enabled == 1);
assert(isequal(size(onDisk.history(1).conformal_set), [3 7]));
assert(onDisk.history(1).conformal_applied);
assert(all(isfinite(onDisk.history(1).proposed)));
count = 0;
for k = 1:numel(held.history), count = count + sum(held.history(k).escalate); end
assert(held.n_escalations == count && count > 3);
R = struct('ok', true, 'first_iteration_rollbacks', failed.n_rollbacks, ...
    'first_iteration_escalations', failed.n_escalations, ...
    'cumulative_escalations', held.n_escalations, 'history_escalations', count);
disp(jsonencode(R));
end
