"""Research-only risk prediction for a fixed, complete joint PID proposal.

This module does not alter the production decoder. Split-CP predicts the actual
paired-cost label, not a teacher's action label. Admitting only {noninferior}
makes harmful execution a subset of label miscoverage. Its marginal bound is
for one exchangeable initial state; it is not a conditional or rollout bound.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .primitives import softmax

NONINFERIOR = 0
HARMFUL = 1


def paired_cost_labels(current_cost, proposed_cost):
    """Zero tolerance: 0 iff the full proposal does not increase measured J."""
    before, after = np.asarray(current_cost, float), np.asarray(proposed_cost, float)
    if before.ndim != 1 or before.shape != after.shape:
        raise ValueError('paired costs must be matching one-dimensional arrays')
    if not np.isfinite(before).all() or not np.isfinite(after).all():
        raise ValueError('paired costs must be finite')
    return (after > before).astype(np.int64)


def risk_features(state_features, applied_step, choice_probs):
    """Fixed 44 features: 20 state descriptors, 3 full steps, 3x7 probabilities."""
    state, step, probs = (np.asarray(x, dtype=float) for x in
                           (state_features, applied_step, choice_probs))
    if state.ndim != 2 or state.shape[1] != 20:
        raise ValueError('state features must have shape (N,20)')
    n = len(state)
    if step.shape != (n,3) or probs.shape != (n,3,7):
        raise ValueError('joint step/probabilities must have shapes (N,3)/(N,3,7)')
    if not all(np.isfinite(x).all() for x in (state,step,probs)):
        raise ValueError('risk features must be finite')
    if (probs < 0).any() or (probs > 1).any() or not np.allclose(probs.sum(-1),1.,atol=1e-10):
        raise ValueError('choice probabilities must be normalized')
    return np.column_stack([state,step,probs.reshape(n,-1)])


@dataclass
class JointRiskModel:
    mean: np.ndarray
    scale: np.ndarray
    coefficient: np.ndarray
    intercept: float
    temperature: float = 1.0

    @classmethod
    def fit(cls, features, labels):
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        x, y = np.asarray(features,float), np.asarray(labels)
        if x.ndim != 2 or x.shape[1] != 44 or not np.isfinite(x).all():
            raise ValueError('training features must be finite (N,44)')
        if y.shape != (len(x),) or not np.array_equal(np.unique(y),[0,1]):
            raise ValueError('training labels must contain both binary classes')
        scaler = StandardScaler().fit(x)
        estimator = LogisticRegression(C=1., solver='lbfgs', max_iter=2000,
                                       random_state=72601).fit(scaler.transform(x),y)
        if estimator.n_iter_.max() >= 2000:
            raise RuntimeError('pre-registered logistic optimizer did not converge')
        return cls(scaler.mean_.copy(),scaler.scale_.copy(),
                   estimator.coef_[0].copy(),float(estimator.intercept_[0]))

    def logits(self, features):
        x = np.asarray(features,float)
        if x.ndim != 2 or x.shape[1] != len(self.mean) or not np.isfinite(x).all():
            raise ValueError('prediction features have invalid shape or values')
        z = ((x-self.mean)/self.scale) @ self.coefficient + self.intercept
        return np.column_stack([np.zeros(len(z)),z])

    def probabilities(self, features):
        if not np.isfinite(self.temperature) or self.temperature <= 0:
            raise ValueError('temperature must be finite and positive')
        return softmax(self.logits(features),axis=-1,temperature=self.temperature)

    def as_dict(self):
        return {'classes':['noninferior','harmful'],
                'mean':self.mean.tolist(),'scale':self.scale.tolist(),
                'coefficient':self.coefficient.tolist(),'intercept':self.intercept,
                'temperature':float(self.temperature)}


def joint_acceptance(prediction_set):
    mask = np.asarray(prediction_set)
    if mask.dtype != bool or mask.ndim != 2 or mask.shape[1] != 2:
        raise ValueError('binary prediction set must be a boolean (N,2) array')
    return mask[:,NONINFERIOR] & ~mask[:,HARMFUL]


def select_joint_gains(current, proposed, prediction_set):
    """Return the entire assessed proposal or the exact current gain vector."""
    before, after = np.asarray(current,float), np.asarray(proposed,float)
    accepted = joint_acceptance(prediction_set)
    if before.shape != (len(accepted),3) or after.shape != before.shape:
        raise ValueError('current/proposed gains must have matching (N,3) shapes')
    if not np.isfinite(before).all() or not np.isfinite(after).all():
        raise ValueError('gains must be finite')
    return np.where(accepted[:,None],after,before)


def risk_report(probabilities, labels, prediction_set, current_cost, proposed_cost):
    p, y, mask = np.asarray(probabilities,float), np.asarray(labels), np.asarray(prediction_set)
    accepted = joint_acceptance(mask)
    before, after = np.asarray(current_cost,float),np.asarray(proposed_cost,float)
    actual_labels = paired_cost_labels(before,after)
    if (y.shape != (len(mask),) or not np.issubdtype(y.dtype,np.integer)
            or not np.array_equal(y,actual_labels) or p.shape != mask.shape):
        raise ValueError('labels/probabilities must match the evaluated paired actions')
    covered = mask[np.arange(len(y)),y]
    harmful_execution = accepted & (y == HARMFUL)
    if np.any(harmful_execution & covered):
        raise AssertionError('harmful execution must be a subset of miscoverage')
    selected = np.where(accepted,after,before)
    delta = selected-before
    def cost_summary(cost):
        return {'mean':float(np.mean(cost)),'median':float(np.median(cost)),
                'p90':float(np.percentile(cost,90))}
    return {
        'n':len(y),'n_accepted':int(accepted.sum()),'execution_rate':float(accepted.mean()),
        'label_coverage':float(covered.mean()),'mean_set_size':float(mask.sum(-1).mean()),
        'empty_set_count':int((mask.sum(-1)==0).sum()),
        'set_counts':{'empty':int((~mask.any(-1)).sum()),
                      'noninferior_only':int((mask[:,0]&~mask[:,1]).sum()),
                      'harmful_only':int((~mask[:,0]&mask[:,1]).sum()),
                      'both':int(mask.all(-1).sum())},
        'miscoverage_count':int((~covered).sum()),
        'harmful_execution_count':int(harmful_execution.sum()),
        'unconditional_harmful_execution_rate':float(harmful_execution.mean()),
        'conditional_harmful_rate':float(harmful_execution.sum()/accepted.sum()) if accepted.any() else None,
        'harmful_execution_subset_miscoverage':bool(np.all(~harmful_execution | ~covered)),
        'proposal_harmful_rate':float((y==HARMFUL).mean()),
        'rejected_noninferior_count':int((~accepted & (y==NONINFERIOR)).sum()),
        'rejected_harmful_count':int((~accepted & (y==HARMFUL)).sum()),
        'current_cost':cost_summary(before),'always_propose_cost':cost_summary(after),
        'selected_cost':cost_summary(selected),
        'selected_minus_current':{'mean':float(delta.mean()),'median':float(np.median(delta)),
             'p90':float(np.percentile(delta,90)),
             'improved_count':int((delta<0).sum()),'unchanged_count':int((delta==0).sum()),
             'worse_count':int((delta>0).sum())},
        'selected_vs_always_propose':{
             'mean_J_difference':float(selected.mean()-after.mean()),
             'median_J_difference':float(np.median(selected)-np.median(after)),
             'p90_J_difference':float(np.percentile(selected,90)-np.percentile(after,90)),
             'paired_delta_median':float(np.median(selected-after))},
    }
