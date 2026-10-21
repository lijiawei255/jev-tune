function bench_run(stopTime, nRuns, outTxt)
%BENCH_RUN  Time Simulink per-run overhead (normal vs fast restart).
%   Run through `matlab -batch "bench_run(1,5,'log.txt')"` so a slow plant
%   model cannot block an interactive session.

if nargin < 1 || isempty(stopTime), stopTime = 1; end
if nargin < 2 || isempty(nRuns), nRuns = 5; end
if nargin < 3 || isempty(outTxt), outTxt = 'bench_out.txt'; end

mdlName = 'jevbench_model';
here = fileparts(mfilename('fullpath'));
cd(fullfile(here, '_tmp'));
fid = fopen(outTxt, 'w');
logf = @(varargin) (fprintf(fid, varargin{:}) && fprintf(varargin{:}));

load_system(mdlName);
try, set_param(mdlName, 'SimMechanicsOpenEditorOnUpdate', 'off'); catch, end
set_param(mdlName, 'StopTime', num2str(stopTime));
gainBlk = [mdlName '/Gain_Kp'];

logf('model=%s stopTime=%g solver=%s\n', mdlName, stopTime, get_param(mdlName,'Solver'));

t = tic; sim(mdlName); tc = 1000*toc(t);
logf('cold_ms=%.1f\n', tc);

tn = zeros(1,nRuns);
for k = 1:nRuns
    set_param(gainBlk, 'Gain', num2str(0.5+0.1*k));
    t = tic; sim(mdlName); tn(k) = 1000*toc(t);
end
logf('normal_ms=%s median=%.1f\n', mat2str(round(tn)), median(tn));

set_param(mdlName, 'FastRestart', 'on');
t = tic; sim(mdlName); tfc = 1000*toc(t);
tf = zeros(1,nRuns);
for k = 1:nRuns
    set_param(gainBlk, 'Gain', num2str(0.5+0.1*k));
    t = tic; sim(mdlName); tf(k) = 1000*toc(t);
end
logf('fr_first_ms=%.1f\n', tfc);
logf('fr_ms=%s median=%.1f\n', mat2str(round(tf)), median(tf));
logf('speedup=%.2f\n', median(tn)/median(tf));

tfs = zeros(1,nRuns);
for k = 1:nRuns
    si = Simulink.SimulationInput(mdlName);
    si = si.setModelParameter('StopTime', num2str(stopTime));
    si = si.setBlockParameter(gainBlk, 'Gain', num2str(0.5+0.1*k));
    t = tic; sim(si); tfs(k) = 1000*toc(t);
end
logf('fr_simin_ms=%s median=%.1f\n', mat2str(round(tfs)), median(tfs));

set_param(mdlName, 'FastRestart', 'off');
close_system(mdlName, 0);
fclose(fid);
end
