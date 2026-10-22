function D = jev_discover(mdlPath, opts)
%JEV_DISCOVER  Find the PID gains, the measured signal and the reference.
%
%   D = jev_discover('C:/work/Motor.slx')
%   D = jev_discover(mdlPath, struct('probe', false, 'work_dir', tempname))
%
%   Discovery is structural first and behavioural second.
%
%     1. structural: walk the signal graph, with subsystem Inports treated as
%        transparent, to find the error junction, the feedback path and every
%        scalar Gain between the two.  A Gain is classified by what sits
%        between it and the error junction: an Integrator makes it integral, a
%        Derivative makes it derivative, nothing makes it proportional.
%        A Gain fed from the output of a Saturate block is anti-windup, not a
%        controller gain, and is dropped.
%     2. behavioural: scale each surviving candidate by 2 and measure how much
%        the closed-loop response moves.  This breaks ties that the structure
%        cannot (two proportional-looking gains) and catches gains that look
%        like a controller but do not touch the response at all.
%
%   Block names are never used to decide what a block *is*.  They are reported
%   in D.evidence so a human can check the guess without reading the code.
%
%   D.confidence
%     'high'    exactly one proportional, one integral and one derivative
%               candidate, confirmed by the probe (or no probe requested)
%     'medium'  a tie had to be broken, or the controller has fewer than three
%               terms (P only, PI only)
%     'low'     outside the design: cascade, several PID blocks, no loop found.
%               The caller must ask the user instead of tuning silently.
%
%   See also JEV_TUNE_MODEL, JEV_TUNE_JSON.

if nargin < 2 || isempty(opts), opts = struct(); end
opts = with_defaults(opts);

D = struct('ok', false, 'model', mdlPath, 'confidence', 'low', ...
    'warnings', {{}}, 'evidence', {{}}, 'candidates', {{}});
if ~isfile(mdlPath)
    D.code = 'model_not_found';
    D.error = sprintf('no such file: %s', mdlPath);
    return
end

if ~isfolder(opts.work_dir), mkdir(opts.work_dir); end
[~, ~, ext] = fileparts(mdlPath);
dst = fullfile(opts.work_dir, ['jev_disc_model' ext]);
mdl = 'jev_disc_model';
if isfile(dst), delete(dst); end
copyfile(mdlPath, dst);
srcDir = fileparts(mdlPath);
if isfolder(fullfile(srcDir, 'images'))
    copyfile(fullfile(srcDir, 'images'), fullfile(opts.work_dir, 'images'));
end

try
    load_system(dst);
catch err
    D.code = 'load_failed';
    D.error = err.message;
    return
end
cleanup = onCleanup(@() safe_close(mdl)); %#ok<NASGU>
warning('off', 'all');

stopTime = model_stop_time(mdl, D);
D.stop_time = stopTime;

% ------------------------------------------------------------------ structure
blks = collect_blocks(mdl);
D.n_blocks = numel(blks);

[cands, errNote, scan] = junction_candidates(mdl, blks);
D.junction_scan = scan;
D.evidence{end+1} = errNote;
if isempty(cands)
    D.code = 'no_loop';
    D.error = 'could not find a closed loop (a Sum whose feedback input is downstream of itself)';
    D.warnings{end+1} = ['no error junction found; pass kp_block/ki_block/kd_block ' ...
        'explicitly, or check that the model has one feedback loop with a Sum error'];
    return
end
[errSum, refIdx, fbIdx] = choose_junction(mdl, cands, stopTime, D);
D.n_junction_candidates = numel(cands);
D.error_junction = strrep(errSum, [mdl '/'], '');

[measure, mport] = resolved_src_port(errSum, fbIdx);
if isempty(measure)
    D.code = 'no_measurement';
    D.error = 'the feedback input of the error junction has no source';
    return
end
% a Scope cannot be in the feedback path, but a To Workspace / Outport can sit
% between the amplifier and the junction; keep walking until a real signal.
measure = unwrap_sink(measure, mdl);
D.measure_block = strrep(measure, [mdl '/'], '');
D.measure_port = mport;
D.evidence{end+1} = sprintf('measured signal: %s port %d (feedback into the error junction)', ...
    D.measure_block, mport);

% ---------------------------------------------------------------- reference
[refCmd, refSrc] = reference_value(mdl, errSum, refIdx);
D.reference = refCmd;
D.reference_source = refSrc;

% ---------------------------------------------------------------- controller
pidBlocks = {};
for k = 1:numel(blks)
    b = blks{k};
    if ~strcmp(get_param(b, 'BlockType'), 'SubSystem'), continue; end
    mt = lower(strtrim(safe_get(b, 'MaskType', '')));
    if any(strcmp(mt, {'pid 1dof', 'pid 1-dof', 'pid controller', 'pid'}))
        pidBlocks{end+1} = b; %#ok<AGROW>
    end
end

if numel(pidBlocks) > 1
    D.code = 'cascade_unsupported';
    D.warnings{end+1} = sprintf(['%d PID blocks found (%s): this looks like a cascade. ' ...
        'The tuner handles one loop; asking the user which loop to tune is safer ' ...
        'than tuning the wrong one.'], numel(pidBlocks), strjoin(names(pidBlocks, mdl), ', '));
    D.candidates = names(pidBlocks, mdl);
    return
end

controller = struct('kind', 'unknown');
if numel(pidBlocks) == 1
    controller = pid_block_config(pidBlocks{1}, mdl, D);
else
    [controller, ok] = three_gain_config(mdl, blks, errSum, measure, opts, D);
    if ~ok, return; end
end
D.controller = controller;
D.cfg = build_cfg(mdl, D, controller, measure, refCmd, stopTime);

% -------------------------------------------------------------------- probe
if opts.probe && strcmp(controller.kind, 'three_gains')
    D = probe_candidates(mdl, D, measure, mport, stopTime, refCmd, opts);
end

% ------------------------------------------------------------------ verdict
D.ok = true;
D.confidence = verdict(D, controller);
if strcmp(D.confidence, 'low')
    D.code = 'ambiguous_controller';
    D.warnings{end+1} = ['low confidence: ask the user which blocks are Kp/Ki/Kd ' ...
        'before tuning (see D.candidates)'];
end

if isempty(refCmd) || ~isfinite(refCmd)
    D.warnings{end+1} = 'the reference could not be inferred; pass ref_source explicitly';
end
safe_close(mdl);
fprintf('[discover] %s  confidence=%s\n', D.error_junction, D.confidence);
end

% =========================================================================
%  graph helpers
% =========================================================================
function out = collect_blocks(root)
% Every block reachable without entering a masked or library-linked subsystem:
% those are configuration boundaries (their dialogs are the interface), so the
% blocks inside them are not candidates for editing.
out = {};
queue = {root};
guard = 0;
while ~isempty(queue) && guard < 5000
    p = queue{1}; queue(1) = [];
    kids = find_system(p, 'SearchDepth', 1, 'LookUnderMasks', 'none', ...
        'FollowLinks', 'off');
    for k = 1:numel(kids)
        b = kids{k};
        if strcmp(b, p), continue; end
        guard = guard + 1;
        out{end+1} = b; %#ok<AGROW>
        if strcmp(get_param(b, 'BlockType'), 'SubSystem')
            masked = strcmp(safe_get(b, 'Mask', 'off'), 'on');
            linked = ~strcmp(safe_get(b, 'LinkStatus', 'none'), 'none');
            if ~masked && ~linked
                queue{end+1} = b; %#ok<AGROW>
            end
        end
    end
end
end

function s = resolved_src(blk, k)
% Source block of input port k, looking through subsystem Inports, so a loop
% that is drawn across subsystem boundaries still looks like one loop.
[s, ~] = resolved_src_port(blk, k);
end

function [b, p] = resolved_src_port(blk, k)
% Source block *and output port* feeding input port k of `blk`.  The port
% matters: a subsystem with four outputs (speed, torque, position, current)
% feeds the error junction from exactly one of them, and tapping the wrong one
% silently tunes against the wrong signal.
[b, p] = source_port_of(blk, k);
guard = 0;
while ~isempty(b) && strcmp(get_param(b, 'BlockType'), 'Inport') && guard < 25
    par = get_param(b, 'Parent');
    if strcmp(get_param(par, 'Type'), 'block_diagram'), b = ''; p = 0; return; end
    idx = str2double(get_param(b, 'Port'));
    [b, p] = source_port_of(par, idx);
    guard = guard + 1;
end
end

function [b, p] = source_port_of(blk, k)
% Walk the actual line instead of PortConnectivity: a line has exactly one
% source port, so this is unambiguous even when the source feeds many blocks.
b = ''; p = 0;
ph = get_param(blk, 'PortHandles');
if k > numel(ph.Inport), return; end
l = get_param(ph.Inport(k), 'Line');
if l <= 0, return; end
sp = get_param(l, 'SrcPortHandle');
if sp <= 0, return; end
b = getfullname(get_param(sp, 'Parent'));
p = get_param(sp, 'PortNumber');
end

function d = resolved_dsts(blk)
% Where the signal produced by `blk` goes next, as full block paths.
%
%   * an unmasked subsystem is transparent: the signal continues at the blocks
%     its Inports drive, which is where a controller drawn inside it lives;
%   * an Outport is a wire, not a computation: the signal continues outside, at
%     whatever the parent subsystem's output port drives;
%   * anything else: whatever its output port 1 drives.
if is_subsystem(blk) && is_open_subsystem(blk)
    d = internal_consumers(blk);
    return
end
d = {};
queue = raw_dst(blk);
queue = queue(~ismember(queue, -1));
seen = containers.Map('KeyType', 'char', 'ValueType', 'logical');
guard = 0;
while ~isempty(queue) && guard < 500
    b = name_of(queue(1)); queue(1) = [];
    guard = guard + 1;
    if strcmp(get_param(b, 'BlockType'), 'Outport')
        more = raw_dst(b);
        queue = [queue, more(~ismember(more, -1))]; %#ok<AGROW>
    elseif ~isKey(seen, b)
        seen(b) = true;
        d{end+1} = b; %#ok<AGROW>
    end
end
end

function raw = raw_dst(blk)
% Destinations of the signal leaving `blk`.  Input ports come first in
% PortConnectivity, so an output port is `number of inputs + 1`; an Outport has
% no output port of its own and refers to its parent's instead.
raw = [];
bt = get_param(blk, 'BlockType');
if strcmp(bt, 'Outport')
    par = get_param(blk, 'Parent');
    if strcmp(get_param(par, 'Type'), 'block_diagram'), return; end
    port = str2double(get_param(blk, 'Port'));
    idx = numel(get_param(par, 'PortHandles').Inport) + port;
    pc = get_param(par, 'PortConnectivity');
else
    ph = get_param(blk, 'PortHandles');
    if isempty(ph.Outport), return; end
    idx = numel(ph.Inport) + 1;
    pc = get_param(blk, 'PortConnectivity');
end
if idx <= numel(pc)
    raw = pc(idx).DstBlock;
end
end

function n = name_of(h)
if ischar(h), n = h; else, n = getfullname(h); end
end

function tf = is_subsystem(blk)
tf = strcmp(get_param(blk, 'BlockType'), 'SubSystem');
end

function tf = is_open_subsystem(blk)
% Unmasked and not a library link: its content is the user's own wiring, so the
% graph may look inside.  A masked block (including every Simscape block and the
% PID Controller) is a configuration boundary and is treated as one node.
tf = strcmp(safe_get(blk, 'Mask', 'off'), 'off') && ...
    strcmp(safe_get(blk, 'LinkStatus', 'none'), 'none');
end

function d = internal_consumers(sub)
% Blocks driven by the Inports of `sub`: where a signal goes after it enters.
d = {};
ins = find_system(sub, 'SearchDepth', 1, 'LookUnderMasks', 'none', ...
    'FollowLinks', 'off', 'BlockType', 'Inport');
for k = 1:numel(ins)
    nin = numel(get_param(ins{k}, 'PortHandles').Inport);
    pc = get_param(ins{k}, 'PortConnectivity');
    if numel(pc) < nin + 1, continue; end
    raw = pc(nin + 1).DstBlock;
    raw = raw(~ismember(raw, -1));
    for j = 1:numel(raw)
        d{end+1} = name_of(raw(j)); %#ok<AGROW>
    end
end
end

function set = forward_set(blk, stopAt, maxDepth)
% Breadth-first downstream walk, never expanding `stopAt` (the plant output).
% That cut is what separates "the controller and the actuator" from "the plant".
set = {};
seen = containers.Map('KeyType', 'char', 'ValueType', 'logical');
frontier = {blk};
depth = 0;
while ~isempty(frontier) && depth < maxDepth
    nxt = {};
    for k = 1:numel(frontier)
        b = frontier{k};
        if isequal(b, stopAt), continue; end
        ds = resolved_dsts(b);
        for j = 1:numel(ds)
            c = ds{j};
            if isKey(seen, c), continue; end
            seen(c) = true;
            set{end+1} = c; %#ok<AGROW>
            nxt{end+1} = c; %#ok<AGROW>
        end
    end
    frontier = nxt;
    depth = depth + 1;
end
end

function [cands, note, scan] = junction_candidates(mdl, blks)
% A summing junction is a *candidate* error junction when at least one of its
% inputs is downstream of itself (the feedback) and at least one is not (the
% reference).  A plant usually contains such sums too -- a torque balance adds
% the motor torque and the load torque, and one of those comes back through the
% loop -- so candidates are ranked here and verified by a run afterwards.
cands = struct('sum', {}, 'score', {}, 'ref', {}, 'fb', {});
scan = struct('sum', {}, 'n_inputs', {}, 'in_feedback', {}, 'fwd', {}, 'score', {});
sums = {};
for k = 1:numel(blks)
    if strcmp(get_param(blks{k}, 'BlockType'), 'Sum'), sums{end+1} = blks{k}; end %#ok<AGROW>
end
for k = 1:numel(sums)
    s = sums{k};
    nin = numel(get_param(s, 'PortHandles').Inport);
    if nin < 2, continue; end
    set = forward_set(s, [], 14);
    inFwd = false(1, nin);
    for i = 1:nin
        src = resolved_src(s, i);
        inFwd(i) = ~isempty(src) && any(strcmp(src, set));
    end
    sc = 0;
    full = struct('sum', strrep(s, [mdl '/'], ''), 'n_inputs', nin, ...
        'in_feedback', inFwd, 'fwd', {set}, 'score', NaN);
    if ~any(inFwd) || all(inFwd)
        scan(end+1) = full; %#ok<AGROW>
        continue
    end
    fb = find(inFwd, 1, 'last');
    ref = find(~inFwd, 1, 'first');
    if sum(inFwd) == 1, sc = sc + 10; end
    if numel(unique(inFwd)) == 2, sc = sc + 2; end
    if has_step_ancestor(resolved_src(s, ref), 10), sc = sc + 5; end
    if strcmpi(safe_get(s, 'IconShape', ''), 'round'), sc = sc + 1; end
    full.score = sc;
    scan(end+1) = full; %#ok<AGROW>
    cands(end+1) = struct('sum', s, 'score', sc, 'ref', ref, 'fb', fb); %#ok<AGROW>
end
if isempty(cands)
    note = 'no error junction found';
else
    [~, order] = sort([cands.score], 'descend');
    cands = cands(order);
    note = sprintf('junction candidates (ranked): %s', strjoin(cellfun( ...
        @(b) strrep(b, [mdl '/'], ''), {cands.sum}, 'UniformOutput', false), ', '));
end
end

function [best, refIdx, fbIdx] = choose_junction(mdl, cands, stopTime, D)
% Structure cannot tell an error junction from a summing point inside the
% plant.  Behaviour can: at a real error junction the reference and the
% steady-state output are the same physical quantity, so their magnitudes
% agree.  A load-torque sum fails that test badly (newton-metres vs rad/s).
best = cands(1).sum; refIdx = cands(1).ref; fbIdx = cands(1).fb;
if numel(cands) == 1, return; end
n = min(numel(cands), 3);
gap = inf(1, n);
for k = 1:n
    [m, mp] = resolved_src_port(cands(k).sum, cands(k).fb);
    if isempty(m), continue; end
    [m, mp] = unwrap_sink(m, mdl, mp);
    if ~jev_instrument(mdl, m, 'jev_junction_probe', mp), continue; end
    [~, y] = simulate(mdl, stopTime, 'jev_junction_probe');
    if isempty(y), continue; end
    yss = abs(median(y(max(1, round(0.8 * numel(y))):end)));
    rv = reference_value(mdl, cands(k).sum, cands(k).ref);
    if isfinite(rv) && rv > 1e-9 && yss > 1e-9
        gap(k) = abs(log(rv / yss));
    end
end
[g, win] = min(gap);
if ~isfinite(g)
    D.warnings{end+1} = ['the error junction could not be verified by a run; ' ...
        'keeping the structural best guess'];
    delete_probe_scope(mdl, 'jev_junction_probe');
    return
end
best = cands(win).sum; refIdx = cands(win).ref; fbIdx = cands(win).fb;
D.junction_agreement = exp(-g);
if win > 1
    D.evidence{end+1} = sprintf(['junction verified by a run: %s ' ...
        '(reference/output magnitude ratio %.2f)'], ...
        strrep(best, [mdl '/'], ''), exp(-g));
end
delete_probe_scope(mdl, 'jev_junction_probe');
end

function delete_probe_scope(mdl, scope)
blk = [mdl '/' scope];
if block_exists(blk)
    try, delete_block(blk); catch, end
end
end

function tf = has_step_ancestor(blk, maxDepth)
tf = false;
if isempty(blk), return; end
frontier = {blk};
seen = {};
for d = 1:maxDepth
    if isempty(frontier), return; end
    nxt = {};
    for k = 1:numel(frontier)
        b = frontier{k};
        if any(strcmp(b, seen)), continue; end
        seen{end+1} = b; %#ok<AGROW>
        if strcmp(get_param(b, 'BlockType'), 'Step'), tf = true; return; end
        nin = numel(get_param(b, 'PortHandles').Inport);
        for i = 1:nin
            s = resolved_src(b, i);
            if ~isempty(s), nxt{end+1} = s; end %#ok<AGROW>
        end
    end
    frontier = nxt;
end
end

function [b, port] = unwrap_sink(b, mdl, port) %#ok<INUSD>
% The feedback source should be a real signal producer.  If it is a Scope or a
% Terminator, step back one block (the port becomes that block's output).
if nargin < 3 || isempty(port), port = 1; end
guard = 0;
while guard < 5
    guard = guard + 1;
    bt = get_param(b, 'BlockType');
    if ~any(strcmp(bt, {'Scope', 'Terminator', 'Display'}))
        return
    end
    [s, sp] = resolved_src_port(b, 1);
    if isempty(s), return; end
    b = s; port = sp;
end
end

% =========================================================================
%  reference
% =========================================================================
function [val, src] = reference_value(mdl, errSum, refIdx)
val = NaN; src = 'auto';
b = resolved_src(errSum, refIdx);
if isempty(b), return; end
stepVal = []; gains = [];
frontier = {b};
seen = {};
for d = 1:10
    if isempty(frontier), break; end
    nxt = {};
    for k = 1:numel(frontier)
        x = frontier{k};
        if any(strcmp(x, seen)), continue; end
        seen{end+1} = x; %#ok<AGROW>
        bt = get_param(x, 'BlockType');
        if strcmp(bt, 'Step')
            v = num_of(x, 'After');
            if ~isfinite(v), v = num_of(x, 'Amplitude'); end
            if isfinite(v), stepVal(end+1) = v; end %#ok<AGROW>
        elseif strcmp(bt, 'Gain')
            g = num_of(x, 'Gain');
            if isfinite(g), gains(end+1) = g; end %#ok<AGROW>
        elseif strcmp(bt, 'Constant')
            v = num_of(x, 'Value');
            if isfinite(v), stepVal(end+1) = v; end %#ok<AGROW>
        end
        nin = numel(get_param(x, 'PortHandles').Inport);
        for i = 1:nin
            s = resolved_src(x, i);
            if ~isempty(s), nxt{end+1} = s; end %#ok<AGROW>
        end
    end
    frontier = nxt;
end
if numel(stepVal) == 1 && ~isempty(gains)
    val = stepVal * prod(gains);
    src = sprintf('%s x %s', num2str(stepVal), mat2str(gains, 5));
elseif numel(stepVal) == 1
    val = stepVal;
    src = sprintf('%s', num2str(stepVal));
end
if isfinite(val), val = abs(val); end
end

% =========================================================================
%  controller
% =========================================================================
function c = pid_block_config(blk, mdl, D)
c = struct('kind', 'pid_block', 'block', strrep(blk, [mdl '/'], ''), ...
    'confidence', 0.95, 'form', 'Parallel', 'p', NaN, 'i', NaN, 'd', NaN);
src = safe_get(blk, 'ControllerParametersSource', 'internal');
if ~strcmpi(src, 'internal')
    c.kind = 'pid_block_external';
    D.warnings{end+1} = ['the PID block takes its gains from inputs ' ...
        '(ControllerParametersSource = external); this tuner writes mask ' ...
        'parameters, so it cannot tune that block'];
    return
end
form = safe_get(blk, 'Form', 'Parallel');
c.form = form;
c.p = num_of(blk, 'P');
c.i = num_of(blk, 'I');
c.d = num_of(blk, 'D');
c.controller = safe_get(blk, 'Controller', 'PID');
c.limit_output = strcmpi(safe_get(blk, 'LimitOutput', 'off'), 'on');
if c.limit_output
    c.u_max = num_of(blk, 'UpperSaturationLimit');
end
D.evidence{end+1} = sprintf('controller: masked PID block %s (form %s, %s)', ...
    c.block, form, c.controller);
% Ideal/Standard forms store I and D as *times*; a multiplicative step would
% invert their meaning, so the copy is switched to Parallel before tuning and
% the equivalent parallel gains are used from then on.
if ~strcmpi(form, 'Parallel') && all(isfinite([c.p c.i c.d]))
    D.warnings{end+1} = sprintf(['the PID block uses the %s form: I and D are ' ...
        'times there, so the gains were converted to the parallel form on the ' ...
        'working copy (the user model is untouched)'], form);
end
end

function [c, ok] = three_gain_config(mdl, blks, errSum, measure, opts, D)
ok = false;
c = struct('kind', 'three_gains');
region = forward_set(errSum, measure, 12);

gains = {};
for k = 1:numel(region)
    b = region{k};
    if ~strcmp(get_param(b, 'BlockType'), 'Gain'), continue; end
    v = num_of(b, 'Gain');
    if ~isfinite(v), continue; end               % matrix gains are not scalars
    if is_antwindup(b, errSum, measure), continue; end
    gains{end+1} = b; %#ok<AGROW>
end

if isempty(gains)
    D.code = 'no_gains';
    D.error = ['no scalar Gain blocks between the error junction and the ' ...
        'measured signal; the controller may be a masked subsystem, in which ' ...
        'case pass controller=pid_block and pid_block=<name>'];
    return
end

cls = cell(size(gains));
for k = 1:numel(gains)
    cls{k} = classify_gain(gains{k}, errSum, 10);
end

idxP = find(strcmp(cls, 'p'));
idxI = find(strcmp(cls, 'i'));
idxD = find(strcmp(cls, 'd'));

% When several blocks look proportional, prefer the one that is *closest* to
% the error junction: an anti-windup or feedforward gain is usually further
% down the chain, and the probe will confirm or reject the choice.
if numel(idxP) > 1
    d = cellfun(@(b) graph_distance(errSum, b, 12), gains(idxP));
    [~, order] = sort(d);
    idxP = idxP(order);
end

c.kp_block = rel(pick_one(gains, idxP), mdl);
c.ki_block = rel(pick_one(gains, idxI), mdl);
c.kd_block = rel(pick_one(gains, idxD), mdl);
c.candidates = cellfun(@(b) rel(b, mdl), gains, 'UniformOutput', false);
c.classes = cls;
c.confidence = 0.5;

D.evidence{end+1} = sprintf('controller region: %d blocks, %d scalar gains (%s)', ...
    numel(region), numel(gains), strjoin(cls, ', '));
for k = 1:numel(gains)
    D.evidence{end+1} = sprintf('  %-40s %-12s upstream: %s', ...
        rel(gains{k}, mdl), cls{k}, upstream_note(gains{k}, errSum));
end
for k = 1:numel(idxP)
    D.candidates{end+1} = struct('block', rel(gains{idxP(k)}, mdl), 'role', 'P?');
end
ok = true;
end

function tf = is_antwindup(blk, errSum, measure)
% A gain whose input comes out of a Saturate block is anti-windup feedback: it
% closes a loop *around the limiter*, not around the plant.
tf = false;
nin = numel(get_param(blk, 'PortHandles').Inport);
for i = 1:nin
    s = resolved_src(blk, i);
    if isempty(s), continue; end
    if strcmp(get_param(s, 'BlockType'), 'Saturate'), tf = true; return; end
    if any(strcmp(get_param(s, 'BlockType'), {'Sum', 'Gain'})) && ...
            reaches_block(s, 'Saturate', 3)
        tf = true; return
    end
end
end

function tf = reaches_block(blk, type, depth)
tf = false;
if depth <= 0, return; end
nin = numel(get_param(blk, 'PortHandles').Inport);
for i = 1:nin
    s = resolved_src(blk, i);
    if isempty(s), continue; end
    if strcmp(get_param(s, 'BlockType'), type), tf = true; return; end
    if reaches_block(s, type, depth - 1), tf = true; return; end
end
end

function role = classify_gain(blk, errSum, maxDepth)
role = 'p';
if has_type_upstream(blk, 'Integrator', maxDepth), role = 'i'; return; end
if has_type_upstream(blk, 'Derivative', maxDepth), role = 'd'; return; end
if has_type_upstream(blk, 'DiscreteIntegrator', maxDepth), role = 'i'; return; end
if has_type_upstream(blk, 'DiscreteDerivative', maxDepth), role = 'd'; return; end
% a Transfer Fcn of the form 1/s is an integrator drawn as a filter
if has_integrator_filter_upstream(blk, maxDepth), role = 'i'; end
end

function tf = has_type_upstream(blk, type, depth)
tf = false;
if depth <= 0, return; end
nin = numel(get_param(blk, 'PortHandles').Inport);
for i = 1:nin
    s = resolved_src(blk, i);
    if isempty(s), continue; end
    bt = get_param(s, 'BlockType');
    if strcmp(bt, type), tf = true; return; end
    if strcmp(bt, 'Sum') || strcmp(bt, 'Gain') || strcmp(bt, 'TransferFcn')
        if has_type_upstream(s, type, depth - 1), tf = true; return; end
    end
end
end

function tf = has_integrator_filter_upstream(blk, depth)
tf = false;
if depth <= 0, return; end
nin = numel(get_param(blk, 'PortHandles').Inport);
for i = 1:nin
    s = resolved_src(blk, i);
    if isempty(s), continue; end
    if strcmp(get_param(s, 'BlockType'), 'TransferFcn')
        den = safe_get(s, 'Denominator', '');
        if ~isempty(regexp(den, '^\s*\[\s*1\s+0\s*\]\s*$', 'once')) || ...
                ~isempty(regexp(den, '^\s*\[\s*1\s+0\s+0', 'once'))
            tf = true; return
        end
    end
    if has_integrator_filter_upstream(s, depth - 1), tf = true; return; end
end
end

function note = upstream_note(blk, errSum)
note = '';
nin = numel(get_param(blk, 'PortHandles').Inport);
for i = 1:nin
    s = resolved_src(blk, i);
    if isempty(s), continue; end
    note = [note get_param(s, 'BlockType') ' ']; %#ok<AGROW>
end
note = strtrim(note);
end

function d = graph_distance(from, to, maxDepth)
% Hop count between two blocks, or maxDepth+1 when not reachable forward.
if isequal(from, to), d = 0; return; end
frontier = {from};
seen = {from};
for d = 1:maxDepth
    nxt = {};
    for k = 1:numel(frontier)
        ds = resolved_dsts(frontier{k});
        for j = 1:numel(ds)
            if isequal(ds{j}, to), return; end
            if any(strcmp(ds{j}, seen)), continue; end
            seen{end+1} = ds{j}; %#ok<AGROW>
            nxt{end+1} = ds{j}; %#ok<AGROW>
        end
    end
    frontier = nxt;
    if isempty(frontier), break; end
end
d = maxDepth + 1;
end

% =========================================================================
%  probe
% =========================================================================
function D = probe_candidates(mdl, D, measure, mport, stopTime, refCmd, opts)
c = D.controller;
picked = {}; role = {};
if ~isempty(c.kp_block), picked{end+1} = resolve_path(mdl, c.kp_block); role{end+1} = 'kp'; end
if ~isempty(c.ki_block), picked{end+1} = resolve_path(mdl, c.ki_block); role{end+1} = 'ki'; end
if ~isempty(c.kd_block), picked{end+1} = resolve_path(mdl, c.kd_block); role{end+1} = 'kd'; end
if isempty(picked), return; end
D.probe = struct('block', {role}, 'effect', {nan});

scope = 'jev_measure';
if ~jev_instrument(mdl, measure, scope, mport)
    D.warnings{end+1} = 'could not attach a logging scope; the probe is skipped';
    return
end
D.cfg.measure_scope = scope;
D.cfg.instrument_block = D.measure_block;
D.cfg.instrument_port = mport;

[t0, y0] = simulate(mdl, stopTime, scope);
if isempty(y0)
    D.warnings{end+1} = 'the model did not run; check StopTime and workspace variables';
    D.code = 'sim_failed';
    return
end

if ~isfinite(refCmd)
    tail = y0(max(1, round(0.8 * numel(y0))):end);
    refCmd = abs(median(tail));
    D.reference = refCmd;
    D.reference_source = 'measured from a probe run (median of the last 20 %)';
    D.cfg.ref_source = refCmd;
    D.warnings{end+1} = sprintf(['the reference was inferred from the steady ' ...
        'state (%.4g); pass ref_source if the loop does not reach it'], refCmd);
end

base = norm(y0 - mean(y0)) + eps;
effects = nan(size(picked));
for k = 1:numel(picked)
    v = num_of(picked{k}, 'Gain');
    if ~isfinite(v) || abs(v) < 1e-12, effects(k) = 0; continue; end
    set_param(picked{k}, 'Gain', num2str(2 * v));
    [t, y] = simulate(mdl, stopTime, scope);
    set_param(picked{k}, 'Gain', num2str(v));
    if isempty(y), effects(k) = inf; continue; end
    yi = interp1(t, y, t0, 'linear', 'extrap');
    effects(k) = norm(yi - y0) / base;
end
D.effects = effects;
D.probe = struct('role', role, 'block', picked, 'effect', num2cell(effects));

for k = 1:numel(picked)
    D.evidence{end+1} = sprintf('  probe: %-32s x2 changes the response by %.3f', ...
        strrep(picked{k}, [mdl '/'], ''), effects(k));
end

% A gain that does nothing is not a controller gain.  Drop it and say so.
for k = 1:numel(picked)
    if effects(k) < 0.02
        D.warnings{end+1} = sprintf(['%s does not affect the response when ' ...
            'doubled (effect %.3f): it is not part of this loop'], ...
            strrep(picked{k}, [mdl '/'], ''), effects(k));
        c = drop_role(c, role{k});
    end
end
D.controller = c;
D.cfg = rmfield_if(D.cfg, {'kp_block', 'ki_block', 'kd_block'});
D.cfg = build_cfg_from(mdl, D.cfg, c);
end

function c = drop_role(c, role)
switch role
    case 'kp', c.kp_block = '';
    case 'ki', c.ki_block = '';
    case 'kd', c.kd_block = '';
end
end

function s = rmfield_if(s, fields)
for k = 1:numel(fields)
    if isfield(s, fields{k}), s = rmfield(s, fields{k}); end
end
end

function c = build_cfg_from(mdl, c, controller)
if strcmp(controller.kind, 'pid_block')
    c.controller = 'pid_block';
    c.pid_block = controller.block;
    return
end
c.controller = 'gains';
if ~isempty(controller.kp_block), c.kp_block = controller.kp_block; end
if ~isempty(controller.ki_block), c.ki_block = controller.ki_block; end
if ~isempty(controller.kd_block), c.kd_block = controller.kd_block; end
end

function [t, y] = simulate(mdl, stopTime, scope)
% One closed-loop run.  The solver picks its own steps, so the time vector
% changes whenever a gain changes: callers resample before comparing.
t = []; y = [];
try
    out = sim(mdl, 'StopTime', num2str(stopTime), 'FastRestart', 'off');
    if isprop(out, scope) || isfield(out, scope)
        ds = out.(scope);
        e = ds.getElement(1);
        y = e.Values.Data(:);
        t = e.Values.Time(:);
    end
catch err
    fprintf('[discover] sim failed: %s\n', err.message);
end
end

function tf = block_exists(path)
tf = false;
try
    h = get_param(path, 'Handle');
    tf = ~isempty(h);
catch
end
end

% =========================================================================
%  misc
% =========================================================================
function c = build_cfg(mdl, D, controller, measure, refCmd, stopTime) %#ok<INUSD>
c = struct('model', D.model, 'stop_time', stopTime, ...
    'measure_scope', 'jev_measure', ...
    'instrument_block', strrep(measure, [mdl '/'], ''), ...
    'instrument_port', D.measure_port);
if strcmp(controller.kind, 'pid_block')
    c.controller = 'pid_block';
    c.pid_block = controller.block;
elseif strcmp(controller.kind, 'three_gains')
    c.controller = 'gains';
    if ~isempty(controller.kp_block), c.kp_block = controller.kp_block; end
    if ~isempty(controller.ki_block), c.ki_block = controller.ki_block; end
    if ~isempty(controller.kd_block), c.kd_block = controller.kd_block; end
end
if ~isempty(refCmd) && isfinite(refCmd)
    c.ref_source = refCmd;
end
end

function conf = verdict(D, controller) %#ok<INUSD>
conf = 'low';
if strcmp(controller.kind, 'pid_block')
    conf = 'high';
    return
end
if ~strcmp(controller.kind, 'three_gains'), return; end
hasP = ~isempty(controller.kp_block);
hasI = ~isempty(controller.ki_block);
hasD = ~isempty(controller.kd_block);
if hasP && hasI && hasD
    conf = 'high';
elseif hasP || hasI
    % a P-only or PI-only loop is a legitimate answer, just less authority
    conf = 'medium';
end
if isfield(controller, 'classes') && sum(strcmp(controller.classes, 'p')) > 1
    conf = 'medium';
end
end

function st = model_stop_time(mdl, D)
st = num_of(mdl, 'StopTime');
if ~isfinite(st) || st <= 0
    st = 10;
    D.warnings{end+1} = 'StopTime is not a number; assuming 10 s';
end
end

function n = names(blocks, mdl)
n = cellfun(@(b) strrep(b, [mdl '/'], ''), blocks, 'UniformOutput', false);
end

function p = rel(blk, mdl)
if isempty(blk), p = ''; return; end
p = strrep(blk, [mdl '/'], '');
end

function p = resolve_path(mdl, relname)
if isempty(relname), p = ''; return; end
p = [mdl '/' relname];
end

function v = num_of(blk, param)
% Model parameters are often expressions (pi/180, 2*Kp, Ts), not literals, so
% str2double would silently return NaN.  str2num evaluates in the base
% workspace, which is exactly the scope Simulink itself uses.
v = NaN;
s = safe_get(blk, param, '');
if isempty(s), return; end
if ~ischar(s), v = s; return; end
v = str2num(s); %#ok<ST2NM>
if ~isscalar(v) || ~isnumeric(v), v = NaN; end
end

function v = safe_get(blk, param, fallback)
try
    v = get_param(blk, param);
catch
    v = fallback;
end
if isempty(v), v = fallback; end
end

function b = pick_one(list, idx)
% a ternary lambda would evaluate list{idx(1)} even when idx is empty
if isempty(idx), b = ''; else, b = list{idx(1)}; end
end

function opts = with_defaults(opts)
d = struct('probe', true, 'work_dir', fullfile(tempdir, 'jev_discover'), 'verbose', false);
f = fieldnames(d);
for k = 1:numel(f)
    if ~isfield(opts, f{k}), opts.(f{k}) = d.(f{k}); end
end
end

function safe_close(mdl)
try
    if ~isempty(find_system('SearchDepth', 0, 'Type', 'block_diagram', 'Name', mdl))
        try, set_param(mdl, 'FastRestart', 'off'); catch, end
        close_system(mdl, 0);
    end
catch
end
end
