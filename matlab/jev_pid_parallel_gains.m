function gains = jev_pid_parallel_gains(form, parameters)
%JEV_PID_PARALLEL_GAINS Convert Simulink PID block coefficients, not pidstd times.
% Ideal uses P*(1 + I/s + D*N*s/(s+N)); N is unchanged by this conversion.
validateattributes(parameters, {'numeric'}, {'real', 'finite', 'numel', 3});
gains = parameters(:).';
if strcmpi(form, 'Ideal')
    gains = [gains(1), gains(1) * gains(2), gains(1) * gains(3)];
elseif ~strcmpi(form, 'Parallel')
    error('jev:pid_form', 'unsupported Simulink PID form: %s', form);
end
end
