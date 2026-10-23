function [t, y] = jev_read_signal(out, name, element)
%JEV_READ_SIGNAL Read one explicitly identified scalar logged signal.
% A multi-element Dataset is ambiguous unless element (index or name) is set.
if nargin < 3, element = []; end
t = []; y = [];
var = matlab.lang.makeValidName(strrep(name, '-', '_'));
if ~(isprop(out, var) || (isstruct(out) && isfield(out, var))), return; end
ds = out.(var);
if isa(ds, 'Simulink.SimulationData.Dataset')
    count = numElements(ds);
    if isempty(element)
        if count ~= 1
            error('jev:wide_signal', ...
                '"%s" contains %d Dataset elements; select one explicitly or use --auto', name, count);
        end
        element = 1;
    end
    try
        signal = getElement(ds, element);
    catch
        error('jev:signal_element', 'the requested element is not present in "%s"', name);
    end
    if isa(signal, 'Simulink.SimulationData.Signal')
        signal = signal.Values;
    end
    if ~isa(signal, 'timeseries')
        error('jev:invalid_signal', '"%s" must contain a scalar timeseries signal', name);
    end
    t = signal.Time; y = signal.Data;
elseif isa(ds, 'timeseries')
    t = ds.Time; y = ds.Data;
elseif isstruct(ds) && isfield(ds, 'time') && isfield(ds, 'signals')
    if numel(ds.signals) ~= 1
        error('jev:wide_signal', '"%s" contains several logged signals', name);
    end
    t = ds.time; y = ds.signals.values;
else
    error('jev:invalid_signal', 'unsupported logged signal format for "%s"', name);
end
if ~isnumeric(t) || ~isnumeric(y) || ~isreal(t) || ~isreal(y) || ...
        numel(t) < 2 || any(~isfinite(t(:)))
    error('jev:invalid_signal', '"%s" requires at least two finite real samples', name);
end
if any(~isfinite(y(:)))
    error('jev:nonfinite_signal', '"%s" contains a nonfinite response', name);
end
t = t(:);
if numel(y) ~= numel(t)
    error('jev:wide_signal', '"%s" must contain exactly one scalar per time sample', name);
end
y = y(:);
if any(diff(t) < 0) || t(end) <= t(1)
    error('jev:invalid_signal', '"%s" has an invalid time vector', name);
end
end
