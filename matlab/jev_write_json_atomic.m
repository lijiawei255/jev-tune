function jev_write_json_atomic(value, path)
%JEV_WRITE_JSON_ATOMIC Publish a complete JSON response by a same-folder rename.
temporary = [char(path) '.tmp'];
fid = fopen(temporary, 'w');
if fid < 0, error('jev:io', 'cannot write %s', temporary); end
try
    fwrite(fid, jsonencode(value), 'char');
    fclose(fid);
catch err
    fclose(fid);
    rethrow(err);
end
[ok, message] = movefile(temporary, path, 'f');
if ~ok, error('jev:io', 'cannot publish %s: %s', path, message); end
end
