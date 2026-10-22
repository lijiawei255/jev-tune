function M = jev_metrics(t, y, u, ref, horizon, umax)
%JEV_METRICS  Response metrics, identical definitions to jev_tune.metrics.
%
%   M = jev_metrics(t, y, u, ref, horizon, umax)
%
%   M is a 9-element row: [overshoot rise settle ess iae itae osc sat_frac sat_over]
%   `u` may be empty (then the saturation entries are 0).

t = t(:); y = y(:);
if isempty(t) || isempty(y)
    % nothing was logged: report "no answer" rather than crashing on y(end)
    M = nan(1, 9);
    return
end
if isempty(ref) || ~isfinite(ref), ref = 1; end
if isempty(horizon), horizon = t(end); end
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
dt = median(diff(t));
iae = sum(abs(e)) * dt;
itae = sum(t .* abs(e)) * dt;

above = y > ref;
osc = 0.5 * sum(diff(above) ~= 0);

if nargin >= 6 && ~isempty(umax) && ~isempty(u)
    u = u(:);
    sat = mean(abs(u) > umax);
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
