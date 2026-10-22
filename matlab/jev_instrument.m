function ok = jev_instrument(mdlName, tapBlock, scopeName, tapPort)
%JEV_INSTRUMENT  Attach a logging Scope to a signal, on the working copy.
%
%   ok = jev_instrument(mdl, 'Plant', 'jev_measure')
%
%   The tuner only ever works on a copy of the user's model, so a model that
%   has no usable Scope needs no manual edit: the tap is added here.
%
%   `tapBlock` may live inside a subsystem.  A Scope lives at the top level, so
%   the signal is tapped where it *leaves* that subsystem, which is the same
%   signal (a subsystem Outport is a wire, not a computation).
%
%   Returns false when the tap cannot be created; callers fall back to asking
%   the user for an explicit block name.

ok = false;
if nargin < 3 || isempty(scopeName), scopeName = 'jev_measure'; end
if nargin < 4 || isempty(tapPort), tapPort = 1; end
if isempty(tapBlock), return; end
blk = [mdlName '/' scopeName];
if ~block_exists(tapBlock)
    fprintf('[instrument] no such block: %s\n', tapBlock);
    return
end
if ~block_exists(blk)
    try
        add_block('simulink/Sinks/Scope', blk, 'Position', [760 40 790 70]);
    catch err
        fprintf('[instrument] could not add a scope: %s\n', err.message);
        return
    end
end
[spec, found] = jev_tap_target(mdlName, tapBlock, tapPort);
if ~found
    fprintf('[instrument] %s does not emerge at the top level\n', tapBlock);
    return
end
try
    % reconnect every call: a previous candidate may have used this scope
    lines = get_param(blk, 'LineHandles');
    for k = 1:numel(lines.Inport)
        if lines.Inport(k) > 0, delete_line(lines.Inport(k)); end
    end
    % add_line wants a system-relative 'block/port' spec, not a full path
    add_line(mdlName, spec, [scopeName '/1'], 'autorouting', 'on');
catch err
    fprintf('[instrument] could not connect %s: %s\n', target, err.message);
    return
end
try
    set_param(blk, 'DataLogging', 'on', ...
        'DataLoggingVariableName', scopeName, ...
        'DataLoggingSaveFormat', 'Dataset', ...
        'DataLoggingLimitDataPoints', 'off');
    ok = true;
catch err
    fprintf('[instrument] could not enable logging: %s\n', err.message);
end
end

% -------------------------------------------------------------------------
function [spec, ok] = jev_tap_target(mdl, blk, port)
% Where a top-level Scope can tap this signal, as a 'block/port' spec relative
% to the model (the form add_line wants).
ok = false; spec = '';
if strcmp(get_param(blk, 'Parent'), mdl)
    spec = sprintf('%s/%d', strrep(blk, [mdl '/'], ''), port);
    ok = true;
    return
end
cur = blk;
port = 0;
guard = 0;
while ~strcmp(get_param(cur, 'Parent'), mdl) && guard < 12
    par = get_param(cur, 'Parent');
    port = outport_carrying(par, cur);
    if port <= 0, return; end
    cur = par;
    guard = guard + 1;
end
if ~strcmp(get_param(cur, 'Parent'), mdl), return; end
spec = sprintf('%s/%d', strrep(cur, [mdl '/'], ''), port);
ok = true;
end

function port = outport_carrying(sub, child)
% Which output port of `sub` carries the signal produced by `child`?
port = -1;
outs = find_system(sub, 'SearchDepth', 1, 'LookUnderMasks', 'none', ...
    'FollowLinks', 'off', 'BlockType', 'Outport');
for k = 1:numel(outs)
    if reaches_upstream(outs{k}, child, 16)
        port = str2double(get_param(outs{k}, 'Port'));
        return
    end
end
end

function tf = reaches_upstream(blk, target, depth)
tf = false;
if depth <= 0 || isempty(blk), return; end
if strcmp(blk, target), tf = true; return; end
nin = numel(get_param(blk, 'PortHandles').Inport);
for i = 1:nin
    s = src_of(blk, i);
    if isempty(s), continue; end
    if strcmp(s, target) || reaches_upstream(s, target, depth - 1)
        tf = true;
        return
    end
end
end

function s = src_of(blk, k)
s = '';
pc = get_param(blk, 'PortConnectivity');
if k > numel(pc), return; end
h = pc(k).SrcBlock;
if isempty(h) || all(h == -1), return; end
s = getfullname(h(1));
end

function tf = block_exists(path)
tf = false;
try
    tf = ~isempty(get_param(path, 'Handle'));
catch
end
end
