# Release verification / 发布验证

[English](#english) · [简体中文](#简体中文)

## English

365 passed; 0 skipped; coverage 83.14%; 149 automatic claims checks; 0 unverified.

v0.9.0 prioritizes model-adapter correctness and simulation-budget evidence. Real MATLAB adapter/controller regressions and the complete local pytest suite were rerun. Claims reconstruct registered evidence, including the preserved failed research, without treating old studies as new experiments. The new practical budget comparison has its own frozen protocol and raw trial ledger. Its synthetic plants do not establish performance on a user's real model.

The release fixes Ideal PID conversion, ambiguous Scope selection, variable-step integration, original-file collisions and stale cross-job model/sweep reuse. CLI options and write-back failures are propagated, worker queue writes are atomic, and total simulation counts include discovery and setup. Simplex respects small budgets and gain bounds; failed identification cannot silently fall back to an oracle baseline.

The practical comparison used 7995 actual simulations. At budget 20, head/hill mean J is 8.022816/7.047616, p90 is 38.097492/11.168309, and mean actual calls are 17.953125/20.000000. Fewer calls did not establish overall superiority; scenario-specific benefits and failures are preserved. No parameters were tuned from these results.

Deeper joint-risk research is paused; failed acceptance and unestablished coverage premises remain unchanged, with deployment disabled. Historical result files and reproduction entry points are checked against the preservation manifest. `python scripts/44_verify_historical_research.py --check` runs the original verifiers in an isolated historical source view; current runtime fixes are not substituted into old experiments. Original direct commands remain available on v0.8.0. Previous release verification is archived, including its original MATLAB objective. Corrected time integration changes current MATLAB costs; historical costs are not silently replaced or presented as comparable current results.

Local MATLAB uses the recorded installation. Hosted Linux runtime/C99 tests and hosted Windows scientific-evidence checks retain their separate scopes; cross-platform bitwise research replay remains unestablished.

[Model adaptation](MODEL_ADAPTATION.md) · [Practical budget](PRACTICAL_BUDGET.md) · [Machine-readable verification](../research/results/release_verification.json) · [Previous verification](../research/results/release_verification_v080.json)

## 简体中文

365 passed; 0 skipped; coverage 83.14%; 149 automatic claims checks; 0 unverified.

v0.9.0优先修复模型适配正确性并补充仿真预算证据。已重跑真实MATLAB适配器/控制器回归及完整本地pytest；claims重建已注册证据，也保留并复核旧研究失败，不将旧研究冒充新实验。新的实用预算对照具有独立冻结协议和逐次仿真账本，其合成对象不构成用户真实模型上的效果证据。

本次修复Ideal PID转换、Scope测量歧义、可变步长积分、原件路径冲突及跨任务模型/扫描缓存污染；转发CLI选项与写回失败，队列文件原子发布，总仿真计入发现和准备。simplex遵守小预算和增益边界，辨识失败不再静默换成oracle基线。

实用对照实际仿真7995次。预算20时，head/hill平均J为8.022816/7.047616，p90为38.097492/11.168309，实际平均调用为17.953125/20.000000。少调用没有证明总体更优，各场景收益与失败如实保留，没有按结果调参。

暂停深化联合风险研究，验收失败与覆盖前提尚未建立的结论保持不变，部署关闭。历史结果与复现入口按保存清单核验；`python scripts/44_verify_historical_research.py --check`在隔离历史源码视图运行原检查器，不将当前运行时修复偷换进旧实验；原直接命令保留在v0.8.0。上一版发布验证及其MATLAB原目标已归档。实际时间积分修正会改变当前MATLAB代价，旧值不被偷偷替换，也不作为可直接比较的当前结果。

本地MATLAB使用记录的安装环境。托管Linux运行时/C99测试与托管Windows科学证据检查的范围不同，研究跨平台逐位重放仍未建立。

[模型适配](MODEL_ADAPTATION.md) · [实用预算](PRACTICAL_BUDGET.md) · [机器可读验证](../research/results/release_verification.json) · [上一版验证](../research/results/release_verification_v080.json)
