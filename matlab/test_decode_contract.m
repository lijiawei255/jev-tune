function R = test_decode_contract()
%TEST_DECODE_CONTRACT Extreme finite logits and invalid input must be handled.
% Real decoder calls, independent of Simulink setup or generated model names.
W = struct('temperature', [realmin/2 realmin/2 realmin/2]);
out = struct('choice', zeros(7, 3), 'score', zeros(5, 1), 'noul', 0);
out.choice(1, :) = 1;
D = jev_decode(W, out);
assert(all(isfinite(D.choice(:))) && all(isfinite(D.step)));
assert(all(D.choice(1, :) == 1) && all(all(D.choice(2:end, :) == 0)));
out.choice(:) = realmax;
D = jev_decode(W, out);
assert(max(abs(D.choice(:) - 1/7)) < 1e-15);
out.choice(:) = -realmax; out.choice(1, :) = realmax;
D = jev_decode(W, out);
assert(all(D.choice(1, :) == 1) && all(isfinite(D.step)));
rejected = 0;
for badT = [0 -1 NaN Inf -Inf]
    invalid = W; invalid.temperature = [badT 1 1];
    failed = false;
    try
        jev_decode(invalid, out);
    catch
        failed = true;
    end
    assert(failed); rejected = rejected + 1;
end
W.temperature = [1 1 1];
for field = {'choice', 'score', 'noul'}
    invalid = out; invalid.(field{1})(1) = NaN;
    failed = false;
    try
        jev_decode(W, invalid);
    catch
        failed = true;
    end
    assert(failed); rejected = rejected + 1;
end
R = struct('ok', true, 'tiny_positive_temperature', realmin/2, ...
    'extreme_logit_cases', 3, 'invalid_cases_rejected', rejected);
end
