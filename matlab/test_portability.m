function R = test_portability(outputFile)
%TEST_PORTABILITY Exercise the production decoder with the shared C/Python vectors.
root = fileparts(fileparts(mfilename('fullpath')));
W = load(fullfile(root, 'models', 'jev_head_weights.mat'));
V = jsondecode(fileread(fullfile(root, 'c', 'test_vectors.json')));
assert(V.schema_version == 4);
assert(strcmp(W.model_sha256, V.model_sha256));
assert(strcmp(W.calibration_sha256, V.calibration_sha256));
assert(isequal(W.temperature(:), V.configuration.temperature(:)));
assert(isequal(W.decode_deltas(:), V.configuration.deltas(:)));
assert(W.tau_act == V.configuration.policy.tau_act);
assert(W.tau_esc == V.configuration.policy.tau_esc);
assert(W.tau_noul == V.configuration.policy.tau_noul);
assert(W.cp_enabled == V.configuration.conformal.enabled);
assert(isequal(W.cp_qhat(:), V.configuration.conformal.qhat_per_axis(:)));
assert(W.cp_k_max == V.configuration.conformal.k_max);
assert(W.cp_alpha == V.configuration.conformal.alpha);
assert(strcmp(W.cp_mode, V.configuration.conformal.mode));
names = {'choice_logits','choice_probs','step','score_logits','score_probs','noul_logit','noul_probability','proposed'};
worst = zeros(1, numel(names));
outputs = struct([]);
for k = 1:numel(V.cases)
    sample = V.cases(k);
    out = jev_head_forward(W, sample.feats(:), sample.curves);
    D = jev_decode(W, out);
    errors = [max(abs(out.choice.' - sample.logits), [], 'all'), ...
        max(abs(D.choice.' - sample.probs), [], 'all'), ...
        max(abs(D.step(:) - sample.step(:))), ...
        max(abs(out.score(:)-sample.score_logits(:))), ...
        max(abs(D.score(:)-sample.score_probs(:))), ...
        abs(out.noul-sample.noul_logit), abs(D.noul-sample.noul), ...
        max(abs(D.proposed(:)-sample.proposed(:)))];
    assert(all(isfinite(errors)));
    worst = max(worst, errors);
    outputs(k).index = k - 1;
    outputs(k).choice_logits = out.choice.';
    outputs(k).choice_probs = D.choice.';
    outputs(k).score_logits = out.score(:).'; outputs(k).score_probs = D.score(:).';
    outputs(k).noul_logit = out.noul; outputs(k).noul = D.noul;
    outputs(k).step = D.step; outputs(k).held = D.held;
    outputs(k).escalate = D.escalate; outputs(k).reason = D.reason;
    outputs(k).proposed = D.proposed; outputs(k).set_size = D.set_size;
    outputs(k).conformal_set = D.conformal_set.';
    outputs(k).conformal_applied = D.conformal_applied;
    outputs(k).conformal_mode = D.conformal_mode;
    outputs(k).conformal_would_hold = D.conformal_would_hold;
    outputs(k).conformal_reason = D.conformal_reason;
    outputs(k).absolute_errors = cell2struct(num2cell(errors), names, 2);
    assert(isequal(D.held(:), sample.held(:)));
    assert(isequal(D.escalate(:), sample.escalate(:)));
    assert(isequal(D.reason(:), sample.reason(:)));
    assert(isequal(D.set_size(:), sample.set_size(:)));
    assert(isequal(D.conformal_set.', sample.conformal_set));
    assert(strcmp(D.conformal_mode, sample.conformal_mode));
    assert(isequal(D.conformal_would_hold(:), sample.conformal_would_hold(:)));
    assert(isequal(D.conformal_reason(:), sample.conformal_reason(:)));
    assert(all(isfinite([D.step D.proposed D.confidence D.noul])));
end
assert(all(worst([1 4 6]) < V.tolerance.logits));
assert(all(worst([2 5 7]) < V.tolerance.probs) && all(worst([3 8]) < V.tolerance.step));
policyOutputs = repmat(struct('name', '', 'step', [], 'held', [], 'escalate', [], ...
    'reason', [], 'conformal_mode', '', 'conformal_set', [], ...
    'conformal_would_hold', [], 'conformal_reason', []), 1, numel(V.policy_cases));
for k = 1:numel(V.policy_cases)
    sample = V.policy_cases(k);
    policyW = W; policyW.temperature = ones(1, 3);
    policyW.tau_act = sample.policy.tau_act;
    policyW.tau_esc = sample.policy.tau_esc;
    policyW.tau_noul = sample.policy.tau_noul;
    policyW.cp_enabled = sample.conformal.enabled;
    policyW.cp_qhat = sample.conformal.qhat_per_axis;
    policyW.cp_k_max = sample.conformal.k_max;
    policyW.cp_alpha = sample.conformal.alpha;
    policyW.cp_mode = sample.conformal.mode;
    % Approximate zero probabilities with the smallest normal finite double.
    out.choice = log(max(sample.probs.', realmin));
    out.score = log(max(sample.score_probs(:), realmin));
    if sample.noul == 1, out.noul = 1000;
    else, out.noul = log(sample.noul / (1-sample.noul)); end
    D = jev_decode(policyW, out);
    assert(max(abs(D.step(:) - sample.step(:))) < V.tolerance.step);
    assert(isequal(D.held(:), sample.held(:)), sample.name);
    assert(isequal(D.escalate(:), sample.escalate(:)), sample.name);
    assert(isequal(D.reason(:), sample.reason(:)), sample.name);
    assert(isequal(D.set_size(:), sample.set_size(:)), sample.name);
    assert(isequal(D.conformal_set.', sample.conformal_set), sample.name);
    assert(strcmp(D.conformal_mode, sample.conformal_mode), sample.name);
    assert(isequal(D.conformal_would_hold(:), sample.conformal_would_hold(:)), sample.name);
    assert(isequal(D.conformal_reason(:), sample.conformal_reason(:)), sample.name);
    assert(max(abs(D.proposed(:) - sample.proposed(:))) < V.tolerance.step);
    policyOutputs(k).name = sample.name;
    policyOutputs(k).step = D.step;
    policyOutputs(k).held = D.held;
    policyOutputs(k).escalate = D.escalate;
    policyOutputs(k).reason = D.reason;
    policyOutputs(k).conformal_mode = D.conformal_mode;
    policyOutputs(k).conformal_set = D.conformal_set.';
    policyOutputs(k).conformal_would_hold = D.conformal_would_hold;
    policyOutputs(k).conformal_reason = D.conformal_reason;
end
bad = W; bad.temperature(1) = 0;
must_reject(@() jev_decode(bad, out));
badOut = out; badOut.choice(1) = NaN;
must_reject(@() jev_decode(W, badOut));
bad = W; bad.cp_enabled = 1; bad.cp_qhat(1) = NaN;
must_reject(@() jev_decode(bad, out));
bad = W; bad.cp_enabled = 1; bad.cp_k_max = 0;
must_reject(@() jev_decode(bad, out));
bad = W; bad.cp_enabled = 1; bad.cp_mode = 'invalid';
must_reject(@() jev_decode(bad, out));
R = struct('ok', true, 'cases', numel(V.cases), 'policy_cases', numel(V.policy_cases), ...
    'schema_version', 3, 'model_sha256', V.model_sha256, ...
    'hash_normalization', 'CRLF to LF for .m/.json; binary files byte-exact', ...
    'configuration_sha256', V.configuration_sha256, ...
    'calibration_sha256', V.calibration_sha256, 'configuration', V.configuration, ...
    'vectors_sha256', file_hash(fullfile(root, 'c', 'test_vectors.json')), ...
    'weights_mat_sha256', file_hash(fullfile(root, 'models', 'jev_head_weights.mat')), ...
    'decoder_sha256', file_hash(fullfile(root, 'matlab', 'jev_decode.m')), ...
    'forward_sha256', file_hash(fullfile(root, 'matlab', 'jev_head_forward.m')), ...
    'max_errors', cell2struct(num2cell(worst), names, 2), ...
    'tolerance', V.tolerance, 'outputs', outputs, 'policy_outputs', policyOutputs, ...
    'matlab_release', version, ...
    'command', 'test_portability(''research/results/matlab_parity_v0100.json'')');
if nargin >= 1 && ~isempty(outputFile)
    fid = fopen(outputFile, 'w'); assert(fid >= 0, 'cannot write parity result');
    cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s\n', jsonencode(R, 'PrettyPrint', true));
end
disp(jsonencode(rmfield(R, {'outputs', 'policy_outputs'})));
end

function h = file_hash(path)
fid = fopen(path, 'rb'); assert(fid >= 0);
bytes = fread(fid, Inf, '*uint8'); fclose(fid);
[~, ~, ext] = fileparts(path);
if any(strcmpi(ext, {'.m', '.json'}))
    bytes(find(bytes(1:end-1) == 13 & bytes(2:end) == 10)) = []; %#ok<FNDSB>
end
digest = java.security.MessageDigest.getInstance('SHA-256');
digest.update(typecast(bytes, 'int8'));
h = lower(reshape(dec2hex(typecast(digest.digest(), 'uint8'), 2).', 1, []));
end

function must_reject(f)
rejected = false;
try, f(); catch, rejected = true; end
assert(rejected, 'invalid numerical input was accepted');
end
