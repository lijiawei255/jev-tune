function mdl = make_demo_model(outDir, variant, opts)
%MAKE_DEMO_MODEL  Build small test benches for the tuner and the discoverer.
%
%   mdl = make_demo_model(outDir)                 % PID block, second-order plant
%   mdl = make_demo_model(outDir, 'unstable')
%   mdl = make_demo_model(outDir, 'gains')        % three Gain blocks, odd names
%   mdl = make_demo_model(outDir, 'nested')       % the same, inside a subsystem,
%                                                 % with saturation, anti-windup
%                                                 % and no Scope at all
%   mdl = make_demo_model(outDir, 'ideal_pid')    % PID block in the Ideal form
%
%   opts.name lets the caller rename the model, which is what the discovery
%   tests use to prove that nothing depends on the model being called
%   jev_demo_plant.
%
%   These exist so the tuner can be checked against something that is NOT the
%   motor-valve benchmark model: a different plant, a different controller encoding, and no
%   Simscape, which makes it fast enough to use in CI.

if nargin < 2 || isempty(variant), variant = 'second_order'; end
if nargin < 3, opts = struct(); end
if ~isfield(opts, 'name') || isempty(opts.name), opts.name = 'jev_demo_plant'; end
name = opts.name;

if ~isfolder(outDir), mkdir(outDir); end
mdl = name;
dst = fullfile(outDir, [mdl '.slx']);
if isfile(dst), delete(dst); end
if bdIsLoaded(mdl), close_system(mdl, 0); end

new_system(mdl);
open_system(mdl);
switch lower(variant)
    case 'unstable', den = '[1 0 -2]';
    case 'integrating', den = '[1 1 0]';
    otherwise, den = '[1 0.6 1]';
end

add_block('simulink/Sources/Step', [mdl '/Step'], ...
    'Time', '1', 'Before', '0', 'After', '1', 'Position', [30 100 60 130]);
add_block('simulink/Math Operations/Sum', [mdl '/Sum_Error'], ...
    'Inputs', '+-', 'Position', [100 103 120 127]);

uSrc = 'Sum_Ctrl/1';          % where the control signal can be tapped
switch lower(variant)
    case 'gains'
        build_gains(mdl, '');
        add_block('simulink/Math Operations/Sum', [mdl '/Sum_Ctrl'], 'Inputs', '+++', ...
            'Position', [300 90 320 140]);
        add_line(mdl, 'alpha/1', 'Sum_Ctrl/1', 'autorouting', 'on');
        add_line(mdl, 'beta/1', 'Sum_Ctrl/2', 'autorouting', 'on');
        add_line(mdl, 'gamma/1', 'Sum_Ctrl/3', 'autorouting', 'on');
        add_line(mdl, 'Sum_Error/1', 'alpha/1', 'autorouting', 'on');
        add_line(mdl, 'Sum_Error/1', 'Integrator/1', 'autorouting', 'on');
        add_line(mdl, 'Integrator/1', 'beta/1', 'autorouting', 'on');
        add_line(mdl, 'Sum_Error/1', 'Derivative/1', 'autorouting', 'on');
        add_line(mdl, 'Derivative/1', 'gamma/1', 'autorouting', 'on');

    case 'nested'
        % Everything the discoverer has to cope with at once: the gains are
        % inside an unmasked subsystem, the names say nothing, there is a
        % saturation with anti-windup, and there is no Scope to log.
        build_nested_controller(mdl);
        add_line(mdl, 'Sum_Error/1', 'Ctrl/1', 'autorouting', 'on');
        uSrc = 'Ctrl/1';

    case 'ideal_pid'
        add_block('simulink/Continuous/PID Controller', [mdl '/PID Controller'], ...
            'Controller', 'PID', 'TimeDomain', 'Continuous-time', ...
            'Form', 'Ideal', 'P', '1', 'I', '1', 'D', '0', ...
            'Position', [160 90 220 140]);
        add_line(mdl, 'Sum_Error/1', 'PID Controller/1', 'autorouting', 'on');
        add_block('simulink/Math Operations/Sum', [mdl '/Sum_Ctrl'], 'Inputs', '+++', ...
            'Position', [300 90 320 140]);
        add_line(mdl, 'PID Controller/1', 'Sum_Ctrl/1', 'autorouting', 'on');

    otherwise
        add_block('simulink/Continuous/PID Controller', [mdl '/PID Controller'], ...
            'Controller', 'PID', 'TimeDomain', 'Continuous-time', ...
            'P', '1', 'I', '0', 'D', '0', 'Position', [160 90 220 140]);
        add_line(mdl, 'Sum_Error/1', 'PID Controller/1', 'autorouting', 'on');
        add_block('simulink/Math Operations/Sum', [mdl '/Sum_Ctrl'], 'Inputs', '+++', ...
            'Position', [300 90 320 140]);
        add_line(mdl, 'PID Controller/1', 'Sum_Ctrl/1', 'autorouting', 'on');
end

add_line(mdl, 'Step/1', 'Sum_Error/1', 'autorouting', 'on');

add_block('simulink/Continuous/Transfer Fcn', [mdl '/Plant'], ...
    'Numerator', '1', 'Denominator', den, 'Position', [380 95 450 135]);
add_block('simulink/Continuous/Transport Delay', [mdl '/Delay'], ...
    'DelayTime', '0.02', 'Position', [470 95 530 135]);

add_line(mdl, uSrc, 'Plant/1', 'autorouting', 'on');
add_line(mdl, 'Plant/1', 'Delay/1', 'autorouting', 'on');
add_line(mdl, 'Delay/1', 'Sum_Error/2', 'autorouting', 'on');

if ~strcmpi(variant, 'nested')
    add_block('simulink/Sinks/Scope', [mdl '/Scope-Position'], 'Position', [590 60 620 90]);
    add_block('simulink/Sinks/Scope', [mdl '/Scope-Current'], 'Position', [590 140 620 170]);
    add_line(mdl, 'Delay/1', 'Scope-Position/1', 'autorouting', 'on');
    add_line(mdl, uSrc, 'Scope-Current/1', 'autorouting', 'on');
end

set_param(mdl, 'StopTime', '10', 'Solver', 'ode45', 'SaveTime', 'on');
save_system(mdl, dst);
close_system(mdl, 0);
fprintf('[demo] built %s (%s)\n', dst, variant);
end

% -------------------------------------------------------------------------
function build_gains(mdl, prefix)
% Deliberately meaningless names: the discoverer must not read them.
add_block('simulink/Math Operations/Gain', [mdl '/' prefix 'alpha'], ...
    'Gain', '2', 'Position', [170 60 210 90]);
add_block('simulink/Continuous/Integrator', [mdl '/' prefix 'Integrator'], ...
    'Position', [170 100 190 120]);
add_block('simulink/Math Operations/Gain', [mdl '/' prefix 'beta'], ...
    'Gain', '3', 'Position', [215 100 255 130]);
add_block('simulink/Continuous/Derivative', [mdl '/' prefix 'Derivative'], ...
    'Position', [170 140 190 160]);
add_block('simulink/Math Operations/Gain', [mdl '/' prefix 'gamma'], ...
    'Gain', '0.05', 'Position', [215 140 255 170]);
end

function build_nested_controller(mdl)
% A subsystem with the same shape as a hand-built PI(D) with anti-windup:
%   e -> Kp -> u
%   e -> Integ -> Ki -> u
%   e -> Deriv -> Kd -> u
%   u -> Sat(+/-1)
%   aw = Sat(u) - u, added to the integrator input (classic clamping)
add_block('simulink/Ports & Subsystems/Subsystem', [mdl '/Ctrl'], ...
    'Position', [160 80 320 160]);
delete_block([mdl '/Ctrl/In1']);   % deleting the block deletes its line
delete_block([mdl '/Ctrl/Out1']);

c = [mdl '/Ctrl'];
add_block('simulink/Sources/In1', [c '/e'], 'Port', '1', 'Position', [20 100 50 120]);
add_block('simulink/Sinks/Out1', [c '/u'], 'Port', '1', 'Position', [560 100 590 120]);
build_gains(mdl, 'Ctrl/');
add_block('simulink/Math Operations/Sum', [c '/int_in'], 'Inputs', '++', ...
    'Position', [90 95 110 125]);
add_block('simulink/Math Operations/Sum', [c '/aw_err'], 'Inputs', '+-', ...
    'Position', [330 180 350 210]);
add_block('simulink/Math Operations/Gain', [c '/Kaw'], 'Gain', '1', ...
    'Position', [375 185 415 215]);
add_block('simulink/Math Operations/Sum', [c '/Sum_Ctrl'], 'Inputs', '+++', ...
    'Position', [440 90 460 160]);
add_block('simulink/Discontinuities/Saturation', [c '/Sat'], ...
    'UpperLimit', '20', 'LowerLimit', '-20', 'Position', [480 100 510 150]);

add_line(c, 'e/1', 'alpha/1', 'autorouting', 'on');
add_line(c, 'e/1', 'int_in/1', 'autorouting', 'on');
add_line(c, 'int_in/1', 'Integrator/1', 'autorouting', 'on');
add_line(c, 'Integrator/1', 'beta/1', 'autorouting', 'on');
add_line(c, 'e/1', 'Derivative/1', 'autorouting', 'on');
add_line(c, 'Derivative/1', 'gamma/1', 'autorouting', 'on');
add_line(c, 'alpha/1', 'Sum_Ctrl/1', 'autorouting', 'on');
add_line(c, 'beta/1', 'Sum_Ctrl/2', 'autorouting', 'on');
add_line(c, 'gamma/1', 'Sum_Ctrl/3', 'autorouting', 'on');
add_line(c, 'Sum_Ctrl/1', 'Sat/1', 'autorouting', 'on');
add_line(c, 'Sat/1', 'u/1', 'autorouting', 'on');
add_line(c, 'Sat/1', 'aw_err/1', 'autorouting', 'on');
add_line(c, 'Sum_Ctrl/1', 'aw_err/2', 'autorouting', 'on');
add_line(c, 'aw_err/1', 'Kaw/1', 'autorouting', 'on');
add_line(c, 'Kaw/1', 'int_in/2', 'autorouting', 'on');
end
