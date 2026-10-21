# 规模效应、并发与版本兼容

这份文档回答三个"真拿去用"才会冒出来的问题：

1. 规模效应到底有多大——**以及它在什么前提下才成立**；
2. MCP 服务器阻塞会不会吃掉规模效应；
3. 别人的 MATLAB 不是 R2024b 还能不能跑。

> 下面所有数字都来自本机实测（motor-valve benchmark 模型，10 s 仿真时长，20 次实验），
> 只有"LLM 往返 3 s"是假设，已标注。

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
