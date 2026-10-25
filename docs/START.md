# Start here

[English](#start-here) · [简体中文](#从这里开始)

Choose the path that matches your goal. Each path is a short reading order, not a required sequence of experiments.

## I only want to use it

Begin with [Try it](../README.md#try-it) for installation and the first commands, then read the [worked examples](EXAMPLES.md) for complete runs and their output. If you have your own Simulink model, run `jev-tune doctor --model <file>` before tuning and follow its `next` guidance when a check fails.

## I want to understand the shell

Start with [How a step works](../README.md#how-a-step-works) to follow one iteration from response to bounded action. Continue with the [five implemented capabilities and their evidence](SAFETY_SHELL.md#five-implemented-capabilities-and-their-evidence), then find the `Layer` table in [ARCHITECTURE](ARCHITECTURE.md#english) for the execution layers; you can skip the historical research opening when that table is all you need.

## I want to port the shell

Follow [Porting the shell to another domain](../AGENTS.md#porting-the-shell-to-another-domain) for the required sequence and domain-owned rules. Then inspect the [lightweight examples in `src/jev_tune/domains/light`](../src/jev_tune/domains/light/README.md#english) for ordered numeric and categorical action paths. Finish with the `Component` / `Reuse boundary` table in [TRANSFER](TRANSFER.md#english) to separate reusable components from PID-specific implementation and evidence.

# 从这里开始

按你的目标选择一条路径。每条路径只是简短的阅读顺序，不要求依次完成实验。

## 只想用

先看首页的[上手](../README.zh-CN.md#上手)，完成安装并运行第一批命令；再看[完整示例](EXAMPLES.md#中文版)，了解完整运行及输出。如果你有自己的 Simulink 模型，调参前先运行 `jev-tune doctor --model <文件>`；检查失败时按其 `next` 指引处理。

## 看懂外壳

从首页的[一次迭代怎么走](../README.zh-CN.md#一次迭代怎么走)开始，跟随一次迭代了解响应如何变成有界动作。接着阅读[五项已实现能力及证据](SAFETY_SHELL.md#五项已实现能力及证据)，再在 [ARCHITECTURE](ARCHITECTURE.md#简体中文) 中查找 `层` 表，核对各执行层；只看分层表时可以跳过前面的历史研究记录。

## 移植到其他领域

先按 [Porting the shell to another domain](../AGENTS.md#porting-the-shell-to-another-domain) 的步骤执行，并明确领域自身承担的规则。再看 [`src/jev_tune/domains/light` 轻量例子](../src/jev_tune/domains/light/README.md#简体中文)，分别了解有序数值动作和类别动作路径。最后查阅 [TRANSFER](TRANSFER.md#简体中文) 的 `组件` / `复用边界` 表，区分可复用组件与 PID 专用实现及证据。
