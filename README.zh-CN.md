# jev-tune

[![tests](https://github.com/lijiawei255/jev-tune/actions/workflows/ci.yml/badge.svg)](https://github.com/lijiawei255/jev-tune/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.12-blue)](pyproject.toml)
[![MATLAB](https://img.shields.io/badge/MATLAB-R2024b%20%E5%AE%9E%E6%B5%8B-orange)](docs/SCALE.md)
[![decision latency](https://img.shields.io/badge/decision-0.19%20ms-brightgreen)](docs/STEP1_RESULTS.md)
[![model size](https://img.shields.io/badge/model-200%20KB-lightgrey)](docs/STEP1_RESULTS.md)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
## 让你的 Agent 直接接管

如果你用编程 Agent（Claude Code、Codex、OpenCode、Cursor——任何能执行命令的），
下面这大半页都不用看。把一句话和你的模型路径丢给它：

> **“用 github.com/lijiawei255/jev-tune 调一下 `D:\work\MyMotor.slx` 的 PID，
> 然后给我看前后对比曲线。”**

Agent 会读 [`AGENTS.md`](AGENTS.md)，里面第一步就是运行 `jev-tune discover`：
它**沿着信号图找**（不看块名）增益块、被测量信号和参考值，再用两次额外仿真确认
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

*这是 `discover` 在一台实验课电机上的全过程，**逐帧都来自模型本身**：误差汇合点由一次
仿真确认（参考值与稳态输出是同一个物理量），每个增益按"它和汇合点之间有什么"分类，
再用两次额外仿真确认"把它翻倍是否真的改变响应"。上面这些块名**没有参与任何判断**——
`Gain_Kp` 改叫 `alpha` 结果完全一样。重新生成用 `scripts/15_make_discovery_gif.py`。*

## 从哪读起

| 我想…… | 去看 |
| :--- | :--- |
| 一分钟内跑起来 | [试一试](#上手) |
| 看一次完整运行（带真实输出） | [`docs/EXAMPLES.md`](docs/EXAMPLES.md) |
| 弄清模型为什么调不了 | `jev-tune doctor --model <文件>` |
| 判断我的模型适不适合 | [`docs/APPLICABILITY.md`](docs/APPLICABILITY.md) |
| 搞清“类型化决策”到底是什么 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 自己核对数字 | [`docs/STEP1_RESULTS.md`](docs/STEP1_RESULTS.md)、[`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md)、[`docs/CLAIMS.md`](docs/CLAIMS.md) |
| 用 Agent 或 MCP 驱动 | [`AGENTS.md`](AGENTS.md) |
| 处理没见过的对象族 | [`docs/SPECIALIZE.md`](docs/SPECIALIZE.md) |
| 批量跑几百个模型 | [`docs/SCALE.md`](docs/SCALE.md) |
| 和 `pidtune` 公平对比 | [pidtune 那一节](docs/APPLICABILITY.md#如果你已经有准确的模型请直接用-pidtune) |

[![English](https://img.shields.io/badge/README-English-blue)](README.md)

**PID 调参，每一次判断都是"选一个选项"，而不是写一段话。**
一个 200 KB 的模型看一眼阶跃响应，在笔记本 CPU 上 **0.19 毫秒**给出一个有界的
增益调整量——不用自回归大模型、不联网、不需要 GPU。发布版还会在**把握度不足时保持
不动**：没把握就不碰被控对象。

> **受 Jev 启发，非官方关联。** 这里借的是它的**接口规范**：`choice`（多选一）、
> `score`（分档打分）、`noul`（是否安全）三个带校准概率的原语。**不是** TypeSafe 的
> 托管 Jev 模型，也**不是** Laya 那个 421M 的文本编码器。运行时策略是本仓库自己训练
> 的数值决策头。本仓库与 TypeSafe AI **无隶属、无背书、无赞助关系**
> （借了什么、没借什么：[docs/JEV_MAPPING.md](docs/JEV_MAPPING.md)）。

![七种方法在同一批对象上比赛](assets/race.gif)

*同一批 40 个未见对象，七种调参方式。**图里每个数字都是实测的**：每 N 次实验后的
中位代价来自 `scripts/12_make_race.py` 的一次真实运行；右图问的是"多久能拿到一个
能用的控制器"（J ≤ 0.6），按 0.4 秒/次折算。斜线阴影那行是在环路上接一个托管模型
的 Agent——它的一次往返实测**中位 5.3 秒**（GLM-5.3-Flash，40 次调用，其中 13 次
输出无法解析）。手工调参不画曲线是刻意的——它给出的是「几小时之后的一组增益」，
不是一串实验。*

![在真实 Simulink 直流电机上调参](assets/tuning.gif)

*上面每一帧都是基准实验里那台直流电机模型上的一次真实闭环实验。调的是
`Kp / Ki / Kd`，右边是它正在最小化的代价。最好的增益出现在第 5 次实验
（约 0.55 秒仿真），停滞检测在第 9 次停下。*

---

## 15 秒看懂

| | |
| :--- | :--- |
| **做什么** | 看刚测到的响应，决定下一步把 PID 增益乘多少 |
| **多快** | 模型前向 **0.19 ms**、完整类型化决策 **0.73 ms**（ONNX，单线程，p99 1.36 ms）；托管大模型 Agent 一次 **5.34 s**（实测，40 次调用） |
| **多省实验** | 真实 Simulink 电机上 **5 次实验**把代价从 **1.238 降到 0.598**（v0.2 的记录运行；修正增益扫描后同一模型起点更好，整定器会直接返回电机自带的增益——[原因](docs/STEP4_RESULTS.md#correction-the-ku-sweep-was-wrong)）；结果不会比 ZN 起点与模型自带增益中更好的那组更差 |
| **多能泛化** | **验证族**（120 株，参与过设计决策）：**0.440 / p90 1.038**，对比 BO 0.567、CMA-ES 1.705。**冻结测试族**（120 株"一阶 + 大延迟"热工对象，从未用于任何决策）：**1.737，第二**——同词表爬山 1.711 更低，BO 1.877、CMA-ES 1.976 更高 |

![前后对比](assets/before_after.png)

*同一个被控对象、三组增益。灰色：Ziegler-Nichols 起点；蓝色：5 次实验后；
虚线：实验课人工调参的结果。那次运行的起点来自 v0.2 的 Ku 扫描，而那个扫描有三处缺陷，
已修复——见 [`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md) 的更正一节。*

---

## 它和别的方法有什么不一样

**对比"接大模型 Agent 调参"**：Agent 在环是"看图 → 写一段话 → 解析那段话"，
每步要等几秒，而且结果埋在自然语言里。这里模型只输出三个原语——`choice` 决定
步长、`score` 评价当前响应、`noul` 判断这一步安不安全——所以决策是一个可以直接
设阈值、可以记录、可以校准的概率向量。温度校准后 ECE 实测 **0.02**。

**对比经典自整定**：Ziegler-Nichols、继电自整定都是"一次成型"，给完就走。
这里是边看边改；而且**策略是一次性学好的**，换一台同族设备不需要重新训。

**对比贝叶斯优化**：BO 每一步都要重新拟合代理模型。这里是摊销的：一次前向即可，
同预算下比 CMA-ES 好 3 倍——但尾部不如 BO，基准表里如实写了。

**当你的对象在训练动物园之外**：它不神，死区、反向响应、开环不稳定都会翻车
（见 [`docs/GENERALIZATION.md`](docs/GENERALIZATION.md)）。正确做法是训一个
"专家"——一条命令、约 1.5 分钟 CPU：

```bash
python scripts/10_specialize.py --scenario valve_dead_zone --name valve
```

在没见过的对象族上实测：中位代价 **2.242 → 2.207（−2%）**，30 个留出抖动、约 95 秒 CPU——
也就是说，专门化**没有**修好这一族。v0.2/v0.3 记的 −49% / −16% 是在 0.4.0 之前
**不可复现**的场景抽样上测的；`docs/SPECIALIZE.md` 已写明，不再引用它们。

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
bash scripts/agent_setup.sh            # 幂等、无交互
python -m jev_tune.cli status --json   # 退出码 0=就绪，2=缺什么会直接告诉你
python -m jev_tune.cli discover --model 你的模型.slx --json
python -m jev_tune.cli matlab --model 你的模型.slx --auto --json
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

*仿真 0.111→0.09 s 与决策 0.19 ms 是实测；LLM 往返是假设，已在图注标明。*

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

## 速度到底省在哪（实测）

| 跑法 | 20 次实验耗时 |
| :--- | ---: |
| Agent 在环（LLM 3 s/次） | 60 s |
| **一个 CLI 进程跑一个任务** | **122 s**（50 s 启动 + 24 s 建模 + 39 s 扫 Ku + 8 s 回路；不带 `--auto`） |
| 常驻 worker（缓存编译和 Ku） | **8.8 s** |
| 长驻 MATLAB 会话 | **2.7 s** |

**优势不来自"模型快"，而来自"MATLAB 别重开、模型别重编译"**。MCP 服务器和
`jev-tune batch` 就是为此设计的。

| 任务数 | Agent 在环 | 一进程一任务 | 常驻 worker |
| ---: | ---: | ---: | ---: |
| 100 | 1.7 h | 3.4 h | **15 min** |
| 1 000 | 17 h | 34 h | **2.5 h** |

完整分解、并发方案与版本矩阵：[`docs/SCALE.md`](docs/SCALE.md)。

---

## 基准

**验证族（120 个双质量谐振对象，每个方法 20 次实验）。** 这一族参与过两个设计决策——
否掉前瞻价值网、比较词表 v1 与 v3——所以它是**验证集**，不是干净测试集。

| 方法 | 最终代价（中位） | p90 | × 参考 | 成功率 | 达目标实验数 | 实验预算 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Jev 决策头** | **0.440** | **1.038** | **1.31** | **41%** | **5.0** | 20 |
| 贝叶斯优化 | 0.567 | 1.510 | 1.56 | 35% | 8.5 | 20 |
| 辨识 → `pidtune` | 0.742 | 1.705 | 1.91 | 29% | 2.0 | 2 |
| 缩小 Z-N | 1.290 | 1.905 | 4.48 | 30% | 1.0 | 1 |
| 实测 Ku/Tu 的 Z-N | 1.860 | 2.791 | 2.99 | 16% | 8.0 | 8 |
| 同词表爬山 | 1.463 | 2.212 | 2.35 | 15% | 5.0 | 20 |
| CMA-ES | 1.705 | 2.519 | 3.58 | 13% | 4.0 | 20 |
| 单纯形 | 2.037 | 2.879 | 4.43 | 7% | 4.0 | 20 |
| Ziegler-Nichols（解析 Ku/Tu） | 2.322 | 3.082 | 5.74 | 6% | 1.0 | 1 |

**冻结测试族（120 个"一阶 + 大延迟"热工对象）。** 由固定网格生成、**不含随机种子**，
在决策头训练完成之后定义，**只评一次**；没有任何设计决策用到它。

| 方法 | 最终代价（中位） | p90 | × 参考 | 成功率 | 达目标实验数 | 实验预算 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 同词表爬山 | **1.711** | **2.447** | **1.14** | **27%** | 9.5 | 20 |
| **Jev 决策头** | 1.737 | 2.871 | 1.30 | 16% | 13.0 | 20 |
| 贝叶斯优化 | 1.877 | 2.662 | 1.32 | 5% | 13.0 | 20 |
| CMA-ES | 1.976 | 2.879 | 1.36 | 4% | 16.0 | 20 |
| 辨识 → `pidtune` | 2.330 | 3.064 | 1.49 | 1% | 2.0 | 2 |
| Ziegler-Nichols | 2.682 | 3.374 | 1.76 | 0% | inf | 1 |

**两张表一起读。** 在它被验证过的那一族上，决策头是不掌握模型的方案里最好的；在它从未
见过的冻结族上，它是**第二**：一个朴素的贪心爬山（同样 7 档增益乘子）中位更低、尾部
更轻。所以诚实的说法是"一个能打赢经典一次性整定与同预算 BO/CMA-ES 的有用默认值"，
而不是"未见对象上最好的整定器"。另外，7 次 Kp 扫描在 120 个热工对象上 **0 个**恢复出
Ku（扫描窗口比死区时间还短），两个 `swept` 行因此走了回退，读的时候要知道。

**真实 Simulink 模型（直流电机）**

| 增益组 | Kp | Ki | Kd | 代价 |
| :--- | ---: | ---: | ---: | ---: |
| Z-N 起点 | 240 | 1160 | 12.4 | 1.238 |
| **Jev 头（第 5 次实验找到）** | 90.7 | 160.9 | 15.5 | **0.598** |
| 实验课人工调参 | 280 | 300 | 30.0 | 0.393 |

细节、caveat 与复现命令：[`docs/STEP1_RESULTS.md`](docs/STEP1_RESULTS.md)、
[`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md)。

---

## 没有做的对照

这个项目**没有**做两件事，列在这里，免得读者从基准里自己猜边界：

| 没做的 | 为什么重要 | 补上它需要什么 |
| :--- | :--- | :--- |
| **不在网络上的语言模型** | 目前的语言基线只有云端 API（单轮 5.34 s、40 次里 13 次解析失败），把"语言层"和"网络往返、输出解析"混在了一起 | 同一个回路里换成本地 1.5B–4B 模型 |
| **外部使用者** | 基准里的每个对象都是我们自己的。"你可以拿它去调你的项目"目前是有测试支撑的设计目标，不是观察到的结果 | 一个同事的模型 |

原来第一条"类型化接口 vs 普通回归头"已经补上并实测：`docs/ABLATION.md` 用同一个
编码器、同一份数据、同一 20 次预算，对比了回归头、argmax、期望解码、方差缩步、
显式弃权与确定性闸门。结论（包括类型化路径**不**占优的地方）都在那份文件里。

## 仓库结构

```
src/jev_tune/
  plants.py       植物动物园 + 向量化闭环仿真
  metrics.py      响应 -> 标量代价
  state.py        20 个特征 + 2×64 曲线
  primitives.py   Choice / Score / Noul（唯一输出面）
  decode.py       期望值解码、信赖域、区间细化
  model.py        决策头 + 一步预测价值网
  train.py        数据 -> 决策头（`expert.py` 是规则专家）
  baselines.py    Z-N、继电、单纯形、CMA-ES、BO
  identified.py   辨识 -> pidtune（工程界基线）
  discover.py     在陌生模型上找增益、信号与参考
  evaluate.py     基准测试用的留出回路
  plot.py         前后对比图
  scenarios.py    10 个"动物园外"场景（泛化测试）
  simulink.py、matlab_runner.py、matlab_worker.py   MATLAB 桥接与 worker
  mcp_server.py   七个 MCP 工具
  cli.py          status / demo / doctor / discover / matlab / loop / batch / check
matlab/          Fast Restart 桥接、手写前向、test_discover.m
scripts/         00 合并分块、00b 重标注、01 数据、02 训练、03 评估、
                 04 onnx、05 报告、06 MATLAB 权重、07 演示素材、08 泛化、
                 09 架构图、10 专家化、11 鲁棒性、12 竞赛图、13 跟踪演示、
                 14 Agent 基线、15 GIF、16 claims 校验
docs/            调研报告、架构、各阶段结果、claims、示例
assets/          README 用到的 GIF 和图片
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
| [`docs/PHASE0_RESEARCH_REPORT.md`](docs/PHASE0_RESEARCH_REPORT.md) | 生态家底、CPU 延迟真相、方案修正 |
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

## 引用

```bibtex
@software{li2026jevtune,
  author = {Li, Jiawei},
  title  = {jev-tune: System-1 typed decisions for PID autotuning},
  year   = {2026},
  url    = {https://github.com/lijiawei255/jev-tune},
  license = {MIT}
}
```

## 边界与参考

* **实验场不止一个。** 方法与出厂权重是在合成植物动物园（2 000 个对象、6 个族）
  上开发的，随后在 10 个分布外控制场景和一个小型生成模型
  （`matlab/make_demo_model.m`）上验证。**基准实验里的那台电机模型**
  只是其中**又一个实验场**：一个刚好在手的、比较真实的 Simulink 被控对象。它
  *不* 参与训练出厂权重，仓库里也不包含该模型——演示图只展示我们自己绘制的曲线。
  其余实验场见 [`docs/GENERALIZATION.md`](docs/GENERALIZATION.md)。
* **Jev**（TypeSafe AI）与 **Laya**（Convai Innovations）启发了本项目实现的接口，
  与之无隶属、无背书关系。
* **MATLAB** / **Simulink** 是 The MathWorks, Inc. 的商标。
* 用了哪些第三方代码、哪些刻意没有放进来、各自的许可证：[`NOTICE.md`](NOTICE.md)。

## 许可证

MIT © JIAWEI LI — 见 [`LICENSE`](LICENSE)。
