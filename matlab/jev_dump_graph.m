function G = jev_dump_graph(mdlPath, outPath)
%JEV_DUMP_GRAPH  Write the top-level signal graph of a model as JSON.
%
%   G = jev_dump_graph('C:/work/Motor.slx', 'graph.json')
%
%   Nodes are the blocks at the top level; edges are the signals between them,
%   with subsystem boundaries collapsed (a wire into a subsystem is an edge to
%   that subsystem).  This is the picture discovery reasons about, so it is also
%   the fastest way to see why a model was or was not understood.
%
%   Used by scripts/15_make_discovery_gif.py; no dependencies beyond Simulink.

if nargin < 2 || isempty(outPath), outPath = 'graph.json'; end
if ~isfile(mdlPath)
    error('jev:io', 'no such file: %s', mdlPath);
end
tmpDir = tempname;
mkdir(tmpDir);
[~, ~, ext] = fileparts(mdlPath);
copyPath = fullfile(tmpDir, ['jev_graph' ext]);
copyfile(mdlPath, copyPath);
srcDir = fileparts(mdlPath);
if isfolder(fullfile(srcDir, 'images'))
    copyfile(fullfile(srcDir, 'images'), fullfile(tmpDir, 'images'));
end

mdl = 'jev_graph';
cleanup = onCleanup(@() close_quiet(mdl)); %#ok<NASGU>
load_system(copyPath);
warning('off', 'all');

blocks = find_system(mdl, 'SearchDepth', 1, 'LookUnderMasks', 'none', ...
    'FollowLinks', 'off');
nodes = struct('id', {}, 'type', {}, 'mask', {});
for k = 1:numel(blocks)
    b = blocks{k};
    if strcmp(b, mdl), continue; end
    n = struct('id', strrep(b, [mdl '/'], ''), ...
        'type', get_param(b, 'BlockType'), ...
        'mask', '');
    mt = '';
    try, mt = get_param(b, 'MaskType'); catch, end
    if ~isempty(mt), n.mask = mt; end
    nodes(end+1) = n; %#ok<AGROW>
end

edges = struct('src', {}, 'src_port', {}, 'dst', {}, 'dst_port', {});
for k = 1:numel(blocks)
    b = blocks{k};
    if strcmp(b, mdl), continue; end
    ph = get_param(b, 'PortHandles');
    for p = 1:numel(ph.Outport)
        line = get_param(ph.Outport(p), 'Line');
        if line <= 0, continue; end
        dsts = get_param(line, 'DstPortHandle');
        for d = 1:numel(dsts)
            if dsts(d) <= 0, continue; end
            target = get_param(dsts(d), 'Parent');
            port = get_param(dsts(d), 'PortNumber');
            % climb out of subsystems: an Inport stands for its parent block
            guard = 0;
            while ~strcmp(get_param(target, 'Parent'), mdl) && guard < 12
                if strcmp(get_param(target, 'BlockType'), 'Inport')
                    parent = get_param(target, 'Parent');
                    port = str2double(get_param(target, 'Port'));
                    target = parent;
                else
                    break
                end
                guard = guard + 1;
            end
            e = struct('src', strrep(b, [mdl '/'], ''), 'src_port', p, ...
                'dst', strrep(target, [mdl '/'], ''), 'dst_port', port);
            edges(end+1) = e; %#ok<AGROW>
        end
    end
end

G = struct('model', mdlPath, 'name', mdl, 'nodes', nodes, 'edges', edges);
tmp = [outPath '.tmp'];
fid = fopen(tmp, 'w');
if fid < 0, error('jev:io', 'cannot write %s', tmp); end
fwrite(fid, jsonencode(G), 'char');
fclose(fid);
movefile(tmp, outPath, 'f');
fprintf('[graph] %d blocks, %d signals -> %s\n', numel(nodes), numel(edges), outPath);
end

function close_quiet(mdl)
try
    if bdIsLoaded(mdl)
        try, set_param(mdl, 'FastRestart', 'off'); catch, end
        close_system(mdl, 0);
    end
catch
end
end
