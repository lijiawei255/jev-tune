% Why is a tuning iteration ~4 s when the standalone benchmark says 111 ms?
cd('C:\workspace\jev-tune\research\sim_json');
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

fprintf('--- with per-call StopTime name-value ---\n');
for i = 1:5
    set_param('jev_lab_model/Gain_Kp', 'Gain', num2str(200 + i));
    t0 = tic; out = sim('jev_lab_model', 'StopTime', '10'); dt = toc(t0);
    fprintf('  run %d: %.3f s\n', i, dt);
end

fprintf('--- StopTime set on the model, plain sim() ---\n');
set_param('jev_lab_model', 'StopTime', '10');
for i = 1:5
    set_param('jev_lab_model/Gain_Kp', 'Gain', num2str(210 + i));
    t0 = tic; out = sim('jev_lab_model'); dt = toc(t0);
    fprintf('  run %d: %.3f s\n', i, dt);
end

fprintf('--- plain sim() without data logging ---\n');
for k = 1:numel(sc)
    set_param(['jev_lab_model/' sc{k}], 'DataLogging', 'off');
end
for i = 1:3
    set_param('jev_lab_model/Gain_Kp', 'Gain', num2str(220 + i));
    t0 = tic; out = sim('jev_lab_model'); dt = toc(t0);
    fprintf('  run %d: %.3f s\n', i, dt);
end

set_param('jev_lab_model', 'FastRestart', 'off');
close_system('jev_lab_model', 0);
