/* Deterministic policy boundaries from the same language-neutral JSON. */
#include <stdio.h>
#include "jev_head.h"
#include "test_common.h"
#include "test_policy.h"

int main(void) {
    int c, ax, i, failures = 0;
    for (c = 0; c < JEV_PC_N; ++c) {
        jev_probs p;
        jev_action a;
        jev_policy pol;
        jev_conformal cp;
        int escalations = 0, expected_escalations = 0;
        pol.tau_act = JEV_PC_POLICY[c][0];
        pol.tau_esc = JEV_PC_POLICY[c][1];
        pol.tau_noul = JEV_PC_POLICY[c][2];
        cp.enabled = (int)JEV_PC_CP_ENABLED[c][0];
        cp.k_max = (int)JEV_PC_CP_K_MAX[c][0];
        for (ax = 0; ax < 3; ++ax) cp.qhat[ax] = JEV_PC_CP_QHAT[c][ax];
        for (ax = 0; ax < 3; ++ax)
            for (i = 0; i < JEV_K; ++i) p.choice[ax][i] = JEV_PC_PROBS[c][ax * JEV_K + i];
        for (i = 0; i < JEV_N_SCORE; ++i) p.score[i] = JEV_PC_SCORE[c][i];
        p.noul = JEV_PC_NOUL[c][0];
        jev_decode(&p, &a);
        jev_abstain(&a, &p, &pol, &escalations);
        jev_apply_conformal(&a, &p, &cp, &escalations);
        for (ax = 0; ax < 3; ++ax) {
            if (finite_diff(a.step[ax], JEV_PC_STEP[c][ax]) > 1e-5f ||
                finite_diff(a.proposed[ax], JEV_PC_PROPOSED[c][ax]) > 1e-5f ||
                a.axis_held[ax] != (int)JEV_PC_HELD[c][ax] ||
                a.escalate[ax] != (int)JEV_PC_ESCALATE[c][ax] ||
                a.reason[ax] != (int)JEV_PC_REASON[c][ax]) failures++;
            if (a.set_size[ax] != (int)JEV_PC_SET_SIZE[c][ax]) failures++;
            for (i = 0; i < JEV_K; ++i)
                if (a.conformal_set[ax][i] != (int)JEV_PC_CONFORMAL_SET[c][ax * JEV_K + i]) failures++;
            expected_escalations += (int)JEV_PC_ESCALATE[c][ax];
        }
        if (escalations != expected_escalations ||
            a.conformal_applied != cp.enabled ||
            a.held != (a.axis_held[0] && a.axis_held[1] && a.axis_held[2]) ||
            jev_should_stop(&p, 0) != (int)JEV_PC_STOP[c][0]) failures++;
        if (jev_should_stop(&p, 1)) failures++;
        jev_decode_argmax(&p, &a);
        jev_abstain(&a, &p, &pol, 0);
        jev_apply_conformal(&a, &p, &cp, 0);
        for (ax = 0; ax < 3; ++ax)
            if (finite_diff(a.step[ax], JEV_PC_ARGMAX_STEP[c][ax]) > 1e-5f) failures++;
    }
    for (c = 0; c < JEV_GC_N; ++c)
        if (jev_gate_rollback(JEV_GC[c][0], JEV_GC[c][1], (int)JEV_GC[c][2],
                              (int)JEV_GC[c][3]) != (int)JEV_GC[c][4]) failures++;
    for (c = 0; c < JEV_AC_N; ++c) {
        float gains[3];
        for (ax = 0; ax < 3; ++ax) gains[ax] = JEV_AC_GAINS[c][ax];
        jev_apply_step(gains, JEV_AC_STEP[c]);
        for (ax = 0; ax < 3; ++ax)
            if (finite_diff(gains[ax], JEV_AC_EXPECTED[c][ax]) >
                1e-5f * (1 + fabsf(JEV_AC_EXPECTED[c][ax]))) failures++;
    }
    /* The checker itself must reject every non-finite pairing. */
    if (finite_diff(NAN, 0) <= 1 || finite_diff(0, NAN) <= 1 ||
        finite_diff(INFINITY, INFINITY) <= 1) failures++;
    printf("policy_cases %d gate_cases %d apply_cases %d failures %d\n",
           JEV_PC_N, JEV_GC_N, JEV_AC_N, failures);
    return failures ? 1 : 0;
}
