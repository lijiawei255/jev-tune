function [feats, curves] = jev_state(M, t, y, u, gains, gzn, ku, tu, prevAction, prevCost, cost, iter, horizon, ref)
%JEV_STATE  Build the 20 features + 2x64 traces exactly as jev_tune.state does.

if nargin < 13 || isempty(ref), ref = 1; end
if nargin < 12 || isempty(horizon), horizon = t(end); end

yc = resample_trace(y(:), 64) / max(abs(ref), 1e-9);
uc = resample_trace(u(:), 64);
if isempty(u)
    uc = zeros(64, 1);
end

os_ = clamp(M(1), -1, 3);
rise_ = clamp(M(2) / horizon, 0, 2);
settle_ = clamp(M(3) / horizon, 0, 2);
ess_ = clamp(M(4), -3, 3);
iae_ = clamp(log10(max(M(5), 1e-9)), -9, 3) / 3;
itae_ = clamp(log10(max(M(6) / (ref * horizon^2), 1e-9)), -9, 3) / 3;
osc_ = clamp(M(7) / 5, 0, 4);
sat_ = clamp(M(8), 0, 1);
satover_ = clamp(M(9), 0, 3);
ymax_ = clamp(max(abs(y)) / max(abs(ref), 1e-9), 0, 12) / 12;

kp_ = clamp(log10(max(gains(1), 1e-9) / max(gzn(1), 1e-9)), -3, 3) / 3;
ki_ = clamp(log10((gains(2) + 1e-6) / (gzn(2) + 1e-6)), -3, 3) / 3;
kd_ = clamp(log10((gains(3) + 1e-6) / (gzn(3) + 1e-6)), -3, 3) / 3;

pa = clamp(prevAction(:).', -0.5, 0.5) * 4;
dp = clamp((prevCost - cost) / 5, -3, 3);
it_ = clamp(iter / 20, 0, 1);
kukp_ = clamp(log10(max(ku, 1e-9) / max(gains(1), 1e-9)), -3, 3) / 3;
tuh_ = clamp(tu / horizon, 0, 5) / 5;

feats = [os_, rise_, settle_, ess_, iae_, itae_, osc_, sat_, satover_, ymax_, ...
         kp_, ki_, kd_, pa(1), pa(2), pa(3), dp, it_, kukp_, tuh_].';
feats(~isfinite(feats)) = 0;
curves = [yc, uc];
curves = reshape(curves.', 1, 2, 64);
end

function v = clamp(x, lo, hi)
v = min(max(x, lo), hi);
end

function r = resample_trace(x, n)
if numel(x) == 1
    r = repmat(x, n, 1);
    return
end
idx = round(linspace(1, numel(x), n));
r = x(idx);
end
