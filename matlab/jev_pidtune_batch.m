function jev_pidtune_batch(inFile, outFile, type)
%JEV_PIDTUNE_BATCH  Run Control System Toolbox `pidtune` over a batch of plants.
%
%   jev_pidtune_batch(inFile, outFile, type)
%
%   inFile  : MAT file with variables numM (n-by-m) and denM (n-by-m),
%             transfer-function coefficients highest power first, row per plant
%   outFile : MAT file written with kp, ki, kd, tf (column vectors)
%   type    : 'P' | 'PI' | 'PID' | 'PIDF' (default 'PID')
%
%   Called from Python as
%       matlab -batch "jev_pidtune_batch('in.mat','out.mat','PID')"
%   which avoids the matlab.engine build entirely.

if nargin < 3 || isempty(type)
    type = 'PID';
end

S = load(inFile);
numM = S.numM;
denM = S.denM;
n = size(numM, 1);

kp = nan(n, 1);
ki = nan(n, 1);
kd = nan(n, 1);
tfilt = nan(n, 1);
msg = cell(n, 1);

for i = 1:n
    num = numM(i, :);
    den = denM(i, :);

    firstNum = find(num ~= 0, 1, 'first');
    firstDen = find(den ~= 0, 1, 'first');
    if isempty(firstNum) || isempty(firstDen)
        continue
    end
    num = num(firstNum:end);
    den = den(firstDen:end);

    try
        C = pidtune(tf(num, den), type);
        [kp(i), ki(i), kd(i), tfilt(i)] = piddata(C);
    catch e
        msg{i} = e.message; %#ok<NASGU>
    end
end

save(outFile, 'kp', 'ki', 'kd', 'tfilt', 'msg');
end

