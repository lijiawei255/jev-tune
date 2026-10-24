#include "jev_head.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); return 1; } } while (0)
static int closed(const jev_action *a) {
    int ax, i;
    if (!a->held || a->conformal_applied || a->conformal_mode != JEV_CP_OFF) return 0;
    for (ax = 0; ax < 3; ++ax) {
        if (a->step[ax] || a->proposed[ax] || a->confidence[ax] ||
            !a->axis_held[ax] || !a->escalate[ax] || a->reason[ax] < 8 ||
            a->set_size[ax] || a->conformal_reason[ax] || a->conformal_would_hold[ax]) return 0;
        for (i = 0; i < JEV_K; ++i) if (a->conformal_set[ax][i]) return 0;
    }
    return 1;
}
int main(void) {
    jev_state s = {{0}, {{0}}};
    jev_action a;
    jev_logits z = {{{0}}, {0}, 0};
    jev_probs p;
    jev_policy pol = {0, 0, 0};
    jev_conformal cp = {1, {.2f, .2f, .2f}, 3, JEV_CP_MONITOR};
    float t[3] = {1,1,1}, bad[] = {NAN, INFINITY, -INFINITY};
    float bad_t[] = {0, -1, NAN, INFINITY, -INFINITY};
    int i, j, ax, k;
    CHECK(jev_decide_checked(&s,t,&pol,&cp,&a) == 0);
    for (k=0;k<3;++k) {
        for(i=0;i<JEV_N_FEATS;++i) {
            s.feats[i]=bad[k]; memset(&a, 0x7f, sizeof a);
            CHECK(jev_decide_checked(&s,t,&pol,&cp,&a) != 0 && closed(&a)); s.feats[i]=0;
        }
        for(ax=0;ax<2;++ax) for(i=0;i<JEV_N_CURVE;++i) {
            s.curves[ax][i]=bad[k]; memset(&a, 0x7f, sizeof a);
            CHECK(jev_decide_checked(&s,t,&pol,&cp,&a) != 0 && closed(&a)); s.curves[ax][i]=0;
        }
    }
    for(ax=0;ax<3;++ax) for(i=0;i<5;++i) {
        t[ax]=bad_t[i]; CHECK(jev_decide_checked(&s,t,&pol,&cp,&a) != 0 && closed(&a));
        jev_answer(&z,t,&p); CHECK(isnan(p.choice[ax][0])); t[ax]=1;
    }
    for(ax=0;ax<3;++ax) t[ax]=nextafterf(0,1);
    CHECK(jev_decide_checked(&s,t,&pol,&cp,&a) == 0);
    for(ax=0;ax<3;++ax) for(i=0;i<JEV_K;++i) z.choice[ax][i]=FLT_MAX;
    for(i=0;i<JEV_N_SCORE;++i) z.score[i]=FLT_MAX;
    jev_answer(&z,t,&p);
    for(ax=0;ax<3;++ax) for(i=0;i<JEV_K;++i) CHECK(fabsf(p.choice[ax][i]-1.0f/JEV_K)<1e-7f);
    for(i=0;i<JEV_N_SCORE;++i) CHECK(fabsf(p.score[i]-.2f)<1e-7f);
    for(ax=0;ax<3;++ax) {z.choice[ax][0]=-FLT_MAX; z.choice[ax][1]=FLT_MAX;}
    jev_answer(&z,t,&p);
    for(ax=0;ax<3;++ax) CHECK(p.choice[ax][0]==0 && isfinite(p.choice[ax][1]));
    for(i=0;i<5;++i) {
        pol.tau_act=bad_t[i];
        if(i==0) pol.tau_act=2;
        CHECK(jev_decide_checked(&s,t,&pol,&cp,&a)!=0 && closed(&a));
    }
    pol.tau_act=0; pol.tau_esc=.1f;
    CHECK(jev_decide_checked(&s,t,&pol,&cp,&a)!=0 && closed(&a)); pol.tau_esc=0;
    pol.tau_noul=NAN; CHECK(jev_decide_checked(&s,t,&pol,&cp,&a)!=0 && closed(&a)); pol.tau_noul=0;
    for(j=0;j<3;++j) for(i=0;i<5;++i) {
        cp.p_min[j]=bad_t[i]; if(i==0) cp.p_min[j]=2;
        CHECK(jev_decide_checked(&s,t,&pol,&cp,&a)!=0 && closed(&a)); cp.p_min[j]=.2f;
    }
    cp.k_max=0; CHECK(jev_decide_checked(&s,t,&pol,&cp,&a)!=0 && closed(&a)); cp.k_max=3;
    cp.mode=2; CHECK(jev_decide_checked(&s,t,&pol,&cp,&a)!=0 && closed(&a)); cp.mode=0;
    cp.enabled=2; CHECK(jev_decide_checked(&s,t,&pol,&cp,&a)!=0 && closed(&a)); cp.enabled=1;
    for(i=0;i<JEV_N_FEATS;++i) s.feats[i]=FLT_MAX;
    CHECK(jev_decide_checked(&s,t,&pol,&cp,&a)==-JEV_INVALID_NUMERIC && closed(&a));
    for(i=0;i<JEV_N_FEATS;++i) s.feats[i]=0;
    for(ax=0;ax<2;++ax) for(i=0;i<JEV_N_CURVE;++i) s.curves[ax][i]=FLT_MAX;
    CHECK(jev_decide_checked(&s,t,&pol,&cp,&a)==-JEV_INVALID_NUMERIC && closed(&a));
    CHECK(jev_decide_checked(NULL,t,&pol,&cp,&a)!=0 && closed(&a));
    CHECK(jev_decide_checked(&s,NULL,&pol,&cp,&a)!=0 && closed(&a));
    CHECK(jev_decide_checked(&s,t,&pol,&cp,NULL)!=0);
    puts("checked shell: all fault and extreme-temperature cases passed");
    return 0;
}
