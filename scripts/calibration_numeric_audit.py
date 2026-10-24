"""Independent Decimal audit, not a replacement inference/calibration runtime.

Arithmetic assumes IEEE binary64 round-to-nearest (including fused/reordered
dot products bounded by gamma(2*n+1)), gradual underflow, and faithful (<= one
ulp) exp/tanh/log/log1p implementations. Decimal exp/ln are correctly rounded; their
adjacent Decimal numbers enclose the real result. Certificates are conditional
on those explicit elementary-function assumptions, not bitwise replay proofs.
No bound is fitted to observed residuals. All public results are JSON-safe.
"""
from __future__ import annotations

from decimal import Decimal as D, localcontext, ROUND_FLOOR, ROUND_CEILING
import math
import sys
from functools import wraps

PRECISION = 80
with localcontext() as _constants:
    _constants.prec = PRECISION
    _constants.rounding = ROUND_CEILING
    U = D(2) ** -53
    ETA = D(2) ** -1074
ASSUMPTIONS = __doc__
BINARY64_MAX = D.from_float(sys.float_info.max)


def decimal80(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with localcontext() as ctx:
            ctx.prec = PRECISION
            return function(*args, **kwargs)
    return wrapped


def _d(value):
    if isinstance(value, D):
        result = value
    elif isinstance(value, str):
        result = D(value)
    else:
        result = D.from_float(float(value))
    if not result.is_finite():
        raise ValueError("finite numeric input required")
    return result


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _op(operation, rounding):
    with localcontext() as ctx:
        ctx.prec = PRECISION
        ctx.rounding = rounding
        return operation()


class Interval:
    def __init__(self, lo, hi=None):
        self.lo, self.hi = _d(lo), _d(lo if hi is None else hi)
        _require(self.lo <= self.hi, "invalid interval")

    def __add__(self, other):
        other = box(other)
        return Interval(_op(lambda: self.lo + other.lo, ROUND_FLOOR),
                        _op(lambda: self.hi + other.hi, ROUND_CEILING))

    def __neg__(self):
        return Interval(self.hi.copy_negate(), self.lo.copy_negate())

    def __sub__(self, other):
        return self + -box(other)

    def __mul__(self, other):
        other = box(other)
        pairs = [(a, b) for a in (self.lo, self.hi) for b in (other.lo, other.hi)]
        return Interval(min(_op(lambda: a*b, ROUND_FLOOR) for a, b in pairs),
                        max(_op(lambda: a*b, ROUND_CEILING) for a, b in pairs))

    def __truediv__(self, other):
        other = box(other)
        _require(not other.lo <= 0 <= other.hi, "division interval crosses zero")
        return self * Interval(_op(lambda: 1/other.hi, ROUND_FLOOR),
                               _op(lambda: 1/other.lo, ROUND_CEILING))

    def widen(self, error):
        error = _d(error)
        _require(error >= 0, "nonnegative error required")
        return self + Interval(error.copy_negate(), error)

    def magnitude(self):
        return max(self.lo.copy_abs(), self.hi.copy_abs())

    def contains(self, value):
        return self.lo <= _d(value) <= self.hi

    def strings(self):
        return [str(self.lo), str(self.hi)]


def box(value):
    return value if isinstance(value, Interval) else Interval(value)


def gamma(n):
    _require(isinstance(n, int) and n >= 0, "nonnegative operation count required")
    numerator = _op(lambda: D(n)*U, ROUND_CEILING)
    denominator = _op(lambda: D(1)-numerator, ROUND_FLOOR)
    _require(denominator > 0, "rounding bound denominator not positive")
    return _op(lambda: numerator/denominator, ROUND_CEILING)


def sum_round_error(n, magnitude):
    """gamma_n*sum|terms| plus amplified per-operation absolute underflow.

    At each operation |delta|<=u|exact result|+eta. The geometric amplification
    of the n absolute errors is at most 1/(1-n*u), bounded by 1+gamma_n.
    """
    g = gamma(n)
    return _op(lambda: g*_d(magnitude) + D(n)*ETA*(1+g), ROUND_CEILING)


def rounded(value, faithful=False):
    """One binary operation: relative-u or faithful relative-2u plus underflow."""
    value = box(value)
    error = _op(lambda: (2 if faithful else 1)*U*value.magnitude() + ETA,
                ROUND_CEILING)
    enclosure = value.widen(error)
    _require(enclosure.magnitude() <= BINARY64_MAX,
             "possible binary64 overflow: certificate unavailable")
    return enclosure


def exp_interval(value):
    value = box(value)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        lo, hi = value.lo.exp(), value.hi.exp()
        return Interval(max(D(0), lo.next_minus()), hi.next_plus())


def log_interval(value):
    value = box(value)
    _require(value.lo > 0, "positive logarithm interval required")
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return Interval(value.lo.ln().next_minus(), value.hi.ln().next_plus())


def tanh_interval(value):
    value = box(value)
    def endpoint(x):
        # exp(-2|x|) avoids overflow and cancellation at large positive x.
        e = exp_interval(Interval(-2)*Interval(x.copy_abs()))
        result = (Interval(1)-e)/(Interval(1)+e)
        return -result if x < 0 else result
    return Interval(endpoint(value.lo).lo, endpoint(value.hi).hi)


def _matrix(model, key, rows, cols=None):
    values = model["state_dict"][key]
    _require(len(values) == rows, "model weight shape mismatch: " + key)
    if cols is None:
        return [_d(value) for value in values]
    _require(all(len(row) == cols for row in values), "model weight shape mismatch: " + key)
    return [[_d(value) for value in row] for row in values]


@decimal80
def audit_forward(model, features, recorded_logits=None, feature_intervals=None):
    """Audit a single canonical float64 16->32(tanh)->32(tanh)->10 MLP."""
    _require(len(features) == 16 and len(model["normalization_mean"]) == 16
             and len(model["normalization_scale"]) == 16, "16 features required")
    _require(model.get("dtype") == "float64", "audit supports declared float64 model only")
    if feature_intervals is None:
        feature_boxes = [Interval(value) for value in features]
    else:
        _require(len(feature_intervals) == 16 and all(len(pair) == 2 for pair in feature_intervals),
                 "16 two-endpoint feature intervals required")
        feature_boxes = [Interval(*pair) for pair in feature_intervals]
        _require(all(bound.contains(value) for bound, value in zip(feature_boxes, features)),
                 "input feature outside supplied feature interval")
    exact, bounds = [], []
    for x, xb, mean, scale in zip(features, feature_boxes, model["normalization_mean"], model["normalization_scale"]):
        _require(_d(scale) > 0, "positive normalization scale required")
        exact.append((Interval(x)-Interval(mean))/Interval(scale))
        bounds.append(rounded(rounded(xb-Interval(mean))/Interval(scale)))
    for layer, n_in, n_out in [(0, 16, 32), (2, 32, 32), (4, 32, 10)]:
        weights = _matrix(model, f"net.{layer}.weight", n_out, n_in)
        biases = _matrix(model, f"net.{layer}.bias", n_out)
        new_exact, new_bounds = [], []
        for row, bias in zip(weights, biases):
            nominal, enclosure, magnitude = Interval(bias), Interval(bias), bias.copy_abs()
            for weight, x, xb in zip(row, exact, bounds):
                nominal = nominal + Interval(weight)*x
                enclosure = enclosure + Interval(weight)*xb
                magnitude = _op(lambda: magnitude + weight.copy_abs()*xb.magnitude(), ROUND_CEILING)
            # At most n multiplies, n adds, and one bias addition; FMA/reordering
            # uses no more roundings. Add one subnormal allowance per operation.
            error = sum_round_error(2*n_in+1, magnitude)
            _require((Interval(magnitude)+Interval(error)).hi <= BINARY64_MAX,
                     "possible dot-product intermediate overflow: certificate unavailable")
            enclosure = enclosure.widen(error)
            if layer != 4:
                nominal, enclosure = tanh_interval(nominal), rounded(tanh_interval(enclosure), faithful=True)
            new_exact.append(nominal)
            new_bounds.append(enclosure)
        exact, bounds = new_exact, new_bounds
    if recorded_logits is not None:
        _require(len(recorded_logits) == 2 and all(len(row) == 5 for row in recorded_logits), "2x5 logits required")
        for index, value in enumerate(value for row in recorded_logits for value in row):
            _require(bounds[index].contains(value), f"recorded logit outside forward envelope: {index}")
    return {"logits": [[str((exact[a*5+k].lo+exact[a*5+k].hi)/2) for k in range(5)] for a in range(2)],
            "logit_intervals": [[bounds[a*5+k].strings() for k in range(5)] for a in range(2)],
            "assumptions": ASSUMPTIONS, "conditional_certificate": True, "bitwise_replay_proven": False}


def _softmax_boxes(logits, temperature, intervals=None):
    _require(_d(temperature) > 0 and len(logits) > 0, "positive temperature and logits required")
    exact = [Interval(value) for value in logits]
    values = [Interval(*pair) for pair in intervals] if intervals is not None else exact
    _require(len(values) == len(logits), "logit interval shape mismatch")
    # The actual maximum is one of the bounded logits, so its range is bounded
    # independently; correlation is discarded conservatively.
    maximum = Interval(max(v.lo for v in values), max(v.hi for v in values))
    exponentials = [rounded(exp_interval(rounded(rounded(v-maximum)/Interval(temperature))), faithful=True) for v in values]
    exponentials = [Interval(max(D(0), v.lo), v.hi) for v in exponentials]
    denominator = Interval(0)
    for value in exponentials:
        denominator = denominator + value
    denominator = denominator.widen(sum_round_error(len(values)-1, denominator.magnitude()))
    _require(denominator.lo > 0, "softmax denominator not certifiable")
    probabilities = [rounded(value/denominator) for value in exponentials]
    return [Interval(max(D(0), p.lo), min(D(1), p.hi)) for p in probabilities]


@decimal80
def audit_softmax(logits, temperatures, recorded_probabilities=None, logit_intervals=None):
    """Per-axis softmax envelope, including binary64 exp/sum/divide errors."""
    _require(len(logits) == len(temperatures), "softmax axis shape mismatch")
    bounds = [_softmax_boxes(row, t, None if logit_intervals is None else logit_intervals[a])
              for a, (row, t) in enumerate(zip(logits, temperatures))]
    if recorded_probabilities is not None:
        _require(len(recorded_probabilities) == len(bounds), "probability axis shape mismatch")
        for axis, (row, values) in enumerate(zip(recorded_probabilities, bounds)):
            _require(len(row) == len(values), "probability option shape mismatch")
            for option, (value, enclosure) in enumerate(zip(row, values)):
                _require(enclosure.contains(value), f"recorded probability outside softmax envelope: {axis}/{option}")
    return {"probability_intervals": [[p.strings() for p in row] for row in bounds],
            "assumptions": ASSUMPTIONS, "conditional_certificate": True, "bitwise_replay_proven": False}


def _objective(logits, labels, beta):
    """High-precision inverse-temperature loss, derivative and curvature."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        loss = derivative = curvature = D(0)
        for row, label in zip(logits, labels):
            z = [_d(v) for v in row]
            maximum = max(z)
            e = [((v-maximum)*beta).exp() for v in z]
            total = sum(e)
            p = [v/total for v in e]
            mean = sum(v*prob for v, prob in zip(z, p))
            loss += total.ln() + (maximum-z[int(label)])*beta
            derivative += mean-z[int(label)]
            curvature += sum(prob*(v-mean)**2 for v, prob in zip(z, p))
        count = D(len(labels))
        return loss/count, derivative/count, curvature/count


def _loss_envelope(logits, labels, temperature):
    total = Interval(0)
    for row, label in zip(logits, labels):
        p = _softmax_boxes(row, temperature)[int(label)]
        _require(p.lo > _d(1e-12), "NLL clip may activate: no smooth calibration certificate")
        total = total + -rounded(log_interval(p), faithful=True)
    total = total.widen(sum_round_error(len(labels)-1, total.magnitude()))
    return rounded(total/Interval(len(labels)))


def _objective_boxes(logits, labels, beta, check_clip=False):
    """Outward Decimal enclosures, with no empirical decimal-error reserve."""
    loss, derivative, curvature = Interval(0), Interval(0), Interval(0)
    beta = box(beta)
    for row, label in zip(logits, labels):
        z = [_d(v) for v in row]
        maximum = max(z)
        e = [exp_interval((Interval(v)-Interval(maximum))*beta) for v in z]
        total = Interval(0)
        for value in e:
            total = total + value
        probabilities = [value/total for value in e]
        if check_clip:
            _require(probabilities[int(label)].lo > _d(1e-12),
                     "NLL clip active or unresolved: no smooth calibration certificate")
        mean = Interval(0)
        for value, probability in zip(z, probabilities):
            mean = mean + Interval(value)*probability
        loss = loss + log_interval(total)+(Interval(maximum)-Interval(z[int(label)]))*beta
        derivative = derivative + mean-Interval(z[int(label)])
        # This expression has a conservative interval even though shared mean
        # dependencies are discarded. It is not used to assert strict positivity.
        for value, probability in zip(z, probabilities):
            delta = Interval(value)-mean
            square = delta*delta
            if delta.lo <= 0 <= delta.hi:
                square = Interval(0, square.hi)
            curvature = curvature + probability*square
    count = Interval(len(labels))
    return loss/count, derivative/count, curvature/count


def _clip_tail_certificate(logits, labels, beta_lo, beta_hi, target):
    """Exclude a clipped tail using per-sample convex tangent lower bounds.

    A work limit only causes rejection; it cannot enlarge a numerical budget.
    All subdivisions are midpoint bisections, never selected by test outcomes.
    """
    cap = -log_interval(Interval(1e-12))
    pending, proven, processed = [(beta_lo, beta_hi)], [], 0
    while pending:
        lo, hi = pending.pop()
        processed += 1
        _require(processed <= 4096, "clipped-tail lower bound unresolved within work limit")
        mid = (lo+hi)/2
        total = Interval(0)
        for row, label in zip(logits, labels):
            loss, slope, _ = _objective_boxes([row], [label], mid)
            tangent = loss+slope*(Interval(lo, hi)-Interval(mid))
            lower = max(D(0), min(tangent.lo, cap.lo))
            total = total+Interval(lower)
        lower = (total/Interval(len(labels))).lo
        if lower >= target:
            proven.append(lower)
        else:
            _require(mid > lo and mid < hi, "clipped tail cannot be separated from recorded objective")
            pending.extend([(lo, mid), (mid, hi)])
    return {"intervals_proven": len(proven), "intervals_processed": processed,
            "minimum_certified_loss_lower_bound": str(min(proven)),
            "required_loss_lower_bound": str(target), "work_limit": 4096}


@decimal80
def audit_temperature(logits, labels, temperature, golden_trace=None):
    """Certify a recorded T by objective loss, never a relaxed T tolerance.

    Convexity is in beta=1/T. Each possibly incorrect floating golden branch
    loses at most its two loss-rounding bounds times the discarded beta-length
    divided by the two probe beta-distance. These bounds add over 60 branches.
    The final beta-interval residual is bounded by its endpoint derivatives.
    The test compares an independently minimized high-precision objective gap
    to this computed budget. A real 60-step trace is required; an unrelated
    search in the checking environment is never substituted for that trace.
    """
    _require(len(logits) == len(labels) and len(labels) > 0, "nonempty calibration rows required")
    _require(all(len(row) == len(logits[0]) and 0 <= int(y) < len(row)
                 and int(y) == y for row, y in zip(logits, labels)), "invalid calibration labels/shape")
    _require(_d(.05) <= _d(temperature) <= _d(20.), "temperature outside frozen search domain")
    _require(golden_trace is not None and len(golden_trace) == 60,
             "actual golden_trace with 60 branches required for path-budget certificate")
    with localcontext() as ctx:
        ctx.prec = PRECISION
        blo, bhi = (Interval(1)/Interval(20.)).lo, (Interval(1)/Interval(.05)).hi
        original_beta_lo, original_beta_hi = blo, bhi
        _objective_boxes(logits, labels, blo, check_clip=True)
        safe_beta_hi = bhi
        try:
            _objective_boxes(logits, labels, bhi, check_clip=True)
        except ValueError:
            # g_i(0)=log(K)<cap and g_i is convex, so on the positive beta ray
            # any clipping begins in an upper tail. The safe endpoint below is
            # inside that tail, conservatively overlapping the smooth region.
            safe, unsafe = blo, bhi
            for _ in range(128):
                point = (safe+unsafe)/2
                try:
                    _objective_boxes(logits, labels, point, check_clip=True)
                    safe = point
                except ValueError:
                    unsafe = point
            safe_beta_hi = safe
        for _ in range(160):
            mid = (blo+bhi)/2
            _, derivative_interval, _ = _objective_boxes(logits, labels, mid)
            if derivative_interval.lo > 0:
                bhi = mid
            elif derivative_interval.hi < 0:
                blo = mid
            else:
                break
        optimum = (blo+bhi)/2
        optimum_loss, _, _ = _objective(logits, labels, optimum)
        recorded_loss, slope, curvature = _objective(logits, labels, 1/_d(temperature))
        recorded_boxes = _objective_boxes(logits, labels, Interval(1)/Interval(temperature))
        recorded_loss_box = recorded_boxes[0]
        _objective_boxes(logits, labels, Interval(1)/Interval(temperature), check_clip=True)
        _objective_boxes(logits, labels, Interval(blo, bhi), check_clip=True)
        optimum_loss_box = _objective_boxes(logits, labels, Interval(blo, bhi))[0]
        lo, hi, budget = .05, 20., D(0)
        branches = []
        for iteration in range(60):
            m1, m2 = lo+.382*(hi-lo), lo+.618*(hi-lo)
            e1, e2 = _loss_envelope(logits, labels, m1), _loss_envelope(logits, labels, m2)
            b1, b2 = Interval(1)/Interval(m1), Interval(1)/Interval(m2)
            f1 = _objective_boxes(logits, labels, b1)[0]
            f2 = _objective_boxes(logits, labels, b2)[0]
            difference1, difference2 = e1-f1, e2-f2
            error = (Interval(difference1.magnitude())+Interval(difference2.magnitude())).hi
            row = golden_trace[iteration]
            _require(row["iteration"] == iteration and row["lo"] == lo and row["hi"] == hi
                     and row["m1"] == m1 and row["m2"] == m2, "invalid golden trace geometry")
            _require(e1.contains(row["nll_m1"]) and e2.contains(row["nll_m2"]), "golden trace loss outside rounding envelope")
            branch = row["nll_m1"] < row["nll_m2"]
            _require(row["branch"] == ("hi=m2" if branch else "lo=m1"), "invalid golden branch")
            distance = b1-b2
            _require(distance.lo > 0, "golden inverse-probe distance not separated")
            discarded = (b2-Interval(1)/Interval(hi)) if branch else (Interval(1)/Interval(lo)-b1)
            _require(discarded.lo >= 0, "invalid discarded inverse-temperature interval")
            allowance = (Interval(error)*(Interval(1)+discarded/distance)).hi
            budget = (Interval(budget)+Interval(allowance)).hi
            branches.append(str(allowance))
            if branch:
                hi = m2
            else:
                lo = m1
        _require(float(temperature) == .5*(lo+hi), "recorded temperature differs from actual trace return")
        final_lo, final_hi = Interval(1)/Interval(hi), Interval(1)/Interval(lo)
        derivative_bound = max(_objective_boxes(logits, labels, final_lo)[1].magnitude(),
                               _objective_boxes(logits, labels, final_hi)[1].magnitude())
        residual = ((final_hi-final_lo)*Interval(derivative_bound)).hi
        budget = (Interval(budget)+Interval(residual)).hi
        gap = max(D(0), (recorded_loss_box-optimum_loss_box).hi)
        _require(gap <= budget, "recorded temperature objective gap exceeds golden rounding budget")
        tail = None
        if safe_beta_hi < original_beta_hi:
            _require(bhi < safe_beta_hi, "smooth minimizer not separated from clipped region")
            target = (Interval(recorded_loss_box.hi)-Interval(budget)).hi
            tail = _clip_tail_certificate(logits, labels, safe_beta_hi, original_beta_hi, target)
        return {"ok": True, "temperature": str(_d(temperature)), "inverse_temperature_derivative": str(slope),
                "inverse_temperature_curvature": str(curvature), "recorded_NLL": str(recorded_loss),
                "inverse_temperature_derivative_interval": recorded_boxes[1].strings(),
                "inverse_temperature_curvature_interval": recorded_boxes[2].strings(),
                "minimum_NLL": str(optimum_loss), "minimum_inverse_temperature_interval": [str(blo), str(bhi)],
                "objective_gap_upper": str(gap), "golden_loss_rounding_budget": str(budget),
                "golden_branch_allowances": branches, "final_interval_residual": str(residual),
                "smooth_search_inverse_temperature_domain": [str(original_beta_lo), str(safe_beta_hi)],
                "clipped_tail_certificate": tail,
                "scope": "Conditional objective-loss certificate with validated recorded trace; not a proof of backend assumptions", "assumptions": ASSUMPTIONS,
                "conditional_certificate": True}


@decimal80
def audit_cp(probabilities, labels, qhat, alpha=.1, probability_intervals=None, recorded_sets=None):
    """Strict rank intervals; operational sets always use exact recorded p/q."""
    n, axes = len(probabilities), len(qhat)
    _require(n > 0 and len(labels) == n and 0 < _d(alpha) < 1, "invalid conformal inputs")
    # Match the original binary64 rank expression exactly; never change rank to
    # admit a nearby threshold. Integer rank is separately included in output.
    rank = math.ceil((n+1)*(1-float(alpha)))
    scores, sets, ambiguous = [[] for _ in range(axes)], [], 0
    for i, (state, target) in enumerate(zip(probabilities, labels)):
        _require(len(state) == axes and len(target) == axes, "conformal axis shape mismatch")
        state_sets = []
        for axis, row in enumerate(state):
            values = [_d(p) for p in row]
            _require(all(0 <= p <= 1 for p in values), "invalid probability")
            normalization = Interval(0)
            for value in values:
                normalization = normalization+Interval(value)
            normalization_error = (normalization-Interval(1)).magnitude()
            normalization_bound = (Interval(gamma(len(values)))*Interval(len(values))).hi
            _require(normalization_error <= normalization_bound, "probability row not normalized")
            label = int(target[axis])
            _require(label == target[axis] and 0 <= label < len(values), "invalid conformal label")
            bounds = [Interval(p) for p in values] if probability_intervals is None else [Interval(*pair) for pair in probability_intervals[i][axis]]
            _require(len(bounds) == len(values), "probability interval shape mismatch")
            for value, bound in zip(values, bounds):
                _require(bound.contains(value), "recorded probability outside supplied interval")
            # Actual NumPy computes one rounded binary64 subtraction here.
            scores[axis].append(rounded(Interval(1)-bounds[label]))
            chosen = []
            for value, bound in zip(values, bounds):
                chosen.append((1-float(value)) <= float(qhat[axis]))
                score = rounded(Interval(1)-bound)
                ambiguous += score.lo <= _d(qhat[axis]) <= score.hi
            state_sets.append(chosen)
        sets.append(state_sets)
    intervals = []
    for axis, column in enumerate(scores):
        if rank > n:
            lower = upper = D(1)
        else:
            lower = sorted(v.lo for v in column)[rank-1]
            upper = sorted(v.hi for v in column)[rank-1]
        _require(0 <= _d(qhat[axis]) <= 1 and lower <= _d(qhat[axis]) <= upper,
                 f"qhat outside strict rank interval: {axis}")
        intervals.append([str(lower), str(upper)])
    if recorded_sets is not None:
        _require(recorded_sets == sets if isinstance(recorded_sets, list) else recorded_sets.tolist() == sets,
                 "recorded full conformal sets differ")
    return {"ok": True, "rank": rank, "qhat_intervals": intervals, "sets": sets,
            "ambiguous_boundary_count": int(ambiguous), "bitwise_replay_proven": False,
            "conditional_certificate": True, "assumptions": ASSUMPTIONS,
            "scope": "Exact recorded p/q sets; interval-boundary ambiguity never expands operational sets"}


def _sum_boxes(values):
    total, magnitude = Interval(0), Interval(0)
    for value in values:
        total = total+value
        magnitude = magnitude+Interval(value.magnitude())
    error = sum_round_error(max(len(values)-1, 0), magnitude.hi)
    _require((magnitude+Interval(error)).hi <= BINARY64_MAX,
             "possible summation intermediate overflow: certificate unavailable")
    return total.widen(error)


def _dot_boxes(left, right):
    _require(len(left) == len(right) and len(left) > 0, "nonempty equal dot shapes required")
    terms = [box(a)*box(b) for a, b in zip(left, right)]
    total, magnitude = Interval(0), Interval(0)
    for term in terms:
        total, magnitude = total+term, magnitude+Interval(term.magnitude())
    error = sum_round_error(2*len(terms), magnitude.hi)
    _require((magnitude+Interval(error)).hi <= BINARY64_MAX,
             "possible dot intermediate overflow: certificate unavailable")
    return total.widen(error)


def _square_box(value):
    value = box(value)
    result = value*value
    if value.lo <= 0 <= value.hi:
        result = Interval(0, result.hi)
    result = rounded(result)
    return Interval(max(D(0), result.lo), result.hi)


def _clip_box(value, lo, hi):
    lo, hi = _d(lo), _d(hi)
    _require(lo <= hi, "ordered clip limits required")
    return Interval(max(lo, min(hi, value.lo)), max(lo, min(hi, value.hi)))


@decimal80
def audit_feedback(current_cost, previous_cost):
    """Enclose original log1p(cost)-log1p(previous), not log(fl(1+cost)).

    Decimal directed addition encloses the mathematical 1+c. Only the log1p
    result receives a binary64 elementary-function error. This avoids silently
    modelling an extra binary64 addition absent from the original np.log1p.
    """
    _require(_d(current_cost) >= 0, "nonnegative current cost required")
    if previous_cost is None:
        feedback = Interval(0)
    else:
        _require(_d(previous_cost) >= 0, "nonnegative previous cost required")
        current = rounded(log_interval(Interval(1)+Interval(current_cost)), faithful=True)
        previous = rounded(log_interval(Interval(1)+Interval(previous_cost)), faithful=True)
        feedback = rounded(current-previous)
    return {"feedback_interval": feedback.strings(), "conditional_certificate": True,
            "assumptions": ASSUMPTIONS,
            "scope": "faithful binary64 log1p results, followed by rounded binary64 subtraction"}


@decimal80
def audit_next_proposal(model, features, temperatures, current_theta, cached_thetas,
                        deltas=(-.2, -.05, 0., .05, .2), feedback_costs=None):
    """Prove every allowed next proposal is outside every cached float tuple.

    The non-PID monitor decoder uses full probabilities, a population-variance
    vocabulary normalizer, variance shrink, +/-0.2 step clipping, then rounded
    theta addition and [0,1] clipping. All these operations are enclosed here;
    no proposal interval is narrowed to an observed decoded step.
    """
    _require(len(current_theta) == 2 and len(temperatures) == 2,
             "two axes required for next proposal")
    theta = [_d(value) for value in current_theta]
    _require(all(0 <= value <= 1 for value in theta), "theta outside [0,1]")
    cached = [[_d(value) for value in row] for row in cached_thetas]
    _require(cached and all(len(row) == 2 and all(0 <= v <= 1 for v in row) for row in cached),
             "nonempty two-axis cached theta tuples required")
    _require(any(row == theta for row in cached), "current theta missing from cache")
    d = [Interval(value) for value in deltas]
    _require(len(d) == 5 and all(d[i].lo <= d[i+1].lo for i in range(4)),
             "five ordered deltas required")
    count = Interval(len(d))
    mean = rounded(_sum_boxes(d)/count)
    centered = [rounded(value-mean) for value in d]
    variance_reference = rounded(_sum_boxes([_square_box(value) for value in centered])/count)
    floor = _d(1e-6)
    variance_reference = Interval(max(floor, variance_reference.lo),
                                  max(floor, variance_reference.hi))
    squared_deltas = [_square_box(value) for value in d]
    feature_intervals = None
    feedback = None
    if feedback_costs is not None:
        _require(len(feedback_costs) == 2, "current/previous feedback costs required")
        feedback = audit_feedback(*feedback_costs)
        feature_intervals = [Interval(value).strings() for value in features]
        feature_intervals[3] = feedback["feedback_interval"]
    forward = audit_forward(model, features, feature_intervals=feature_intervals)
    probabilities = audit_softmax(forward["logits"], temperatures,
                                  logit_intervals=forward["logit_intervals"])
    proposals, steps = [], []
    for axis in range(2):
        p = [Interval(*pair) for pair in probabilities["probability_intervals"][axis]]
        mu = _dot_boxes(p, d)
        second = _dot_boxes(p, squared_deltas)
        variance = rounded(second-_square_box(mu))
        variance = Interval(max(D(0), variance.lo), max(D(0), variance.hi))
        scaled_variance = rounded(rounded(Interval(1)*variance)/variance_reference)
        gate = rounded(Interval(1)/rounded(Interval(1)+scaled_variance))
        step = _clip_box(rounded(mu*gate), -.2, .2)
        proposal = _clip_box(rounded(Interval(theta[axis])+step), 0., 1.)
        steps.append(step)
        proposals.append(proposal)
    separating_axes = []
    for index, row in enumerate(cached):
        separated = [axis for axis in range(2) if not proposals[axis].contains(row[axis])]
        _require(separated, f"next proposal may hit cached tuple {index}: freshness unproven")
        separating_axes.append(separated)
    return {"ok": True, "conditional_certificate": True, "assumptions": ASSUMPTIONS,
            "step_intervals": [value.strings() for value in steps],
            "proposal_intervals": [value.strings() for value in proposals],
            "population_variance_reference_interval": variance_reference.strings(),
            "cached_tuples_checked": len(cached), "separating_axes_per_cached_tuple": separating_axes,
            "feedback_certificate": feedback,
            "scope": "All enclosed next proposals are fresh; no objective evaluation or cache lookup executed"}
