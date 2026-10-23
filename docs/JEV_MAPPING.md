# JEV_MAPPING

[English](#english) · [简体中文](#简体中文)

## English

Jev-inspired and not affiliated with, endorsed by or sponsored by TypeSafe AI.
This repository contains no Jev/Laya weights, tokenizer, text input or API access.
The trained policy is this repository's numeric PID head.

Primary sources: [TypeSafe introduction](https://docs.typesafe.ai/introduction),
[Choice](https://docs.typesafe.ai/primitives/choice),
[Score](https://docs.typesafe.ai/primitives/score),
[Noul](https://docs.typesafe.ai/primitives/noul). These are vendor public descriptions,
not measurements or guarantees obtained by this project. The previously cited
jevtypesafeai.com architecture page is an independent third-party site, not
official architecture evidence; its implementation claims are not relied on here.

| Concept | Implemented here | Limit |
| :--- | :--- | :--- |
| Choice | 3 axes × 7 options, distributions and numeric payloads | PID checkpoint; confidence=max(p), not a correctness guarantee |
| Score | five ordered cost bands, distribution | fixed synthetic rubric |
| Noul | synthetic healthy-step label | no independently validated safety probability; tau_noul defaults to 0 |
| Calibration | per-axis NLL temperature loaded at runtime | expert agreement differs from outcome calibration; T also changes expectation actions |
| Abstention | default split-CP monitoring; optional hard_hold and legacy tau_act/tau_esc and global tau_noul | keep last tested parameter; escalation flag only; separate measured rollback |
| Many questions | three Choice + Score + Noul in one forward | scaling with arbitrary question count unmeasured |
| Registry | fixed supported IDs, UnknownQuestion on unsupported IDs | no natural-language questions or arbitrary rubric |
| Training | supervised imitation of simulated coordinate search | no Jev training recipe reused |

The reusable parts and the PID-specific runner are separated in
[TRANSFER](TRANSFER.md). A typed interface does not itself demonstrate a causal
advantage: read [ABLATION](ABLATION.md) and its single-training-seed limitation.
Laya's [reported calibration table](https://github.com/NandhaKishorM/laya/blob/main/BENCHMARKS.md#calibration)
contains ECE 0.466→0.081 on its own task; it is background, not a matched PID comparison.

## 简体中文

本仓库受Jev启发，与TypeSafe AI无隶属、背书或赞助关系，不含Jev/Laya权重、分词器、文本输入或API访问。
实际策略是本仓库训练的数值PID头。

一手来源：[TypeSafe介绍](https://docs.typesafe.ai/introduction)、[Choice](https://docs.typesafe.ai/primitives/choice)、
[Score](https://docs.typesafe.ai/primitives/score)、[Noul](https://docs.typesafe.ai/primitives/noul)。
这些是厂商公开描述，不是本仓库测得的性能或保证。此前引用的jevtypesafeai.com架构页属于独立第三方，
不能作为官方架构证据，本项目不再依赖其内部实现描述。

| 概念 | 本仓库实现 | 边界 |
| :--- | :--- | :--- |
| Choice | 3轴×7选项、分布与数值载荷 | PID权重，max(p)不保证正确 |
| Score | 5个有序代价档及分布 | 固定合成评分标准 |
| Noul | 合成健康动作标签 | 不是独立验证的安全概率，tau_noul默认0 |
| 校准 | 每轴NLL温度在运行时应用 | 专家一致性不等于结果校准，T也改变期望动作 |
| 弃权 | 默认完整CP集合监测，可选hard_hold及旧tau_act/tau_esc及全局tau_noul | 保持上次实测参数，升级仅标记，事后回滚独立 |
| 多问题 | 一次前向回答3个Choice及Score/Noul | 任意问题数扩展未测 |
| 注册表 | 固定ID，未知项抛UnknownQuestion | 不接受自然语言问题或任意标准 |
| 训练 | 仿真坐标搜索专家的监督模仿 | 未复用Jev训练配方 |

可复用组件与PID闭环边界见[TRANSFER](TRANSFER.md)。类型接口本身不证明因果收益，
见[ABLATION](ABLATION.md)及其单训练种子限制。
Laya的[源校准表](https://github.com/NandhaKishorM/laya/blob/main/BENCHMARKS.md#calibration)确有ECE 0.466→0.081，
但任务不同，只作背景，不是同条件PID对比。


Split-CP calibration and its restricted marginal teacher-label guarantee are documented in [CONFORMAL](CONFORMAL.md); they are this project's implementation, not a claim about Jev internals.

分裂CP校准及其有限的边际专家标签覆盖保证见[CONFORMAL](CONFORMAL.md)，这是本仓库实现，不是对Jev内部架构的推断。
