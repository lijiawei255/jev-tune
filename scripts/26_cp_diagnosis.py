"""Reproduce frozen-model CP mechanism diagnostics; never selects policy parameters."""
import hashlib,importlib.util,json
from argparse import Namespace
from pathlib import Path
import numpy as np
import torch
from jev_tune.decode import ActionSpace,ConformalPolicy,decide,apply_step
from jev_tune.primitives import Answer,Choice,Noul,Option,softmax
from jev_tune.expert import generate
from jev_tune.decision import load_backend
from jev_tune.evaluate import evaluate_head
from jev_tune.metrics import cost_from_metrics
from jev_tune.plants import sample_plants,ultimate_gain,simulate,HELDOUT_FAMILIES
from _experiment_protocol import manifest


def render(d):
    initial=d["initial_counterfactual"]
    cp=d["seed17_replay"]["temperature_CP"]
    temp=d["seed17_replay"]["temperature_only"]
    table="| policy | median J | actual simulations |\n| :--- | ---: | ---: |\n"
    for name,r in [("Temp Only",temp),("hard_hold repeat (historical)",cp),*d["new_policy_replay"].items()]:
        table+=f"| {name} | {r['median_final_J']:.6f} | {r['actual_simulations']} |\n"
    lines=["# CP mechanism diagnosis / CP机制诊断", "", "[English](#english) · [简体中文](#简体中文)", ""]
    for zh in (False,True):
        lines += ["## 简体中文" if zh else "## English", "",
          ("冻结原模型、温度、alpha和q_hat；重放同一seed17的120株、最大预算20。旧hard_hold重复观测是诊断对照；默认monitor保留完整集合但不否决轴。停止模式只计实际测量，不把填充历史当新观测。" if zh else
           "Frozen model, temperature, alpha and q_hat. Replay seed17 on 120 plants at maximum budget20. Historical hard_hold repeats are a diagnostic control; default monitor preserves full sets without vetoing axes. Stopping counts actual measurements, not padded history."),"",table,
          (f"旧hard_hold: 全保持{cp['all_hold_transition_count']}次；末段至少连续5次保持{cp['trailing_all_hold_at_least_5_plants']}株；不同参数组中位数{cp['unique_gain_count_median']:g}。" if zh else f"Historical hard_hold: {cp['all_hold_transition_count']} full holds; {cp['trailing_all_hold_at_least_5_plants']} plants with at least5 final holds; median unique gains {cp['unique_gain_count_median']:g}."),
          (f"冻结初态反事实：被禁轴{initial['vetoed_axis_original_step_alone']['n']}个；改善超过2%有{initial['vetoed_axis_original_step_alone']['improve_more_than_2pct_count']}个；恶化超过2%有{initial['vetoed_axis_original_step_alone']['harm_more_than_2pct_count']}个。" if zh else f"Frozen initial-state counterfactual: vetoed axes {initial['vetoed_axis_original_step_alone']['n']}; improve >2% {initial['vetoed_axis_original_step_alone']['improve_more_than_2pct_count']}; harm >2% {initial['vetoed_axis_original_step_alone']['harm_more_than_2pct_count']}."),"",
          ("专项反事实仅评价一次仿真提案，不证明长期安全。专家标签是单轴离散精确最优项，实际动作是三轴连续组合；集合覆盖不能自动转成联合动作改善或安全。初态校准不覆盖自适应轨迹及域外对象。" if zh else
           "One-step simulated counterfactuals do not prove long-run safety. Teacher labels describe discrete single-axis argmins; actual proposals are continuous joint actions. Set coverage does not imply joint action improvement or safety. Initial-state calibration does not cover adaptive trajectories or shifted domains."),"",
          "Reproduce / 复现: `python scripts/26_cp_diagnosis.py`; data / 数据: `research/results/cp_diagnosis.json`.",""]
    return "\n".join(lines)

def main():
    torch.set_num_threads(1)
    root=Path(__file__).resolve().parents[1]
    cal=json.loads((root/"models/calibration.json").read_text())
    q=np.asarray(cal["split_conformal"]["qhat_per_axis"])
    T=np.asarray(cal["choice_temperature"])
    space=ActionSpace()
    d=space.deltas
    policy=ConformalPolicy(tuple(q),alpha=.1,k_max=3,mode="hard_hold")
    def scalar(x): return float(x) if np.ndim(x)==0 else np.asarray(x).tolist()
    def summarize_sets(p,labels=None,proposed=None):
        mask=(1-p)<=q[None,:,None]
        size=mask.sum(-1)
        empty=size==0
        large=size>3
        mixed=(mask & (d<0)).any(-1)&(mask & (d>0)).any(-1)
        veto=empty|large|mixed
        result={
            "n_states":len(p),"mean_set_size_per_axis":size.mean(0).tolist(),
            "empty_rate_per_axis":empty.mean(0).tolist(),
            "large_rate_per_axis":large.mean(0).tolist(),
            "mixed_rate_per_axis":mixed.mean(0).tolist(),
            "large_and_mixed_rate_per_axis":(large&mixed).mean(0).tolist(),
            "large_only_rate_per_axis":(large&~mixed).mean(0).tolist(),
            "small_but_mixed_rate_per_axis":((size<=3)&mixed).mean(0).tolist(),
            "veto_rate_per_axis":veto.mean(0).tolist(),
            "all_axes_held_rate":float(veto.all(-1).mean()),
            "any_axis_held_rate":float(veto.any(-1).mean()),
        }
        if labels is not None:
            included=np.take_along_axis(mask,labels[...,None],axis=-1)[...,0]
            result["teacher_label_coverage_per_axis"]=included.mean(0).tolist()
            result["argmax_accuracy_per_axis"]=(p.argmax(-1)==labels).mean(0).tolist()
        if proposed is not None:
            result["vetoed_nonzero_proposal_rate_per_axis"]=(veto&(abs(proposed)>1e-12)).mean(0).tolist()
            z=(size==1)&mask[:,:,3]
            result["singleton_zero_count_per_axis"]=z.sum(0).tolist()
            result["singleton_zero_nonzero_proposal_count_per_axis"]=(z&(abs(proposed)>1e-12)).sum(0).tolist()
        return result,mask,veto
    
    splits={}
    for name in ("temperature_fit","cp_fit","empirical_eval"):
        with np.load(root/"data/calibration"/(name+".npz")) as z: splits[name]={k:z[k] for k in z.files}
    z=splits["empirical_eval"]
    p=softmax(z["choice_logits"],temperature=T[None,:,None])
    options=[Option(str(m),float(v)) for m,v in zip(space.multipliers,d)]
    answer=Answer([Choice(name,options,p[:,a]) for a,name in enumerate(("Kp","Ki","Kd"))],noul=Noul("healthy",np.ones(len(p))))
    plain=decide(answer,space,abstain=None)
    cp=decide(answer,space,abstain=None,conformal=policy)
    initial,mask,veto=summarize_sets(p,z["choice"],plain.proposed)
    raw=softmax(z["choice_logits"])
    initial["mean_pmax_before_temperature_per_axis"]=raw.max(-1).mean(0).tolist()
    initial["mean_pmax_after_temperature_per_axis"]=p.max(-1).mean(0).tolist()
    initial["threshold_min_probability"]=(1-q).tolist()
    
    spec=importlib.util.spec_from_file_location("calibration_source",root/"scripts/02_train.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    plants=mod.independent_plants(512,62603)
    np.testing.assert_array_equal(plants.noise_seed,z["plant_identity"])
    data,_,_,gzn=generate(plants,steps=1,seed=62603,verbose=False)
    np.testing.assert_array_equal(data.choice,z["choice"])
    np.testing.assert_array_equal(data.feats,z["feats"])
    np.testing.assert_array_equal(data.curves,z["curves"])
    g0=np.clip(gzn,1e-4,1e3)
    def cost(p,g):
        r=simulate(p,g)
        return cost_from_metrics(r["metrics"],y_curve=r["y_curve"])
    j0=cost(plants,g0)
    jplain=cost(plants,apply_step(g0,plain.step))
    jcp=cost(plants,apply_step(g0,cp.step))
    axis_gains=np.repeat(g0[None],3,axis=0)
    for a in range(3):
        step=np.zeros_like(g0);step[:,a]=plain.step[:,a]
        axis_gains[a]=apply_step(g0,step)
    axis_j=cost(plants.take(np.tile(np.arange(512),3)),axis_gains.reshape(-1,3)).reshape(3,512).T
    candidate_cost=data.act_cost.reshape(3,space.k,512).transpose(2,0,1)
    best=candidate_cost.min(-1)
    ordered=np.sort(candidate_cost,axis=-1)
    gap=(ordered[:,:,1]-best)/np.maximum(best,1e-9)
    negative=np.min(np.where(mask&(d<0),candidate_cost,np.inf),axis=-1)
    positive=np.min(np.where(mask&(d>0),candidate_cost,np.inf),axis=-1)
    mixed=(mask&(d<0)).any(-1)&(mask&(d>0)).any(-1)
    fullhold=veto.all(-1)
    def outcomes(values,baseline,selected):
        values=np.broadcast_to(values,np.shape(selected));baseline=np.broadcast_to(baseline,np.shape(selected))
        return {"n":int(selected.sum()),
                "improve_more_than_2pct_count":int(((values<baseline*.98)&selected).sum()),
                "harm_more_than_2pct_count":int(((values>baseline*1.02)&selected).sum()),
                "median_delta":float(np.median((values-baseline)[selected])) if selected.any() else None}
    counterfactual={
        "description":"Same frozen empirical initial states; simulator one-step interventions; not a deployment safety claim.",
        "full_step_original_on_all_held_states":outcomes(jplain,j0,fullhold),
        "all_original_full_steps":outcomes(jplain,j0,np.ones(512,dtype=bool)),
        "all_CP_steps":outcomes(jcp,j0,np.ones(512,dtype=bool)),
        "vetoed_axis_original_step_alone":outcomes(axis_j,j0[:,None],veto),
        "allowed_axis_original_step_alone":outcomes(axis_j,j0[:,None],~veto),
        "original_full_step_better_than_CP_more_than_2pct_count":int((jplain<jcp*.98).sum()),
        "CP_full_step_better_than_original_more_than_2pct_count":int((jcp<jplain*.98).sum()),
        "temp_harm_removed_by_CP":int(((jplain>1.02*j0)&(jcp<=1.02*j0)).sum()),
        "new_harm_with_CP_mask":int(((jcp>1.02*j0)&(jplain<=1.02*j0)).sum()),
        "new_harm_all_partial_holds":bool(veto[(jcp>1.02*j0)&(jplain<=1.02*j0)].any(1).all()
            and (~veto[(jcp>1.02*j0)&(jplain<=1.02*j0)].all(1)).all()),
        "teacher_best_vs_second_relative_gap_lt_1pct_per_axis":(gap<.01).mean(0).tolist(),
        "teacher_best_vs_second_relative_gap_lt_5pct_per_axis":(gap<.05).mean(0).tolist(),
        "mixed_axis_count":int(mixed.sum()),
        "mixed_both_directions_improve_over_start_2pct":int((mixed&(negative<j0[:,None]*.98)&(positive<j0[:,None]*.98)).sum()),
        "mixed_both_directions_within_axis_best_relative_cost":{str(eps):int((mixed&(np.maximum(negative,positive)<=best*(1+eps))).sum()) for eps in (.01,.05,.10)},
        "expert_rerun_actual_plant_runs":data.simulation_counts["total"],
    }
    print("frozen initial-state diagnosis complete",flush=True)
    backend=load_backend("models")
    pl=sample_plants(120,seed=17,families=HELDOUT_FAMILIES,heldout=True)
    ku,tu=ultimate_gain(pl)
    start=np.column_stack([.6*ku,1.2*ku/tu,.075*ku*tu])
    temp=evaluate_head(backend,pl,start,ku,tu,budget=20,seed=17,abstain=None,conformal=None,stop_on_no_action=False)
    controlled=evaluate_head(backend,pl,start,ku,tu,budget=20,seed=17,abstain=None,conformal="hard_hold",stop_on_no_action=False)
    def rollout_stats(r):
        tr=r.decisions
        held=tr["axis_held"].all(-1)&tr["valid"]
        unchanged=np.all(r.trajectory["gains"][:,1:]==r.trajectory["gains"][:,:-1],axis=-1)
        unique=np.array([len(np.unique(g,axis=0)) for g in r.trajectory["gains"]])
        longest=[];trailing=[]
        for seq in held:
            m=c=0
            for v in seq:
                c=c+1 if v else 0;m=max(m,c)
            longest.append(m);trailing.append(c)
        sizes=tr["set_size"]
        masks=tr["conformal_set"]
        big=sizes>3
        mixed=(masks&(d<0)).any(-1)&(masks&(d>0)).any(-1)
        return {
            "median_final_J":float(np.median(r.best_j)),"mean_final_J":float(r.best_j.mean()),
            "actual_simulations":int(r.actual_simulations.sum()),"decision_report":r.decision_report(),
            "all_hold_transition_count":int(held.sum()),
            "repeated_identical_gain_measurement_count":int(unchanged.sum()),
            "unique_gain_count_mean":float(unique.mean()),"unique_gain_count_median":float(np.median(unique)),
            "unique_gain_count_histogram":{str(k):int((unique==k).sum()) for k in sorted(set(unique.tolist()))},
            "all_19_transitions_held_plants":int((held.sum(1)==19).sum()),
            "trailing_all_hold_at_least_5_plants":int((np.asarray(trailing)>=5).sum()),
            "longest_all_hold_mean":float(np.mean(longest)),
            "rollout_large_axis_rate":float(big.mean()),
            "rollout_mixed_axis_rate":float(mixed.mean()),
            "rollout_large_and_mixed_axis_rate":float((big&mixed).mean()),
            "rollout_small_but_mixed_axis_rate":float(((sizes<=3)&mixed).mean()),
            "unique_gains_per_plant":unique.tolist(),"longest_all_hold_per_plant":longest,
            "trailing_all_hold_per_plant":trailing,
        }
    rt=rollout_stats(temp);rc=rollout_stats(controlled)
    monitor=evaluate_head(backend,pl,start,ku,tu,budget=20,seed=17,abstain=None,conformal="monitor")
    stopped=evaluate_head(backend,pl,start,ku,tu,budget=20,seed=17,abstain=None,conformal="hard_hold")
    np.testing.assert_allclose(monitor.best_j,temp.best_j,rtol=1e-10,atol=1e-10)
    extra={name:{"median_final_J":float(np.median(r.best_j)),"mean_final_J":float(r.best_j.mean()),
                 "actual_simulations":int(r.actual_simulations.sum()),"per_plant":r.best_j.tolist(),
                 "actual_simulations_per_plant":r.actual_simulations.tolist()}
           for name,r in (("monitor",monitor),("hard_hold_stop",stopped))}
    raw_results=json.loads((root/"research/results/ablation.json").read_text())
    rows={r["variant"]:r for r in raw_results["rows"]}
    np.testing.assert_allclose(temp.best_j,rows["C2_temperature_only"]["per_draw"][1]["per_plant"],rtol=1e-10,atol=1e-10)
    np.testing.assert_allclose(controlled.best_j,rows["C3_temperature_CP"]["per_draw"][1]["per_plant"],rtol=1e-10,atol=1e-10)
    diag={
        "manifest":manifest(Namespace(),files=[root/'models/jev_head.pt',root/'models/calibration.json',root/'data/calibration/empirical_eval.npz']),
        "simulation_counts":{
            "expert_reconstruction":data.simulation_counts["total"],
            "counterfactual_measurements":6*512,
            "closed_loop":sum(int(r.actual_simulations.sum()) for r in (temp,controlled,monitor,stopped)),
            "total":data.simulation_counts["total"]+6*512+sum(int(r.actual_simulations.sum()) for r in (temp,controlled,monitor,stopped)),
        },
        "calibration_sha256":hashlib.sha256((root/"models/calibration.json").read_bytes()).hexdigest(),
        "frozen_initial_eval":initial,"initial_counterfactual":counterfactual,
        "seed17_replay":{"n":120,"budget":20,"matched_published_results":True,"temperature_only":rt,"temperature_CP":rc,
            "paired_mean_final_J_difference":float(np.mean(controlled.best_j-temp.best_j)),
            "temporal_diagnostics":{
                "set_size_mean_by_iteration":controlled.decisions["set_size"].mean(axis=(0,2)).tolist(),
                "fully_held_plants_by_iteration":controlled.decisions["axis_held"].all(-1).sum(0).tolist(),
                "hold_first_then_move_later_plants":int((controlled.decisions["axis_held"][:,0].all(-1)
                    & ~controlled.decisions["axis_held"].all(axis=(1,2))).sum()),
            }},
        "new_policy_replay":extra,
        "limits":["single fixed checkpoint and simulator","initial calibration distribution differs from adaptive held-out trajectories",
                  "teacher argmin action labels are not safety labels","one-step counterfactuals are not long-term policy guarantees",
                  "no thresholds selected on these outcomes"],
    }
    (root/"research/results/cp_diagnosis.json").write_text(json.dumps(diag,indent=2),encoding="utf-8")
    print(json.dumps(diag["new_policy_replay"],indent=2))
    (root/"docs/CP_DIAGNOSIS.md").write_text(render(diag),encoding="utf-8")

if __name__ == "__main__":
    main()
