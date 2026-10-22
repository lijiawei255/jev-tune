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
%   lab model: a different plant, a different controller encoding, and no
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

if strcmpi(variant, 'two_loops')
    build_two_loops(mdl, outDir, dst);
    return
elseif strcmpi(variant, 'cascade')
    build_cascade(mdl, outDir, dst);
    return
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

% -------------------------------------------------------------------------
function build_two_loops(mdl, outDir, dst)
% Two unrelated position loops in one model, with names that say nothing.
% Discovery must see two loops, not one ambiguous one, and --all-loops must be
% able to tune both without either one starting from the other's copy.
loop(mdl, 'a', 1, '1', '[1 0.6 1]', 1.0);
loop(mdl, 'b', 2, '1', '[1 1]', 0.6);
% A fixed step keeps this fixture fast: after loop a is tuned it becomes stiff,
% and a variable-step solver would then crawl through *both* loops on every
% experiment.  That slowdown is real engineering behaviour, not a bug, so the
% fixture avoids it and the docs mention it.
set_param(mdl, 'StopTime', '10', 'Solver', 'ode4', ...
    'FixedStep', '0.0005', 'SaveTime', 'on');
save_system(mdl, dst);
close_system(mdl, 0);
fprintf('[demo] built %s (two_loops)\n', dst);
end

function loop(mdl, tag, y, num, den, amp)
% One closed loop: Step -> Sum(+,-) -> Gain x3 -> Plant -> Delay -> back.
add_block('simulink/Sources/Step', [mdl '/Step_' tag], ...
    'Time', '1', 'Before', '0', 'After', num2str(amp), ...
    'Position', [30 y*140 60 y*140+30]);
add_block('simulink/Math Operations/Sum', [mdl '/dSum_' tag], ...
    'Inputs', '+-', 'Position', [100 y*140 120 y*140+24]);
add_block('simulink/Math Operations/Gain', [mdl '/k_' tag '_1'], ...
    'Gain', '2', 'Position', [170 y*140-40 210 y*140-10]);
add_block('simulink/Continuous/Integrator', [mdl '/i_' tag], ...
    'Position', [170 y*140 190 y*140+20]);
add_block('simulink/Math Operations/Gain', [mdl '/k_' tag '_2'], ...
    'Gain', '3', 'Position', [215 y*140 255 y*140+30]);
% filtered derivative (s/(0.01s+1)), the way a real controller does it:
% a raw Derivative block produces an unbounded spike on the step edge, which a
% fixed-step solver cannot integrate
add_block('simulink/Continuous/Transfer Fcn', [mdl '/d_' tag], ...
    'Numerator', '[1 0]', 'Denominator', '[0.01 1]', ...
    'Position', [165 y*140+40 205 y*140+70]);
add_block('simulink/Math Operations/Gain', [mdl '/k_' tag '_3'], ...
    'Gain', '0.05', 'Position', [215 y*140+40 255 y*140+70]);
add_block('simulink/Math Operations/Sum', [mdl '/dSum_' tag '_u'], ...
    'Inputs', '+++', 'Position', [290 y*140 310 y*140+50]);
add_block('simulink/Continuous/Transfer Fcn', [mdl '/plant_' tag], ...
    'Numerator', num, 'Denominator', den, ...
    'Position', [340 y*140 410 y*140+40]);
% a transport delay gives the loop a real ultimate gain; without one a
% second-order plant is stable at every gain and Z-N has no answer
add_block('simulink/Continuous/Transport Delay', [mdl '/delay_' tag], ...
    'DelayTime', '0.02', 'Position', [420 y*140 480 y*140+40]);

add_line(mdl, ['Step_' tag '/1'], ['dSum_' tag '/1'], 'autorouting', 'on');
add_line(mdl, ['dSum_' tag '/1'], ['k_' tag '_1/1'], 'autorouting', 'on');
add_line(mdl, ['dSum_' tag '/1'], ['i_' tag '/1'], 'autorouting', 'on');
add_line(mdl, ['i_' tag '/1'], ['k_' tag '_2/1'], 'autorouting', 'on');
add_line(mdl, ['dSum_' tag '/1'], ['d_' tag '/1'], 'autorouting', 'on');
add_line(mdl, ['d_' tag '/1'], ['k_' tag '_3/1'], 'autorouting', 'on');
add_line(mdl, ['k_' tag '_1/1'], ['dSum_' tag '_u/1'], 'autorouting', 'on');
add_line(mdl, ['k_' tag '_2/1'], ['dSum_' tag '_u/2'], 'autorouting', 'on');
add_line(mdl, ['k_' tag '_3/1'], ['dSum_' tag '_u/3'], 'autorouting', 'on');
add_line(mdl, ['dSum_' tag '_u/1'], ['plant_' tag '/1'], 'autorouting', 'on');
add_line(mdl, ['plant_' tag '/1'], ['delay_' tag '/1'], 'autorouting', 'on');
add_line(mdl, ['delay_' tag '/1'], ['dSum_' tag '/2'], 'autorouting', 'on');
end

function build_cascade(mdl, outDir, dst)
% The canonical cascade, built by hand (Gain + Integrator, no masked block) so
% the *structural* guard is what catches it, not a PID-block count:
%   speed loop (slow):  w_err  -> ka + kb/s -> i_ref
%   current loop (fast): i_err -> kc + kd/s -> voltage
%   armature 1/(0.05 s + 1), mechanics 1/(0.5 s + 1)
% The inner reference is the outer controller's output, so these are not two
% independent loops and the tuner must refuse rather than pick one.
add_block('simulink/Sources/Step', [mdl '/w_ref'], ...
    'Time', '1', 'Before', '0', 'After', '1', 'Position', [20 100 50 130]);
add_block('simulink/Math Operations/Sum', [mdl '/w_err'], ...
    'Inputs', '+-', 'Position', [90 103 110 127]);

add_block('simulink/Math Operations/Gain', [mdl '/ka'], 'Gain', '2', ...
    'Position', [150 70 190 100]);
add_block('simulink/Continuous/Integrator', [mdl '/ib'], ...
    'Position', [150 110 170 130]);
add_block('simulink/Math Operations/Gain', [mdl '/kb'], 'Gain', '3', ...
    'Position', [195 110 235 140]);
add_block('simulink/Math Operations/Sum', [mdl '/w_sum'], 'Inputs', '++', ...
    'Position', [280 95 300 140]);

add_block('simulink/Math Operations/Sum', [mdl '/i_err'], ...
    'Inputs', '+-', 'Position', [340 103 360 127]);
add_block('simulink/Math Operations/Gain', [mdl '/kc'], 'Gain', '2', ...
    'Position', [400 70 440 100]);
add_block('simulink/Continuous/Integrator', [mdl '/id'], ...
    'Position', [400 110 420 130]);
add_block('simulink/Math Operations/Gain', [mdl '/kd'], 'Gain', '3', ...
    'Position', [445 110 485 140]);
add_block('simulink/Math Operations/Sum', [mdl '/i_sum'], 'Inputs', '++', ...
    'Position', [530 95 550 140]);

add_block('simulink/Continuous/Transfer Fcn', [mdl '/armature'], ...
    'Numerator', '1', 'Denominator', '[0.05 1]', 'Position', [590 95 660 135]);
add_block('simulink/Continuous/Transfer Fcn', [mdl '/mech'], ...
    'Numerator', '1', 'Denominator', '[0.5 1]', 'Position', [700 95 770 135]);

add_line(mdl, 'w_ref/1', 'w_err/1', 'autorouting', 'on');
add_line(mdl, 'w_err/1', 'ka/1', 'autorouting', 'on');
add_line(mdl, 'w_err/1', 'ib/1', 'autorouting', 'on');
add_line(mdl, 'ib/1', 'kb/1', 'autorouting', 'on');
add_line(mdl, 'ka/1', 'w_sum/1', 'autorouting', 'on');
add_line(mdl, 'kb/1', 'w_sum/2', 'autorouting', 'on');
add_line(mdl, 'w_sum/1', 'i_err/1', 'autorouting', 'on');
add_line(mdl, 'i_err/1', 'kc/1', 'autorouting', 'on');
add_line(mdl, 'i_err/1', 'id/1', 'autorouting', 'on');
add_line(mdl, 'id/1', 'kd/1', 'autorouting', 'on');
add_line(mdl, 'kc/1', 'i_sum/1', 'autorouting', 'on');
add_line(mdl, 'kd/1', 'i_sum/2', 'autorouting', 'on');
add_line(mdl, 'i_sum/1', 'armature/1', 'autorouting', 'on');
add_line(mdl, 'armature/1', 'mech/1', 'autorouting', 'on');
add_line(mdl, 'mech/1', 'w_err/2', 'autorouting', 'on');
add_line(mdl, 'armature/1', 'i_err/2', 'autorouting', 'on');

set_param(mdl, 'StopTime', '10', 'Solver', 'ode45', 'SaveTime', 'on');
save_system(mdl, dst);
close_system(mdl, 0);
fprintf('[demo] built %s (cascade)\n', dst);
end
