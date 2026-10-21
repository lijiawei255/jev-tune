% Compare fixed gain sets on the lab model: ZN start, lab hand-tuned, head result.
cd('C:\workspace\jev-tune\matlab');
R = load('C:\workspace\jev-tune\research\sim_tune\tune_result.mat'); R = R.R;
cd('C:\workspace\jev-tune\research\sim_tune');
if bdIsLoaded('jev_lab_model')
    try, set_param('jev_lab_model', 'FastRestart', 'off'); catch, end
    close_system('jev_lab_model', 0);
end
load_system('jev_lab_model');
set_param('jev_lab_model', 'FastRestart', 'on');
try, set_param('jev_lab_model', 'SimMechanicsOpenEditorOnUpdate', 'off'); catch, end
warning('off', 'all');
for k = 1:numel(R.scopes)
    set_param(['jev_lab_model/' R.scopes{k}], 'DataLogging', 'on', ...
        'DataLoggingVariableName', strrep(R.scopes{k}, '-', '_'), ...
        'DataLoggingSaveFormat', 'Dataset', 'DataLoggingLimitDataPoints', 'off');
end

sets = {[167 673.4 10.355], [280 300 30], [240 1160 12.4], R.final_gains(:).'};
names = {'lab-ZN (Ku=278)', 'lab hand-tuned', 'our ZN start', 'jev head result'};
for i = 1:numel(sets)
    g = sets{i};
    set_param('jev_lab_model/Gain_Kp', 'Gain', num2str(g(1)));
    set_param('jev_lab_model/Gain_Ki', 'Gain', num2str(g(2)));
    set_param('jev_lab_model/Gain_Kd', 'Gain', num2str(g(3)));
    out = sim('jev_lab_model', 'StopTime', '10');
    e = out.Scope_Position.getElement(1);
    y = e.Values.Data(:, 1); t = e.Values.Time;
    M = jev_metrics(t, y, zeros(size(t)), R.ref, 10, []);
    J = cost_of(M, 10, R.ref);
    fprintf('%-18s [%6.4g %6.4g %6.4g] -> J=%.3f  OS=%.2f rise=%.2f settle=%.2f ess=%.4f\n', ...
        names{i}, g, J, M(1), M(2), M(3), M(4));
end
set_param('jev_lab_model', 'FastRestart', 'off');
close_system('jev_lab_model', 0);

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
