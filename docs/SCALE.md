
> [English](#scale-concurrency-and-matlab-versions) · [简体中文](#规模效应并发与版本兼容)

# Scale, concurrency and MATLAB versions

> **Version scope:** the throughput tables below are historical measurements with cross-job model/sweep caching. Since v0.9.0 each job starts from a fresh source copy and repeats required discovery/sweep measurements; `keep_loaded` no longer reuses an already tuned copy or stale sweep. The MATLAB process stays warm and Fast Restart remains available within one job. The historical warm-job timings are not current promises; use each result's `timings` and `n_total_simulations`. See [MODEL_ADAPTATION](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/MODEL_ADAPTATION.md).
>
> **版本范围：**下方吞吐表来自跨任务复用模型/扫描缓存的历史测量。自v0.9.0起，每个任务从原件新建副本，重新执行必要的发现和扫描；`keep_loaded`不再沿用已调过的副本或旧扫描。MATLAB进程仍常驻，同一任务内仍使用Fast Restart。历史热启动耗时不代表当前承诺，请读取本次`timings`及`n_total_simulations`。见[MODEL_ADAPTATION](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/MODEL_ADAPTATION.md)。

Three questions that only show up when someone actually deploys this.

> Every number below is measured on the reference machine (lab model, 10 s
> horizon, 20 experiments). Only "LLM turn = 3 s" is an assumption, and it is
> labelled as such.
>
> The phase table is for `jev-tune matlab` **without** `--auto`. With `--auto`
> — what every command in the README uses — discovery loads and compiles the
> model first, so the same job reports `setup 0.7 s`, `sweep 3.6 s`, `loop 0.7 s`
> instead of `24.3 / 38.7 / 5.4 s` (lab model, 5 experiments, 2026-10-23). The
> work did not disappear; it moved into `discover`.

## 1. Where the wall clock goes

The tuner reports its own timing split (`result.timings`):

| phase | first job (cold) | afterwards (warm) |
| :--- | ---: | ---: |
| `setup` (copy, load, compile, Fast Restart) | 27.9 s | **0.03 s** |
| `sweep` (Kp sweep for Ku/Tu, 7 deliberately unstable runs) | 39.8 s | **0.002 s** (cached) |
| `loop` (20 simulations + 20 decisions) | 8.4 s | 8.1 s |
| `save` (.mat + JSON) | 0.1 s | 0.1 s |
| **total** | **77 s** | **8.8 s** |

Plus **MATLAB cold start ≈ 50 s** (measured here, with the installed connectors).

Same task, four ways:

| how | time | vs agent loop |
| :--- | ---: | ---: |
| agent in the loop (LLM 3 s/turn) | 60 s | 1× |
| one CLI process per job | **122 s** | **slower** |
| warm worker (after the first job) | **8.8 s** | **7×** |
| long-lived MATLAB session | **2.7 s** | **22×** |

**The scale effect is not automatic.** It comes from three things, all required:

1. MATLAB stays resident (saves 50 s of startup);
2. the compiled model is cached (saves 28 s of setup);
3. Ku/Tu is cached (saves 40 s of sweeping).

With all three: **20 experiments go from 60 s to 9 s**.

### Across many jobs

| jobs | agent loop | one process each | warm worker |
| ---: | ---: | ---: | ---: |
| 10 | 10 min | 20 min | 1.5 min |
| 100 | 1.7 h | 3.4 h | 15 min |
| 1 000 | 17 h | 34 h | 2.5 h |

(Extrapolated at 8.8 s/job; real throughput is also bounded by how many MATLAB
instances your licence allows.)

## 2. Does a blocking MCP server eat the scale effect?

**No — the bottleneck was never blocking.** It was startup, compilation and the
Kp sweep.

One job is 8.8 s, so 1 000 jobs serially = 2.5 h, still 7× faster than the
agent loop. The real killer is "one MATLAB per job": 122 s each ⇒ 34 h, i.e.
*slower* than the agent.

What is implemented:

1. **MCP `tune_simulink` uses a resident worker** (`matlab_worker.py`,
   process-wide singleton) — MATLAB starts on the first call and is reused;
2. **`jev-tune batch --jobs jobs.json`** — one process, a whole queue;
3. **caching** — the compiled model and Ku/Tu persist for the session
   (`keep_loaded`).

For linear speed-up, start several worker processes (bounded by the licence).

## 3. Operational trap: the Fast Restart modal dialog

If a model is left initialised in Fast Restart, *any* `close_system` raises
**"…initialized in Fast Restart. Do you want to exit Fast Restart and close the
model?"** — and an unattended agent session hangs on it.

Handled:

* desktop sessions (`usejava('desktop')`) **never cache**, so interactive use
  cannot leave that state behind;
* every close path disables Fast Restart first;
* `jev_close_all` closes everything without a prompt.

## 4. MATLAB versions

> **What is actually tested:** MATLAB **R2024b** (Update 6) with Simulink, Simscape
> and Control System Design. Older releases are supported by the code's fallbacks
> (`-batch` detection, `-r`) but have **not** been run against the self-check, so
> treat `R2019a+` as an expectation, not a measurement.

The original code hard-coded `C:\Program Files\MATLAB\R2024b` and assumed
`matlab -batch`. Both are gone.

**Discovery**: `MATLAB_EXE` → `PATH` → Windows registry → install scan → POSIX
paths. **Launcher**: probes `matlab -help` for `-batch`, otherwise falls back to
`-nodisplay -nosplash -r "…; exit"`.

**Capability probe**: `jev-tune matlab --probe` (or the MCP tool
`tune_probe_matlab`) reports release, Fast Restart, scope logging and pidtune.

| feature | minimum release | note |
| :--- | :--- | :--- |
| Fast Restart | R2013b | without it every run recompiles, 8–19× slower |
| Scope data logging | R2014a | otherwise use To Workspace |
| `jsonencode/jsondecode` | R2016b | used by the bridge |
| `-batch` | R2019a | falls back to `-r` below that |
| head forward pass | any | plain matrix maths |

**Verified on R2024b only**; older releases rely on the probe and the fallbacks
and have not been tested one by one.

## 5. Self-audit: where the code contradicted the product story

| # | problem | impact | status |
| :--- | :--- | :--- | :--- |
| 1 | hard-coded MATLAB path | breaks on other releases | ✅ discovery |
| 2 | hard-coded gain/scope names | cannot run someone else's model | ✅ `cfg.*_block` |
| 3 | `-batch` assumed R2019a+ | fails on older releases | ✅ `-r` fallback |
| 4 | one MATLAB per job | scale effect disappears | ✅ worker + batch |
| 5 | recompile + Kp sweep per job | 8.1 of 8.8 s should be simulation | ✅ cached |
| 6 | only three separate gain blocks | models with a `PID Controller` block unsupported | ✅ `cfg.controller='pid_block'` + second bench |
| 7 | cost fixed to step-response metrics | tracking / disturbance projects unsupported | ⚠️ open (next) |
| 8 | reference inferred from `Step × Deg2Rad` | wrong for other commands | ✅ `cfg.ref_source` |
| 9 | training distribution is 10 s / 5 ms | features drift otherwise | ✅ `warnings` |
| 10 | name `jev-tune` | mistaken for "the Jev model" | ✅ stated in README |
| 11 | Fast Restart dialog | unattended sessions hang | ✅ desktop never caches + `jev_close_all` |

**The only hard gap left is #7**: the tuner currently optimises step-response
quality. Tracking or disturbance rejection needs new metrics and a retrain
(specialist flow, ~30 min CPU).

---

以下为中文全文。

## 规模效应、并发与版本兼容

这份文档回答三个"真拿去用"才会冒出来的问题：

1. 规模效应到底有多大——**以及它在什么前提下才成立**；
2. MCP 服务器阻塞会不会吃掉规模效应；
3. 别人的 MATLAB 不是 R2024b 还能不能跑。

> 下面所有数字都来自本机实测（一个示例电机模型，10 s 仿真时长，20 次实验），
> 只有"LLM 往返 3 s"是假设，已标注。
>
> 阶段表对应**不带** `--auto` 的 `jev-tune matlab`。带 `--auto` 时（README 里
> 所有命令都是）发现阶段会先把模型加载、编译一遍，所以同一个任务报的是
> `setup 0.7 s`、`sweep 3.6 s`、`loop 0.7 s`，而不是 `24.3 / 38.7 / 5.4 s`
> （同一台电机、5 次实验，2026-10-23 实测）。时间没有消失，只是移进了
> `discover`。

---

## 1. 实测：一次任务的时间去哪了

调参器自己会把耗时拆成四段返回（`result.timings`）：

| 阶段 | 第一次（冷） | 之后（热） |
| :--- | ---: | ---: |
| `setup`（复制模型、加载、编译、Fast Restart） | 27.9 s | **0.03 s** |
| `sweep`（扫 Kp 找 Ku/Tu，7 次故意不稳定的仿真） | 39.8 s | **0.002 s**（缓存） |
| `loop`（20 次仿真 + 20 次决策） | 8.4 s | 8.1 s |
| `save`（写 .mat + JSON） | 0.1 s | 0.1 s |
| **合计** | **77 s** | **8.8 s** |

外加 **MATLAB 冷启动 ≈ 50 s**（本机实测，含已装的连接器）。

同一个任务（20 次实验）四种跑法：

| 跑法 | 耗时 | 相对 Agent 在环 |
| :--- | ---: | ---: |
| Agent 在环（LLM 3 s/次） | 60 s | 1× |
| 一次 CLI 进程一个任务 | **122 s** | **更慢** |
| 常驻 worker（首次之外） | **8.8 s** | **7×** |
| 长驻 MATLAB 会话（很热） | **2.7 s** | **22×** |

**结论很硬**：规模效应不是自动成立的。它来自三件事，缺一不可：

1. MATLAB 常驻（省 50 s 启动）；
2. 模型编译缓存（省 28 s setup）；
3. Ku/Tu 缓存（省 40 s 扫描）。

三件都做了之后，**20 次实验从 60 秒压到 9 秒**。

### 换成批量看

| 任务数 | Agent 在环 | 一进程一任务 | 常驻 worker |
| ---: | ---: | ---: | ---: |
| 10 | 10 min | 20 min | 1.5 min |
| 100 | 1.7 h | 3.4 h | 15 min |
| 1 000 | 17 h | 34 h | 2.5 h |

（按 8.8 s/任务线性外推；实际还受 MATLAB 许可证并发数限制。）

---

## 2. 阻塞的 MCP 会不会吃掉规模效应？

**不会——瓶颈从来不是阻塞，而是启动、编译和扫描。**

一次任务 8.8 s，1 000 个串行 = 2.5 h，仍比 Agent 在环的 17 h 快 7 倍。
真正的杀手是"每个任务重开 MATLAB"（122 s ⇒ 34 h，反而更慢）。

当前实现：

1. **MCP 的 `tune_simulink` 走常驻 worker**（`matlab_worker.py` 单例）：第一次调用启动 MATLAB，之后复用；
2. **`jev-tune batch --jobs jobs.json`**：一个进程顺序跑整个队列；
3. **缓存**：编译后的模型 + Ku/Tu 随会话保存（`keep_loaded`）。

需要线性加速时，起多个 worker 进程即可（受许可证并发数限制）。

---

## 3. 一个必须记住的运维坑：Fast Restart 的模态弹窗

模型停在 Fast Restart 里时，任何 `close_system` 都会弹出
**"…initialized in Fast Restart. Do you want to exit Fast Restart and close the model?"**
——无人值守的 Agent 会话会卡在这个弹窗上。

已处理：

* 桌面会话（`usejava('desktop')` 为真）**强制关闭缓存**，所以交互式使用不会留下这种状态；
* 所有关闭路径都先 `set_param(mdl,'FastRestart','off')`；
* 提供 `jev_close_all`：一键关掉所有模型且不触发弹窗。

---

## 4. 版本兼容

原来的代码有两处硬假设：MATLAB 装在 `C:\Program Files\MATLAB\R2024b`，以及
`matlab -batch` 一定可用。两处都已修掉。

**发现顺序**：`MATLAB_EXE` → `PATH` → Windows 注册表 → 安装目录扫描 → POSIX 路径。

**启动器**：探测 `matlab -help` 是否含 `-batch`，没有就退回 `-nodisplay -nosplash -r "…; exit"`。

**能力探测**：`jev-tune matlab --probe`（或 MCP 的 `tune_probe_matlab`）报告
release / Fast Restart / scope 记录 / pidtune。

| 功能 | 最低版本 | 说明 |
| :--- | :--- | :--- |
| Fast Restart | R2013b | 没有它每次重编译，慢 8–19× |
| Scope 数据记录 | R2014a | 否则改用 To Workspace |
| `jsonencode/jsondecode` | R2016b | 桥接层用 |
| `-batch` | R2019a | 低于此版本自动退回 `-r` |
| 决策头前向 | 任意 | 纯矩阵运算 |

**实测范围：只有 R2024b 真正跑通**，其他版本靠探测 + 降级，未逐一验证。

---

## 5. 产品逻辑不一致清单（自查，含最新状态）

| # | 问题 | 影响 | 状态 |
| :--- | :--- | :--- | :--- |
| 1 | MATLAB 路径写死 | 换版本失败 | ✅ 自动发现 |
| 2 | 增益块/示波器名写死 | 别人的模型跑不了 | ✅ `cfg.*_block` |
| 3 | `-batch` 假设 R2019a+ | 老版本失败 | ✅ 退回 `-r` |
| 4 | 每任务重开 MATLAB | 规模效应归零 | ✅ 常驻 worker + batch |
| 5 | 每任务重编译 + 重扫 Ku | 8.8 s 里 8.1 s 是纯仿真，其余已缓存 | ✅ 已修 |
| 6 | 只支持三个独立增益块 | 用 `PID Controller` 块调不了 | ✅ `cfg.controller='pid_block'`，并有第二个验证模型 |
| 7 | 代价函数固定为阶跃指标 | 跟踪/扰动抑制不适用 | ⚠️ 未修（下一步） |
| 8 | 参考值默认 `Step × Deg2Rad` | 非阶跃输入算错 | ✅ `cfg.ref_source` |
| 9 | StopTime 与训练分布差太远 | 特征失真 | ✅ 返回 `warnings` |
| 10 | 名字 `jev-tune` 易误解 | 以为用了 Jev 模型 | ✅ README 已澄清 |
| 11 | Fast Restart 弹窗 | 无人值守会话卡死 | ✅ 桌面强制不缓存 + `jev_close_all` |

**唯一剩下的硬缺口是 #7**：现在只能优化"阶跃响应质量"。要做跟踪/扰动抑制，
需要新的指标 + 重新训练（专门化流程，约 30 min CPU）。这是下一步。
