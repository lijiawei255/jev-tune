function S = bench_iter(modelPath, workDir, outputPath, config)
%BENCH_ITER Simulate explicit user gain sets and record responses/timing.
% Paths are absolute or repository-relative. See save_demo_traces for config.
% Repeated gain_sets can measure repeated-call timing; no preset model or gains.
% 显式提供模型、工作目录、输出和配置，不隐式读取未分发的实验文件。
if nargin < 4
    error('jev:helperInputs', 'Supply modelPath, workDir, outputPath and config.');
end
S = save_demo_traces(modelPath, '', outputPath, workDir, config);
end
