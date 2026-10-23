# Explicit abstention: independent validation and random hold

> [English](#english) · [简体中文](#简体中文)

## English

Select only on seed 7; validate only on [17, 27], excluding selection data.
CP is not tuned on these validation plants: qhat is fixed from the independent CP calibration split. Action coverage differs from teacher-label set coverage; the latter and independent evaluation set sizes are preserved in the JSON calibration_evidence.
N=120/draw; budget=20; selected tau_act=None.

The shipped default is Temperature+CP monitor without a CP veto or pmax threshold. temperature_CP preserves historical hard_hold repetitions; CP_hold_stop stops no-action repeats. tau_act=0.35 is a legacy control; selecting a candidate here does not change production. The threshold sweep and its random control disable CP; separate rows compare CP and matched random holds.

CP alpha=0.1, n=512, rank=462, qhat=[0.9068, 0.8765, 0.9069].

Independent evaluation teacher-label coverage per axis [0.9199, 0.9062, 0.8828]; mean set size [3.0156, 1.9062, 2.5762]. This diagnoses label-set coverage on IID plant initial states. It does not ensure 90% coverage over multi-step rollouts, shifted domains or the accepted-action subset, nor does it certify closed-loop improvement or safety.

| selection tau | coverage | median J | p90 | harmful | ECE |
| ---: | ---: | ---: | ---: | ---: | ---: |
| None | 1.0000 | 0.4823 | 1.0298 | 0.2689 | 0.2598 |
| 0.3 | 0.9579 | 0.4947 | 1.1114 | 0.2353 | 0.2922 |
| 0.35 | 0.8373 | 0.5415 | 1.2147 | 0.1922 | 0.3156 |
| 0.4 | 0.5601 | 0.6160 | 1.3342 | 0.1793 | 0.3098 |
| 0.45 | 0.3478 | 0.6987 | 1.3825 | 0.1160 | 0.3319 |
| 0.5 | 0.2803 | 0.7831 | 1.4306 | 0.0782 | 0.3441 |
| 0.55 | 0.2482 | 0.7786 | 1.5208 | 0.0760 | 0.3234 |
| 0.6 | 0.2272 | 0.9226 | 1.5728 | 0.0541 | 0.3248 |
| 0.7 | 0.1930 | 1.0571 | 1.7540 | 0.0364 | 0.3056 |

| validation policy | median J mean ± std | p90 mean | proposal coverage | measured transition coverage | measured axis coverage | harmful | ECE | actual experiments | rollbacks |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no_abstention | 0.4394 ± 0.0023 | 1.0638 | 1.0000 | 1.0000 | 1.0000 | 0.2406 | 0.2641 | 20.0000 | 0 |
| threshold | 0.4394 ± 0.0023 | 1.0638 | 1.0000 | 1.0000 | 1.0000 | 0.2406 | 0.2641 | 20.0000 | 0 |
| random_hold | 0.4394 ± 0.0023 | 1.0638 | 1.0000 | 1.0000 | 1.0000 | 0.2406 | 0.2641 | 20.0000 | 0 |
| legacy_pmax_0.35 | 0.4908 ± 0.0226 | 1.2992 | 0.8206 | 0.8206 | 0.5101 | 0.1942 | 0.3069 | 20.0000 | 0 |
| temperature_CP | 0.6669 ± 0.0859 | 1.3250 | 0.4664 | 0.4664 | 0.2762 | 0.2067 | 0.2642 | 20.0000 | 0 |
| CP_random_hold | 0.5770 ± 0.0126 | 1.4842 | 0.4664 | 0.4664 | 0.2762 | 0.1359 | 0.2940 | 20.0000 | 0 |
| CP_monitor | 0.4394 ± 0.0023 | 1.0638 | 1.0000 | 1.0000 | 1.0000 | 0.2406 | 0.2641 | 20.0000 | 0 |
| CP_hold_stop | 0.6890 ± 0.0879 | 1.3317 | 0.9089 | 1.0000 | 0.6028 | 0.1912 | 0.2691 | 9.1083 | 0 |

Proposal coverage includes terminal proposals in its denominator; measured transition coverage (the JSON coverage alias) includes only policy decisions followed by an actual measurement, excluding rollbacks. Both count at least one permitted axis. Rates are means across draws and counts are totals. CP_hold_stop has 2141 proposals and 1946 measured policy transitions. Fully held terminal proposals are excluded from the measured denominator, so its measured coverage 1.0000 does not mean abstention is absent; proposal coverage is 0.9089.


The random control shuffles whole three-axis hold masks without outcome labels. It preserves scheduled mask frequencies and is a matched-coverage diagnostic, not a deployment rule. Rollbacks may change actual event counts; measured coverage is reported. Coverage counts steps with at least one permitted axis. Harm means a >2% cost increase after execution. ECE descriptively compares mean axis pmax with joint improvement; it does not establish a calibrated joint success probability. Each policy uses one trained checkpoint; these results do not establish safety.

## 简体中文

只在seed 7选阈值；验证仅用[17, 27]，不计入选择集。
CP不在这些验证对象上调参；其qhat固定来自独立CP校准划分。动作覆盖率不同于专家标签集合覆盖率；后者及独立评估平均集合大小保存于JSON的calibration_evidence。
N=120/draw; budget=20; selected tau_act=None.

当前默认是Temperature+CP monitor，完整集合仅作诊断，不否决轴、不叠加pmax阈值。temperature_CP行保留旧hard_hold重复观测；CP_hold_stop停止无动作重复。tau_act=0.35是旧策略对照；候选阈值的本次选择不会修改生产策略。阈值扫描与其随机对照均关闭CP；另列CP及覆盖匹配随机保持。

CP alpha=0.1, n=512, rank=462, qhat=[0.9068, 0.8765, 0.9069].

独立评估的专家标签逐轴覆盖率 [0.9199, 0.9062, 0.8828]; 平均集合大小 [3.0156, 1.9062, 2.5762]. 这是IID对象初态分布上的标签集合覆盖诊断，不保证多步闭环、域外分布或获准执行子集达到90%覆盖，也不是闭环改善概率或安全保证。

| selection tau | coverage | median J | p90 | harmful | ECE |
| ---: | ---: | ---: | ---: | ---: | ---: |
| None | 1.0000 | 0.4823 | 1.0298 | 0.2689 | 0.2598 |
| 0.3 | 0.9579 | 0.4947 | 1.1114 | 0.2353 | 0.2922 |
| 0.35 | 0.8373 | 0.5415 | 1.2147 | 0.1922 | 0.3156 |
| 0.4 | 0.5601 | 0.6160 | 1.3342 | 0.1793 | 0.3098 |
| 0.45 | 0.3478 | 0.6987 | 1.3825 | 0.1160 | 0.3319 |
| 0.5 | 0.2803 | 0.7831 | 1.4306 | 0.0782 | 0.3441 |
| 0.55 | 0.2482 | 0.7786 | 1.5208 | 0.0760 | 0.3234 |
| 0.6 | 0.2272 | 0.9226 | 1.5728 | 0.0541 | 0.3248 |
| 0.7 | 0.1930 | 1.0571 | 1.7540 | 0.0364 | 0.3056 |

| 验证策略 | 中位 J 均值 ± 标准差 | p90均值 | 提案覆盖率 | 已测转移覆盖率 | 已测轴覆盖率 | 有害步 | ECE | 实际实验次数 | 回滚 |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no_abstention | 0.4394 ± 0.0023 | 1.0638 | 1.0000 | 1.0000 | 1.0000 | 0.2406 | 0.2641 | 20.0000 | 0 |
| threshold | 0.4394 ± 0.0023 | 1.0638 | 1.0000 | 1.0000 | 1.0000 | 0.2406 | 0.2641 | 20.0000 | 0 |
| random_hold | 0.4394 ± 0.0023 | 1.0638 | 1.0000 | 1.0000 | 1.0000 | 0.2406 | 0.2641 | 20.0000 | 0 |
| legacy_pmax_0.35 | 0.4908 ± 0.0226 | 1.2992 | 0.8206 | 0.8206 | 0.5101 | 0.1942 | 0.3069 | 20.0000 | 0 |
| temperature_CP | 0.6669 ± 0.0859 | 1.3250 | 0.4664 | 0.4664 | 0.2762 | 0.2067 | 0.2642 | 20.0000 | 0 |
| CP_random_hold | 0.5770 ± 0.0126 | 1.4842 | 0.4664 | 0.4664 | 0.2762 | 0.1359 | 0.2940 | 20.0000 | 0 |
| CP_monitor | 0.4394 ± 0.0023 | 1.0638 | 1.0000 | 1.0000 | 1.0000 | 0.2406 | 0.2641 | 20.0000 | 0 |
| CP_hold_stop | 0.6890 ± 0.0879 | 1.3317 | 0.9089 | 1.0000 | 0.6028 | 0.1912 | 0.2691 | 9.1083 | 0 |

提案覆盖率的分母包含终止提案；已测转移覆盖率（JSON的coverage别名）仅统计后续确有测量的策略决策，不含回滚。两者均以至少一轴获准为分子。覆盖率取各轮均值，计数为各轮合计。CP_hold_stop有2141个提案、1946个已测策略转移：全轴保持后的终止提案被排除在已测分母之外，所以已测覆盖率1.0000不表示没有弃权；其提案覆盖率为0.9089。


随机对照打乱三轴保持mask，保留预定mask频率，不使用代价标签；它是覆盖匹配诊断，不是部署策略。回滚可能改变实际事件数，表中另报实际覆盖率。coverage是至少一轴获准的整步比例；harmful统计执行后代价增加超过2%的转移。ECE用三轴平均pmax与整步改善作描述性比较，不将它当已验证的联合成功概率。每种策略仅一个训练检查点；结果不是安全保证。
