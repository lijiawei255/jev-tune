function out = jev_head_forward(W, feats, curves)
%JEV_HEAD_FORWARD  Hand-written forward pass of the trained Jev head.
%
%   out = jev_head_forward(W, feats, curves)
%
%   W      : struct of weights from models/jev_head_weights.mat
%   feats  : 20-by-N (or N-by-20), state features
%   curves : N-by-2-by-64 or 2-by-64-by-N, normalised traces
%
%   out.choice : K-by-3-by-N logits   (Kp, Ki, Kd)
%   out.score  : 5-by-N logits
%   out.noul   : 1-by-N logit
%
%   Plain MATLAB: no Deep Learning Toolbox, no Python, no IPC. This is what
%   lets the Simulink loop spend microseconds on the decision.

feats = double(feats);
if size(feats, 1) ~= 20 && size(feats, 2) == 20
    feats = feats.';
end
N = size(feats, 2);

curves = double(curves);
if ndims(curves) == 3 && size(curves, 2) == 2
    curves = permute(curves, [2 3 1]);          % (N,2,64) -> (2,64,N)
end
if ndims(curves) < 3
    curves = reshape(curves, size(curves, 1), size(curves, 2), 1);
end

% ---------------------------------------------------------------- curve branch
c1 = max(conv1d_s2(curves, W.cv1_w, W.cv1_b, 2, 2), 0);
c2 = max(conv1d_s2(c1, W.cv2_w, W.cv2_b, 2, 2), 0);
gap = reshape(mean(c2, 2), [], N);              % 32 x N

% ---------------------------------------------------------------- feature branch
h = max(W.mlp1_w * feats + W.mlp1_b(:), 0);
h = max(W.mlp2_w * h + W.mlp2_b(:), 0);            % 64 x N

% ---------------------------------------------------------------- trunk
z = [gap; h];
z = max(W.tr1_w * z + W.tr1_b(:), 0);
z = max(W.tr2_w * z + W.tr2_b(:), 0);              % 128 x N

% ---------------------------------------------------------------- heads
K = size(W.ch0_w, 1);
choice = zeros(K, 3, N);
choice(:, 1, :) = reshape(W.ch0_w * z + W.ch0_b(:), K, 1, N);
choice(:, 2, :) = reshape(W.ch1_w * z + W.ch1_b(:), K, 1, N);
choice(:, 3, :) = reshape(W.ch2_w * z + W.ch2_b(:), K, 1, N);

out.choice = choice;
out.score = W.score_w * z + W.score_b(:);
out.noul = W.noul_w * z + W.noul_b(:);
end

% --------------------------------------------------------------------------- %
function y = conv1d_s2(x, W, b, stride, pad)
% x: (Cin,L,N), W: (Cout,Cin,K) -> y: (Cout,Lout,N)
[cin, L, N] = size(x);
[cout, ~, K] = size(W);
Lout = floor((L + 2 * pad - K) / stride) + 1;
y = zeros(cout, Lout, N);
for i = 1:Lout
    base = (i - 1) * stride - pad;
    for k = 1:K
        j = base + k;
        if j >= 1 && j <= L
            xk = reshape(x(:, j, :), cin, N);
            y(:, i, :) = y(:, i, :) + reshape(W(:, :, k) * xk, cout, 1, N);
        end
    end
end
y = y + reshape(b, cout, 1, 1);
end
