# What this repository borrows from Jev — and what it does not

> [English](#english) · [简体中文](#简体中文)

## English

This page exists because the repository is named `jev-tune` and uses Jev's
interface. It is **not** a Jev client, it contains **no Jev weights**, and it is
not affiliated with TypeSafe AI. Everything below separates what is publicly
documented about Jev from what is implemented here.

Public sources used (accessed 2026-10-23):

* Jev architecture — <https://www.jevtypesafeai.com/jev/architecture>
* Jev primitives, as documented by the TypeSafe SDK — <https://learnjev.com/tutorials/three-primitives>

### Concept-by-concept

| Concept | Jev (public description) | This repository | Status | Difference |
| :--- | :--- | :--- | :--- | :--- |
| Non-autoregressive decision | Typed, calibrated output instead of generated text; hosted API | One forward pass of a 200 KB convolutional encoder (`src/jev_tune/model.py`) | implemented | Numeric state (20 features + 2×64 trace samples), not text |
| `choice` | One of up to 255 options, with per-option probabilities and a confidence | 7 multiplicative gain steps per axis, 3 axes (`src/jev_tune/decode.py`, `decision.py`) | implemented | 7 options, no free-text criteria; the "confidence" is `max(p)` and is logged, not thresholded |
| `score` | Ordered level scale, fractional score + distribution + confidence | 5 cost bands of the current response (`decision.SCORE_LEVELS`) | implemented | The levels are fixed cost bands, not user-supplied rubric text |
| `noul` | Calibrated yes/no, probability in [0,1], optional true/false criteria | P(the proposed step keeps the loop healthy) | implemented | Trained on a synthetic label, not on human criteria |
| Probabilities, not just an answer | Every answer carries a distribution | Softmax over the choice logits; expectation + variance decode | implemented | — |
| Calibration | "Calibration, not fluent writing, is the target"; confidence is concentration, not a correctness guarantee | One temperature per axis fitted by NLL (`models/calibration.json`), **applied inside the loop** (`decision.NumericBackend`), ECE reported in `docs/STEP1_RESULTS.md` | implemented | ECE there measures agreement with the **expert's** step, not whether the step lowered the cost; the outcome ECE (0.28) is in `docs/ABSTENTION.md` |
| Threshold execution / escalation | Typed answers can be acted on directly or escalated | Three-zone `AbstainPolicy` in `decode.py`, inside `evaluate_head` and the MATLAB bridge: execute / hold / hold-and-flag-escalation | implemented | The escalation is a **flag**, not an action; there is no upstream service to escalate to. The deterministic gate remains separate and runs after the fact |
| Many questions in one forward pass | "Questions in a call run in parallel in one round trip"; roughly 40–200× faster than a frontier LLM | 5 questions (3 choices + score + noul) answered by one forward pass | partial | The **scaling** claim ("more questions, nearly the same latency") is not measured here (planned as J3) |
| Questions as input | A map of question id → typed question over a shared state | A fixed registry of question ids (`decision.tuner_questions`); an unknown id raises `UnknownQuestion` | partial | No natural-language question, no user-defined rubric, no per-call state schema |
| System-1 / System-2 split | Jev is described as a System One model | The head is the fast path; a one-step lookahead value net exists but is **off by default** because it measured worse | partial | There is no LLM/System-2 fallback in the loop |
| Training objective | Publicly described as an RLCD training objective (the internals are not published) | Supervised imitation of a coordinate-line-search expert on simulated plants, plus BCE for `noul` and CE for `score` (`src/jev_tune/train.py`) | implemented, different | Nothing about Jev's training recipe is reused |

### What is explicitly not borrowed

* No Jev weights, tokenizer, text encoder, API access, prompts or training data.
* No claim of compatibility: "Jev-inspired" here means the three typed
  primitives and the idea of a bounded, probabilistic answer. It does not mean
  the outputs match Jev's, or that this code can call Jev.
* Laya's 421 M text encoder is likewise absent. It appears only as a citation in
  `docs/STEP1_RESULTS.md` and `docs/PHASE0_RESEARCH_REPORT.md`.

### What would make this a Jev *implementation* rather than an inspiration

A typed decision layer that takes arbitrary, user-defined questions as input
(text or a schema), a text or multimodal state encoder, and calibration measured
against outcomes rather than against a teacher's labels. The gap is listed here
so a reader does not have to infer it.

---

## 简体中文

本页存在的原因：仓库叫 `jev-tune`，用的是 Jev 的**接口风格**。它不是 Jev 客户端，
**不含任何 Jev 权重**，与 TypeSafe AI 无隶属关系。下面逐项区分"Jev 公开文档怎么
说"与"本仓库实际实现了什么"。

公开来源（2026-10-23 访问）：

* Jev 架构说明 — <https://www.jevtypesafeai.com/jev/architecture>
* Jev 三种原语（TypeSafe SDK 文档）— <https://learnjev.com/tutorials/three-primitives>

### 逐项对照

| 概念 | Jev（公开描述） | 本仓库 | 状态 | 差异 |
| :--- | :--- | :--- | :--- | :--- |
| 非自回归决策 | 返回类型化、校准过的结果，而不是生成文本；托管 API | 200 KB 卷积编码器一次前向（`src/jev_tune/model.py`） | 已实现 | 输入是数值状态（20 特征 + 2×64 曲线采样），不是文本 |
| `choice` | 最多 255 个选项中选一个，带每项概率与 confidence | 每个增益轴 7 个乘法档位，共 3 轴（`decode.py`、`decision.py`） | 已实现 | 只有 7 档；confidence 取 `max(p)`，只记录、不做阈值 |
| `score` | 有序档位，返回分数、分布与 confidence | 当前响应的 5 个代价档（`decision.SCORE_LEVELS`） | 已实现 | 档位是固定代价区间，不是用户给的评分标准 |
| `noul` | 校准的是/否，返回 [0,1] 概率，可带 true/false 判据 | "这一步能否保持闭环健康"的概率 | 已实现 | 标签由合成规则生成，不是人写的判据 |
| 给概率而不只给答案 | 每个答案都带分布 | 对 choice logits 做 softmax；期望 + 方差解码 | 已实现 | — |
| 校准 | "目标是校准，而不是流畅"；confidence 是答案集中度，不是正确性保证 | 每轴一个温度（NLL 拟合，`models/calibration.json`），**在回路内真正应用**（`decision.NumericBackend`），ECE 见 `docs/STEP1_RESULTS.md` | 已实现 | 那里的 ECE 衡量的是与**专家动作**的一致率，不是"这一步是否降低代价"；结果侧 ECE（0.28）在 `docs/ABSTENTION.md` |
| 阈值执行 / 升级 | 类型化答案可直接执行或升级 | `decode.py` 的三段式 `AbstainPolicy`，接在 `evaluate_head` 与 MATLAB 桥里：执行 / 保持 / 保持并打升级标记 | 已实现 | 升级只是**标记**，不是动作；这里没有可升级到的上游服务。确定性闸门仍独立、事后运行 |
| 多问题共享一次前向 | "一次往返里并行求值"；比前沿 LLM 快约 40–200 倍 | 一次前向回答 5 个问题（3 个 choice + score + noul） | 部分 | "问题变多、延迟几乎不变"这条**没有测**（计划中的 J3） |
| 问题作为输入 | 问题 id → 类型化问题，共享同一状态 | 固定问题注册表（`decision.tuner_questions`），未知 id 抛 `UnknownQuestion` | 部分 | 没有自然语言问题、没有用户自定义评分标准 |
| System-1 / System-2 分工 | Jev 被描述为 System One 模型 | 决策头是快路径；一步前瞻价值网存在但**默认关闭**（实测更差） | 部分 | 回路里没有 LLM / System-2 兜底 |
| 训练方式 | 公开说法是 RLCD 训练目标（内部细节未公开） | 在仿真对象上模仿坐标线搜索专家，另加 `noul` 的 BCE 与 `score` 的 CE（`train.py`） | 已实现，但不同 | 没有复用 Jev 的任何训练配方 |

### 明确没有借的东西

* 没有 Jev 权重、分词器、文本编码器、API 访问、提示词或训练数据。
* 不声明"兼容"：这里的 "Jev-inspired" 只指三种类型化原语和"有界、带概率的
  答案"这个思路；不代表输出与 Jev 一致，也不代表这份代码能调用 Jev。
* Laya 的 421 M 文本编码器同样不在运行时；它只作为引用出现在
  `docs/STEP1_RESULTS.md` 与 `docs/PHASE0_RESEARCH_REPORT.md`。

### 什么情况下才算"实现了 Jev"而不是"受其启发"

需要：能接受任意用户定义问题（文本或 schema）的类型化决策层、文本或多模态状态
编码器、以及按**真实结果**而不是按教师标签衡量的校准。把这些差距写在这里，
是为了让读者不必自己推断。
