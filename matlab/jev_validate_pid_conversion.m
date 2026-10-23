function jev_validate_pid_conversion(block)
%JEV_VALIDATE_PID_CONVERSION Restrict Ideal conversion to verified zero-state PID.
if strcmpi(get_param(block, 'Form'), 'Parallel'), return; end
if ~strcmpi(get_param(block, 'Form'), 'Ideal')
    error('jev:pid_form', 'only Parallel and Ideal Simulink PID forms are supported');
end
expected = struct('ControllerParametersSource', 'internal', ...
    'InitialConditionSource', 'internal', 'ExternalReset', 'none', ...
    'TrackingMode', 'off', 'AntiWindupMode', 'none', 'LimitOutput', 'off');
names = fieldnames(expected);
for k = 1:numel(names)
    if ~strcmpi(get_param(block, names{k}), expected.(names{k}))
        error('jev:unsupported_pid_configuration', ...
            'Ideal conversion requires %s=%s; this configuration is not verified', ...
            names{k}, expected.(names{k}));
    end
end
parameters = get_param(block, 'DialogParameters');
if isfield(parameters, 'LimitIntegratorOutput') && ...
        ~strcmpi(get_param(block, 'LimitIntegratorOutput'), 'off')
    error('jev:unsupported_pid_configuration', 'Ideal conversion with integrator limits is not verified');
end
for name = {'InitialConditionForIntegrator', 'InitialConditionForFilter', 'DifferentiatorICPrevScaledInput'}
    if isfield(parameters, name{1})
        value = str2double(get_param(block, name{1}));
        if ~isscalar(value) || ~isfinite(value) || value ~= 0
            error('jev:unsupported_pid_configuration', ...
                'Ideal conversion requires a literal zero %s', name{1});
        end
    end
end
end
