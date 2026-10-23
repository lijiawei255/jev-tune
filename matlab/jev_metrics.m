function M = jev_metrics(t, y, u, ref, horizon, umax)
%JEV_METRICS Response metrics integrated on the actual Simulink time grid.
%
%   M = jev_metrics(t, y, u, ref, horizon, umax)
%
%   M is a 9-element row: [overshoot rise settle ess iae itae osc sat_frac sat_over]
%   `u` may be empty (then the saturation entries are 0).

t = t(:); y = y(:);
if numel(t) < 2 || numel(t) ~= numel(y) || ~isreal(t) || ~isreal(y) || ...
        any(~isfinite(t)) || any(~isfinite(y)) || any(diff(t) < 0) || t(end) <= t(1)
    error('jev:invalid_signal', 'response requires matching finite samples on a nondecreasing time grid');
end
if isempty(ref) || ~isscalar(ref) || ~isreal(ref) || ~isfinite(ref) || ref <= 0
    error('jev:ref', 'only finite positive step references are supported');
end
if isempty(horizon), horizon = t(end); end
validateattributes(horizon, {'numeric'}, {'scalar', 'real', 'positive', 'finite'});
e = ref - y;

% overshoot (fraction of the reference, 0 when there is none)
peak = max(y);
over = max(0, (peak - ref) / abs(ref));

% 10-90 % rise time
t10 = first_cross(t, y, 0.1 * ref);
t90 = first_cross(t, y, 0.9 * ref);
if isnan(t10) || isnan(t90)
    rise = horizon;
else
    rise = t90 - t10;
end

% settling: last time the response leaves the +-2 % band
outside = abs(y - ref) > 0.02 * abs(ref);
if any(outside)
    settle = t(find(outside, 1, 'last'));
else
    settle = 0;
end

ess = (ref - y(end)) / abs(ref);
iae = trapz(t, abs(e));
itae = trapz(t, t .* abs(e));

above = y > ref;
osc = 0.5 * sum(diff(above) ~= 0);

if nargin >= 6 && ~isempty(umax) && ~isempty(u)
    u = u(:);
    validateattributes(umax, {'numeric'}, {'scalar', 'real', 'positive', 'finite'});
    if numel(u) ~= numel(t) || ~isreal(u) || any(~isfinite(u))
        error('jev:invalid_signal', 'actuator samples must be finite and aligned to the response time grid');
    end
    sat = trapz(t, double(abs(u) > umax)) / (t(end) - t(1));
    over_u = max(max(abs(u) - umax, 0)) / umax;
else
    sat = 0;
    over_u = 0;
end

M = [over, rise, settle, ess, iae, itae, osc, sat, over_u];
end

function tc = first_cross(t, y, level)
idx = find(y >= level, 1, 'first');
if isempty(idx)
    tc = NaN;
else
    tc = t(idx);
end
end
