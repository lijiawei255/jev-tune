function mdl = make_demo_model(outDir, variant)
%MAKE_DEMO_MODEL  Build a small, non-Simscape test bench with a PID Controller block.
%
%   mdl = make_demo_model(outDir)            % second-order plant + delay
%   mdl = make_demo_model(outDir, 'unstable')
%
%   This exists so the tuner can be checked against something that is NOT the
%   motor-valve benchmark model: a different plant, a different controller encoding (a masked
%   "PID Controller" block instead of three Gain blocks) and no Simscape, which
%   makes it fast enough to use in CI.

if nargin < 2 || isempty(variant), variant = 'second_order'; end
if ~isfolder(outDir), mkdir(outDir); end
mdl = 'jev_demo_plant';
dst = fullfile(outDir, [mdl '.slx']);
if isfile(dst), delete(dst); end
if bdIsLoaded(mdl), close_system(mdl, 0); end

new_system(mdl);
open_system(mdl);

add_block('simulink/Sources/Step', [mdl '/Step'], ...
    'Time', '1', 'Before', '0', 'After', '1', 'Position', [30 100 60 130]);
add_block('simulink/Math Operations/Sum', [mdl '/Sum_Error'], ...
    'Inputs', '+-', 'Position', [100 103 120 127]);
add_block('simulink/Continuous/PID Controller', [mdl '/PID Controller'], ...
    'Controller', 'PID', 'TimeDomain', 'Continuous-time', ...
    'P', '1', 'I', '0', 'D', '0', 'Position', [160 90 220 140]);

switch lower(variant)
    case 'unstable'
        num = '1'; den = '[1 0 -2]';
    case 'integrating'
        num = '1'; den = '[1 1 0]';
    otherwise
        num = '1'; den = '[1 0.6 1]';
end
add_block('simulink/Continuous/Transfer Fcn', [mdl '/Plant'], ...
    'Numerator', num, 'Denominator', den, 'Position', [260 95 330 135]);
add_block('simulink/Continuous/Transport Delay', [mdl '/Delay'], ...
    'DelayTime', '0.02', 'Position', [350 95 410 135]);

add_block('simulink/Sinks/Scope', [mdl '/Scope-Position'], 'Position', [470 60 500 90]);
add_block('simulink/Sinks/Scope', [mdl '/Scope-Current'], 'Position', [470 140 500 170]);

add_line(mdl, 'Step/1', 'Sum_Error/1', 'autorouting', 'on');
add_line(mdl, 'Sum_Error/1', 'PID Controller/1', 'autorouting', 'on');
add_line(mdl, 'PID Controller/1', 'Plant/1', 'autorouting', 'on');
add_line(mdl, 'Plant/1', 'Delay/1', 'autorouting', 'on');
add_line(mdl, 'Delay/1', 'Scope-Position/1', 'autorouting', 'on');
add_line(mdl, 'Delay/1', 'Sum_Error/2', 'autorouting', 'on');
add_line(mdl, 'PID Controller/1', 'Scope-Current/1', 'autorouting', 'on');

set_param(mdl, 'StopTime', '10', 'Solver', 'ode45', 'SaveTime', 'on');

save_system(mdl, dst);
close_system(mdl, 0);
fprintf('[demo] built %s (%s)\n', dst, variant);
end
