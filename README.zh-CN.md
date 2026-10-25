[English](README.md) · [简体中文](README.zh-CN.md)

# jev-tune

[![tests](https://github.com/lijiawei255/jev-tune/actions/workflows/ci.yml/badge.svg)](https://github.com/lijiawei255/jev-tune/actions/workflows/ci.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23624699.svg)](https://doi.org/10.5281/zenodo.23624699)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.12-blue)](pyproject.toml)
[![MATLAB](https://img.shields.io/badge/MATLAB-R2024b%20verified-orange)](docs/SCALE.md)

**以PID自动整定为验证床的校准决策与安全外壳。** 200 KB的CPU小模型回答类型化问题：
`choice`（选哪个增益步长）、`score`（当前响应多好）、`noul`（下一步是否健康）。外壳对答案做
温度缩放、构造split-conformal标签集合，在集合为空、过宽或方向冲突时于**执行前**保持该轴，
并由确定性的`SafetyGate`在测量变差后回滚。同一核心可作为float32、零动态内存的C99移植，
在MATLAB/Simulink中运行，也可用于纯Python的VLA动作掩码。

```bash
git clone https://github.com/lijiawei255/jev-tune && cd jev-tune && pip install -e .
jev-tune demo --plants 12                    # 留出对象：头 vs Z-N vs CMA-ES，约20 s
python -m jev_tune.domains.light.vla_mask    # 同一外壳用于类别型机器人动作
```

| 层 | 模块 | 默认 |
| :--- | :--- | :--- |
| 温度缩放 | `core.primitives` | 开 |
| split-conformal集合与否决 | `core.policy.ConformalPolicy` | core与C为`hard_hold`；PID回路为`monitor`（[原因](docs/TRADEOFFS.md)） |
| 事前Hold | `core.policy.decide` | 按策略，逐轴记录原因 |
| 回滚 | `core.gate.SafetyGate` | 开 |

> **受Jev启发，与TypeSafe AI无隶属关系。** 实现的是Jev*接口*（类型化`choice`/`score`/`noul`），
> 不是Jev模型：不含Jev/Laya权重、文本输入或API（[借用了什么](docs/JEV_MAPPING.md)）。
> 适用边界、负结果、跨CPU复现失败与免责声明见[BOUNDARIES](docs/BOUNDARIES.md)；冻结研究见[ARCHIVE](docs/ARCHIVE.md)。

## 让你的 Agent 直接接管

如果你用编程 Agent（Claude Code、Codex、OpenCode、Cursor——任何能执行命令的），
下面这大半页都不用看。把一句话和你的模型路径丢给它：

> **“用 github.com/lijiawei255/jev-tune 调一下 `D:\work\MyMotor.slx` 的 PID，
> 然后给我看前后对比曲线。”**

Agent 会读 [`AGENTS.md`](AGENTS.md)，里面第一步就是运行 `jev-tune discover`：
它**沿着信号图找**（不看块名）增益块、被测量信号和参考值，再用计入发现账本的仿真确认
自己的猜测：

```bash
jev-tune discover --model MyMotor.slx --json      # Agent 先跑这个
jev-tune matlab --model MyMotor.slx --auto --plot before_after.png --write-back
```

不需要改块名，不需要有个叫 `Scope_Position` 的示波器，也不用自己算参考值。
如果模型有歧义，命令会如实返回 `confidence: medium` 而不是瞎猜，Agent 只问你一个问题。

如果模型被拒绝或直接失败，`jev-tune doctor --model <文件>` 会用九行说清为什么——
能不能加载、能不能编译、有没有引用模型或受保护模型、求解器是什么、到底能不能找到一个回路：

```console
$ jev-tune doctor --model MyMotor.slx
check       ok?   detail
file        ok    MyMotor.slx (95 KB)
loads       ok    MATLAB 2024b
referenced  ok    none
protected   ok    none
stateflow   ok    none
compiles    FAIL  Unrecognized function or variable 'Tsim'.
                  -> define the variables the model asks for, then run it once
solver      ...
```

**一个模型里有多个回路？** 互相独立的多回路（四轴、三温区）用 `--all-loops`
逐个调、增益累积写回同一个文件。**串级会被明确拒绝**：返回 `cascade_suspect`
并列出它找到的回路——只调其中一环却报告"成功"，比直接说"不调"更糟。详见
[`docs/APPLICABILITY.md`](docs/APPLICABILITY.md#一个模型里有多个回路)。

![在不认识的模型上做自动发现](assets/discover.gif)

*动图使用本项目自建模型及真实graph/discovery记录，展示误差汇合点、增益路径分类和
确认扰动仿真；图来自生成模型及其公开图记录。公开输入和重生成步骤见
[`OPEN_SOURCE`](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/OPEN_SOURCE.md)。*

## 从哪读起

| 我想…… | 去看 |
| :--- | :--- |
| 一分钟内跑起来 | [试一试](#上手) |
| 看一次完整运行（带真实输出） | [`docs/EXAMPLES.md`](docs/EXAMPLES.md) |
| 弄清模型为什么调不了 | `jev-tune doctor --model <文件>` |
| 判断我的模型适不适合 | [`docs/APPLICABILITY.md`](docs/APPLICABILITY.md) |
| 搞清“类型化决策”到底是什么 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 自己核对数字 | [`docs/STEP1_RESULTS.md`](docs/STEP1_RESULTS.md)、[`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md)、[[`docs/CLAIMS.md`](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/CLAIMS.md)](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/CLAIMS.md) |
| 用 Agent 或 MCP 驱动 | [`AGENTS.md`](AGENTS.md) |
| 处理没见过的对象族 | [`docs/SPECIALIZE.md`](docs/SPECIALIZE.md) |
| 批量跑几百个模型 | [`docs/SCALE.md`](docs/SCALE.md) |
| 和 `pidtune` 公平对比 | [pidtune 那一节](docs/APPLICABILITY.md#如果你已经有准确的模型请直接用-pidtune) |

[![English](https://img.shields.io/badge/README-English-blue)](README.md)

**PID调参：温度缩放、完整CP集合与独立执行策略。**
数值头在CPU上一次前向；默认monitor保留集合而不否决动作，hard_hold作为显式对照，确定性参数不变时停止重复仿真。

> **受 Jev 启发，非官方关联。** 这里借的是它的**接口规范**：`choice`（多选一）、
> `score`（分档打分）、`noul`（是否安全）三个带校准概率的原语。**不是** TypeSafe 的
> 托管 Jev 模型，也**不是** Laya 那个 421M 的文本编码器。运行时策略是本仓库自己训练
> 的数值决策头。本仓库与 TypeSafe AI **无隶属、无背书、无赞助关系**
> （借了什么、没借什么：[docs/JEV_MAPPING.md](docs/JEV_MAPPING.md)）。

![七种方法在同一批对象上比赛](assets/race.gif)

*同一批 40 个未见对象，七种调参方式。**图里每个数字都是实测的**：每 N 次实验后的
中位代价来自 [`scripts/12_make_race.py`](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/scripts/12_make_race.py) 的一次真实运行；右图问的是"多久能拿到一个
能用的控制器"（J ≤ 0.6），按 0.4 秒/次折算。斜线阴影那行是在环路上接一个托管模型
的 Agent——它的一次往返实测**中位 5.3 秒**（GLM-5.3-Flash，40 次调用，其中 13 次
输出无法解析）。手工调参不画曲线是刻意的——它给出的是「几小时之后的一组增益」，
不是一串实验。*

![在真实 Simulink 直流电机上调参](assets/tuning.gif)

*这是采用旧目标与旧扫描流程的历史运行，修正说明见
[`STEP4_RESULTS`](docs/STEP4_RESULTS.md)。每一帧都是电机阀门基准上的一次已记录闭环实验。调的是
`Kp / Ki / Kd`，右边是它正在最小化的代价。最好的增益出现在第 5 次实验
（约 0.55 秒仿真），停滞检测在第 9 次停下。*

---



## 15 秒看懂

| | |
| :--- | :--- |
| **做什么** | 看刚测到的响应，决定下一步把 PID 增益乘多少 |
| **多快** | ONNX前向中位0.022 ms；Python默认类型化/弃权路径中位0.375 ms、p99 1.230 ms。宿主时延不代表WCET，见[COMPUTE](docs/COMPUTE.md)。 |
| **历史MATLAB运行** | v0.2实验课电机的**5次实验**将记录代价从**1.238降至0.598**。这是旧目标下的历史测量，不是当前重跑；之前的扫描修复和v0.9时间网格积分修正都没有更新这些数字。见[STEP4_RESULTS](docs/STEP4_RESULTS.md)。 |
| **多能泛化** | 历史验证族中位0.482；冻结热工族中位1.833，对应基线与oracle先验见下表；独立的v0.9固定起点评测见[PRACTICAL_BUDGET](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/PRACTICAL_BUDGET.md)。 |

![前后对比](assets/before_after.png)

*旧代价定义下的v0.2历史图，不代表当前重跑。同一个被控对象、三组增益。
灰色：Ziegler-Nichols 起点；蓝色：5 次实验后；
虚线：实验课人工调参的结果。那次运行的起点来自 v0.2 的 Ku 扫描，而那个扫描有三处缺陷，
已修复——见 [`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md) 的更正一节。*

---

## 它和别的方法有什么不一样

**对比"接大模型 Agent 调参"**：Agent 在环是"看图 → 写一段话 → 解析那段话"，
每步要等几秒，而且结果埋在自然语言里。这里模型只输出三个原语——`choice` 决定
步长、`score` 评价当前响应、`noul` 判断这一步安不安全——所以决策是一个可以直接
记录和校准的概率向量。可选保持策略见[ABSTENTION](docs/ABSTENTION.md)，默认CP监测
不否决提案；校准目标与适用边界见[CONFORMAL](docs/CONFORMAL.md)，不等于校准后的安全执行概率。

**对比经典自整定**：Ziegler-Nichols、继电自整定都是"一次成型"，给完就走。
这里是边看边改；而且**策略是一次性学好的**，换一台同族设备不需要重新训。

**对比普通预测头和优化器**：一次前向的计算成本不等于更少仿真或更好的控制器。
[ABLATION](docs/ABLATION.md)报告匹配划分的回归/argmax对照；一个训练权重与三个评测样本
不能证明类型接口具有普遍因果优势。[PRACTICAL_BUDGET](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/PRACTICAL_BUDGET.md)在固定
起点下同时列返回代价和实际调用。结果取决于对象与先验，head并非在所有组和指标上优于传统基线。

**为什么不用`pidtune`？** 有合适线性模型时，应把`pidtune`作为基线并回到完整模型验证。
历史的“辨识→`pidtune`”是另一种流程，失败边界见[BENCHMARK](docs/BENCHMARK.md)。
准确模型不等于默认设计必然最小化本仓库代价。

**当你的对象在训练动物园之外**：它不神，死区、反向响应、开环不稳定都会翻车
（见 [`docs/GENERALIZATION.md`](docs/GENERALIZATION.md)）。先与同一实际仿真额度下的
有界传统搜索比较；训练"专家"是可选的另行研究，不保证修复：

```bash
python scripts/10_specialize.py --scenario valve_dead_zone --name valve
```

专门化依赖离线仿真，也可能让留出性能变差。当前实测及撤回的历史归因见[SPECIALIZE](docs/SPECIALIZE.md)。

---

## 上手

### 人用

```bash
git clone https://github.com/lijiawei255/jev-tune && cd jev-tune
conda create -n jev-tune python=3.12 -y && conda activate jev-tune
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e .
jev-tune demo            # 12 个未见对象，决策头 vs CMA-ES vs Z-N，约 20 秒
```

然后在自己模型上，**先跑 doctor 再调参**。它约 40 秒（几乎全是 MATLAB 启动），回答的是
决定后面一切的那个问题：这个模型到底能不能调？

```bash
jev-tune doctor  --model C:/path/你的模型.slx           # 加载、编译、求解器、回路
jev-tune matlab  --model C:/path/你的模型.slx --auto --plot before_after.png
```

`compiles` 那行失败，后面全都不用试了，而且它会点名缺哪个工作区变量；`tunable` 失败，
原因就在那一行和 `--json` 里。九个检查、一行一个，真实输出见
[`docs/EXAMPLES.md`](docs/EXAMPLES.md)。

**请 clone，不要 `pip install jev-tune`。** MATLAB 桥（`matlab/*.m`）和权重
（`models/`，600 KB）跟着仓库走，PyPI 上的 wheel 会是一个不完整的包：命令能跑，
但找不到真正干活的东西。仓库本身就是分发单元——不需要 PyPI、Docker 或 GPU。
`git clone` 慢的话，用绿色的 **Code → Download ZIP** 得到同一棵树。

### Agent 用

让你的助手读 [`AGENTS.md`](AGENTS.md)，简版就是：

```bash
bash scripts/agent_setup.sh            # macOS / Linux / WSL；幂等、无交互
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\agent_setup.ps1
```

安装脚本在所选Python环境中以editable方式安装项目，但子进程不会激活调用者的shell。
使用裸`python`前，应在当前shell执行它输出的`[setup] activate:`命令，激活所选conda
环境或`.venv`。Agent每次使用独立shell时，每条Python命令都应显式调用`[setup] python:`
输出的解释器绝对路径；status JSON的`executable`也提供该路径。把以下示例路径换成
实际输出的解释器：

```bash
"/path/from/setup/python" -m jev_tune.cli status --json   # 退出码 0=就绪，2=缺什么会直接告诉你
"/path/from/setup/python" -m jev_tune.cli discover --model 你的模型.slx --json
"/path/from/setup/python" -m jev_tune.cli matlab --model 你的模型.slx --auto --json
```

```powershell
& "C:/path/from/setup/python.exe" -m jev_tune.cli status --json
& "C:/path/from/setup/python.exe" -m jev_tune.cli discover --model 你的模型.slx --json
& "C:/path/from/setup/python.exe" -m jev_tune.cli matlab --model 你的模型.slx --auto --json
```

或者注册 MCP 服务器，让助手把它当工具直接调：

```jsonc
{ "mcpServers": { "jev-tune": { "command": "jev-tune-mcp" } } }
```

工具：`tune_status`、`tune_probe_matlab`、`tune_doctor`、`tune_discover`、
`tune_simulink`、`tune_apply_gains`、`tune_demo`。`tune_doctor` 解释"为什么不能调"；
`tune_discover` 告诉助手哪几个块是控制器、哪一路信号是被测量；`tune_simulink`
返回最终增益 + 每次实验的代价 + 回滚次数——**一次工具调用，而不是二十次**。

![Agent 在环 vs 决策头](assets/agent_vs_head.png)

*历史示意使用仿真0.111→0.09 s与仅前向0.19 ms；当前完整决策实测见docs/COMPUTE.md，LLM往返为图中标明的假设。*

### 在自己的 Simulink 模型上用

```matlab
addpath('matlab');
R = jev_tune_model('你的模型.slx', 'work_dir', 20, 10, 1.0);
```

加 `--auto`（或 cfg.auto_discover=true）时**块名完全无所谓**：发现器沿信号图找
控制器、被测量信号和参考值，模型没有示波器就在副本上插一个记录点。不加 `--auto`
时才按根层 `Gain_Kp`/`Gain_Ki`/`Gain_Kd` + `Scope-*` 的老约定走。

### 没有 MATLAB？直接用传递函数

```bash
jev-tune loop --num 1 --den "1 0.6 1" --delay 0.02
```

同一个决策头、同一套决策契约，只把"做一次实验"换成 ODE 积分。它也是 CI 每次推送
都会跑的路径，所以决策链路不会只在 MATLAB 里被验证。

---

## 一次迭代怎么走

```
被控对象 / Simulink ──► 响应 (t, y, u)
                          │
                          ▼
               20 个指标 + 2×64 点曲线          ← 超调、上升、调节、IAE/ITAE、
                          │                       饱和占比，以及"上一步动作+结果"
                          ▼
        ┌─────────────────────────────────┐
        │  决策头（约 200 KB，ONNX）       │
        │  choice ×3    score    noul     │
        └────────────────┬────────────────┘
                         ▼
   期望值解码 + 方差信赖域（没把握就小步走）
                         ▼
   确定性安全闸（限幅、回滚）—— `noul` 只是建议
                         ▼
                 新的 Kp, Ki, Kd
```

更多设计说明：[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

---

## 历史吞吐测量

以下来自曾使用跨任务模型与Ku扫描缓存的旧实现。该缓存现已停用，表内耗时及折算任务总量
均为历史记录，不是当前吞吐承诺。

| 历史配置 | 记录的20次迭代任务耗时 |
| :--- | ---: |
| Agent 在环（LLM 3 s/次） | 60 s |
| **一个 CLI 进程跑一个任务** | **122 s**（50 s 启动 + 24 s 建模 + 39 s 扫 Ku + 8 s 回路；不带 `--auto`） |
| 旧常驻worker（缓存编译和Ku） | **8.8 s** |
| 长驻 MATLAB 会话 | **2.7 s** |

当前worker可保留MATLAB进程，但每个任务会重新设置模型并扫描；当前吞吐需重新测量。
`iters`只限制调参循环，发现、探测和验证仍会增加仿真；实际尝试次数见`n_total_simulations`。

| 任务数 | Agent 在环 | 一进程一任务 | 常驻 worker |
| ---: | ---: | ---: | ---: |
| 100 | 1.7 h | 3.4 h | **15 min** |
| 1 000 | 17 h | 34 h | **2.5 h** |

历史单任务耗时来自参考机器；LLM时延及任务总量是条件假设与外推。历史分解、当前限制及
版本矩阵见[`docs/SCALE.md`](docs/SCALE.md)。

---

## 基准

**验证族：120个two_mass对象。** 参与过设计决策的历史基准。迭代方法最多20次，一次性方法列实际消耗；表内迭代次数是分配上限，不是提前停止后的实测次数。解析起点方法共享oracle Ku/Tu，扫描失败统一采用固定非oracle先验。

| method | median J | p90 J | maximum budget / one-shot actual |
| :--- | ---: | ---: | ---: |
| `jev_head` | 0.482 | 1.030 | 20 |
| `bo` | 0.547 | 1.552 | 20 |
| `jev_head_swept` | 0.510 | 1.014 | 20 |
| `shrunk_zn` | 1.290 | 1.905 | 1 |
| `identify+pidtune_PID` | 0.742 | 1.705 | 2 |
| `swept_zn` | 1.860 | 2.791 | 8 |
| `vocab_hill` | 1.463 | 2.212 | 20 |
| `cmaes` | 1.723 | 2.521 | 20 |
| `simplex` | 2.037 | 2.879 | 20 |
| `zn_classic` | 2.322 | 3.082 | 1 |

**冻结热工族：120个固定网格对象。** 训练后冻结，此前正确性修复后重测，未据此选择新权重；不是预注册前瞻测试。

| method | median J | p90 J | maximum budget / one-shot actual |
| :--- | ---: | ---: | ---: |
| `vocab_hill` | 1.711 | 2.447 | 20 |
| `jev_head_swept` | 1.785 | 3.800 | 20 |
| `jev_head` | 1.833 | 2.816 | 20 |
| `bo` | 1.878 | 2.684 | 20 |
| `cmaes` | 2.000 | 2.879 | 20 |
| `identify+pidtune_PID` | 2.330 | 3.064 | 2 |
| `zn_classic` | 2.682 | 3.374 | 1 |
| `swept_zn` | 3.580 | 5.334 | 8 |
| `shrunk_zn` | 4.854 | 5.158 | 1 |
| `simplex` | 2.302 | 3.146 | 20 |

这些冻结行与v0.9[实用预算评测](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/PRACTICAL_BUDGET.md)分开；后者列实际调用，也不证明head全面优于基线。历史辨识→pidtune行保留原实现的失败边界。计账规则见[BENCHMARK](docs/BENCHMARK.md)，扫描恢复/回退见[原始表](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1)。

**历史Simulink模型结果（直流电机，旧目标）**

此表保留v0.2记录，不是v0.9重跑，不可与按真实时间网格修正后的目标直接数值比较。

| 增益组 | Kp | Ki | Kd | 代价 |
| :--- | ---: | ---: | ---: | ---: |
| Z-N 起点 | 240 | 1160 | 12.4 | 1.238 |
| **Jev 头（第 5 次实验找到）** | 90.7 | 160.9 | 15.5 | **0.598** |
| 实验课人工调参 | 280 | 300 | 30.0 | 0.393 |

细节、caveat 与复现命令：[`docs/STEP1_RESULTS.md`](docs/STEP1_RESULTS.md)、
[`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md)。

---

## 没有做的对照

以下是这个项目尚未做的对照中的两项，列在这里，免得读者从基准里自己猜边界：

| 没做的 | 为什么重要 | 补上它需要什么 |
| :--- | :--- | :--- |
| **不在网络上的语言模型** | 目前的语言基线只有云端 API（单轮 5.34 s、40 次里 13 次解析失败），把"语言层"和"网络往返、输出解析"混在了一起 | 同一个回路里换成本地 1.5B–4B 模型 |
| **外部使用者** | 基准里的每个对象都是我们自己的。"你可以拿它去调你的项目"目前是有测试支撑的设计目标，不是观察到的结果 | 一个同事的模型 |

原来第一条"类型化接口 vs 普通回归头"已经补上并实测：`docs/ABLATION.md` 用同一个
编码器、同一份数据、同一 20 次预算，对比了回归头、argmax、期望解码、方差缩步、
显式弃权与确定性闸门。结论（包括类型化路径**不**占优的地方）都在那份文件里。

## 仓库结构

```
src/jev_tune/core/           numpy-only shell: primitives, policy, calibration, gate
src/jev_tune/domains/pid/    PID test bed: plants, metrics, state, expert, model, train,
                             decision backends, evaluate, baselines, MATLAB bridge, plot
src/jev_tune/domains/light/  linear_shell.py (ordered numeric), vla_mask.py (categorical)
src/jev_tune/cli.py          status / demo / doctor / discover / matlab / loop / batch / check
src/jev_tune/mcp_server.py   the seven MCP tools
c/                           C99 float32 reference, zero malloc, generated vectors
matlab/                      Fast Restart bridge, hand-written forward pass, tests
scripts/                     01 dataset, 02 train, 03 evaluate, 04 ONNX, 06 MATLAB weights,
                             10 specialize, 11 robustness, 18 export C, 20 abstention,
                             22 calibrate-only, archive.py, docs_relink.py
docs/                        design, results, BOUNDARIES, TRADEOFFS, ARCHIVE
```

## 我的任务能用吗

| 你的任务 | 适配度 |
| :--- | :--- |
| 单入单出 PID、阶跃响应、对象能给出 Simulink 模型或传递函数 | **开箱即用** |
| 控制器是掩码的 `PID Controller` 块 | 开箱即用（一个开关） |
| 有死区、反向响应，或对象与训练动物园差别很大 | 跑一次专家化，约 2 分钟 |
| 目标是跟踪 / 扰动抑制 | 换指标 + 重训（策略与目标绑定） |
| 串级、MIMO、非 PID 控制器、硬件在环 | 超出当前设计范围 |

在 200 个零样本对象上，**没有任何一个的最终结果差于 Z-N 起点**——返回的永远是
实测过最好的那组增益，某一步爆炸时还有确定性回退。完整范围、鲁棒性表和逐任务
工作量估计：[`docs/APPLICABILITY.md`](docs/APPLICABILITY.md)。

## 文档语言

所有给人看的文档都是**中英双语同文件**：英文在前，中文译文在后，顶部有语言切换。
覆盖本 README（[English](README.md)）、`NOTICE`、`CONTRIBUTING`、`SECURITY`、
`CODE_OF_CONDUCT`，以及 `docs/` 下的每一篇。

| 文档 | 回答什么 |
| :--- | :--- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 原语契约与一次迭代 |
| [`docs/STEP1_RESULTS.md`](docs/STEP1_RESULTS.md) | 延迟、校准、留出基准 |
| [`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md) | 真实 Simulink 模型，以及那次值得记录的退步 |
| [`docs/GENERALIZATION.md`](docs/GENERALIZATION.md) | 十个动物园外场景，以及它到底输在哪 |
| [`docs/SCALE.md`](docs/SCALE.md) | 规模效应、并发、MATLAB 版本 |
| [`docs/SPECIALIZE.md`](docs/SPECIALIZE.md) | 按项目专家化的流程 |
| [`docs/APPLICABILITY.md`](docs/APPLICABILITY.md) | 能做什么、不能做什么、每个缺口的工作量 |

## 参与贡献

欢迎 issue 和 PR，先读 [`CONTRIBUTING.md`](CONTRIBUTING.md)。三条底线：
**用数字说话**、**不要悄悄退化基准**、**不要绕过 `choice/score/noul` 契约**。

现在最需要帮忙的地方：

| 方向 | 需要什么 |
| :--- | :--- |
| 目标函数预设 | 跟踪 / 扰动抑制指标 |
| 并发 worker | 批量时的多 MATLAB 并行 |
| 死区特征 | 区分"死区抖动"和"增益过大" |
| 更多对象族 | 有公开动力学的、动物园里没有的 |
| 翻译 | 目前有英文和简体中文 |

## 如何引用

请优先引用**概念DOI [10.5281/zenodo.23624699](https://doi.org/10.5281/zenodo.23624699)**，它始终指向
最新正式归档版本。若需固定到某一版本，请引用该版本DOI（见Zenodo记录页）。

```bibtex
@software{li_jevtune,
  author  = {Li, Jiawei},
  title   = {jev-tune: a Jev-inspired calibrated decision and safety shell for typed PID autotuning},
  doi     = {10.5281/zenodo.23624699},
  url     = {https://github.com/lijiawei255/jev-tune},
  license = {MIT}
}
```

机器可读的引用信息（作者、ORCID、DOI）见仓库根目录[`CITATION.cff`](CITATION.cff)，
GitHub的“Cite this repository”按钮即读取该文件。

## 致谢与边界

* **实验场不止一个。** 方法与出厂权重是在合成植物动物园（2 000 个对象、6 个族）
  上开发的，随后在 10 个分布外控制场景和一个小型生成模型
  （`matlab/make_demo_model.m`）上验证。**电机阀门基准模型**
  只是其中**又一个实验场**：一个刚好在手的、比较真实的 Simulink 被控对象。公开训练代码使用合成仿真；基准模型观察影响了后续动物园设计，因此属于开发示例。
  当前源码树和新发布不含该外部模型原文件，保留的历史响应图是本项目自主绘制。
  其余实验场见 [`docs/GENERALIZATION.md`](docs/GENERALIZATION.md)。
* **Jev**（TypeSafe AI）与 **Laya**（Convai Innovations）启发了本项目实现的接口，
  与之无隶属、无背书关系。
* **MATLAB** / **Simulink** 是 The MathWorks, Inc. 的商标。
* 用了哪些第三方代码、哪些刻意没有放进来、各自的许可证：[`NOTICE.md`](NOTICE.md)。
* 完整源码、模型、数据的分发及排除清单：[`OPEN_SOURCE`](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/OPEN_SOURCE.md)。

## 许可证

MIT © JIAWEI LI — 见 [`LICENSE`](LICENSE)。
