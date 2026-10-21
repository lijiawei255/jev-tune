% One-at-a-time sensitivity of the lab model to Kd (and Kp) around the human optimum.
cd('C:\workspace\jev-tune\matlab');
cd('C:\workspace\jev-tune\research\sim_tune');
if bdIsLoaded('jev_lab_model')
    try, set_param('jev_lab_model', 'FastRestart', 'off'); catch, end
    close_system('jev_lab_model', 0);
end
load_system('jev_lab_model');
try, set_param('jev_lab_model', 'SimMechanicsOpenEditorOnUpdate', 'off'); catch, end
set_param('jev_lab_model', 'FastRestart', 'on');
warning('off', 'all');
sc = get_param(find_system('jev_lab_model', 'SearchDepth', 1, 'BlockType', 'Scope'), 'Name');
for k = 1:numel(sc)
    set_param(['jev_lab_model/' sc{k}], 'DataLogging', 'on', ...
        'DataLoggingVariableName', strrep(sc{k}, '-', '_'), ...
        'DataLoggingSaveFormat', 'Dataset', 'DataLoggingLimitDataPoints', 'off');
end

ref = 0.5236;
fprintf('--- Kd sweep at Kp=280, Ki=300 ---\n');
set_param('jev_lab_model/Gain_Kp', 'Gain', '280');
set_param('jev_lab_model/Gain_Ki', 'Gain', '300');
for kd = [5 10 20 30 45 60]
    J = run_one(kd, ref);
    fprintf('Kd=%5.1f  J=%.3f\n', kd, J);
end

fprintf('--- Kp sweep at Ki=300, Kd=30 ---\n');
set_param('jev_lab_model/Gain_Kd', 'Gain', '30');
for kp = [150 200 240 280 320 400]
    J = run_kp(kp, ref);
    fprintf('Kp=%5.1f  J=%.3f\n', kp, J);
end
set_param('jev_lab_model', 'FastRestart', 'off');
close_system('jev_lab_model', 0);

function J = run_one(kd, ref)
    set_param('jev_lab_model/Gain_Kd', 'Gain', num2str(kd));
    J = sim_cost(ref);
end

function J = run_kp(kp, ref)
    set_param('jev_lab_model/Gain_Kp', 'Gain', num2str(kp));
    J = sim_cost(ref);
end

function J = sim_cost(ref)
    out = sim('jev_lab_model', 'StopTime', '10');
    e = out.Scope_Position.getElement(1);
    y = e.Values.Data(:, 1); t = e.Values.Time;
    M = jev_metrics(t, y, zeros(size(t)), ref, 10, []);
    os_ = min(max(M(1), 0), 2);
    ts_ = min(max(M(2), 0), 1);
    st_ = min(max(M(3) / 10, 0), 1);
    ess_ = min(max(abs(M(4)), 0), 2);
    it = min(max(M(6) / (ref * 100), 0), 3);
    J = os_ + (0.5 * ts_ + st_) + 4 * ess_ + it;
end
