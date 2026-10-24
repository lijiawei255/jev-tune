"""Numerical mutations must fail independent certificates, without hash tricks."""
import copy
import importlib.util
import math
from decimal import localcontext
from pathlib import Path
import numpy as np
import pytest
from jev_tune.primitives import softmax, calibrate_temperature, fit_split_conformal

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("decimal_numeric_audit_test", ROOT / "scripts/calibration_numeric_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
trace_spec = importlib.util.spec_from_file_location("audit_original_trace_tests", ROOT / "scripts/51_diagnose_calibration_runtime.py")
trace_module = importlib.util.module_from_spec(trace_spec)
trace_spec.loader.exec_module(trace_module)


def original_trace(logits, labels):
    temperature, trace = trace_module.golden_trace(logits, labels)
    assert temperature == calibrate_temperature(logits, labels)
    return trace


def example_model():
    model = {"dtype": "float64", "normalization_mean": [0.] * 16, "normalization_scale": [1.] * 16, "state_dict": {}}
    for layer, n_in, n_out in [(0, 16, 32), (2, 32, 32), (4, 32, 10)]:
        model["state_dict"][f"net.{layer}.weight"] = [[.001*(i+j+1) for j in range(n_in)] for i in range(n_out)]
        model["state_dict"][f"net.{layer}.bias"] = [.003*(i+1) for i in range(n_out)]
    return model


def forward(model, features):
    values = [(x-m)/s for x, m, s in zip(features, model["normalization_mean"], model["normalization_scale"])]
    for layer in (0, 2, 4):
        values = [sum(w*x for w, x in zip(row, values))+bias for row, bias in zip(model["state_dict"][f"net.{layer}.weight"], model["state_dict"][f"net.{layer}.bias"])]
        if layer != 4: values = [math.tanh(x) for x in values]
    return np.array(values).reshape(2, 5)


def test_real_forward_softmax_envelopes_accept_binary64_without_bitwise_claim():
    model, features = example_model(), [.01*(i+1) for i in range(16)]
    recorded = forward(model, features)
    certificate = audit.audit_forward(model, features, recorded)
    probabilities = softmax(recorded, temperature=np.array([.7, 1.2])[:, None])
    checked = audit.audit_softmax(certificate["logits"], [.7, 1.2], probabilities, certificate["logit_intervals"])
    assert not checked["bitwise_replay_proven"] and not certificate["bitwise_replay_proven"]
    assert "faithful" in checked["assumptions"]


def test_every_feature_and_normalizer_mutation_is_numerically_rejected():
    model, features = example_model(), [.01*(i+1) for i in range(16)]
    recorded = forward(model, features)
    for axis in range(16):
        changed = features.copy(); changed[axis] += .25
        with pytest.raises(ValueError, match="recorded logit"):
            audit.audit_forward(model, changed, recorded)
    for key in ("normalization_mean", "normalization_scale"):
        changed = copy.deepcopy(model); changed[key][0] += .25
        with pytest.raises(ValueError, match="recorded logit"):
            audit.audit_forward(changed, features, recorded)


@pytest.mark.parametrize("layer", [0, 2, 4])
@pytest.mark.parametrize("kind", ["weight", "bias"])
def test_all_layer_weight_and_bias_groups_mutation_rejected(layer, kind):
    model, features = example_model(), [.01*(i+1) for i in range(16)]
    recorded = forward(model, features)
    changed = copy.deepcopy(model)
    key = f"net.{layer}.{kind}"
    if kind == "weight":
        changed["state_dict"][key] = [[x+.1 for x in row] for row in changed["state_dict"][key]]
    else: changed["state_dict"][key] = [x+.1 for x in changed["state_dict"][key]]
    with pytest.raises(ValueError, match="recorded logit"):
        audit.audit_forward(changed, features, recorded)


def test_each_probability_and_temperature_mutation_rejected():
    logits = [[.1, .2, .3, .4, .5], [.5, .4, .3, .2, .1]]
    recorded = softmax(logits)
    for axis in range(2):
        for option in range(5):
            changed = recorded.copy(); changed[axis, option] += .001
            with pytest.raises(ValueError, match="recorded probability"):
                audit.audit_softmax(logits, [1., 1.], changed)
        temperatures = [1., 1.]; temperatures[axis] = 2.
        with pytest.raises(ValueError, match="recorded probability"):
            audit.audit_softmax(logits, temperatures, recorded)


def test_original_temperature_loss_certificate_and_large_mutation():
    logits = np.array([[.01, 0.], [-.01, 0.]])
    labels = np.array([0, 0])
    original = calibrate_temperature(logits, labels)
    trace = original_trace(logits, labels)
    result = audit.audit_temperature(logits, labels, original, golden_trace=trace)
    assert result["ok"] and len(result["golden_branch_allowances"]) == 60
    assert audit.D(result["objective_gap_upper"]) <= audit.D(result["golden_loss_rounding_budget"])
    with pytest.raises(ValueError, match="temperature"):
        audit.audit_temperature(logits, labels, .05, golden_trace=trace)


def test_active_clip_refuses_a_smooth_certificate():
    logits, labels = np.array([[0., 100.], [0., 100.]]), np.array([0, 0])
    with pytest.raises(ValueError, match="clip"):
        audit.audit_temperature(logits, labels, 1., golden_trace=original_trace(logits, labels))


def test_clipped_tail_can_be_proven_worse_without_ignoring_it():
    logits = np.array([[4., 0.], [-4., 0.]])
    labels = np.array([0, 0])
    original = calibrate_temperature(logits, labels)
    result = audit.audit_temperature(logits, labels, original, golden_trace=original_trace(logits, labels))
    tail = result["clipped_tail_certificate"]
    assert tail and tail["intervals_proven"] > 0
    assert audit.D(tail["minimum_certified_loss_lower_bound"]) >= audit.D(tail["required_loss_lower_bound"])


def test_strict_cp_rank_and_exact_complete_sets_and_q_mutation():
    rng = np.random.default_rng(93)
    probabilities = softmax(rng.normal(size=(20, 2, 5)))
    labels = rng.integers(0, 5, size=(20, 2))
    fitted = fit_split_conformal(probabilities, labels)
    q = fitted.qhat_per_axis.tolist()
    sets = ((1-probabilities) <= fitted.qhat_per_axis[None, :, None]).tolist()
    result = audit.audit_cp(probabilities, labels, q, recorded_sets=sets)
    assert result["rank"] == fitted.quantile_rank and result["sets"] == sets
    assert result["ambiguous_boundary_count"] > 0 and not result["bitwise_replay_proven"]
    for axis in range(2):
        bad = q.copy(); bad[axis] += .001
        with pytest.raises(ValueError, match="strict rank"):
            audit.audit_cp(probabilities, labels, bad)
    wrong = copy.deepcopy(sets); wrong[0][0][0] = not wrong[0][0][0]
    with pytest.raises(ValueError, match="full conformal sets"):
        audit.audit_cp(probabilities, labels, q, recorded_sets=wrong)


def test_decimal_calling_context_cannot_change_public_envelopes():
    model, features = example_model(), [.01*(i+1) for i in range(16)]
    recorded = forward(model, features)
    results = []
    for precision in (7, 28, 110):
        with localcontext() as ctx:
            ctx.prec = precision
            checked = audit.audit_forward(model, features, recorded)
            probabilities = audit.audit_softmax(checked["logits"], [1., 1.], logit_intervals=checked["logit_intervals"])
            results.append((checked["logit_intervals"], probabilities["probability_intervals"], audit.gamma(33)))
    assert results[0] == results[1] == results[2]


def test_cross_zero_tanh_and_subnormal_rounding_are_outward():
    with localcontext() as ctx:
        ctx.prec = 7
        values = audit.tanh_interval(audit.Interval("-1e-35", "2e-35"))
        assert values.lo < 0 < values.hi
        assert values.contains("-1e-35") and values.contains("1.99999999999999999999999999999999999e-35")
        smallest = math.ulp(0.)
        error = audit.sum_round_error(32, audit.D(0))
        assert error >= audit.D.from_float(smallest)*32
    tiny = audit.rounded(audit.Interval("1e-400"))
    assert tiny.contains(0.) and tiny.contains("1e-400")


def test_strong_dot_cancellation_is_enclosed_and_possible_overflow_rejected():
    model = example_model()
    model["state_dict"]["net.0.weight"] = [[1e100, -1e100] + [0.] * 14 for _ in range(32)]
    features = [1., 1.] + [0.] * 14
    audit.audit_forward(model, features, forward(model, features))
    model["state_dict"]["net.0.weight"] = [[1e308, -1e308] + [0.] * 14 for _ in range(32)]
    with pytest.raises(ValueError, match="overflow"):
        audit.audit_forward(model, features)


def test_gamma_denominator_and_interval_division_boundaries_fail_closed():
    with pytest.raises(ValueError, match="denominator"):
        audit.gamma(2**53)
    with pytest.raises(ValueError, match="crosses zero"):
        audit.Interval(1)/audit.Interval("-1e-100", "1e-100")
    with localcontext() as ctx:
        ctx.prec = 120
        n = 33
        reference = audit.D(n)*audit.U/(1-audit.D(n)*audit.U)
        assert audit.gamma(n) >= reference


def test_recorded_probability_immediately_outside_envelope_is_rejected():
    logits = [[.1, .2]]
    result = audit.audit_softmax(logits, [1.])
    with localcontext() as ctx:
        ctx.prec = 110
        above = audit.D(result["probability_intervals"][0][0][1]).next_plus()
    recorded = [[str(above), .5]]
    with pytest.raises(ValueError, match="recorded probability"):
        audit.audit_softmax(logits, [1.], recorded)


def test_missing_or_numerically_tampered_real_trace_is_rejected():
    logits, labels = np.zeros((3, 2)), np.zeros(3, dtype=int)
    original = calibrate_temperature(logits, labels)
    with pytest.raises(ValueError, match="actual golden_trace"):
        audit.audit_temperature(logits, labels, original)
    trace = original_trace(logits, labels)
    changed = copy.deepcopy(trace)
    changed[2]["nll_m1"] += .001
    with pytest.raises(ValueError, match="rounding envelope"):
        audit.audit_temperature(logits, labels, original, golden_trace=changed)


def test_temperature_and_label_mutations_fail_on_nonflat_real_fit():
    logits = np.array([[.02, 0.], [-.01, 0.], [.005, 0.]])
    labels = np.array([0, 0, 1])
    original = calibrate_temperature(logits, labels)
    trace = original_trace(logits, labels)
    audit.audit_temperature(logits, labels, original, golden_trace=trace)
    with pytest.raises(ValueError, match="temperature"):
        audit.audit_temperature(logits, labels, 2. if original != 2. else 3., golden_trace=trace)
    changed = labels.copy(); changed[0] = 1
    with pytest.raises(ValueError, match="rounding envelope"):
        audit.audit_temperature(logits, changed, original, golden_trace=trace)


def frozen_action_step(probabilities):
    from jev_tune.primitives import Answer, Choice, Option, Noul
    from jev_tune.decode import decide
    deltas = [-.2, -.05, 0., .05, .2]
    answer = Answer(choice=[Choice(str(axis), [Option(str(d), d) for d in deltas], probabilities[axis]) for axis in range(2)], noul=Noul("finite", 1.))
    return decide(answer, max_step=.2, shrinkage=1., abstain=None).step


def test_next_proposal_contains_original_decoder_and_certifies_freshness():
    model, features, theta = example_model(), [.01*(i+1) for i in range(16)], [.5, .5]
    probabilities = softmax(forward(model, features))
    step = frozen_action_step(probabilities)
    proposal = np.clip(np.array(theta)+step, 0., 1.)
    result = audit.audit_next_proposal(model, features, [1., 1.], theta, [theta, [0., 0.]])
    assert result["ok"] and result["cached_tuples_checked"] == 2
    assert result["conditional_certificate"]
    for axis in range(2):
        assert audit.Interval(*result["step_intervals"][axis]).contains(step[axis])
        assert audit.Interval(*result["proposal_intervals"][axis]).contains(proposal[axis])
    assert audit.Interval(*result["population_variance_reference_interval"]).contains(np.var([-.2, -.05, 0., .05, .2]))
    # Fresh-call budget exhaustion alone cannot prove termination: a previously
    # observed next tuple remains a valid request even after the last fresh call.
    with pytest.raises(ValueError, match="may hit cached tuple"):
        audit.audit_next_proposal(model, features, [1., 1.], theta, [theta, proposal.tolist()])


@pytest.mark.parametrize("boundary", [False, True])
def test_next_cached_zero_or_clipped_boundary_action_cannot_be_certified_fresh(boundary):
    model = example_model()
    for layer in (0, 2, 4):
        model["state_dict"][f"net.{layer}.weight"] = [[0. for _ in row] for row in model["state_dict"][f"net.{layer}.weight"]]
        model["state_dict"][f"net.{layer}.bias"] = [0. for _ in model["state_dict"][f"net.{layer}.bias"]]
    theta = [1., 1.] if boundary else [.5, .5]
    if boundary: model["state_dict"]["net.4.bias"] = [0., 0., 0., 0., 4.]*2
    step = frozen_action_step(softmax(forward(model, [0.]*16)))
    np.testing.assert_array_equal(np.clip(np.array(theta)+step, 0., 1.), theta)
    with pytest.raises(ValueError, match="freshness unproven"):
        audit.audit_next_proposal(model, [0.]*16, [1., 1.], theta, [theta])


def test_square_interval_crossing_zero_has_nonnegative_lower_endpoint():
    square = audit._square_box(audit.Interval("-.1", ".2"))
    assert square.lo == 0 and square.hi >= audit.D(".04")


def test_feedback_close_cost_cancellation_encloses_original_point_in_any_context():
    current, previous = np.nextafter(1., 2.), 1.
    point = float(np.log1p(current)-np.log1p(previous))
    results = []
    for precision in (7, 28, 110):
        with localcontext() as ctx:
            ctx.prec = precision
            result = audit.audit_feedback(current, previous)
            bound = audit.Interval(*result["feedback_interval"])
            assert bound.contains(point) and bound.contains(0.)
            results.append(result["feedback_interval"])
    assert results[0] == results[1] == results[2]
    # log1p does not round the addition 1+c to binary64 first.
    tiny = audit.Interval(*audit.audit_feedback(1e-20, 0.)["feedback_interval"])
    assert tiny.contains(float(np.log1p(1e-20))) and tiny.lo > 0


def test_feature_intervals_propagate_corners_and_reject_wrong_shape_or_point():
    model, features = example_model(), [.01*(i+1) for i in range(16)]
    bounds = [[value, value] for value in features]
    bounds[3] = [features[3]-.005, features[3]+.005]
    result = audit.audit_forward(model, features, feature_intervals=bounds)
    for endpoint in bounds[3]:
        corner = features.copy(); corner[3] = endpoint
        logits = forward(model, corner)
        for axis in range(2):
            for option in range(5):
                assert audit.Interval(*result["logit_intervals"][axis][option]).contains(logits[axis, option])
    with pytest.raises(ValueError, match="feature intervals"):
        audit.audit_forward(model, features, feature_intervals=bounds[:15])
    wrong = copy.deepcopy(bounds); wrong[3] = [features[3]+.001, features[3]+.002]
    with pytest.raises(ValueError, match="input feature outside"):
        audit.audit_forward(model, features, feature_intervals=wrong)


def test_terminal_proposal_propagates_feedback_and_refuses_wrong_input_point():
    model, features = example_model(), [.01*(i+1) for i in range(16)]
    current, previous = np.nextafter(1., 2.), 1.
    features[3] = float(np.log1p(current)-np.log1p(previous))
    result = audit.audit_next_proposal(model, features, [1., 1.], [.5, .5], [[.5, .5]],
                                       feedback_costs=(current, previous))
    assert result["ok"]
    assert audit.Interval(*result["feedback_certificate"]["feedback_interval"]).contains(features[3])
    features[3] += .001
    with pytest.raises(ValueError, match="input feature outside"):
        audit.audit_next_proposal(model, features, [1., 1.], [.5, .5], [[.5, .5]],
                                   feedback_costs=(current, previous))
