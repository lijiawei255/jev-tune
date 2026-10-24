# Final architecture review / 架构终审

[English](#english) · [简体中文](#简体中文)

## English

At the user's request, GPT-6 Astra performed the independent read-only review;
GPT-6.1 sol implemented the changes. The review examined the typed execution
path, frozen-weight temperature/CP calibration, pre-action holds and measured
fallback, C99/MATLAB numerical handling, embedded transfer boundaries, experiment
accounting, tests and the publication evidence chain. It did not replace actual
tests or establish clinical, VLA or target-board validity.

The initial review blocked acquisition until complete failure ledgers, committed
execution dependencies, deterministic checker inference and destructive evidence
tests were implemented. A later review required checked C inference, stable
temperature scaling, explicit internal stack-frame reporting and publication
hashes covering prose and the claims registry. The resulting fixes and tests
were reviewed again before final test execution.

The first full suite also detected that fresh host resource and parity reports
had overwritten preserved historical paths. The release keeps those historical
files intact and stores current measurements under versioned `v0100` paths.
The preservation manifest and its assertions remain unchanged; the corrected
evidence references require another complete test and claims run.

The user's additional publication check found four MATLAB analysis helpers
with a personal checkout path. They now require explicit external inputs;
real generated-model tests exercise them from another current directory,
preserve source-model bytes and reject ambiguous signals. An independent
temporary checkout also ran the CLI and selected tests without the ignored
training data, using the existing dependency environment.

Current visual assets were regenerated: discovery uses the project's generated
model and public graph records, while old response plots retain their historical
scope. The new release inventory lists formal model artifacts and four pinned
synthetic data files. It covers the current tree and new assets; at the user's
explicit direction, Git history is not rewritten. The notices also distinguish
benchmark feedback during development from an independent external test.

The reviewer authorized the frozen implementation to proceed to full pytest and
fresh claims verification, with no outstanding release blocker found in that
review. Final release acceptance remains conditional on the actual tests,
independent reconstruction receipts and package hashes recorded in
[RELEASE_VERIFICATION](RELEASE_VERIFICATION.md). Failed policy acceptance is
retained in [NONPID_TRANSFER](NONPID_TRANSFER.md); it is not converted into a
policy deployment approval by this architecture review.

The reusable reference and its limits are described in
[SAFETY_SHELL](SAFETY_SHELL.md). Physical limits, signal quality, recovery,
refractory logic and target execution deadlines remain independently validated
domain responsibilities. The software supplies no clinical protocol, VLA
perception stack, board qualification or FPGA design.

## 简体中文

按用户要求，由 GPT-6 Astra 承担独立只读审查，GPT-6.1 sol 负责实施。终审覆盖
类型化实际执行链、冻结权重的温度/CP外围标定、事前保持与测后恢复、C99/MATLAB
数值处理、嵌入式迁移边界、实验计账、测试本身及发布证据链。审查不替代实际测试，
也不构成临床、VLA或目标板有效性证据。

初审要求在正式采集前修复完整失败账本、执行源码提交绑定、校验器确定性配置，
并增加破坏性证据测试。后续复核要求增加C检查入口、稳定温度缩放、明确内部栈帧，
以及绑定正文和claims注册表的发布哈希；这些修复与测试均在最终全量测试前再次复核。

首次全量测试还检出新的宿主资源及对齐报告覆盖了封存路径。发布保留历史文件原样，
本次测量另存为带`v0100`版本的路径。历史保留清单及其断言保持不变；修正证据引用后
重新执行完整测试和claims检查。

用户追加的发布审查发现四个MATLAB辅助脚本写死个人检出路径，现改为显式外部输入；
真实自建模型测试从另一当前目录调用，验证原模型字节不变并拒绝歧义信号。独立临时
检出也在不复制被忽略训练数据的情况下运行CLI及指定测试，复用既有依赖环境。

当前图像已重新生成：发现动图采用本项目自建模型及公开图记录，旧响应曲线仍标为
历史。新发布清单列出正式模型产物与四份有pin的合成数据，范围为当前树与新附件；
依用户明确要求未改写Git历史。声明也区分了基准开发反馈与独立外测。

审查者已同意冻结实现并进入完整pytest及全新claims检查，该轮未发现尚未解决的
发布阻断。最终放行仍以[发布验证](RELEASE_VERIFICATION.md)记录的真实测试、
独立重建回执和打包哈希为准。[非PID研究](NONPID_TRANSFER.md)未通过的策略收益
验收保持原样，架构审查不会把它变成策略部署许可。

可复用参考及边界见[SAFETY_SHELL](SAFETY_SHELL.md)。物理限制、信号质量、恢复、
不应期和目标执行时限仍由经过独立验证的领域外壳负责；仓库不提供临床协议、VLA
感知栈、板端资格证明或FPGA设计。
