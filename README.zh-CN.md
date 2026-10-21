# jev-tune

[![tests](https://github.com/lijiawei255/jev-tune/actions/workflows/ci.yml/badge.svg)](https://github.com/lijiawei255/jev-tune/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.12-blue)](pyproject.toml)
[![MATLAB](https://img.shields.io/badge/MATLAB-R2019a%2B-orange)](docs/SCALE.md)
[![decision latency](https://img.shields.io/badge/decision-0.19%20ms-brightgreen)](docs/STEP1_RESULTS.md)
[![model size](https://img.shields.io/badge/model-200%20KB-lightgrey)](docs/STEP1_RESULTS.md)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![English](https://img.shields.io/badge/README-English-blue)](README.md)

**PID 调参，每一次判断都是"选一个选项"，而不是写一段话。**
一个 200 KB 的模型看一眼阶跃响应，在笔记本 CPU 上 **0.19 毫秒**给出一个有界的
增益调整量——不用自回归大模型、不联网、不需要 GPU。

> **这里的 "Jev" 指什么？** 指它的**接口规范**：`choice`（多选一）、`score`
> （分档打分）、`noul`（是否安全）三个带校准概率的原语。**不是** TypeSafe 的托管
> Jev 模型，也**不是** Laya 那个 421M 的文本编码器。运行时策略是本仓库自己训练
> 的数值决策头；Laya 最多只能当可选的文本后端。

![七种方法在同一批对象上比赛](assets/race.gif)

*同一批 40 个未见对象，七种调参方式。**所有曲线都是实测的**：每 N 次实验后的中位
代价，来自 `scripts/12_make_race.py` 的一次真实运行。右图问的是真正重要的问题——
多久能拿到一个"能用"的控制器（J ≤ 0.6），按 motor-valve benchmark 上实测的 0.4 秒/次折算。图里唯一
的假设是那条斜线阴影的行：每次实验假设一次 3 秒的大模型往返。*

![在真实 Simulink 直流电机上调参](assets/tuning.gif)

*上面每一帧都是 motor-valve benchmark motor-valve benchmark 直流电机模型上的一次真实闭环实验。调的是
`Kp / Ki / Kd`，右边是它正在最小化的代价。最好的增益出现在第 5 次实验
（约 0.55 秒仿真），停滞检测在第 9 次停下。*

---

## 15 秒看懂

| | |
| :--- | :--- |
| **做什么** | 看刚测到的响应，决定下一步把 PID 增益乘多少 |
| **多快** | 单次决策 **0.19 ms**（ONNX，单线程）；托管 Jev 一次 236–276 ms，通用大模型 Agent 一次几秒 |
| **多省实验** | **5 次实验**把真实 Simulink 电机回路的代价降了 **52%** |
| **多能泛化** | 在训练时没见过的对象族上，同样 20 次仿真预算，中位代价 **0.47** vs CMA-ES **1.81** |

![前后对比](assets/before_after.png)

*同一个被控对象、三组增益。灰色：Ziegler-Nichols 起点；蓝色：5 次实验后；
虚线：实验课人工调参的结果。*

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

在没见过的对象族上实测：中位代价 **2.242 → 1.152（−49%）**。详见
[`docs/SPECIALIZE.md`](docs/SPECIALIZE.md)。

---

## 上手

### 人用

```bash
conda create -n jev-tune python=3.12 -y && conda activate jev-tune
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e .
jev-tune demo            # 12 个留出对象，决策头 vs CMA-ES vs Z-N，约 20 秒
```

### Agent 用

让你的助手读 [`AGENTS.md`](AGENTS.md)，简版就是：

```bash
bash scripts/agent_setup.sh            # 幂等、无交互
python -m jev_tune.cli status --json   # 退出码 0=就绪，2=缺什么会直接告诉你
python -m jev_tune.cli matlab --model 你的模型.slx --json
```

或者注册 MCP 服务器，让助手把它当工具直接调：

```jsonc
{ "mcpServers": { "jev-tune": { "command": "jev-tune-mcp" } } }
```

工具：`tune_status`、`tune_probe_matlab`、`tune_simulink`、`tune_demo`。
`tune_simulink` 接收模型路径，返回最终增益 + 每次实验的代价 + 回滚次数——
**一次工具调用，而不是二十次**。

![Agent 在环 vs 决策头](assets/agent_vs_head.png)

*仿真 0.111→0.09 s 与决策 0.19 ms 是实测；LLM 往返是假设，已在图注标明。*

### 在自己的 Simulink 模型上用

```matlab
addpath('matlab');
R = jev_tune_model('你的模型.slx', 'work_dir', 20, 10, 1.0);
```

需要根层有 `Gain_Kp`/`Gain_Ki`/`Gain_Kd` 三个块和 `Scope-*` 示波器；如果名字不同，
用 `cfg.kp_block` 等改（或用 CLI 的 `--kp-block`）。控制器是掩码的
`PID Controller` 块时，用 `cfg.controller='pid_block'`。

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
| **一个 CLI 进程跑一个任务** | **122 s**（50 s 启动 + 28 s 建模 + 40 s 扫 Ku） |
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

**留出族（120 个对象，双质量谐振，训练时从未出现）**，目标 = 1.05 × 240 次仿真的
CMA-ES 参考。

| 方法 | 最终代价（中位） | p90 | × 参考 | 仿真次数 |
| :--- | ---: | ---: | ---: | ---: |
| **Jev 决策头** | **0.468** | 1.037 | **1.29** | 20 |
| 贝叶斯优化 | 0.567 | 1.510 | 1.56 | 20 |
| 辨识 → `pidtune` | 0.742 | 1.705 | 1.91 | 2 |
| 继电自整定 | 0.906 | **0.935** | 2.36 | 2 |
| CMA-ES | 1.813 | 2.618 | 3.75 | 18 |
| Ziegler-Nichols | 2.322 | 3.082 | 5.74 | 1 |

**真实 Simulink 模型（motor-valve benchmark 直流电机）**

| 增益组 | Kp | Ki | Kd | 代价 |
| :--- | ---: | ---: | ---: | ---: |
| Z-N 起点 | 240 | 1160 | 12.4 | 1.238 |
| **Jev 头（第 5 次实验找到）** | 90.7 | 160.9 | 15.5 | **0.598** |
| 实验课人工调参 | 280 | 300 | 30.0 | 0.393 |

细节、caveat 与复现命令：[`docs/STEP1_RESULTS.md`](docs/STEP1_RESULTS.md)、
[`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md)。

---

## 仓库结构

```
src/jev_tune/
  plants.py      植物动物园 + 向量化闭环仿真
  metrics.py     响应 -> 标量代价
  state.py       20 个特征 + 2×64 曲线
  primitives.py  Choice / Score / Noul（唯一输出面）
  decode.py      期望值解码、信赖域、区间细化
  model.py       决策头 + 一步预测价值网
  baselines.py   Z-N、继电、单纯形、CMA-ES、BO
  identified.py  辨识 -> pidtune（工程界基线）
  scenarios.py   10 个"动物园外"场景（泛化测试）
  cli.py         status / demo / check / matlab / batch
matlab/          Fast Restart 桥接 + 手写 MATLAB 前向
scripts/         00 数据、01 分块、02 训练、03 评估、04 onnx、
                 05 报告、06 MATLAB 权重、07 演示素材、
                 08 泛化、09 图、10 专家化
docs/            调研报告、架构、各阶段结果
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

* 演示动图和 [`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md) 的数字，来自对
  **电机阀门基准模型**的调参实验。该模型属于基准材料，
  **本仓库不转发**，图里只有我们自己画出来的曲线。这是个人项目、不是基准作业，
  也不代表基准背书。
* **Jev**（TypeSafe AI）与 **Laya**（Convai Innovations）启发了本项目实现的接口，
  与之无隶属、无背书关系。
* **MATLAB** / **Simulink** 是 The MathWorks, Inc. 的商标。
* 用了哪些第三方代码、哪些刻意没有放进来、各自的许可证：[`NOTICE.md`](NOTICE.md)。

## 许可证

MIT © JIAWEI LI — 见 [`LICENSE`](LICENSE)。
