/*
 * jev_head.h -- C99 reference implementation of the jev-tune decision step.
 *
 * Scope: inference only.  No training, no plant simulation, no dynamic memory,
 * only standard C99/libm calls. Fixed-size arrays only.
 *
 * The Python package (`src/jev_tune`) remains the authority; this file exists so
 * that a port to C, C++, Rust or MicroPython can be checked against the same
 * numbers.  See c/README.md and docs/TRANSFER.md.
 *
 * Correctness is defined by `c/test_vectors.json` (language-neutral) and
 * `c/test_vectors.h` (the same values as C arrays): inputs, logits,
 * probabilities and the decoded step, with tolerances.
 */
#ifndef JEV_HEAD_H
#define JEV_HEAD_H

#include <float.h>
#if FLT_RADIX != 2 || FLT_MANT_DIG != 24 || DBL_MANT_DIG < 53
#error "jev_head requires binary32 float and at least binary64 double precision"
#endif

#define JEV_N_FEATS 20
#define JEV_N_CURVE 64
#define JEV_K 7
#define JEV_N_SCORE 5
#define JEV_N_METRICS 10
#define JEV_MAX_STEP 0.32f
#define JEV_GAIN_LO 1e-4f
#define JEV_GAIN_HI 1e3f
#define JEV_CP_MONITOR 0
#define JEV_CP_HARD_HOLD 1
#define JEV_CP_OFF -1

/* one decision state: 20 features + 2 x 64 resampled trace samples */
typedef struct {
    float feats[JEV_N_FEATS];
    float curves[2][JEV_N_CURVE];
} jev_state;

/* raw network output, before softmax */
typedef struct {
    float choice[3][JEV_K];
    float score[JEV_N_SCORE];
    float noul_logit;
} jev_logits;

/* typed answers: Choice x3, Score, Noul */
typedef struct {
    float choice[3][JEV_K]; /* probabilities, one row per gain axis */
    float score[JEV_N_SCORE];
    float noul; /* P(statement is true), already sigmoid-ed */
} jev_probs;

typedef struct {
    float step[3];       /* log10 gain steps, already clipped to +/-MAX_STEP */
    float proposed[3];   /* full-distribution proposal, before either veto */
    int held;            /* 1 only when policy vetoed all axes */
    float confidence[3]; /* max probability per axis */
    int axis_held[3];     /* policy veto, distinct from a confident zero step */
    int escalate[3];      /* held and below tau_esc */
    int reason[3];        /* 0 act, 1 low confidence, 2 escalate, 3 noul,
                            4 empty CP set, 5 oversized CP set, 6 mixed signs,
                            7 invalid conformal policy (fail closed) */
    int set_size[3];      /* conformal set size; zero when disabled */
    int conformal_set[3][JEV_K];
    int conformal_applied;
    int conformal_mode;  /* OFF, MONITOR, or HARD_HOLD */
    int conformal_would_hold[3]; /* diagnostic, even when monitor executes */
    int conformal_reason[3];     /* 0 none, 4 empty, 5 large, 6 mixed signs */
} jev_action;

/* forward pass: conv1d(2->16, k5, s2) -> conv1d(16->32, k5, s2) -> avgpool
 * -> mlp(20->64->64) -> concat -> trunk(96->128->128) -> heads */
void jev_forward(const jev_state *s, jev_logits *out);

/* temperature -> softmax / sigmoid.  `temperature` is the three fitted values
 * from models/calibration.json; pass {1,1,1} to disable calibration. */
void jev_answer(const jev_logits *logits, const float temperature[3],
                jev_probs *out);

/* expected value + variance shrink + clip (the shipped decoder) */
void jev_decode(const jev_probs *p, jev_action *out);

/* pure discrete control: argmax instead of the expectation */
void jev_decode_argmax(const jev_probs *p, jev_action *out);

/* deterministic gate: 1 means "roll back to 0.6 * best", 0 means "keep going" */
int jev_gate_rollback(float cost, float best_cost, int rollbacks,
                      int max_rollbacks);

/* explicit a-priori abstention: hold the axes whose calibrated p_max is below
 * tau_act.  Same three zones as src/jev_tune/decode.py::AbstainPolicy. */
typedef struct {
    float tau_act;
    float tau_esc;
    float tau_noul;
} jev_policy;

void jev_abstain(jev_action *act, const jev_probs *p, const jev_policy *pol,
                 int *escalations);

/* Split-conformal label sets; these quantify teacher-label coverage, not
 * closed-loop stability. Apply after the optional legacy p_max/Noul policy.
 * MONITOR preserves the action and records would_hold/reason. Only HARD_HOLD
 * vetoes and flags escalation; Noul has main-reason precedence. */
typedef struct {
    int enabled;
    double qhat[3];      /* retain near-one calibration quantiles exactly */
    int k_max;
    int mode;           /* zero initialization defaults to MONITOR */
} jev_conformal;

/* Return 0 on success, -1 for an invalid enabled policy. Invalid mode,
 * quantile or k_max holds all axes without claiming a valid prediction set. */
int jev_apply_conformal(jev_action *act, const jev_probs *p,
                         const jev_conformal *cp, int *escalations);

/* gains <- clip(gains * 10^step) */
void jev_apply_step(float gains[3], const float step[3]);

/* early stop: the response is already in the best cost band and the head
 * believes the next step is safe.  Off by default in Python; provided so a
 * port can reproduce the ablation. */
int jev_should_stop(const jev_probs *p, int best_band);

/* 20 features + 2 x 64 curves, exactly as src/jev_tune/state.py does it.
 * `metrics` are the 10 response descriptors the caller already computed. */
void jev_build_state(const float metrics[JEV_N_METRICS],
                     const float y_trace[JEV_N_CURVE],
                     const float u_trace[JEV_N_CURVE], const float gains[3],
                     const float gains_zn[3], float ku, float tu,
                     const float prev_action[3], float prev_cost, float cost,
                     float iteration, float horizon, float ref,
                     jev_state *out);

/* resample a raw trace to JEV_N_CURVE points (nearest sample, same indices as
 * numpy.linspace(0, n-1, 64).round()) */
void jev_resample(const float *y, const float *u, int n, float *y_out,
                  float *u_out);

#endif /* JEV_HEAD_H */
