function D = jev_decode(W, out, stepGain)
%JEV_DECODE Calibrated single-state typed decision, shared by runtime and tests.
% D.proposed retains the pre-abstention proposal. D.held means the policy
% vetoed that axis, not merely that a confident choice selected no change.
if nargin < 3, stepGain = 1; end
validateattributes(stepGain, {'numeric'}, {'scalar', 'finite', 'nonnegative'});
temp = field_default(W, 'temperature', ones(1, 3));
temp = double(temp(:).');
validateattributes(temp, {'numeric'}, {'size', [1 3], 'finite', 'positive'});
tauAct = field_default(W, 'tau_act', 0);
tauEsc = field_default(W, 'tau_esc', 0);
tauNoul = field_default(W, 'tau_noul', 0);
validateattributes([tauAct tauEsc tauNoul], {'numeric'}, ...
    {'size', [1 3], 'finite', '>=', 0, '<=', 1});
assert(tauEsc <= tauAct, 'jev:policy', 'tau_esc must not exceed tau_act');
d = field_default(W, 'decode_deltas', log10([.5 .7 .87 1 1.15 1.43 2]));
d = double(d(:).');
maxStep = field_default(W, 'decode_max_step', .32);
validateattributes(d, {'numeric'}, {'size', [1 7], 'finite'});
validateattributes(maxStep, {'numeric'}, {'scalar', 'finite', 'positive'});
validateattributes(out.choice, {'numeric'}, {'size', [7 3], 'finite'});
validateattributes(out.score, {'numeric'}, {'numel', 5, 'finite'});
validateattributes(out.noul, {'numeric'}, {'scalar', 'finite'});
% Center before division: finite logits and tiny positive T must stay valid.
z = double(out.choice);
p = exp((z - max(z, [], 1)) ./ temp);
p = p ./ sum(p, 1);
score = exp(double(out.score(:)) - max(double(out.score(:))));
D.choice = p; D.score = score ./ sum(score);
D.noul = 1 / (1 + exp(-double(out.noul)));
D.confidence = max(p, [], 1);
mu = d * p;
variance = max((d.^2) * p - mu.^2, 0);
D.proposed = min(max(stepGain * mu ./ (1 + variance / max(var(d, 1), 1e-6)), ...
    -maxStep), maxStep);
low = D.confidence < tauAct;
D.held = low | (D.noul < tauNoul);
D.escalate = (D.confidence < tauEsc) & D.held;
D.reason = zeros(1, 3);
D.reason(low) = 1; D.reason(D.escalate) = 2;
D.conformal_applied = logical(field_default(W, 'cp_enabled', false));
D.conformal_set = false(7, 3); D.set_size = zeros(1, 3);
D.conformal_mode = 'off';
D.conformal_would_hold = false(1, 3); D.conformal_reason = zeros(1, 3);
if D.conformal_applied
    D.conformal_mode = char(field_default(W, 'cp_mode', 'monitor'));
    if ~any(strcmp(D.conformal_mode, {'monitor', 'hard_hold'}))
        error('jev:cp_mode', 'cp_mode must be monitor or hard_hold');
    end
    qhat = double(W.cp_qhat(:).');
    validateattributes(qhat, {'numeric'}, {'size', [1 3], 'finite', '>=', 0, '<=', 1});
    validateattributes(W.cp_k_max, {'numeric'}, {'scalar', 'integer', 'positive', 'finite'});
    validateattributes(W.cp_alpha, {'numeric'}, {'scalar', 'finite', '>', 0, '<', 1});
    % Keep the full TS distribution for the expected-value proposal. The CP
    % set is never a truncated/renormalized p. Monitor only records evidence.
    D.conformal_set = (1 - p) <= qhat;
    D.set_size = sum(D.conformal_set, 1);
    mixed = any(D.conformal_set & (d.' > 0), 1) & ...
        any(D.conformal_set & (d.' < 0), 1);
    empty = D.set_size == 0;
    oversized = D.set_size > W.cp_k_max;
    reject = empty | oversized | mixed;
    D.conformal_would_hold = reject;
    D.conformal_reason(mixed) = 6;
    D.conformal_reason(oversized) = 5;
    D.conformal_reason(empty) = 4;
    if strcmp(D.conformal_mode, 'hard_hold')
        D.held = D.held | reject;
        D.escalate = D.escalate | reject;
        D.reason(reject) = D.conformal_reason(reject);
    end
end
if D.noul < tauNoul, D.reason(:) = 3; end
D.step = D.proposed; D.step(D.held) = 0;
end

function v = field_default(s, name, fallback)
if isfield(s, name), v = s.(name); else, v = fallback; end
end
