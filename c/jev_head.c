/*
 * jev_head.c -- see jev_head.h.  No allocation, no global mutable state.
 *
 * Layout note: PyTorch stores conv weights as (out, in, k) and linear weights as
 * (out, in); the exported arrays keep that order, so the loops below index them
 * directly without transposing.
 */
#include "jev_head.h"

#include <math.h>
#include <stddef.h>

#include "jev_head_weights.h"

#define CV1_OUT 16
#define CV2_OUT 32
#define CV1_LEN 32 /* floor((64 + 2*2 - 5)/2) + 1 */
#define CV2_LEN 16 /* floor((32 + 2*2 - 5)/2) + 1 */
#define HIDDEN 128

static float relu(float x) { return x > 0.0f ? x : 0.0f; }

static float clipf(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

static float safe_log10(float x) {
    return log10f(x > 1e-9f ? x : 1e-9f);
}

static void conv1d(const float *x, int in_ch, int in_len, const float *w,
                   const float *b, int out_ch, int k, int stride, int pad,
                   float *y, int out_len) {
    int oc, i, ic, kk;
    for (oc = 0; oc < out_ch; ++oc) {
        for (i = 0; i < out_len; ++i) {
            float acc = b[oc];
            for (ic = 0; ic < in_ch; ++ic) {
                for (kk = 0; kk < k; ++kk) {
                    int idx = i * stride - pad + kk;
                    if (idx >= 0 && idx < in_len) {
                        acc += w[(oc * in_ch + ic) * k + kk] *
                               x[ic * in_len + idx];
                    }
                }
            }
            y[oc * out_len + i] = relu(acc);
        }
    }
}

static void linear(const float *x, int n_in, const float *w, const float *b,
                   int n_out, float *y, int relu_out) {
    int o, i;
    for (o = 0; o < n_out; ++o) {
        float acc = b[o];
        const float *row = w + (size_t)o * (size_t)n_in;
        for (i = 0; i < n_in; ++i) {
            acc += row[i] * x[i];
        }
        y[o] = relu_out ? relu(acc) : acc;
    }
}

void jev_forward(const jev_state *s, jev_logits *out) {
    float c_in[2 * JEV_N_CURVE];
    float c1[CV1_OUT * CV1_LEN];
    float c2[CV2_OUT * CV2_LEN];
    float pooled[CV2_OUT];
    float m1[64], m2[64], t1[HIDDEN], t2[HIDDEN];
    float concat[CV2_OUT + 64];
    int ch, i;

    for (ch = 0; ch < 2; ++ch) {
        for (i = 0; i < JEV_N_CURVE; ++i) {
            c_in[ch * JEV_N_CURVE + i] = s->curves[ch][i];
        }
    }
    conv1d(c_in, 2, JEV_N_CURVE, jev_w_cv1, jev_b_cv1, CV1_OUT, 5, 2, 2, c1,
           CV1_LEN);
    conv1d(c1, CV1_OUT, CV1_LEN, jev_w_cv2, jev_b_cv2, CV2_OUT, 5, 2, 2, c2,
           CV2_LEN);

    /* adaptive average pool over the remaining length -> one value per channel */
    for (ch = 0; ch < CV2_OUT; ++ch) {
        float acc = 0.0f;
        for (i = 0; i < CV2_LEN; ++i) {
            acc += c2[ch * CV2_LEN + i];
        }
        pooled[ch] = acc / (float)CV2_LEN;
    }

    linear(s->feats, JEV_N_FEATS, jev_w_mlp1, jev_b_mlp1, 64, m1, 1);
    linear(m1, 64, jev_w_mlp2, jev_b_mlp2, 64, m2, 1);

    for (i = 0; i < CV2_OUT; ++i) {
        concat[i] = pooled[i];
    }
    for (i = 0; i < 64; ++i) {
        concat[CV2_OUT + i] = m2[i];
    }
    linear(concat, CV2_OUT + 64, jev_w_tr1, jev_b_tr1, HIDDEN, t1, 1);
    linear(t1, HIDDEN, jev_w_tr2, jev_b_tr2, HIDDEN, t2, 1);

    for (ch = 0; ch < 3; ++ch) {
        switch (ch) {
            case 0:
                linear(t2, HIDDEN, jev_w_ch0, jev_b_ch0, JEV_K, out->choice[0], 0);
                break;
            case 1:
                linear(t2, HIDDEN, jev_w_ch1, jev_b_ch1, JEV_K, out->choice[1], 0);
                break;
            default:
                linear(t2, HIDDEN, jev_w_ch2, jev_b_ch2, JEV_K, out->choice[2], 0);
                break;
        }
    }
    linear(t2, HIDDEN, jev_w_score, jev_b_score, JEV_N_SCORE, out->score, 0);
    linear(t2, HIDDEN, jev_w_noul, jev_b_noul, 1, &out->noul_logit, 0);
}

static void softmax(const float *z, int n, float *p) {
    float mx = z[0], sum = 0.0f;
    int i;
    for (i = 1; i < n; ++i) {
        if (z[i] > mx) mx = z[i];
    }
    for (i = 0; i < n; ++i) {
        p[i] = expf(z[i] - mx);
        sum += p[i];
    }
    for (i = 0; i < n; ++i) {
        p[i] /= sum;
    }
}

void jev_answer(const jev_logits *logits, const float temperature[3],
                jev_probs *out) {
    float z[JEV_K];
    int ax, i;
    for (ax = 0; ax < 3; ++ax) {
        float t = temperature[ax] > 1e-6f ? temperature[ax] : 1e-6f;
        for (i = 0; i < JEV_K; ++i) {
            z[i] = logits->choice[ax][i] / t;
        }
        softmax(z, JEV_K, out->choice[ax]);
    }
    softmax((const float *)logits->score, JEV_N_SCORE, out->score);
    out->noul = 1.0f / (1.0f + expf(-logits->noul_logit));
}

/* The Python vocabulary: multiplicative steps around 1.0, log-spaced. */
static const float JEV_MULT[JEV_K] = {0.50f, 0.70f, 0.87f, 1.00f,
                                      1.15f, 1.43f, 2.00f};

static float population_var(void) {
    float d[JEV_K], mean = 0.0f, acc = 0.0f;
    int i;
    for (i = 0; i < JEV_K; ++i) {
        d[i] = log10f(JEV_MULT[i]);
        mean += d[i];
    }
    mean /= (float)JEV_K;
    for (i = 0; i < JEV_K; ++i) {
        acc += (d[i] - mean) * (d[i] - mean);
    }
    return acc / (float)JEV_K; /* population variance, no mutable static state */
}

void jev_decode(const jev_probs *p, jev_action *out) {
    float var_ref = population_var();
    int ax, i;
    for (ax = 0; ax < 3; ++ax) {
        float mu = 0.0f, e2 = 0.0f, var, gate, conf = 0.0f;
        for (i = 0; i < JEV_K; ++i) {
            float d = log10f(JEV_MULT[i]);
            mu += p->choice[ax][i] * d;
            e2 += p->choice[ax][i] * d * d;
            if (p->choice[ax][i] > conf) conf = p->choice[ax][i];
        }
        var = e2 - mu * mu;
        if (var < 0.0f) var = 0.0f;
        gate = 1.0f / (1.0f + var / var_ref);
        out->step[ax] = clipf(mu * gate, -JEV_MAX_STEP, JEV_MAX_STEP);
        out->proposed[ax] = out->step[ax];
        out->confidence[ax] = conf;
        out->axis_held[ax] = out->escalate[ax] = out->reason[ax] = 0;
        out->set_size[ax] = 0;
        out->conformal_would_hold[ax] = out->conformal_reason[ax] = 0;
        for (i = 0; i < JEV_K; ++i) out->conformal_set[ax][i] = 0;
    }
    out->held = 0;
    out->conformal_applied = 0;
    out->conformal_mode = JEV_CP_OFF;
}

void jev_decode_argmax(const jev_probs *p, jev_action *out) {
    int ax, i;
    for (ax = 0; ax < 3; ++ax) {
        int best = 0;
        float conf = 0.0f;
        for (i = 0; i < JEV_K; ++i) {
            if (p->choice[ax][i] > p->choice[ax][best]) best = i;
            if (p->choice[ax][i] > conf) conf = p->choice[ax][i];
        }
        out->step[ax] = clipf(log10f(JEV_MULT[best]), -JEV_MAX_STEP,
                              JEV_MAX_STEP);
        out->proposed[ax] = out->step[ax];
        out->confidence[ax] = conf;
        out->axis_held[ax] = out->escalate[ax] = out->reason[ax] = 0;
        out->set_size[ax] = 0;
        out->conformal_would_hold[ax] = out->conformal_reason[ax] = 0;
        for (i = 0; i < JEV_K; ++i) out->conformal_set[ax][i] = 0;
    }
    out->held = 0;
    out->conformal_applied = 0;
    out->conformal_mode = JEV_CP_OFF;
}

int jev_gate_rollback(float cost, float best_cost, int rollbacks,
                      int max_rollbacks) {
    float threshold = 3.0f * best_cost + 1.0f;
    if (threshold < 8.0f) threshold = 8.0f;
    return (cost > threshold) && (rollbacks < max_rollbacks);
}

void jev_abstain(jev_action *act, const jev_probs *p, const jev_policy *pol,
                 int *escalations) {
    int ax, i;
    for (ax = 0; ax < 3; ++ax) {
        float conf = 0.0f;
        int low, unsafe;
        for (i = 0; i < JEV_K; ++i) {
            if (p->choice[ax][i] > conf) conf = p->choice[ax][i];
        }
        low = pol != 0 && conf < pol->tau_act;
        unsafe = pol != 0 && p->noul < pol->tau_noul;
        act->axis_held[ax] = low || unsafe;
        act->escalate[ax] = act->axis_held[ax] && conf < pol->tau_esc;
        act->reason[ax] = unsafe ? 3 : (act->escalate[ax] ? 2 : (low ? 1 : 0));
        if (act->axis_held[ax]) {
            act->step[ax] = 0.0f;
            if (escalations != 0 && act->escalate[ax]) {
                (*escalations)++;
            }
        }
    }
    act->held = act->axis_held[0] && act->axis_held[1] && act->axis_held[2];
}

int jev_apply_conformal(jev_action *act, const jev_probs *p,
                         const jev_conformal *cp, int *escalations) {
    int ax, i, invalid = 0;
    if (cp != 0 && cp->enabled) {
        invalid = (cp->mode != JEV_CP_MONITOR && cp->mode != JEV_CP_HARD_HOLD) || cp->k_max < 1;
        for (ax = 0; ax < 3; ++ax)
            invalid |= !isfinite(cp->qhat[ax]) || cp->qhat[ax] < 0.0 || cp->qhat[ax] > 1.0;
    }
    if (invalid) {
        act->conformal_applied = 0;
        act->conformal_mode = JEV_CP_OFF;
        for (ax = 0; ax < 3; ++ax) {
            if (!act->escalate[ax] && escalations != 0) (*escalations)++;
            act->axis_held[ax] = act->escalate[ax] = 1;
            act->step[ax] = 0.0f;
            if (act->reason[ax] != 3) act->reason[ax] = 7;
            act->set_size[ax] = act->conformal_would_hold[ax] = act->conformal_reason[ax] = 0;
            for (i = 0; i < JEV_K; ++i) act->conformal_set[ax][i] = 0;
        }
        act->held = 1;
        return -1;
    }
    act->conformal_applied = cp != 0 && cp->enabled;
    act->conformal_mode = act->conformal_applied ? cp->mode : JEV_CP_OFF;
    for (ax = 0; ax < 3; ++ax) {
        int n = 0, positive = 0, negative = 0, reason = 0;
        for (i = 0; i < JEV_K; ++i) {
            int selected = act->conformal_applied && (1.0 - (double)p->choice[ax][i]) <= cp->qhat[ax];
            act->conformal_set[ax][i] = selected;
            if (selected) {
                n++;
                positive |= JEV_MULT[i] > 1.0f;
                negative |= JEV_MULT[i] < 1.0f;
            }
        }
        act->set_size[ax] = n;
        act->conformal_would_hold[ax] = act->conformal_reason[ax] = 0;
        if (!act->conformal_applied) continue;
        if (n == 0) reason = 4;
        else if (n > cp->k_max) reason = 5;
        else if (positive && negative) reason = 6;
        act->conformal_would_hold[ax] = reason != 0;
        act->conformal_reason[ax] = reason;
        if (reason && cp->mode == JEV_CP_HARD_HOLD) {
            if (!act->escalate[ax] && escalations != 0) (*escalations)++;
            act->axis_held[ax] = act->escalate[ax] = 1;
            act->step[ax] = 0.0f;
            if (act->reason[ax] != 3) act->reason[ax] = reason;
        }
    }
    act->held = act->axis_held[0] && act->axis_held[1] && act->axis_held[2];
    return 0;
}

void jev_apply_step(float gains[3], const float step[3]) {
    int i;
    for (i = 0; i < 3; ++i) {
        gains[i] = clipf(gains[i] * powf(10.0f, step[i]), JEV_GAIN_LO,
                         JEV_GAIN_HI);
    }
}

int jev_should_stop(const jev_probs *p, int best_band) {
    int i, arg = 0;
    for (i = 1; i < JEV_N_SCORE; ++i) {
        if (p->score[i] > p->score[arg]) arg = i;
    }
    return (arg == best_band) && (p->noul > 0.9f);
}

void jev_build_state(const float metrics[JEV_N_METRICS],
                     const float y_trace[JEV_N_CURVE],
                     const float u_trace[JEV_N_CURVE], const float gains[3],
                     const float gains_zn[3], float ku, float tu,
                     const float prev_action[3], float prev_cost, float cost,
                     float iteration, float horizon, float ref,
                     jev_state *out) {
    float max_abs_y = 0.0f;
    int i;

    for (i = 0; i < JEV_N_CURVE; ++i) {
        float ay = fabsf(y_trace[i]);
        if (ay > max_abs_y) max_abs_y = ay;
        out->curves[0][i] = y_trace[i] / ref;
        out->curves[1][i] = u_trace[i];
    }

    out->feats[0] = clipf(metrics[0], -1.0f, 3.0f);
    out->feats[1] = clipf(metrics[1] / horizon, 0.0f, 2.0f);
    out->feats[2] = clipf(metrics[2] / horizon, 0.0f, 2.0f);
    out->feats[3] = clipf(metrics[3], -3.0f, 3.0f);
    out->feats[4] = clipf(safe_log10(metrics[4]), -9.0f, 3.0f) / 3.0f;
    out->feats[5] =
        clipf(safe_log10(metrics[5] / (ref * horizon * horizon)), -9.0f, 3.0f) /
        3.0f;
    out->feats[6] = clipf(metrics[6] / 5.0f, 0.0f, 4.0f);
    out->feats[7] = clipf(metrics[7], 0.0f, 1.0f);
    out->feats[8] = clipf(metrics[8], 0.0f, 3.0f);
    out->feats[9] = clipf(max_abs_y / (ref > 1e-9f ? ref : 1e-9f), 0.0f, 12.0f) / 12.0f;
    out->feats[10] =
        clipf(safe_log10(gains[0] / (gains_zn[0] > 1e-9f ? gains_zn[0] : 1e-9f)),
              -3.0f, 3.0f) /
        3.0f;
    out->feats[11] =
        clipf(safe_log10((gains[1] + 1e-6f) / (gains_zn[1] + 1e-6f)), -3.0f,
              3.0f) /
        3.0f;
    out->feats[12] =
        clipf(safe_log10((gains[2] + 1e-6f) / (gains_zn[2] + 1e-6f)), -3.0f,
              3.0f) /
        3.0f;
    out->feats[13] = clipf(prev_action[0], -0.5f, 0.5f) * 4.0f;
    out->feats[14] = clipf(prev_action[1], -0.5f, 0.5f) * 4.0f;
    out->feats[15] = clipf(prev_action[2], -0.5f, 0.5f) * 4.0f;
    out->feats[16] = clipf((prev_cost - cost) / 5.0f, -3.0f, 3.0f);
    out->feats[17] = clipf(iteration / 20.0f, 0.0f, 1.0f);
    out->feats[18] =
        clipf(safe_log10(ku / (gains[0] > 1e-9f ? gains[0] : 1e-9f)), -3.0f,
              3.0f) /
        3.0f;
    out->feats[19] = clipf(tu / horizon, 0.0f, 5.0f) / 5.0f;

    /* numpy.nan_to_num: nan -> 0, +inf -> 3, -inf -> -3 */
    for (i = 0; i < JEV_N_FEATS; ++i) {
        float v = out->feats[i];
        if (isnan(v)) {
            out->feats[i] = 0.0f;
        } else if (isinf(v)) {
            out->feats[i] = (v > 0.0f) ? 3.0f : -3.0f;
        }
    }
}

/* numpy.round() is round-half-to-even; lroundf is half-away-from-zero. */
static int round_half_even(float x) {
    float fl = floorf(x);
    float diff = x - fl;
    int n = (int)fl;
    if (diff > 0.5f) {
        return n + 1;
    }
    if (diff < 0.5f) {
        return n;
    }
    return (n % 2 == 0) ? n : n + 1;
}

void jev_resample(const float *y, const float *u, int n, float *y_out,
                  float *u_out) {
    int c;
    if (n <= 0) {
        for (c = 0; c < JEV_N_CURVE; ++c) {
            y_out[c] = 0.0f;
            u_out[c] = 0.0f;
        }
        return;
    }
    for (c = 0; c < JEV_N_CURVE; ++c) {
        /* same index sequence as np.linspace(0, n-1, 64) */
        float pos = (n == 1) ? 0.0f
                             : (float)c * (float)(n - 1) / (float)(JEV_N_CURVE - 1);
        int idx = round_half_even(pos);
        if (idx < 0) idx = 0;
        if (idx >= n) idx = n - 1;
        y_out[c] = y[idx];
        u_out[c] = u[idx];
    }
}
