function time_phases(model, workRoot)
%TIME_PHASES  Where does a chained run spend its time outside a warm session?
if ~isfolder(workRoot), mkdir(workRoot); end
cd('C:/workspace/jev-tune/matlab');
bdclose('all');

t = tic;
D = jev_discover(model, struct('probe', true, 'all_loops', true, ...
    'work_dir', fullfile(workRoot, 'd1')));
fprintf('discover#1        %.1f s (ok=%d)\n', toc(t), D.ok);

t = tic;
D2 = jev_discover(model, struct('probe', true, 'all_loops', true, ...
    'loop_junction', D.loops(1).junction, 'work_dir', fullfile(workRoot, 'd2')));
fprintf('discover#2        %.1f s (ok=%d)\n', toc(t), D2.ok);

t = tic;
R = jev_tune_model(model, fullfile(workRoot, 'run'), 4, 10, 1.0, D2.cfg);
fprintf('tune(4 iters)     %.1f s (setup %.1f sweep %.1f loop %.1f)\n', ...
    toc(t), R.timings.setup, R.timings.sweep, R.timings.loop);

t = tic;
W = jev_writeback(model, R.final_gains, struct('target', fullfile(workRoot, 'out.slx')), ...
    fullfile(workRoot, 'wb.json'));
fprintf('writeback         %.1f s (ok=%d)\n', toc(t), W.ok);
end
