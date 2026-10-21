# Phase 0 · 调研验证与架构定稿报告

> 项目：jev-tune — System-1（Jev 范式）决策模型驱动的控制参数极速整定框架
> 日期：2026-10-21 · 环境：Windows + MATLAB R2024b (Update 6) + Anaconda
> 状态：**调研完成，等待你的确认后再动工程代码**

---

## 0. 执行摘要（先看这一页）

**结论：项目方向成立，但初始技术假设中有 3 条必须修正，1 条需降级，1 条被证实。**

| # | 初始假设 | 核查结果 | 处置 |
| :-- | :--- | :--- | :--- |
| 1 | `Laya` 是真实可用的开源 Jev 替代（`NandhaKishorM/laya` / HF `convaiinnovations/laya`，Apache-2.0） | ✅ **真实存在**，33.8k★，三套 checkpoint，ONNX 导出 + 6 种语言绑定，`laya.train.finetune` 可用 | 采纳为 Track B 基座 |
| 2 | 冻结 ModernBERT 主干，仅微调 26.5M Decision Head | ⚠️ **head≈26M 正确**（421M−395M），但**官方 checkpoint 是"主干全量微调"**（`fine_tuned_from_checkpoint: true`，7313 updates / 1.96h），不是冻结主干 | 我们自己做"冻结主干 + 只训头"，这正是我们要的训练形态 |
| 3 | Windows 纯 CPU 单步推理 **数十毫秒** | ❌ **不成立（fp32/PyTorch）**：本机同级 CPU 实测 288–580 ms/次。只有 **INT8（OpenVINO/ONNX）+ 短状态** 才到 **28–90 ms** | 把 KPI 改成"INT8 + ≤120 token 下 30–90 ms"，并引入数值原生小头做 Track A |
| 4 | `Von` 可作为备选基座 | ❌ **检索不到任何仓库/模型**（GitHub 两组关键词 + Exa 均无命中） | 从备选清单移除 |
| 5 | `NumericJev` / `AnyJev` 是可用论文思想 | ✅ 均真实：NumericJev = arXiv 2609.28587（已改名 **JevNext**，`Bring-AI/jev-numeric`）；AnyJev = `nokia-applied-research/AnyJev` + 技术报告 | 采纳它们的**解码器**与**去偏/闭式头**思想 |

**最关键的三个新事实（决定了架构）**

1. **Simulink 侧瓶颈不是推理，是重复编译。** 本机实测（R2024b，你给的 motor-valve benchmark 电机模型，StopTime=1 s）：普通模式 **763 ms/次**，Fast Restart **40 ms/次（18.9×）**，冷启动 10.1 s。推理 40 ms 与仿真 40 ms 同量级——**"推理比仿真快"这个卖点必须靠 Fast Restart 才能兑现**。
2. **421M 文本编码器读 8 个数字是浪费。** 395M 主干吃掉 99% 算力，只为产出 26M 头的输入；控制状态是 15–25 维数值，天然不需要 tokenizer。生态里机器人项目（drone 2.5 Hz、MuJoCo skill 选择）全都把决策模型放在**慢速高层**——这既是先例，也是警告。
3. **生态是空白，也是风险。** 全 GitHub 检索（992 项目目录 + 30 余个 awesome 列表）**没有任何一个用 Jev/System-1 做连续参数整定或 Simulink 调参的项目**。机会是首创，风险是"没人证明它比经典方法更好"→ 因此**必须自带 baseline（Z-N / 继电自整定 / 单纯形 / CMA-ES / 贝叶斯优化）**，否则不可发表、不可信。

**放行建议**：可以进入 Step 1，但工程目标从"毫秒级闭环保姆式调参"改成：

> **在 Windows 纯 CPU 上，用 Jev 原语（Choice/Score/Noul）在一次前向内给出有界的增益修正，使达到目标响应的迭代次数比经典自整定减少 ≥50%，单次决策 ≤90 ms。**

---

## 1. 调研方法与证据等级

| 等级 | 来源 | 用途 |
| :--- | :--- | :--- |
| A（可复现） | 本机实测（MATLAB R2024b）+ 仓库源码/配置文件 | 结论依据 |
| B（一手文档） | 官方 README / BENCHMARKS.md / HF 模型卡 / arXiv | 结论依据 |
| C（第三方实测） | 社区 benchmark（laya.tools 汇总、laya-cpp、OpenVINO fork） | 交叉验证 |
| D（营销稿） | 行业博客"sub-10ms PLC"一类 | **不作为依据** |

已核查对象：`NandhaKishorM/laya`、`convaiinnovations/laya*`、`receptron/laya`、`jev-cookbook`(×6)、`TianyuCodings/NanoJev`、`jaredpalmer/kev`、`nokia-applied-research/AnyJev`、`Bring-AI/jev-numeric`(NumericJev)、`feder-cr/jev`、`kshetrajna12/reflex`、`TheoLeeCJ/SemIf-OpenJev`、`browser-use/jev-ultrafast`、`rupeshs/laya-ov-int8`、`ggml-org/Laya-GGUF`、`samiul000/laya-cpp`、MathWorks `matlab-mcp-server`、`simulink-mcp`、`akkified/pid-tuning-llm`、`Von`。

---

## 2. 维度一：Jev / System-1 开源生态的真实可用性

### 2.1 生态全景（2026-10 现状）

事实上的标准是 **TypeSafe 的 Jev**（托管 API，System One），围绕它长出了"本地开源替代"生态：

| 项目 | ★ | 许可 | 形态 | 对我们的价值 |
| :--- | --: | :--- | :--- | :--- |
| `NandhaKishorM/laya` (HF `convaiinnovations/laya`) | 33.8k | Apache-2.0 | 非自回归判定模型，3 个 checkpoint，ONNX + TS/Rust/Go/Java/.NET 绑定 | **主基座** |
| `TianyuCodings/NanoJev` | 2.6k | MIT | 端到端训练管线 + 并行决策，面向游戏/导航 | 借鉴训练脚本结构 |
| `jaredpalmer/kev` (0.5B–27B) | 9.4k | Apache-2.0 | Qwen3.5 **冻结主干 + LoRA + pointer head** | 证明"冻结主干"路线；CPU 太重 |
| `nokia-applied-research/AnyJev` | 1.5k | Apache-2.0 | 把**任意** LLM 变成 Jev 风格：logit 读出 + 去偏 + 闭式头 | **方法学金矿**（见 2.5） |
| `Bring-AI/jev-numeric`（原 NumericJev） | — | — | 训练无关的数值解码（区间树） | **连续量解码器** |
| `feder-cr/jev` / `reflex` / `SemIf-OpenJev` | 0.9k/0.2k/4.9k | — | C++/Qwen 小模型复刻 | 备选，暂不深入 |
| `rupeshs/laya-ov-int8` + `laya-openvino` | — | — | Laya 的 OpenVINO INT8 导出（405 MB） | **Windows CPU 延迟关键** |

> 说明：生态里"Jev"一词已被大量非模型项目复用（路由器、浏览器、交易机器人），检索时需用 `system one` / `typed decision` 做消歧。

### 2.2 Laya 深挖（我们真正要用它的话，必须知道这些）

**架构与配置**（来自 HF `rl_agent_config.json`，非推测）：

```json
{ "encoder": "answerdotai/ModernBERT-large", "head_layers": 2,
  "max_len": 512, "head_max_len": 192, "max_prefixes": 6,
  "temperature_by_options": { "choice:2": 1.906, "choice:3-5": 1.760, "choice:6-10": 1.000,
                              "score:3-5": 1.251, "noul:2": 1.983, "choice:11+": 0.1006 },
  "training": { "updates": 7313, "epochs_completed": 1, "hours": 1.96, "fine_tuned_from_checkpoint": true } }
```

| 项目 | 事实 |
| :--- | :--- |
| 参数量 | `model.safetensors` = 842.6 MB ≈ **421M**（ModernBERT-large 395M + 2 层头 + option-marker scorer ≈ **26M**，与提示词一致） |
| 三套权重 | `laya`（421M, 512 ctx, 英文最强）/ `laya-multilingual`（322M mmBERT, 1024→8k）/ `laya-typed-decisions`（421M，判定任务微调版 0.766） |
| 输入 | state 可以是**文本、邮件、工单或 JSON**——控制特征直接以 JSON 喂它是"官方支持"的路径 |
| 输出 | `choice`（每选项概率）/ `score`（有序分布）/ `noul`（校准 P(true)）；**一次前向回答全部问题**（3 个增益 3 个 question = 1 次前向，代价≈1 个） |
| 选项机制 | 每个选项在自己的 `[MASK]` 位打分后 softmax → **新增选项无需重训**（对我们是关键：增益倍率表可随时改） |
| 上限 | 建议 `choice` 选项 **< 20 个**；`head_max_len=192` 是"选项文本"预算；`banking77`(77 类) 掉到 0.425 就是预算天花板 |
| 校准 | 出厂**过度自信**（ECE 0.466 / 0.314），需按 (问题类型, 选项数) 重拟温度；官方给了分桶温度 |
| 训练 | `from laya.train import finetune, TrainConfig`；`laya-train` CLI；损失含 `rlcd_loss`（against strictly proper scoring rules）、`soft_ce_loss` |
| 部署 | `ONNXAgent`（CPU，torch 运行时不需要）；官方导出脚本 `export/export_onnx.py`；另有 TS/Rust/Go/Java/.NET 原生绑定 |

**CPU 延迟的真实数字（这是"毫秒级"承诺的生死线）**

| 硬件 / 运行时 | 状态长度 | 单次决策 | 来源 |
| :--- | :--- | :--- | :--- |
| Tesla T4（GPU, fp32） | ~90 tok | 32.8–39.5 ms | 官方 BENCHMARKS（A/B 级） |
| Ryzen 9 6900HX（WSL2, fp32, intra=8/inter=1） | 短 | **329 ms（p50）** | 官方 BENCHMARKS |
| AMD EPYC 9R14 4 核（fp32） | 3 选项 | **580 ms** | 官方 BENCHMARKS |
| i9-14900HX | 71 / 261 / 927 tok | **50 / 307 / 1315 ms** | 社区 `laya-cpu-benchmark`（C 级） |
| 12 代酷睿 + **OpenVINO INT8**（405 MB） | 短 | **40 ms**；flappy demo 28 ms | `rupeshs/laya-ov-int8`（C 级） |
| i3-1215U + ONNX Runtime **INT8** | 短 | **171 ms**（fp32 438 ms） | `samiul000/laya-cpp`（C 级） |

**三条可直接落地的工程结论**
1. **必须 INT8**：`rupeshs/laya-ov-int8` 保留 98.9% 的 top-1 一致率，但 INT4 会漂移 0.69 概率、破坏阈值门控——**INT8 是下限，不要 INT4**。
2. **状态长度是延迟的一阶项**（50 ms@71 tok → 1.3 s@927 tok）。我们的状态必须压到 **≤120 token**，且优先放数值而非长句。
3. **线程配置是免费的 12×**：官方实测 `torch.set_num_threads(物理核数)` + `set_num_interop_threads(1)` 把 9.4 s 降到 783 ms（默认 10 intra/5 inter 在单次前向上纯粹是自残）。

### 2.3 缺少的能力（生态没有替我们解决的问题）

- **没有任何 Laya/Jev 变体支持"数值回归输出"**。`score` 是 5 级有序量表，不是连续量；连续量要靠外部解码器（见 §4）。
- **没有任何 Laya 的中文/工程语料微调示例**，但我们是数值任务，不受影响。
- **JS/TS/Rust 绑定齐全，但没有 MATLAB 绑定**；MATLAB 侧只能走 ONNX Runtime（`py.onnxruntime` 或 `importNetworkFromONNX`）。

---

## 3. 维度二：MATLAB/Simulink 侧的通信与重启瓶颈

### 3.1 本机实测（A 级证据，直接回答提示词里的问题）

模型：你的 `motor_valve_model.slx`（90 个 block，含 Simscape Multibody 蝶阀 + STL，可变步长），复制到 ASCII 路径后只改 `Gain_Kp`，脚本 `research/bench/bench_run.m`（不改原模型）。

| 配置 | StopTime = 1 s | StopTime = 15 s（模型默认） |
| :--- | ---: | ---: |
| 冷启动（编译 + 3D 初始化） | 10.1 s | 9.4 s |
| 普通模式（每次重编译） | **763 ms**（549–1009） | **869 ms**（620–1112） |
| **Fast Restart（复用编译）** | **40 ms**（36–44） | **111 ms**（88–319） |
| Fast Restart + `SimulationInput` | 102 ms | 150 ms |
| 加速比 | **18.9×** | **7.8×** |

**解读**
- 每次普通运行的 ~750 ms 里，**>90% 是重编译**；真正的求解在 1 s 仿真时只有 ~40 ms。→ **Fast Restart 不是优化项，是前提条件**。
- 50 次迭代的总预算：普通模式 **38 s** vs Fast Restart **2 s**。所以"决策 40 ms + 仿真 40 ms ≈ 80 ms/迭代"是可达的；不启用 FR 时决策开销被编译噪声彻底淹没。
- **坑 1**：`Simulink.SimulationInput` + `setBlockParameter` 每次多 ~60 ms（对象构建/校验）。Python 桥接若追求极限，应**直接 `set_param` + `sim(mdl)`**，只在需要并行时才用 `SimulationInput`/`parsim`。
- **坑 2**：带 Simscape Multibody 的模型默认会拉起 Mechanics Explorer 3D 视图——我第一次跑时内存冲到 **11 GB**、单次仿真数分钟不返回（已终止并改用 `SimMechanicsOpenEditorOnUpdate=off`）。**调参循环里必须关掉 3D 与动画**。
- **坑 3**：模型名必须是合法 MATLAB 标识符（`motor_valve_model.slx` 直接报错），桥接层要重命名。

### 3.2 官方数据（B 级，交叉验证）

MathWorks 对自动变速器模型跑 100 次：普通 328 s → Fast Restart 307 s（仅 6%，因为求解本身占大头）；**说明 FR 的收益 = 编译时间占比**，模型越小收益越大。我们的模型正属于"编译重、求解轻"的类型，所以收益 8–19×。

Fast Restart 的官方限制（决定了桥接协议）：
- 只能改**可调参数**、外部输入、初始状态；**不能改结构/采样时间等不可调参数**（否则自动重新编译）。
- 限制条件对 PID 调参完全够用：`Kp/Ki/Kd` 是可调参数。
- 并行时每个 worker 各编译一次（`UseFastRestart="on"`），因此 `parsim` 适合批量验证，不适合逐次闭环。

### 3.3 同类项目对比（决定"我们不要重复造什么"）

| 项目 | ★ | 做法 | 结论 |
| :--- | --: | :--- | :--- |
| **MathWorks `matlab-mcp-server`**（官方） | 1.7k | MCP → 常驻 MATLAB 会话，执行代码/读模型 | **直接复用**，我们不需要自己写 MCP |
| `matlab/agentic-toolkit-installer` | — | 官方一键装 MATLAB/Simulink Agentic Toolkit | 值得装（本机已有同类能力） |
| `sohumsuthar/simulink-mcp`、`wya5217799/simulink-mcp` | 27 / 1 | 社区版 Simulink MCP | 参考，不依赖 |
| `akkified/pid-tuning-llm` | 0 | 空壳仓库 | 无参考价值 |
| Jev 生态的机器人项目（drone 2.5 Hz、MuJoCo skill、ESP32） | 1–237 | 决策模型放**高层**，底层仍是经典控制 | **架构先例：模型不碰快速环** |
| 行业博客"Jev 在 PLC 上 sub-10 ms / 120 FPS" | — | 无代码、无可复现指标 | **D 级，不采信** |

**结论**：公开世界里**"System-1 决策模型 + Simulink 调参"是空白**。我们既不缺通信方案（Fast Restart + 常驻会话已足够），也不能靠"比别人快"当卖点——必须靠**迭代次数（样本效率）**说话。

---

## 4. 维度三：离散原语 → 连续控制参数

### 4.1 两个方案的实测含义

**方案 A：纯 NumericJev（K 叉区间树细化）**
- 论文（arXiv 2609.28587）实测：100 值网格、`K=10` 只需 **2 轮**决策；range-normalized MAE **1.84%**，直接选候选是 5.18%；83.4% 落在 5% 相对误差内（vs 80.5%）。
- 代价：每轮一次完整前向。本地 Laya + INT8 → 2 轮 ≈ **80–180 ms**；托管 Jev（236–276 ms/次）→ 0.5–0.6 s。
- **致命弱点（论文自承）**：早期选错区间**不可恢复**；分辨率与精度是两回事。

**方案 B：倍率 Choice + Noul 回滚**
- 每个增益一个 `choice`：`{×0.80, ×0.90, ×1.00, ×1.10, ×1.25}`；三个增益共享一次前向（Laya 原生支持多问题批处理）。
- 分辨率：单步 10–25%，但**每步安全、可解释、可回滚**；配合"上一次动作-效果"特征，等价于给模型一个**近似梯度**，收敛曲线平滑。
- 代价：1 次前向 ≈ **40–90 ms**。

### 4.2 结论：不是二选一，是"粗-细-停"三级

```
state ──► [L1 粗调] choice×3 (Kp,Ki,Kd 倍率)  ──┐   1 次前向, 40-90ms
        │                                        ├──► [安全闸] noul + 确定性限幅/回滚
        │   [L2 细调] log 空间 K=3 区间细化 (2-3 轮) ─┘   仅当 L1 进入 ±10% 邻域
        └─► [L3 收敛] score("当前响应已达目标") ≥ τ 即早停
```

**为什么这样组合**
- 粗阶段用倍率：动作空间小、语义明确、与 Z-N 等启发式同构，天然安全。
- 细阶段用 NumericJev：只在最后 10% 精度上花 2–3 次前向，避免"早期错区间不可恢复"的缺点。
- 用 `Score` 做早停：这是最容易被忽略的收益——**省掉的迭代次数比单次延迟重要一个量级**（50 次 → 15 次 = 3× 墙钟时间）。
- `Noul` 只做"模型意见"，**最终否决权必须在确定性代码里**（增益上下限、闭环稳定性判据、执行器饱和、发散检测）。理由：Laya 出厂过度自信，末校准概率不可信（官方 ECE 0.466）。

### 4.3 一个必须写进契约的细节

倍率作用在 **log 增益空间**：`Δ = log10(K_new/K_old) ∈ {−0.097, −0.046, 0, +0.041, +0.097}`。好处：Kp/Ki/Kd 量级差 3–4 个数量级时，动作语义统一；且 L2 的区间细化天然是线性尺度。

---

## 5. 维度四：Devil's Advocate（我作为批判者看到的 6 个盲区）

1. **"421M 文本编码器读 8 个数字"的架构债务**
   ModernBERT 从未见过控制特征；数字被 tokenizer 切成 digit token，`1.234` 与 `1.235` 的表示差异远大于它们的物理差异。395M 主干消耗 99% 算力，只为给 26M 头提供输入。
   → **正解**：把 **"Jev 契约"（Choice/Score/Noul + 校准概率 + proper scoring 训练）与 "文本编码器"解耦**。数值状态用 1–3M 的 MLP/小型 Transformer 编码，ONNX 上 **<1 ms**，才是真正的"毫秒级 System-1"。

2. **"毫秒级闭环优化"是营销语言，不是需求**
   调参是 **10–100 次迭代**的离线过程（每次 80 ms 完全够用）；只有"在线增益自适应"才需要 ms 级。把两者混在一个 KPI 里，会导致错误的技术选型（为了 5 ms 去蒸馏一个本来 40 ms 就够的模型）。

3. **"曲线→JSON 有信息损失"这个担心，方向反了**
   超调/上升时间/调节时间/稳态误差/IAE/ITAE/振荡次数/衰减比 是控制工程百年来公认的**充分统计量**（人类调参就靠它们）。真正的信息损失风险在于——**指标集不足以判定"该往哪调"**：
   - "欠阻尼振荡"和"增益过高"在超调上不可区分；
   - 执行器饱和会把"增益不足"伪装成"响应慢"。
   → **必须补**：`u(t)` 饱和占比、稳态斜率、二次振荡幅度、相对 Z-N 参考增益的比值、**上一次动作及其 Δ指标**（这一项把开环映射变成闭环搜索，是整套方案能否收敛的关键）。

4. **合成数据"零成本"只在仿真域成立**
   随机二阶/带延迟/带饱和的传递函数族，scipy 步进一次 ~10 μs → 百万样本几小时。但 **sim-to-Simulink gap** 是真实存在的（你的模型是 Simscape 多体 + 蝶阀非线性）。→ 必须留 20% 的植物来自 Simulink 降阶模型的辨识参数，并做**跨域迁移验收**。

5. **没有 baseline 的"AI 调参"没有说服力**
   对单个已知对象，**Z-N / 继电自整定 / 单纯形 / CMA-ES / 贝叶斯优化**往往 20–40 次评估就收敛，且零训练成本。System-1 模型的正当性只在三处：
   (a) **摊薄成本**——训一次，跨植物族复用；
   (b) **样本效率**——用专家轨迹蒸馏，把 40 次压到 10–15 次；
   (c) **可解释/可门控**——概率可以直接用于早停与熔断。
   → 验收指标必须写成"**达到同等 ITAE 所需仿真次数**"和"**跨植物族零样本迁移成功率**"，而不是"单次推理多少毫秒"。

6. **概率校准是隐藏的地雷**
   Laya 出厂过度自信（ECE 0.466，`noul:2` 温度需要 1.98），而我们整个早停/熔断逻辑都建立在概率上。→ 训练后必须做**温度重拟 + 可靠性图验收**（目标 ECE ≤ 0.05），否则 `score ≥ τ` 的早停会系统性提前。

---

## 6. 架构定稿

### 6.1 双轨设计（同一契约，两种后端）

```
                    ┌───────────────────────────────┐
                    │  Primitives Contract (稳定层)  │
                    │  Choice / Score / Noul         │
                    │  + calibrated probabilities    │
                    └──────────────┬────────────────┘
                                   │
        ┌──────────────────────────┴───────────────────────────┐
        │                                                      │
┌───────▼─────────────┐                            ┌───────────▼──────────────┐
│ Track A: NumericHead │  状态: float[24]           │ Track B: LayaBackend     │
│ 1–3M MLP/小Transformer│  延迟: <1 ms (ONNX)        │ 状态: JSON→文本           │
│ 合成数据训练          │  用途: 主路径/批量实验      │ INT8: 40–90 ms            │
│ 可解释、可蒸馏        │                            │ 用途: 零样本基线/教师/    │
└──────────────────────┘                            │      自然语言诊断         │
                                                     └──────────────────────────┘
```

**为什么保留 Track B**：它是**今天就能跑通**的零样本基线；也是 Track A 的教师（用 Laya 的 JSON 状态判定为合成数据做伪标签/基准学习）；还能吃"文本型状态"（如"电机有异响、电流纹波增大"这类只能文本描述的现象）。

### 6.2 一次迭代的数据流

```
Simulink/Python 植物
   │ step response (t, y, u)
   ▼
FeatureExtractor ──► StateVector(24)  ──► NumericHead ──► {choice×3, score, noul}
   │  (超调/上升/调节/ess/IAE/ITAE/振荡/饱和/上次Δ)          │
   │                                                       ▼
   │                                            SafetyGate (确定性)
   │                                            · 增益上下限/量级比
   │                                            · 闭环极点实部 < 0（辨识模型）
   │                                            · 饱和/发散 → 回滚
   ▼                                                       ▼
接受新增益 ◄────────────────────────────────  Δlog-gain 动作
```

### 6.3 接口契约（第一步就冻结，避免后面推倒）

```python
# src/jev_tune/primitives/contract.py
class Choice:  options: list[str]; probs: np.ndarray
class Score:   levels:  list[str]; dist:  np.ndarray
class Noul:    p_true:  float                     # 校准后的 P(statement)

class DecisionBackend(Protocol):
    def decide(self, state: State, questions: list[Question]) -> dict[str, Answer]: ...
    # 契约要求：所有 question 在一次前向内完成；未知/越界返回 None 而非抛异常
```

---

## 7. 合成数据集方案（零成本、可控、可验证）

**植物动物园（Python，scipy，单次仿真 ~10 μs）**

| 族 | 参数随机化 | 对应现实 |
| :--- | :--- | :--- |
| 一阶+纯延迟 | `T ∈ [0.02, 2] s, L ∈ [0, 0.5T]` | 温度、流量 |
| 二阶欠/过阻尼 | `ωn ∈ [1, 100] rad/s, ζ ∈ [0.05, 2]` | 电机速度环 |
| 三阶 + RHP 零点 | 额外极点/零点 | 电流环、机械谐振 |
| 积分型 | `1/(s(Ts+1))` | 位置环 |
| 带饱和/死区/量化/噪声 | 限幅 ±u_max、编码器量化 | 真实执行器 |
| PMSM 电流环 | `dq` 解耦 + 反电势 | 你的实验对象 |

**标注生成（关键：标注"下一步动作"，不是"最终增益"）**
1. 每个植物随机 2000 组 `(Kp,Ki,Kd)`（Z-N 球内对数均匀），仿真 → 指标 + 代价 `J = w₁·OS + w₂·Ts + w₃·|ess| + w₄·ITAE`。
2. 用 CMA-ES 从随机初值搜到最优，记录**搜索轨迹**。
3. 轨迹上每个状态 `s_t` 的标签 = `argmax_Δ (J(s_t) − J(s_t+Δ))`，即"哪一步让代价下降最快"。
4. 得到 `(state, action)` 对 ≈ 植物数 × 轨迹长度；1 万个植物 × 20 步 = 20 万样本，CPU 数小时。
5. 20% 植物用 Simulink 降阶模型辨识出的参数（覆盖 sim-to-real gap）。

**训练目标**：`rlcd_loss`（严格适当评分规则，让概率可用）+ 交叉熵；用 AnyJev 的**闭式线性头**做 warm start（100–300 样本、CPU 秒级，可快速试错），再用小 Transformer 头提升。

---

## 8. MVP 仓库结构与工程约定

```
jev-tune/
├─ docs/
│  ├─ PHASE0_RESEARCH_REPORT.md      ← 本文件
│  ├─ ARCHITECTURE.md
│  └─ adr/                           决策记录（为什么双轨/为什么倍率+区间树）
├─ configs/                          yaml：植物族、指标权重、动作表、阈值
├─ src/jev_tune/
│  ├─ primitives/                    contract.py, calibrate.py（温度/可靠性图）
│  ├─ state/                         features.py, encode.py（数值 & 文本两条）
│  ├─ decode/                        multipliers.py, interval_tree.py, safety.py
│  ├─ plants/                        zoo.py, pmsm.py, reduced_order.py
│  ├─ sim/                           metrics.py, runner.py
│  ├─ baselines/                     zn.py, relay.py, simplex.py, cmaes.py, bo.py
│  ├─ models/                        numeric_head.py, laya_backend.py, export_onnx.py
│  ├─ bridge/                        matlab_engine.py, fast_restart.py
│  └─ cli.py
├─ matlab/                           jev_setup.m, jev_run_once.m, jev_bench.m
├─ scripts/                          gen_dataset.py, train.py, eval_vs_baselines.py
├─ tests/                            test_primitives.py, test_metrics.py, test_safety.py
├─ research/bench/                   本机 benchmark 脚本与实测日志（证据留存）
├─ data/  models/                    ← 均在 .gitignore 内
```

**`.gitignore` 追加（MATLAB/Simulink 缓存，现有 Python 规则保留）**

```gitignore
# ---- MATLAB / Simulink ----
slprj/
*.slxc
*.slx.r20*
*.mdl.r*
*.slx.autosave
*.autosave
*.asv
*.mex*
*.sdi
sdi/
*.dmr
*.slmx.r*
*.slreqx.r*
*.sldd.r*
codegen/
work/
*.mlappinstall
*.mltbx

# ---- 本项目产物 ----
data/
models/
research/bench/_tmp/
*.log
```

**环境（Anaconda，专用环境，不动 base）**

```powershell
conda create -n jev-tune python=3.12 -y     # 3.12：matlabengine 24.2 支持上限
conda activate jev-tune
pip install numpy scipy pandas matplotlib pydantic typer pyyaml pytest
pip install onnx onnxruntime onnxscript optimum[onnxruntime]   # Track A + INT8
pip install "C:\Program Files\MATLAB\R2024b\extern\engines\python"  # matlab.engine
# Track B（可选）：pip install laya[onnx]  /  laya-openvino（非 PyPI，需 git 安装）
```

> `matlab.engine` 必须用**与本机 MATLAB 同版本**的包（R2024b → 24.2.x），且 Python ≤3.12；这就是选 3.12 而不是 3.13 的原因。

---

## 9. 路线图（每步都有可验收的数字）

| 阶段 | 内容 | 验收标准 |
| :--- | :--- | :--- |
| **Step 1** 纯 Python 闭环（1–2 天） | 植物动物园 + 指标 + 5 个 baseline + Fast Restart 之外的"零开销仿真" | 百万样本生成 <2 h；baseline 收敛曲线可复现（固定种子） |
| **Step 2** 决策引擎（3–5 天） | Primitives 契约 + 倍率/区间树解码 + 安全闸 + NumericHead 训练 | 在**未见过的植物族**上，达到同等 ITAE 所需仿真次数 ≤ baseline 的 50%；单次决策 <1 ms |
| **Step 3** Laya 接入（2–3 天） | JSON 状态 → Laya INT8 → 同一契约；零样本 vs 微调对比 | CPU 单次 ≤90 ms（≤120 token）；微调后 ECE ≤0.05；与 Track A 的胜率对比成表 |
| **Step 4** Simulink 桥（2–3 天） | 常驻 MATLAB 会话 + Fast Restart + 你的 motor-valve benchmark 电机模型验收 | 单迭代 ≤120 ms（决策 40 + 仿真 40 + 通信 ≤40）；整定结果与 MATLAB PID Tuner 对比 |
| **Step 5**（可选）部署 | ONNX → MATLAB `importNetworkFromONNX` / Simulink Predict 块 | 零 Python 依赖跑通一次闭环 |

**必须一起交付的对照实验**（否则项目没有说服力）：
`Z-N` · `继电自整定` · `单纯形` · `CMA-ES` · `贝叶斯优化` · `Laya 零样本` · `NumericHead`，统一指标：**ITAE、超调、调节时间、达到目标所需仿真次数、墙钟时间、失败率**。

---

## 10. 需要你拍板的 5 个点

1. **KPI 口径**：接受"单次决策 ≤90 ms（INT8）"而不是"数十毫秒"？（fp32 PyTorch 做不到，这是硬约束）
2. **双轨是否都做**：Track A（数值原生，ms 级）+ Track B（Laya，生态对齐）——还是只做 Track B 以保持"纯 Jev 血统"？
3. **验收对象**：Step 1–2 用合成植物，Step 4 用你的 motor-valve benchmark 电机模型——是否还需要 PMSM 电流环/位置环作为第二验收对象？
4. **baseline 范围**：5 个经典方法是否都要跑？（工作量约 +1 天，但没有它就发不了论文/写不了报告）
5. **形态**：先做 **CLI + Python 库**（可复现、可测），还是直接做 **MATLAB App/GUI**？（建议前者，GUI 最后加）

---

## 附录 A：证据索引

| 编号 | 内容 | 链接 |
| :--- | :--- | :--- |
| E1 | Laya 仓库（Apache-2.0，33.8k★） | github.com/NandhaKishorM/laya |
| E2 | Laya 官方延迟/精度表（含 CPU 多平台） | 同上 `BENCHMARKS.md` |
| E3 | Laya 权重与 `rl_agent_config.json` | huggingface.co/convaiinnovations/laya |
| E4 | 训练 API（`laya.train.finetune`, `rlcd_loss`） | 同上 `docs/reference/train.md` |
| E5 | OpenVINO INT8（405 MB，40 ms） | huggingface.co/rupeshs/laya-ov-int8 · laya.tools/laya-openvino |
| E6 | 社区 CPU 基准汇总 | laya.tools/laya-benchmarks |
| E7 | NumericJev / JevNext（K 叉区间树，MAE 1.84%） | arxiv.org/abs/2609.28587 · github.com/Bring-AI/jev-numeric |
| E8 | AnyJev（旋转去偏 + 闭式头 L2） | github.com/nokia-applied-research/AnyJev · arxiv.org/html/2610.00831 |
| E9 | Kev-0.8B（冻结主干 + LoRA + pointer head） | huggingface.co/jaredpalmer/kev-0.8b |
| E10 | NanoJev（MIT，训练管线） | github.com/TianyuCodings/NanoJev |
| E11 | MathWorks Fast Restart 官方说明与限制 | mathworks.com/help/simulink/ug/how-fast-restart-improves-iterative-simulations.html |
| E12 | MathWorks 100 次迭代对比（328 s → 307 s） | mathworks.com/company/technical-articles/improving-simulation-performance-in-simulink.html |
| E13 | 官方 MATLAB MCP Server | github.com/matlab/matlab-mcp-server |
| E14 | 决策模型在机器人上只做高层（drone 2.5 Hz） | systemonemodels.org/examples/for/robotics-and-devices/ |
| E15 | **本机实测**：Simulink 逐次运行开销 | `research/bench/bench_run.m` + `bench_log_1s.txt` / `bench_log_15s.txt` |

## 附录 B：本机 benchmark 复现
```powershell
# 1) 复制模型到 ASCII 路径（Simulink 要求文件名为合法标识符）
Copy-Item "...\model_workspace\motor_valve_model.slx" "research\bench\_tmp\jevbench_model.slx"
# 2) 后台跑，避免阻塞交互式 MATLAB 会话
& "C:\Program Files\MATLAB\R2024b\bin\matlab.exe" -batch `
  "addpath('C:\workspace\jev-tune\research\bench'); bench_run(15,5,'bench_log_15s.txt')"
```

> 原始日志：`research/bench/bench_log_1s.txt`、`bench_log_15s.txt`（每次运行的逐次耗时都在里面）。

---

## 附录 C：Step 1–2 实测增补（2026-10-22）

本报告写于 Phase 0 结束时。后续实现与实测出现了三个需要更新的数字，详见 `docs/STEP1_RESULTS.md`。

| 项目 | Phase 0 的判断 | Step 1–2 实测 |
| :--- | :--- | :--- |
| 决策延迟 | 数值原生头 `<1 ms`（推断） | **0.186 ms（p50）/ 0.237 ms（p99）**，ONNX Runtime 单线程，与 PyTorch 差 2.3e-5 |
| 概率校准 | "必须重拟温度，目标 ECE ≤0.05"（预判 Laya 式过度自信） | 本项目的头出厂 ECE 仅 **0.025–0.033**，温度拟合后 **0.017–0.021**（T≈0.93） |
| 经典基线强度 | 估计 Z-N 是主要对手 | **MATLAB `pidtune`（模型已知、0 次仿真）median J=0.81** 远强于 Z-N（2.9），因此"模型未知/模型失配"才是学习型调参的正当场景，评估必须同时给出 `identify+pidtune`（2 次仿真） |

另：`Von` 的缺失与 `Laya` 的 CPU 延迟结论不变；本机 `matlab.engine` 无法构建（MathWorks 的 setup.py 校验失败），已改为 `matlab -batch` + MAT 文件交换，效果等价且更稳。
