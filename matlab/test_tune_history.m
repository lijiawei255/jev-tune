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
% Use explicit nonzero own gains; the runtime preserves genuine zeros now.
set_param([mdl '/PID Controller'], 'I', '0.001', 'D', '0.001');
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
% A second rejected run at best*.6 must not keep retrying an identical rollback.
load_system(source);
set_param(mdl, 'StartFcn', [ ...
    'iTrial=str2double(get_param(''jev_lab_model/PID Controller'',''I'')); ' ...
    'if iTrial > 0.01 || abs(iTrial-0.0006) < 1e-10; ' ...
    'error(''jev:fixture_fault'',''intentional rollback failure''); end']);
save_system(mdl, source); close_system(mdl, 0);
rollbackStop = jev_tune_model(source, fullfile(workRoot, 'rollback_stop'), 6, 10, 1, cfg);
assert(rollbackStop.n_rollbacks == 2 && rollbackStop.n_recorded_measurements == 2);
assert(strcmp(rollbackStop.stop_reason, 'rollback_no_action'));
assert(strcmp(rollbackStop.hist(2).event, 'stop_rollback_no_action'));
assert(rollbackStop.hist(end).measurement_reused && rollbackStop.final_J == rollbackStop.own_J);
% Remove the fault for an ordinary multi-iteration all-held run.
load_system(source); set_param(mdl, 'StartFcn', '');
save_system(mdl, source); close_system(mdl, 0);
cfg.tau_act = 1; cfg.tau_esc = 1;
cfg.stop_on_no_action = false; % preserve repeated measurements explicitly
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
assert(strcmp(onDisk.decision_policy.cp_mode, 'monitor'));
assert(isequal(size(onDisk.history(1).conformal_set), [3 7]));
assert(onDisk.history(1).conformal_applied);
assert(all(isfinite(onDisk.history(1).proposed)));
assert(onDisk.n_no_action_stops == 0 && onDisk.n_recorded_measurements == numel(onDisk.history));
count = 0;
for k = 1:numel(held.history), count = count + sum(held.history(k).escalate); end
assert(held.n_escalations == count && count > 3);

% Monitor remains the Temp-Only action even when every CP set is empty.
cfg.tau_act = 0; cfg.tau_esc = 0; cfg.cp_qhat = [0 0 0];
cfg.cp_mode = 'monitor'; cfg.iters = 3; cfg.stop_on_no_action = true;
monitor = jev_tune_model(source, fullfile(workRoot, 'monitor'), 3, 10, 1, cfg);
assert(all(monitor.hist(1).conformal_would_hold));
assert(all(monitor.hist(1).conformal_reason == 4));
assert(~any(monitor.hist(1).held) && ~any(monitor.hist(1).escalate));
assert(all(monitor.hist(1).step == monitor.hist(1).proposed));
assert(any(monitor.hist(1).step ~= 0));
cfg.cp_enabled = false;
disabled = jev_tune_model(source, fullfile(workRoot, 'disabled'), 3, 10, 1, cfg);
maxCostDifference = max(abs([monitor.hist.J] - [disabled.hist.J]));
maxGainDifference = max(abs([monitor.hist.gains] - [disabled.hist.gains]));
assert(maxCostDifference < 1e-10);
assert(maxGainDifference < 1e-10);

% Explicit hard hold stops after one measurement; the recorded best response
% is reused for the final row rather than inventing a second observation.
cfg.cp_enabled = true; cfg.cp_mode = 'hard_hold';
cfg.work_dir = fullfile(workRoot, 'stopped'); cfg.iters = 4;
fid = fopen(jobPath, 'w'); assert(fid >= 0);
fprintf(fid, '%s', jsonencode(cfg)); fclose(fid);
stopped = jev_tune_json(jobPath, resultPath);
assert(stopped.ok);
assert(stopped.n_no_action_stops == 1 && stopped.n_recorded_measurements == 1);
assert(stopped.n_experiments == 1 && stopped.n_history_records == 2);
assert(strcmp(stopped.stop_reason, 'no_action'));
assert(strcmp(stopped.history(1).event, 'stop_no_action'));
assert(stopped.history(end).measurement_reused);
assert(all(stopped.history(1).held) && all(stopped.history(1).conformal_would_hold));
assert(stopped.final_J <= min(stopped.history(1).J, stopped.own_J));
assert(stopped.n_total_simulations == sum(cell2mat(struct2cell(stopped.measurements))));
R = struct('ok', true, 'first_iteration_rollbacks', failed.n_rollbacks, ...
    'first_iteration_escalations', failed.n_escalations, ...
    'cumulative_escalations', held.n_escalations, 'history_escalations', count, ...
    'monitor_matches_CP_disabled', true, 'no_action_measurements', stopped.n_recorded_measurements, ...
    'repeated_observation_measurements', held.n_recorded_measurements, ...
    'monitor_off_max_cost_difference', maxCostDifference, ...
    'monitor_off_max_gain_difference', maxGainDifference, ...
    'hard_hold_no_action_stops', stopped.n_no_action_stops, ...
    'hard_hold_final_reused', stopped.history(end).measurement_reused, ...
    'hard_hold_n_experiments', stopped.n_experiments, 'hard_hold_n_history_records', stopped.n_history_records, ...
    'hard_hold_total_simulations', stopped.n_total_simulations, 'hard_hold_measurements', stopped.measurements, ...
    'rollback_no_action_measurements', rollbackStop.n_recorded_measurements, ...
    'rollback_no_action_reason', rollbackStop.stop_reason, ...
    'rollback_no_action_final_reused', rollbackStop.hist(end).measurement_reused, ...
    'hard_hold_final_J', stopped.final_J, 'hard_hold_initial_J', stopped.history(1).J, ...
    'hard_hold_own_J', stopped.own_J, 'monitor_final_J', monitor.final_J, ...
    'monitor_initial_J', monitor.hist(1).J, 'monitor_own_J', monitor.own_J, ...
    'matlab_release', version);
disp(jsonencode(R));
end
