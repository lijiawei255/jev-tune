function jev_tune_worker(queueDir, stopFile, pollSeconds)
%JEV_TUNE_WORKER  Keep one MATLAB session alive and serve tuning jobs.
%
%   jev_tune_worker('queue_dir', 'stop.flag', 0.05)
%
%   Protocol (plain files, no sockets, no toolboxes):
%     client writes   queue_dir/job_<id>.json   {model, iters, ...}
%     worker writes   queue_dir/res_<id>.json   {ok, final_gains, history, ...}
%     client deletes  queue_dir/job_<id>.json (or worker does, after reading)
%     stopping        create queue_dir/stop.flag
%
%   A cold MATLAB start costs ~50 s and a model compile ~10 s, both far larger
%   than the ~0.1 s simulation and 0.002 s decision they wrap. Serving many
%   jobs from one warm session is what makes the throughput advantage real.

if nargin < 3 || isempty(pollSeconds), pollSeconds = 0.05; end
if ~isfolder(queueDir), mkdir(queueDir); end
if isfile(stopFile), delete(stopFile); end

readyFile = fullfile(queueDir, 'ready.flag');
fid = fopen(readyFile, 'w'); fwrite(fid, '1'); fclose(fid);
fprintf('[worker] ready: %s\n', queueDir);
fprintf('[worker] stop file: %s\n', stopFile);

n = 0;
while true
    if isfile(stopFile)
        fprintf('[worker] stop requested after %d jobs\n', n);
        delete(stopFile);
        break
    end

    jobs = dir(fullfile(queueDir, 'job_*.json'));
    if isempty(jobs)
        pause(pollSeconds);
        continue
    end

    [~, order] = sort({jobs.name});
    job = jobs(order(1));
    jobPath = fullfile(queueDir, job.name);
    id = regexprep(job.name, '^job_(.*)\.json$', '$1');
    resPath = fullfile(queueDir, ['res_' id '.json']);

    try
        jev_tune_json(jobPath, resPath);
        n = n + 1;
    catch err
        fid = fopen(resPath, 'w');
        fwrite(fid, jsonencode(struct('ok', false, 'error', err.message)), 'char');
        fclose(fid);
    end

    if isfile(jobPath), delete(jobPath); end
end
