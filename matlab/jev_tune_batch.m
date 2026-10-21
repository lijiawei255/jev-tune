function jev_tune_batch(jobListPath, outPath)
%JEV_TUNE_BATCH  Run many tuning jobs in ONE MATLAB session.
%
%   jev_tune_batch('jobs.json', 'results.jsonl')
%
%   A cold MATLAB start costs ~50 s on a typical laptop while a whole tuning
%   run costs ~2 s, so one process per job destroys any throughput advantage.
%   This entry point pays the startup once and then loops over the queue,
%   writing one JSON object per line as each job finishes (so a crash keeps the
%   partial results).
%
%   jobs.json is an array of objects with the same keys as jev_tune_json.m

jobs = jsondecode(fileread(jobListPath));
if isstruct(jobs) && numel(jobs) > 1
    jobs = num2cell(jobs);
elseif isstruct(jobs)
    jobs = {jobs};
else
    jobs = jobs(:).';
end

tmpDir = tempname;
mkdir(tmpDir);
cleanup = onCleanup(@() rmdir(tmpDir, 's')); %#ok<NASGU>

fid = fopen(outPath, 'w');
if fid < 0
    error('jev:io', 'cannot write %s', outPath);
end
cleanupFid = onCleanup(@() fclose(fid)); %#ok<NASGU>

fprintf('[batch] %d jobs\n', numel(jobs));
tAll = tic;
for i = 1:numel(jobs)
    job = jobs{i};
    jobFile = fullfile(tmpDir, sprintf('job_%03d.json', i));
    resFile = fullfile(tmpDir, sprintf('res_%03d.json', i));
    f = fopen(jobFile, 'w');
    fwrite(f, jsonencode(job), 'char');
    fclose(f);

    t0 = tic;
    jev_tune_json(jobFile, resFile);
    wall = toc(t0);

    txt = fileread(resFile);
    res = jsondecode(txt);
    if ~isfield(res, 'model') && isfield(job, 'model')
        res.model = job.model;
    end
    res.index = i;
    res.job_wall_s = wall;
    fprintf(fid, '%s\n', jsonencode(res));

    fprintf('[batch] %d/%d  J=%.3f  %.1fs\n', i, numel(jobs), ...
        getfield_safe(res, 'final_J', NaN), wall);
end
fprintf('[batch] done in %.1f s (%.1f s/job)\n', toc(tAll), toc(tAll) / numel(jobs));
end

function v = getfield_safe(s, name, default)
if isfield(s, name) && ~isempty(s.(name))
    v = s.(name);
else
    v = default;
end
end
