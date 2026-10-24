function S = cmp_gains(modelPath, resultPath, outputPath, workDir, config)
%CMP_GAINS Compare gain sets from explicit external MAT variable R.gain_sets.
% Paths are absolute or repository-relative. See save_demo_traces for config.
% 显式指定模型、含R.gain_sets的结果文件、输出、工作目录和配置。
if nargin < 5 || isempty(resultPath)
    error('jev:helperInputs', 'Supply modelPath, resultPath, outputPath, workDir and config.');
end
S = save_demo_traces(modelPath, resultPath, outputPath, workDir, config);
end
