function jev_assert_distinct_paths(source, target)
%JEV_ASSERT_DISTINCT_PATHS Refuse a working/output path that aliases the source.
% Canonicalization resolves relative paths, dot segments and filesystem links
% before any delete, copy or save operation can affect the user's source.
a = canonical(source);
b = canonical(target);
if (ispc && strcmpi(a, b)) || (~ispc && strcmp(a, b))
    error('jev:source_overwrite', ...
        'source and destination resolve to the same file: %s', a);
end
end

function path = canonical(path)
if usejava('jvm')
    file = javaObject('java.io.File', char(path));
    path = char(file.getCanonicalPath());
else
    [folder, name, ext] = fileparts(char(path));
    if isempty(folder), folder = pwd; end
    [ok, info] = fileattrib(folder);
    if ~ok, error('jev:path', 'cannot resolve directory: %s', folder); end
    path = fullfile(info.Name, [name ext]);
end
end
