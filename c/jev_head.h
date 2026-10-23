/*
 * jev_head.h -- C99 reference implementation of the jev-tune decision step.
 *
 * Scope: inference only.  No training, no plant simulation, no dynamic memory,
 * no libm beyond expf/log10f/isfinitef (C99 math).  Fixed-size arrays only.
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

#define JEV_N_FEATS 20
#define JEV_N_CURVE 64
#define JEV_K 7
#define JEV_N_SCORE 5
#define JEV_N_METRICS 10
#define JEV_MAX_STEP 0.32f
#define JEV_GAIN_LO 1e-4f
#define JEV_GAIN_HI 1e3f

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
    int held;            /* 1 when the decode chose "hold" on every axis */
    float confidence[3]; /* max probability per axis */
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
