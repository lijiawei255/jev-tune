% Save reference responses (Z-N start, head result, human hand-tuned) for the demo assets.
cd('C:\workspace\jev-tune\matlab');
R = load('C:\workspace\jev-tune\research\sim_tune\tune_result.mat'); R = R.R;
cd('C:\workspace\jev-tune\research\sim_tune');
if bdIsLoaded('jev_lab_model')
    try, set_param('jev_lab_model', 'FastRestart', 'off'); catch, end
    close_system('jev_lab_model', 0);
end
load_system('jev_lab_model');
try, set_param('jev_lab_model', 'SimMechanicsOpenEditorOnUpdate', 'off'); catch, end
set_param('jev_lab_model', 'FastRestart', 'on');
warning('off', 'all');
for k = 1:numel(R.scopes)
    set_param(['jev_lab_model/' R.scopes{k}], 'DataLogging', 'on', ...
        'DataLoggingVariableName', strrep(R.scopes{k}, '-', '_'), ...
        'DataLoggingSaveFormat', 'Dataset', 'DataLoggingLimitDataPoints', 'off');
end

sets = {R.gzn, R.final_gains(:).', [280 300 30]};
names = {'zn', 'head', 'human'};
S = struct('name', {}, 'gains', {}, 't', {}, 'y', {}, 'J', {});
for i = 1:numel(sets)
    g = sets{i};
    set_param('jev_lab_model/Gain_Kp', 'Gain', num2str(g(1)));
    set_param('jev_lab_model/Gain_Ki', 'Gain', num2str(g(2)));
    set_param('jev_lab_model/Gain_Kd', 'Gain', num2str(g(3)));
    out = sim('jev_lab_model', 'StopTime', '10');
    e = out.Scope_Position.getElement(1);
    y = e.Values.Data(:, 1); t = e.Values.Time;
    M = jev_metrics(t, y, zeros(size(t)), R.ref, 10, []);
    S(end+1) = struct('name', names{i}, 'gains', g, 't', t, 'y', y, 'J', cost_of(M, 10, R.ref));
    fprintf('%-6s [%6.4g %6.4g %6.4g] J=%.3f\n', names{i}, g, S(end).J);
end
set_param('jev_lab_model', 'FastRestart', 'off');
close_system('jev_lab_model', 0);
save('C:\workspace\jev-tune\research\sim_tune\demo_traces.mat', 'S', 'R');

function J = cost_of(M, horizon, ref)
os_ = min(max(M(1), 0), 2);
ts_ = min(max(M(2), 0), 1);
st_ = min(max(M(3) / horizon, 0), 1);
ess_ = min(max(abs(M(4)), 0), 2);
itae = min(max(M(6) / (max(ref, 1e-9) * horizon^2), 0), 3);
sat_ = min(max(M(8), 0), 1);
over_ = min(max(M(9), 0), 3);
J = os_ + (0.5 * ts_ + st_) + 4 * ess_ + itae + sat_ + 0.5 * over_;
end
