"""Research rollout for complete joint proposals and sequential risk sets.

This deliberately stops at the production rollback threshold instead of
introducing an uncalibrated recovery action. Rejected-candidate measurements
are diagnostics: they never enter the operating history or returned optimum.
The caller owns calibration validity and any statistical interpretation.
"""
from __future__ import annotations

import numpy as np

from .decision import as_backend
from .decode import apply_step, decide
from .metrics import DIVERGED_J, cost_from_metrics
from .plants import simulate, ultimate_gain
from .risk import joint_acceptance, risk_features
from .state import build_state


_COUNT_KEYS = ("operating_initial", "executed", "diagnostic_rejected", "diagnostic_collected")


def _number(x):
    return float(x) if np.isfinite(x) else None


def _counts(values):
    out = {key: int(value) for key, value in zip(_COUNT_KEYS, values)}
    out["operating"] = out["operating_initial"] + out["executed"]
    out["total"] = sum(out[key] for key in _COUNT_KEYS)
    return out


def run_joint_rollout(backend, risk_model, plants, qhats, *, horizon=20,
                      mode="monitor", collect_step=None, diagnostic=True):
    """Run up to ``horizon`` proposal stages, plus one initial measurement.

    Simulation is the fixed 10-second, unit-reference, noiseless step task.
    ``monitor`` executes complete changed proposals and records shadow gates.
    ``gated`` executes only the singleton {noninferior}; rejection terminates
    that plant. ``diagnostic`` controls rejected-candidate label measurements.
    ``collect`` follows gated prefix quantiles until zero-based collect_step,
    then measures each reached changed candidate without executing it. Only
    the prefix needs quantiles in collect mode; the target set is unspecified.

    Returns JSON-compatible lists/dicts, with no padded measurements. In each
    transition proposal_valid, measured and executed are separate facts.
    Diagnostic labels/costs cannot update policy state or best-so-far gains.
    """
    if mode not in ("monitor", "gated", "collect"):
        raise ValueError("mode must be monitor, gated or collect")
    if not isinstance(horizon, (int, np.integer)) or horizon < 1:
        raise ValueError("horizon must be a positive integer number of proposal stages")
    if mode == "collect":
        if not isinstance(collect_step, (int, np.integer)) or not 0 <= collect_step < horizon:
            raise ValueError("collect_step must be a zero-based stage inside horizon")
        required = int(collect_step)
    else:
        if collect_step is not None:
            raise ValueError("collect_step is only used in collect mode")
        required = horizon
    q = np.asarray(qhats, dtype=float)
    if q.ndim != 1 or len(q) < required or np.isnan(q).any() or (q < 0).any() or ((q > 1) & ~np.isposinf(q)).any():
        raise ValueError("need per-stage quantiles in [0,1] or positive infinity")
    noise = getattr(plants, "noise_sigma", None)
    if noise is not None and (not np.isfinite(noise).all() or np.any(np.asarray(noise) != 0)):
        raise ValueError("joint rollout protocol requires zero measurement noise")

    n = int(plants.n)
    counts = np.zeros((n, len(_COUNT_KEYS)), dtype=int)
    transitions = []
    collected = {key: [] for key in ("features", "labels", "current_cost", "proposed_cost",
                                    "plant_index", "plant_identity", "stage")}
    if n == 0:
        return {"mode": mode, "horizon": int(horizon), "n_plants": 0, "per_plant": [],
                "transitions": [], "collected": collected, "simulation_counts": _counts(np.zeros(4, int))}

    backend = as_backend(backend)
    ku, tu = ultimate_gain(plants)
    if not np.isfinite(ku).all() or not np.isfinite(tu).all() or (ku <= 0).any() or (tu <= 0).any():
        raise ValueError("joint rollout requires finite positive analytic ZN priors")
    gzn = np.column_stack([.6 * ku, 1.2 * ku / tu, .075 * ku * tu])
    gains = np.clip(gzn, 1e-4, 1e3)
    identity = np.asarray(getattr(plants, "noise_seed", np.arange(n)))

    def measure(indices, candidate, bucket):
        # Count actual plant-runs at the simulation call, not per result record.
        counts[indices, _COUNT_KEYS.index(bucket)] += 1
        response = simulate(plants if len(indices) == n and np.array_equal(indices, np.arange(n))
                            else plants.take(indices), candidate, horizon=10., ref=1.)
        cost = cost_from_metrics(response["metrics"], y_curve=response["y_curve"], horizon=10., ref=1.)
        finite = np.isfinite(cost)
        for key in ("metrics", "y_curve", "u_curve"):
            finite &= np.isfinite(response[key]).reshape(len(indices), -1).all(axis=1)
        unstable = ~finite | (cost >= DIVERGED_J) | (np.max(np.abs(response["y_curve"]), axis=1) > 12.)
        return response, np.asarray(cost, float), finite, unstable

    state, current_j, finite, unstable = measure(np.arange(n), gains, "operating_initial")
    initial_j, initial_gains = current_j.copy(), gains.copy()
    best_j = np.where(finite, current_j, np.inf)
    best_gains = gains.copy()
    prev_action = np.zeros((n, 3))
    prev_cost = np.zeros(n)
    done = np.zeros(n, bool)
    reasons = np.full(n, "horizon", dtype=object)
    # Unknown operating observations must not silently look like a harm-free
    # trajectory. Diagnostics remain separate and are flagged in their rows.
    any_harm, any_harm2 = ~finite.copy(), ~finite.copy()
    history = [[{"stage": -1, "gains": gains[i].tolist(), "cost": _number(current_j[i]),
                 "observed_finite": bool(finite[i])}] for i in range(n)]

    def record(i, stage, reason, **fields):
        item = {"plant_index": int(i), "plant_identity": int(identity[i]), "stage": int(stage),
                "gains_before": gains[i].tolist(), "cost_before": _number(current_j[i]),
                "gains_proposed": None, "proposed_step": None, "applied_step": None,
                "choice_probabilities": None, "features": None, "probabilities": None,
                "qhat": None, "qhat_full_set": False, "prediction_set": None, "accepted": None,
                "proposal_valid": False, "measured": False, "executed": False,
                "measurement_kind": None, "cost_after": None, "label": None,
                "observed_finite": None, "harmful": None, "harmful_gt2pct": None,
                "reason": reason}
        item.update(fields)
        transitions.append(item)
        return item

    for stage in range(horizon):
        active = np.flatnonzero(~done)
        if not active.size:
            break
        safety = unstable[active] | (current_j[active] > np.maximum(3. * best_j[active] + 1., 8.))
        for i in active[safety]:
            reasons[i] = "unstable" if unstable[i] else "safety_threshold"
            record(i, stage, reasons[i])
            done[i] = True
        idx = active[~safety]
        if not idx.size:
            continue
        feats, curves = build_state(
            state["metrics"][idx], state["y_curve"][idx], state["u_curve"][idx],
            gains[idx], gzn[idx], ku[idx], tu[idx], prev_action=prev_action[idx],
            prev_cost=prev_cost[idx], cost=current_j[idx], iteration=np.full(len(idx), stage),
            horizon=10., ref=1.)
        answer = backend.answer(feats, curves)
        decision = decide(answer, getattr(backend, "space", None), use_expectation=True,
                          shrinkage=1., abstain=None, conformal=None)
        proposal = apply_step(gains[idx], decision.step)
        applied = np.log10(proposal / gains[idx])
        probabilities = np.stack([choice.probs for choice in answer.choice], axis=1)
        features = risk_features(feats, applied, probabilities)
        changed = np.any(proposal != gains[idx], axis=1)
        rows = {}
        for j, i in enumerate(idx):
            rows[int(i)] = record(i, stage, "proposal" if changed[j] else "no_action",
                proposal_valid=True, gains_proposed=proposal[j].tolist(),
                proposed_step=decision.step[j].tolist(), applied_step=applied[j].tolist(),
                choice_probabilities=probabilities[j].tolist(), features=features[j].tolist())
            if not changed[j]:
                done[i] = True
                reasons[i] = "no_action"
        reached = idx[changed]
        if not reached.size:
            continue
        target_collection = mode == "collect" and stage == collect_step
        proposed_changed = proposal[changed]
        changed_features = features[changed]
        if target_collection:
            accepted = np.zeros(len(reached), bool)
            execute = np.zeros(len(reached), bool)
            buckets = [(np.ones(len(reached), bool), "diagnostic_collected")]
        else:
            risk_p = np.asarray(risk_model.probabilities(changed_features), float)
            if (risk_p.shape != (len(reached), 2) or not np.isfinite(risk_p).all()
                    or (risk_p < 0).any() or (risk_p > 1).any()
                    or not np.allclose(risk_p.sum(axis=1), 1., atol=1e-10)):
                raise ValueError("risk model must return normalized finite binary probabilities")
            # Score-space comparison retains exact calibration-score ties.
            # Algebraically this is p >= 1-q, including equality.
            sets = (1. - risk_p) <= q[stage]
            accepted = joint_acceptance(sets)
            execute = np.ones(len(reached), bool) if mode == "monitor" else accepted
            for j, i in enumerate(reached):
                rows[int(i)].update(probabilities=risk_p[j].tolist(), prediction_set=sets[j].tolist(),
                    accepted=bool(accepted[j]), qhat=_number(q[stage]), qhat_full_set=bool(q[stage] >= 1.))
            buckets = [(execute, "executed")]
            if diagnostic:
                buckets.append((~execute, "diagnostic_rejected"))

        # Rejection stops regardless of whether its optional label is measured.
        for j, i in enumerate(reached):
            if target_collection or not execute[j]:
                done[i] = True
                reasons[i] = "collected" if target_collection else "risk_rejected"
                rows[int(i)]["reason"] = reasons[i]

        for selection, bucket in buckets:
            ids = reached[selection]
            if not ids.size:
                continue
            candidate = proposed_changed[selection]
            observed, costs, valid_observation, diverged = measure(ids, candidate, bucket)
            for j, i in enumerate(ids):
                row = rows[int(i)]
                before = current_j[i]
                label = int(costs[j] > before) if np.isfinite(costs[j]) else None
                harm2 = bool(costs[j] > before * 1.02) if label is not None else None
                row.update(measured=True, measurement_kind=bucket, cost_after=_number(costs[j]),
                           label=label, observed_finite=bool(valid_observation[j]),
                           harmful=None if label is None else bool(label), harmful_gt2pct=harm2)
                if bucket == "diagnostic_collected":
                    collected["features"].append(row["features"])
                    collected["labels"].append(label)
                    collected["current_cost"].append(row["cost_before"])
                    collected["proposed_cost"].append(row["cost_after"])
                    collected["plant_index"].append(int(i))
                    collected["plant_identity"].append(int(identity[i]))
                    collected["stage"].append(int(stage))
                if bucket != "executed":
                    continue
                row["executed"] = True
                row["reason"] = "executed"
                prev_action[i], prev_cost[i] = np.asarray(row["applied_step"]), before
                gains[i], current_j[i] = candidate[j], costs[j]
                finite[i], unstable[i] = valid_observation[j], diverged[j]
                for key in ("metrics", "y_curve", "u_curve"):
                    state[key][i] = observed[key][j]
                any_harm[i] |= bool(label) if valid_observation[j] and label is not None else True
                any_harm2[i] |= bool(harm2) if valid_observation[j] and harm2 is not None else True
                if valid_observation[j] and costs[j] < best_j[i]:
                    best_j[i], best_gains[i] = costs[j], candidate[j]
                history[i].append({"stage": int(stage), "gains": gains[i].tolist(),
                                   "cost": _number(current_j[i]), "observed_finite": bool(finite[i])})
                if unstable[i] or current_j[i] > max(3. * best_j[i] + 1., 8.):
                    done[i] = True
                    reasons[i] = "unstable" if unstable[i] else "safety_threshold"
                    row["reason"] = "executed_" + reasons[i]

    per_plant = [{"plant_index": i, "plant_identity": int(identity[i]),
        "initial_J": _number(initial_j[i]), "initial_gains": initial_gains[i].tolist(),
        "best_J": _number(best_j[i]), "best_gains": best_gains[i].tolist(),
        "best_valid": bool(np.isfinite(best_j[i])), "current_J": _number(current_j[i]),
        "current_gains": gains[i].tolist(), "stop_reason": str(reasons[i]),
        "any_harm": bool(any_harm[i]), "any_harm_gt2pct": bool(any_harm2[i]),
        "simulation_counts": _counts(counts[i]), "operating_history": history[i]}
        for i in range(n)]
    return {"mode": mode, "horizon": int(horizon), "n_plants": n, "per_plant": per_plant,
            "transitions": transitions, "collected": collected,
            "simulation_counts": _counts(counts.sum(axis=0))}


__all__ = ["run_joint_rollout"]
