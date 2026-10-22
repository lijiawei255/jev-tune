# Contributing

> [English](#contributing) · [简体中文](#参与贡献)


Thanks for looking. This project is small and opinionated; the fastest way to
get a change merged is to read the four rules below and then send something
focused.

## Ground rules

1. **Numbers, not adjectives.** Any claim about speed or quality must come with
   a measurement and the command that produced it. "Faster" without a number
   will be asked for one.
2. **Never regress the benchmark silently.** If your change moves
   `scripts/03_evaluate.py` or `scripts/08_generalize.py`, include the before/after
   table in the PR. A worse tail is acceptable if it is stated.
3. **Keep the decision contract.** Everything the tuner outputs must be a
   `choice`, a `score`, or a `noul` (`src/jev_tune/primitives.py`). PRs that add
   a "predict the gain directly" path will be declined — that is the thing this
   project tests the alternative to.
4. **Keep `noul` advisory.** Hard limits, rollback and the safety veto live in
   deterministic code (`evaluate.py`, `jev_tune_model.m`). Do not move them into
   the model.

## Getting set up

```bash
bash scripts/agent_setup.sh            # or scripts/agent_setup.ps1 on Windows
python -m jev_tune.cli check           # pytest, must be green
python -m jev_tune.cli demo --plants 12
```

For MATLAB work you need R2019a+ with Simulink; `jev-tune matlab --probe` tells
you what your release supports.

## What is most useful right now

These are the open gaps, roughly in order of value:

| Area | What it needs | Size |
| :--- | :--- | :--- |
| **Typed interface vs a regression head** | same features, same expert data, same training budget: `choice / score / noul` against regressing the gain deltas. This is the one comparison the project has not made (`docs/CLAIMS.md`, "What is not tested") | small |
| **A local language-model baseline** | a 1.5B–4B model in the same loop, so the language layer and the network round trip stop being one number | medium |
| **A model that is not ours** | run it on a third-party `.slx` and publish the table; `jev-tune doctor --model` output is the most useful part of the report | small |
| **Objective presets** | tracking / disturbance-rejection metrics next to the step-response cost (see `metrics.py`) | medium |
| **Concurrent workers** | run N MATLAB workers in parallel for large batches (`matlab_worker.py`) | medium |
| **Cross-model cache** | reuse the compiled model when several jobs share one `.slx` | small |
| **Dead-band feature** | a state descriptor that distinguishes "chattering in a dead band" from "too much gain" | small |
| **More plant families** | anything with published dynamics the zoo lacks (e.g. thermal with large dead time, cascaded loops) | small |
| **Docs / translations** | we have English and 简体中文; other languages welcome | small |
| **A second external benchmark** | run the tuner on *your* model and publish the table | medium |

Good first issues are tagged `good first issue` on GitHub.

## Sending a change

1. Fork, branch from `main` (`feat/…`, `fix/…`, `docs/…`).
2. Keep the diff focused; unrelated reformatting makes review slow.
3. Add or update a test if you touch code under `src/`.
4. Run `python -m jev_tune.cli check` and, if you touched the tuner,
   `python -m jev_tune.cli demo --plants 12`.
5. Open a PR using the template. Say what you measured, on what machine.

Commit messages: one line, imperative, under ~72 characters; the body explains
*why* and quotes any number you are claiming.

## Reporting a bug

Use the issue template. The three things that make a report actionable:

* the exact command,
* the JSON output (`--json`),
* your MATLAB release and OS if the MATLAB path is involved.

Please do **not** attach a company's Simulink model. If the plant is sensitive,
describe its dynamics or reproduce with `matlab/make_demo_model.m`.

## Licence of contributions

By opening a PR you agree that your contribution is licensed under the MIT
licence of this repository. No contributor licence agreement is required.

---

## 参与贡献

谢谢你看这里。项目不大、也有明确的主张；想让改动被合并，读下面四条然后发一个
聚焦的 PR 就行。

### 四条底线

1. **用数字说话。** 任何关于速度或质量的结论都要有测量和复现命令。"更快"这种
   说法一定会被要求给数据。
2. **不要悄悄退化基准。** 改动影响 `scripts/03_evaluate.py` 或
   `scripts/08_generalize.py` 时，PR 里要附修改前后的对照表。尾部变差可以接受，
   但必须写出来。
3. **保持决策契约。** 调参器输出的一切必须是 `choice`、`score` 或 `noul`
   （`src/jev_tune/primitives.py`）。引入"直接回归增益"通道的 PR 会被拒绝——
   那正是本项目要对照验证的东西。
4. **`noul` 只作建议。** 硬限幅、回滚与安全否决都放在确定性代码里
   （`evaluate.py`、`jev_tune_model.m`），不要搬进模型。

### 环境准备

```bash
bash scripts/agent_setup.sh            # Windows 用 scripts/agent_setup.ps1
python -m jev_tune.cli check           # pytest，必须全绿
python -m jev_tune.cli demo --plants 12
```

MATLAB 相关工作需要 R2019a+ 与 Simulink；`jev-tune matlab --probe` 会告诉你当前
版本支持什么。

### 现在最需要帮忙的地方

| 方向 | 需要什么 | 规模 |
| :--- | :--- | :--- |
| **类型化接口 vs 回归头** | 同样的特征、同样的专家数据、同样的训练预算，用 `choice / score / noul` 对照"直接回归增益增量"。这是项目唯一没做的对照（见 `docs/CLAIMS.md` 的 "What is not tested"） | 小 |
| **本地语言模型基线** | 在同一回路里跑 1.5B–4B 本地模型，把"语言层"和"网络往返"拆成两个数 | 中 |
| **一个不是我们的模型** | 在第三方 `.slx` 上跑一遍并公开表格；报告里最有价值的是 `jev-tune doctor --model` 的输出 | 小 |
| **目标函数预设** | 在阶跃指标之外，加跟踪 / 扰动抑制指标（见 `metrics.py`） | 中 |
| **并发 worker** | 批量场景下并行跑 N 个 MATLAB（`matlab_worker.py`） | 中 |
| **跨模型缓存** | 多个任务共用同一个 `.slx` 时复用已编译模型 | 小 |
| **死区特征** | 区分"在死区里抖动"和"增益过大"的状态描述 | 小 |
| **更多对象族** | 动物园里没有、且有公开动力学的对象（大延迟热过程、串级回路等） | 小 |
| **文档与翻译** | 目前有英文和简体中文，其他语言欢迎 | 小 |
| **第二份外部基准** | 用你的模型跑一遍并公开表格 | 中 |

标注为 `good first issue` 的 issue 适合第一次参与。

### 提交改动

1. Fork，从 `main` 切分支（`feat/…`、`fix/…`、`docs/…`）。
2. 保持 diff 聚焦；顺手重排格式会让 review 变慢。
3. 改了 `src/` 下的代码就补一个测试。
4. 跑 `python -m jev_tune.cli check`；改了调参器再跑
   `python -m jev_tune.cli demo --plants 12`。
5. 用 PR 模板提交，写清你测了什么、在什么机器上测的。

提交信息：一行、祈使句、72 字符以内；正文说明**为什么**，并附上你声称的数字。

### 报告问题

用 issue 模板。让报告可行动的三件事：

* 完整命令；
* `--json` 输出；
* 涉及 MATLAB 路径时，附上 MATLAB 版本和操作系统。

**请不要**上传公司的 Simulink 模型。如果对象敏感，描述它的动力学，或用
`matlab/make_demo_model.m` 复现。

### 贡献的许可

提交 PR 即表示你同意以本仓库的 MIT 许可发布你的贡献，无需签署额外协议。

## Models that discovery gets wrong

The most useful contribution right now is a model that `jev-tune discover` fails
on. Open the *Discovery failed on a real model* issue template; the `--json`
output plus a block list is enough, and you do not need to share a proprietary
model.
