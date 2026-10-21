function [kp, ki, kd, tf] = jev_pidtune(numM, denM, type)
%JEV_PIDTUNE  Batch PID design with Control System Toolbox `pidtune`.
%
%   [kp, ki, kd, tf] = jev_pidtune(numM, denM, type)
%
%   numM, denM : n-by-m matrices of transfer-function coefficients, highest
%                power first, row per plant (leading zeros mean "no such power")
%   type       : 'P' | 'PI' | 'PID' | 'PIDF' (default 'PID')
%
%   Returns the parallel-form gains of the designed controller
%       C(s) = kp + ki/s + kd*s
%   and the derivative filter time constant tf (seconds) that pidtune used.

if nargin < 3 || isempty(type)
    type = 'PID';
end

n = size(numM, 1);
kp = nan(n, 1);
ki = nan(n, 1);
kd = nan(n, 1);
tf = nan(n, 1);

for i = 1:n
    num = numM(i, :);
    den = denM(i, :);

    % strip leading zeros (padding) but keep at least one coefficient
    firstNum = find(num ~= 0, 1, 'first');
    if isempty(firstNum)
        continue
    end
    num = num(firstNum:end);

    firstDen = find(den ~= 0, 1, 'first');
    if isempty(firstDen)
        continue
    end
    den = den(firstDen:end);

    try
        G = tf(num, den);
        C = pidtune(G, type);
        [kp(i), ki(i), kd(i), tf(i)] = piddata(C);
    catch
        % leave NaN -- the caller counts it as a design failure
    end
end
end
