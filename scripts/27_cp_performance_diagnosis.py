"""Compute paired diagnostic statistics from generated experiment JSON; no fitting."""
import json
from pathlib import Path
import numpy as np
from jev_tune.evaluate import HARM_METRIC
from _experiment_protocol import sha256

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    return json.loads((ROOT/'research/results'/f'{name}.json').read_text(encoding='utf-8'))

def array(r):
    return np.asarray([d['per_plant'] for d in r['per_draw']]).ravel()
def differences(x,y):
    d = np.asarray(x)-np.asarray(y)
    return {'n':len(d),'mean_delta':float(d.mean()),'median_delta':float(np.median(d)),
            'ci95_mean_delta':[float(d.mean()-1.96*d.std(ddof=1)/np.sqrt(len(d))),float(d.mean()+1.96*d.std(ddof=1)/np.sqrt(len(d)))],
            'quantiles_delta':dict(zip(['min','p10','p25','p50','p75','p90','p95','max'],np.quantile(d,[0,.1,.25,.5,.75,.9,.95,1]).tolist())),
            'better':int((d < -1e-9).sum()),'worse':int((d > 1e-9).sum()),'equal':int((np.abs(d)<=1e-9).sum()),
            'mean_cost_left':float(np.mean(x)),'mean_cost_right':float(np.mean(y)),
            'median_cost_left':float(np.median(x)),'median_cost_right':float(np.median(y)),
            'p90_cost_left':float(np.percentile(x,90)),'p90_cost_right':float(np.percentile(y,90))}
def exposure(reports):
    if any(r.get('harm_metric',{}).get('version') != HARM_METRIC['version'] for r in reports):
        raise ValueError('rerun E1/E2: historical harmful_rate used >2%, not zero tolerance')
    decisions=sum(r['n_decisions'] for r in reports)
    executed=sum(r['n_executed'] for r in reports)
    harmed=sum(r['n_harmful'] for r in reports)
    harmed_gt_2pct=sum(r['n_harmful_gt_2pct'] for r in reports)
    improved=sum(round(r['n_executed']*r['improvement_rate']) for r in reports if r['n_executed'])
    partial=sum(round(r['n_decisions']*r['partial_hold_rate']) for r in reports)
    allowed_axes=sum(round(r['n_decisions']*3*r['axis_coverage']) for r in reports)
    return {'decisions':decisions,'executed':executed,'full_holds':decisions-executed,
            'partial_holds':partial,'all_axes_permitted':executed-partial,
            'allowed_axes':allowed_axes,'total_axes':decisions*3,
            'harmful_count':harmed,'improved_count':improved,
            'harmful_gt_2pct_count':harmed_gt_2pct,
            'harmful_per_executed':harmed/executed if executed else None,
            'harmful_per_decision':harmed/decisions if decisions else None,
            'harmful_gt_2pct_per_executed':harmed_gt_2pct/executed if executed else None,
            'harmful_gt_2pct_per_decision':harmed_gt_2pct/decisions if decisions else None,
            'improved_per_executed':improved/executed if executed else None,
            'improved_per_decision':improved/decisions if decisions else None,
            'rollbacks':sum(r['n_rollbacks'] for r in reports)}


def main():
    a, s = load('ablation'), load('abstention')
    if any(p.get('harm_metric',{}).get('version') != HARM_METRIC['version'] for p in (a,s)):
        raise ValueError('rerun E1/E2 before diagnosing the new zero-tolerance harm definition')
    ab = {r['variant']:r for r in a['rows']}
    result={'harm_metric':dict(HARM_METRIC),
            'source_sha256':{name:sha256(ROOT/'research/results'/f'{name}.json') for name in ('ablation','abstention')},
            'source_fields':{'E1':'rows[].median_mean=mean of 3 draw medians; p90_median=median of 3 draw p90; paired_vs_temperature_only.mean_delta=mean of 360 paired plant-cost deltas',
                             'E2':'summary[].median_mean=mean of 2 validation draw medians; p90_mean=mean of 2 draw p90; source per_plant paired within seed',
                             'harm':'canonical strict after>before; gt_2pct fields preserve v0.6 threshold; exact event counts, not rates rounded back to counts',
                             'harmful_per_decision':'harmful permitted measured policy transitions / all measured policy transitions; excludes terminal proposals and rollback events, not an unconditional risk guarantee'},
            'E1':{},'E2':{},'exposure':{'E1':{},'E2':{}}}
    for left,right in [('C3_temperature_CP','C2_temperature_only'),('C2_temperature_only','C1_uncalibrated'),('C3_temperature_CP','C0_MLP_regression')]:
        result['E1'][left+' minus '+right]=differences(array(ab[left]),array(ab[right]))
    for name in ['C0_MLP_regression','C1_uncalibrated','C2_temperature_only','C3_temperature_CP']:
        result['exposure']['E1'][name]=exposure([d['decision_report'] for d in ab[name]['per_draw']])
    for left,right in [('temperature_CP','CP_random_hold'),('temperature_CP','no_abstention'),('CP_random_hold','no_abstention')]:
        lr=[r for r in s['validation'] if r['policy']==left]
        rr=[r for r in s['validation'] if r['policy']==right]
        result['E2'][left+' minus '+right]={'combined':differences(np.asarray([r['per_plant'] for r in lr]).ravel(),np.asarray([r['per_plant'] for r in rr]).ravel()),
               'by_draw':{str(l['draw_seed']):differences(l['per_plant'],r['per_plant']) for l,r in zip(lr,rr)}}
    for name in ['temperature_CP','CP_random_hold','no_abstention']:
        result['exposure']['E2'][name]=exposure([r for r in s['validation'] if r['policy']==name])
    result['E1_primary_by_draw']={name:[{key:d[key] for key in ['draw','median','p90','coverage','harmful_rate','harmful_gt_2pct_rate','rollbacks']} for d in ab[name]['per_draw']] for name in ['C1_uncalibrated','C2_temperature_only','C3_temperature_CP']}
    out=ROOT/'research/results/cp_performance_diagnosis.json'
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
