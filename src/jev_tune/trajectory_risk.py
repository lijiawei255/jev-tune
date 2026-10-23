"""Independent research engine for risk-ranked, complete scaled PID actions.

No production or v1 policy is changed. A simulation cache is private to each
plant and this run. Diagnostic observations become operating observations only
if their exact gain vector is subsequently adopted by the fixed policy.
"""
from __future__ import annotations

import numpy as np

from .decision import as_backend
from .decode import apply_step, decide
from .metrics import DIVERGED_J, cost_from_metrics
from .plants import simulate, ultimate_gain
from .risk import risk_features
from .state import build_state


SCALES = (1., .5, .25)
_BUCKETS = ("operating_initial", "executed", "diagnostic_rejected",
            "diagnostic_collected", "diagnostic_training")


def trajectory_risk_features(state, applied_step, choice_probs, *, stage,
                             feature_mode="history_zero"):
    """Risk-only initial history correction; never edit the proposal state."""
    if feature_mode not in ("legacy", "history_zero"):
        raise ValueError("feature_mode must be legacy or history_zero")
    state = np.asarray(state, float).copy()
    if feature_mode == "history_zero" and stage == 0:
        if state.ndim != 2 or state.shape[1] != 20:
            raise ValueError("state features must have shape (N,20)")
        state[:, 16] = 0.
    return risk_features(state, applied_step, choice_probs)


def _number(value):
    return float(value) if np.isfinite(value) else None


def _key(gains):
    return np.asarray(gains, dtype="<f8").tobytes()


def _counts(values):
    out = {name: int(values[j]) for j, name in enumerate(_BUCKETS)}
    out["operating"] = out["operating_initial"] + out["executed"]
    out["total"] = sum(out[name] for name in _BUCKETS)
    out.update(requests=int(values[5]), cache_hits=int(values[6]), execution_requests=int(values[7]))
    return out


def run_trajectory_risk(backend, risk_model, plants, qhats=None, *, horizon=20,
                        mode="monitor", selector="full_only", feature_mode="history_zero",
                        collect_step=None, diagnostic=True):
    """Run fixed 10-second noiseless research trajectories, returning raw JSON.

    Training measures all distinct changed candidates, follows scale index
    plant_index % 3, and collects all unique candidate labels. Monitor follows
    scale 1. Gated/collect select full_only or min predicted harmful probability
    before constructing a CP set. Ties keep the first candidate. The target
    collect stage only observes the selected candidate, then stops.

    ``simulation_counts`` counts actual cache misses by request purpose. Its
    ``operating`` is initial + executed misses; ``requests`` and ``cache_hits``
    are separate. Transition ``executed`` means the complete candidate was
    adopted; ``measured`` means a real observation exists, possibly reused.
    ``simulation_performed`` identifies a new simulation on that request.
    No-action and safety stops precede CP eligibility. Safety stops introduce
    no rollback. Returned best gains consider only operating_history entries.
    """
    if mode not in ("training", "monitor", "gated", "collect"):
        raise ValueError("mode must be training, monitor, gated or collect")
    if selector not in ("full_only", "model_min_risk"):
        raise ValueError("selector must be full_only or model_min_risk")
    if feature_mode not in ("legacy", "history_zero"):
        raise ValueError("feature_mode must be legacy or history_zero")
    if not isinstance(horizon, (int, np.integer)) or horizon < 1:
        raise ValueError("horizon must be a positive number of proposal stages")
    if mode == "collect":
        if not isinstance(collect_step, (int, np.integer)) or not 0 <= collect_step < horizon:
            raise ValueError("collect_step must be a zero-based stage inside horizon")
        required = int(collect_step)
    else:
        if collect_step is not None:
            raise ValueError("collect_step is only valid in collect mode")
        required = horizon if mode == "gated" else 0
    q = None if qhats is None else np.asarray(qhats, float)
    if required and q is None:
        raise ValueError("gated stages require frozen prefix quantiles")
    if q is not None:
        if (q.ndim != 1 or len(q) < required or np.isnan(q).any() or (q < 0).any()
                or ((q > 1) & ~np.isposinf(q)).any()):
            raise ValueError("quantiles must be per-stage values in [0,1] or positive infinity")
        if mode == "monitor" and len(q) < horizon:
            raise ValueError("monitor shadow quantiles must cover the horizon")
    if (mode in ("gated", "collect") or (mode == "monitor" and q is not None)) and risk_model is None:
        raise ValueError("risk selection/CP requires a frozen risk model")
    noise = getattr(plants, "noise_sigma", None)
    if noise is not None and (not np.isfinite(noise).all() or np.any(np.asarray(noise) != 0)):
        raise ValueError("trajectory risk research requires zero measurement noise")

    n = int(plants.n)
    counts = np.zeros((n, 8), int)
    transitions = []
    collected = {key: [] for key in ("features", "labels", "current_cost", "proposed_cost",
        "plant_index", "plant_identity", "stage", "candidate_index", "scale", "simulation_performed", "cache_hit")}
    metadata = {"mode": mode, "selector": selector, "feature_mode": feature_mode,
                "horizon": int(horizon), "scales": list(SCALES), "n_plants": n}
    if n == 0:
        return dict(metadata, per_plant=[], transitions=[], collected=collected,
                    simulation_counts=_counts(np.zeros(8, int)))

    backend = as_backend(backend)
    ku, tu = ultimate_gain(plants)
    if not np.isfinite(ku).all() or not np.isfinite(tu).all() or (ku <= 0).any() or (tu <= 0).any():
        raise ValueError("finite positive analytic ZN priors are required")
    gzn = np.column_stack([.6 * ku, 1.2 * ku / tu, .075 * ku * tu])
    gains = np.clip(gzn, 1e-4, 1e3)
    initial_gains = gains.copy()
    identity = np.asarray(getattr(plants, "noise_seed", np.arange(n)))
    caches = [{} for _ in range(n)]

    def request(indices, requested_gains, buckets, stage):
        """One request per listed plant; batch only actual cache misses."""
        answers, misses, missing_gains, missing_pos = [], [], [], []
        for j, i in enumerate(indices):
            counts[i, 5] += 1
            if buckets[j] == "executed":
                counts[i, 7] += 1
            key = _key(requested_gains[j])
            if key in caches[i]:
                counts[i, 6] += 1
                answers.append((caches[i][key], True))
            else:
                answers.append(None)
                misses.append(int(i)); missing_gains.append(requested_gains[j]); missing_pos.append(j)
        if misses:
            ids = np.asarray(misses, int)
            response = simulate(plants.take(ids), np.asarray(missing_gains), horizon=10., ref=1.)
            costs = cost_from_metrics(response["metrics"], y_curve=response["y_curve"], horizon=10., ref=1.)
            for a, (i, pos) in enumerate(zip(misses, missing_pos)):
                bucket = buckets[pos]
                counts[i, _BUCKETS.index(bucket)] += 1
                finite = bool(np.isfinite(costs[a]) and all(
                    np.isfinite(response[key][a]).all() for key in ("metrics", "y_curve", "u_curve")))
                entry = {key: np.asarray(response[key][a]).copy() for key in ("metrics", "y_curve", "u_curve")}
                entry.update(cost=float(costs[a]), finite=finite,
                    unstable=not finite or costs[a] >= DIVERGED_J or np.max(np.abs(entry["y_curve"])) > 12.,
                    source_kind=bucket, source_stage=int(stage), measurement_id=int(counts[i, :5].sum()) - 1)
                caches[i][_key(requested_gains[pos])] = entry
                answers[pos] = (entry, False)
        return answers

    current = [entry for entry, _ in request(np.arange(n), gains, ["operating_initial"] * n, -1)]
    initial_j = np.array([entry["cost"] for entry in current])
    best_j = np.array([entry["cost"] if entry["finite"] else np.inf for entry in current])
    best_gains = gains.copy()
    prev_action, prev_cost = np.zeros((n, 3)), np.zeros(n)
    done = np.zeros(n, bool)
    reasons = np.full(n, "horizon", dtype=object)
    any_harm = np.array([not entry["finite"] for entry in current])
    any_harm2 = any_harm.copy()
    history = [[{"stage": -1, "gains": gains[i].tolist(), "cost": _number(entry["cost"]),
        "observed_finite": entry["finite"], "cache_hit": False,
        "measurement_id": entry["measurement_id"]}] for i, entry in enumerate(current)]

    def new_row(i, stage, reason):
        row = {"plant_index": int(i), "plant_identity": int(identity[i]), "stage": int(stage),
            "gains_before": gains[i].tolist(), "cost_before": _number(current[i]["cost"]),
            "gains_proposed": None, "proposed_step": None, "base_step": None, "applied_step": None,
            "choice_probabilities": None, "features": None, "probabilities": None,
            "prediction_set": None, "qhat": None, "qhat_full_set": False, "accepted": None,
            "candidates": [], "selected_index": None, "proposal_valid": False,
            "measured": False, "simulation_performed": False, "cache_hit": False,
            "executed": False, "measurement_kind": None, "cost_after": None,
            "label": None, "observed_finite": None, "harmful": None,
            "harmful_gt2pct": None, "reason": reason}
        transitions.append(row)
        return row

    def attach_observation(candidate, entry, cached, bucket, before):
        label = int(entry["cost"] > before) if np.isfinite(entry["cost"]) else None
        candidate.update(measured=True, simulation_performed=not cached, cache_hit=bool(cached),
            measurement_kind=bucket, measurement_source_kind=entry["source_kind"],
            measurement_source_stage=entry["source_stage"], measurement_id=entry["measurement_id"],
            cost_after=_number(entry["cost"]), label=label, observed_finite=entry["finite"],
            harmful=None if label is None else bool(label),
            harmful_gt2pct=None if label is None else bool(entry["cost"] > before * 1.02))

    def collect(i, stage, candidate):
        values = dict(features=candidate["features"], labels=candidate["label"],
            current_cost=_number(current[i]["cost"]), proposed_cost=candidate["cost_after"],
            plant_index=int(i), plant_identity=int(identity[i]), stage=int(stage),
            candidate_index=candidate["index"], scale=candidate["scale"],
            simulation_performed=candidate["simulation_performed"], cache_hit=candidate["cache_hit"])
        for key, value in values.items():
            collected[key].append(value)

    for stage in range(horizon):
        idx = []
        for i in np.flatnonzero(~done):
            if current[i]["unstable"] or current[i]["cost"] > max(3 * best_j[i] + 1, 8):
                reasons[i] = "unstable" if current[i]["unstable"] else "safety_threshold"
                new_row(i, stage, reasons[i]); done[i] = True
            else:
                idx.append(int(i))
        idx = np.asarray(idx, int)
        if not idx.size:
            break
        feat, curves = build_state(*(np.stack([current[i][key] for i in idx])
                                    for key in ("metrics", "y_curve", "u_curve")),
            gains[idx], gzn[idx], ku[idx], tu[idx], prev_action=prev_action[idx],
            prev_cost=prev_cost[idx], cost=np.array([current[i]["cost"] for i in idx]),
            iteration=np.full(len(idx), stage), horizon=10., ref=1.)
        answer = backend.answer(feat, curves)
        decision = decide(answer, getattr(backend, "space", None), use_expectation=True,
                          shrinkage=1., abstain=None, conformal=None)
        choice_p = np.stack([choice.probs for choice in answer.choice], axis=1)
        proposals = np.stack([apply_step(gains[idx], decision.step * scale) for scale in SCALES], axis=1)
        applied = np.log10(proposals / gains[idx, None, :])
        features = np.stack([trajectory_risk_features(feat, applied[:, c], choice_p,
            stage=stage, feature_mode=feature_mode) for c in range(3)], axis=1)
        risk_p = None
        if risk_model is not None:
            risk_p = np.asarray(risk_model.probabilities(features.reshape(-1, 44)), float)
            if (risk_p.shape != (len(idx) * 3, 2) or not np.isfinite(risk_p).all()
                    or ((risk_p < 0) | (risk_p > 1)).any()
                    or not np.allclose(risk_p.sum(-1), 1., atol=1e-10)):
                raise ValueError("risk model must return normalized finite binary probabilities")
            risk_p = risk_p.reshape(len(idx), 3, 2)
        if mode == "training":
            selection = idx % 3
        elif mode == "monitor" or selector == "full_only":
            selection = np.zeros(len(idx), int)
        else:
            selection = np.argmin(risk_p[:, :, 1], axis=1)
        target = mode == "collect" and stage == collect_step
        rows, selected_entries = {}, {}
        for a, i in enumerate(idx):
            row = new_row(i, stage, "proposal")
            rows[i] = row
            row.update(proposal_valid=True, base_step=decision.step[a].tolist(),
                       choice_probabilities=choice_p[a].tolist(), selected_index=int(selection[a]))
            seen = {}
            for c, scale in enumerate(SCALES):
                key = _key(proposals[a, c]); equivalent = seen.setdefault(key, c)
                row["candidates"].append({"index": c, "scale": scale, "equivalent_to": equivalent,
                    "gains": proposals[a, c].tolist(), "commanded_step": (decision.step[a] * scale).tolist(),
                    "applied_step": applied[a, c].tolist(), "changed": bool(np.any(proposals[a, c] != gains[i])),
                    "features": features[a, c].tolist(),
                    "probabilities": None if risk_p is None else risk_p[a, c].tolist(),
                    "measured": False, "simulation_performed": False, "cache_hit": False,
                    "measurement_kind": None, "cost_after": None, "label": None, "observed_finite": None,
                    "harmful": None, "harmful_gt2pct": None})
            candidate = row["candidates"][selection[a]]
            row.update(gains_proposed=candidate["gains"], proposed_step=candidate["commanded_step"],
                       applied_step=candidate["applied_step"], features=candidate["features"],
                       probabilities=candidate["probabilities"])
            if not candidate["changed"]:
                row["reason"] = reasons[i] = "no_action"; done[i] = True
            elif mode not in ("training",) and not target and q is not None:
                mask = (1 - np.asarray(candidate["probabilities"])) <= q[stage]
                row.update(prediction_set=mask.tolist(), accepted=bool(mask[0] and not mask[1]),
                           qhat=_number(q[stage]), qhat_full_set=bool(q[stage] >= 1))
            if candidate["changed"] and (target or (mode in ("gated", "collect") and not row["accepted"])):
                row["reason"] = reasons[i] = "collected" if target else "risk_rejected"
                done[i] = True

        # Candidate order is fixed. Only requested actions are simulated;
        # equivalent or earlier measured actions are exact per-plant cache hits.
        for c in range(3):
            requested, requested_gains, buckets = [], [], []
            for i in idx:
                row = rows[i]; candidate = row["candidates"][c]
                if not candidate["changed"]:
                    continue
                selected = c == row["selected_index"]
                if mode == "training":
                    bucket = "executed" if selected else "diagnostic_training"
                elif not selected:
                    continue
                elif target:
                    bucket = "diagnostic_collected"
                elif mode == "monitor" or row["accepted"]:
                    bucket = "executed"
                elif diagnostic:
                    bucket = "diagnostic_rejected"
                else:
                    continue
                requested.append(int(i)); requested_gains.append(candidate["gains"]); buckets.append(bucket)
            if not requested:
                continue
            answers = request(np.asarray(requested), np.asarray(requested_gains), buckets, stage)
            for i, (entry, cached), bucket in zip(requested, answers, buckets):
                candidate = rows[i]["candidates"][c]
                attach_observation(candidate, entry, cached, bucket, current[i]["cost"])
                if mode == "training" and candidate["equivalent_to"] == c:
                    collect(i, stage, candidate)
                elif target:
                    collect(i, stage, candidate)
                if c == rows[i]["selected_index"]:
                    selected_entries[i] = (entry, cached, bucket)

        for i in idx:
            row = rows[i]; candidate = row["candidates"][row["selected_index"]]
            if i not in selected_entries:
                continue
            entry, cached, bucket = selected_entries[i]
            for key in ("measured", "simulation_performed", "cache_hit", "measurement_kind", "cost_after",
                        "label", "observed_finite", "harmful", "harmful_gt2pct", "measurement_id",
                        "measurement_source_kind", "measurement_source_stage"):
                row[key] = candidate[key]
            if bucket != "executed":
                continue
            row["executed"] = True; row["reason"] = "executed"
            before = current[i]["cost"]
            prev_cost[i] = before; prev_action[i] = candidate["applied_step"]
            gains[i] = candidate["gains"]; current[i] = entry
            any_harm[i] |= not entry["finite"] or entry["cost"] > before
            any_harm2[i] |= not entry["finite"] or entry["cost"] > before * 1.02
            if entry["finite"] and entry["cost"] < best_j[i]:
                best_j[i] = entry["cost"]; best_gains[i] = gains[i]
            history[i].append({"stage": int(stage), "gains": gains[i].tolist(), "cost": _number(entry["cost"]),
                "observed_finite": entry["finite"], "cache_hit": cached,
                "measurement_id": entry["measurement_id"]})
            if entry["unstable"] or entry["cost"] > max(3 * best_j[i] + 1, 8):
                done[i] = True
                reasons[i] = "unstable" if entry["unstable"] else "safety_threshold"
                row["reason"] = "executed_" + reasons[i]

    per_plant = [{"plant_index": i, "plant_identity": int(identity[i]),
        "behavior_index": i % 3 if mode == "training" else None,
        "initial_gains": initial_gains[i].tolist(), "initial_J": _number(initial_j[i]),
        "best_gains": best_gains[i].tolist(), "best_J": _number(best_j[i]),
        "best_valid": bool(np.isfinite(best_j[i])), "current_gains": gains[i].tolist(),
        "current_J": _number(current[i]["cost"]), "stop_reason": str(reasons[i]),
        "any_harm": bool(any_harm[i]), "any_harm_gt2pct": bool(any_harm2[i]),
        "operating_history": history[i], "simulation_counts": _counts(counts[i])}
        for i in range(n)]
    return dict(metadata, per_plant=per_plant, transitions=transitions, collected=collected,
                simulation_counts=_counts(counts.sum(axis=0)))


__all__ = ["SCALES", "trajectory_risk_features", "run_trajectory_risk"]
