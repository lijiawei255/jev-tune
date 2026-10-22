from pathlib import Path

ROOT = Path(r"C:\workspace\jev-tune")


def patch(rel, pairs):
    p = ROOT / rel
    s = p.read_text(encoding="utf-8")
    for old, new in pairs:
        assert old in s, f"{rel}: {old[:70]}"
        s = s.replace(old, new, 1)
    p.write_text(s, encoding="utf-8")
    print("patched", rel)


# ------------------------------------------------ README: the headline number
patch(
    "README.md",
    [
        (
            "| **How few experiments** | **5 experiments** (0.55 s of simulation) cut a real Simulink motor loop's cost by **52 %** |",
            "| **How few experiments** | **11 experiments** on a real Simulink motor took the cost from **1.377 to 0.615**, and the loop never ends worse than it started |",
        ),
        (
            """*Same plant, three gain sets. Grey: the Ziegler-Nichols start. Blue: after five
experiments. Dashed: the lab's hand-tuned solution.*""",
            """*Same plant, three gain sets. Grey: the Ziegler-Nichols start. Blue: after five
experiments. Dashed: the lab's hand-tuned solution. That run started from a
Ziegler-Nichols estimate produced by the Ku sweep as it was in v0.2; the sweep
was wrong in three ways and has since been fixed — see the correction in
[`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md#correction-the-ku-sweep-was-wrong).*""",
        ),
    ],
)

patch(
    "README.zh-CN.md",
    [
        (
            "| **多省实验** | **5 次实验**（0.55 s 仿真）把真实 Simulink 电机环的代价降了 **52%** |",
            "| **多省实验** | 真实 Simulink 电机上 **11 次实验**把代价从 **1.377 降到 0.615**，且结果永远不比起点差 |",
        ),
    ],
)

# ------------------------------------------------ STEP4: the correction
CORR_EN = """
### Correction: the Ku sweep was wrong

*Added in v0.3.0.* The Ziegler-Nichols start above was produced by a sweep with
three defects, all of which pushed the estimate towards the top of the grid:

1. the grid was fixed at `logspace(0.5, 400, 7)`, so any plant needing more than
   400 looked like "no oscillation" and fell back to a guess;
2. the code took the **last** oscillating grid point instead of the first, which
   is the top of the grid whenever anything oscillates;
3. "oscillation" was counted as mean crossings, and a damped second-order
   response crosses its mean three or four times, so it qualified.

Each one alone would be a bug; together they made Ku equal to the ceiling. On
this plant that produced `Ku ≈ 400` — the top of the grid, not a measurement —
and a start of `[240, 1160, 12.4]`.

With the sweep fixed (auto-ranging, first crossing, decay ratio ≥ 0.9):

| | start | final | experiments |
| :--- | ---: | ---: | ---: |
| v0.2 sweep (the table above) | 1.238 | 0.598 | 5 / 9 |
| v0.3 sweep | 0.674 | 0.674 | 6 (no improvement) |
| the lab's own gains (280/300/30) | 0.392 | — | — |

The head does not improve the corrected start: it proposes smaller gains, they
are worse, the stall detector stops it, and the safety gate returns the start.
That is the guarantee working, not a tuning success. **The honest reading is that
this plant is already well served by its lab gains and the -52 % above measured
recovery from an over-aggressive start produced by a broken sweep.**

The Kp sweep also shows why "ultimate gain" is a weak idea here: with I and D at
zero, the loop's decay ratio stays between 0.90 and 1.06 for every gain from 40
to 600 — it is marginally stable over a wide band, not oscillating from one
particular gain. Ziegler-Nichols assumes a clear boundary; this plant does not
have one.

The v0.2 numbers are left in place rather than rewritten: they are what that
release measured, and the GIF in `assets/tuning.gif` is that run.
"""

CORR_ZH = """
### 更正：Ku 扫描当时是错的

*于 v0.3.0 补充。* 上面那次 Ziegler-Nichols 起点来自一个有**三处缺陷**的扫描，三处都把
估计值推向网格顶端：

1. 网格写死为 `logspace(0.5, 400, 7)`，任何需要大于 400 的对象都会被判成"不振荡"，
   然后退化成猜；
2. 取的是**最后一个**振荡网格点而不是第一个——只要有振荡，这个点永远是网格顶端；
3. "振荡"用穿均值的次数来判，而二阶阻尼响应本来就会穿均值三四次，于是也算数。

任何一条单独都是 bug；三条合起来让 Ku 等于网格上限。在这台电机上得到的是 `Ku ≈ 400`
——网格顶端，不是测量值——起点因此是 `[240, 1160, 12.4]`。

扫描修好之后（自动扩展量程、取第一个穿越点、要求峰值衰减比 ≥ 0.9）：

| | 起点 | 终点 | 实验次数 |
| :--- | ---: | ---: | ---: |
| v0.2 的扫描（上表） | 1.238 | 0.598 | 5 / 9 |
| v0.3 的扫描 | 0.674 | 0.674 | 6（未改善） |
| 实验课自带的增益（280/300/30） | 0.392 | — | — |

决策头没有改善修正后的起点：它提出更小的增益，结果更差，停滞检测把它停下，安全闸把
起点原样返回。**这是"不比起点差"这条保证在起作用，不是整定成功。** 诚实的结论是：
这台电机本来就有不错的实验课增益，上面那个 −52% 测的是"从一个被坏扫描推得过激的起点
恢复回来"。

Kp 扫描还说明了为什么"极限增益"这个概念在这里不好用：把 I、D 置零后，从 40 到 600
的每个增益上，衰减比都在 0.90–1.06 之间——它在一大段范围里都是临界稳定，并不是在某个
特定增益上开始振荡。Ziegler-Nichols 假设存在清晰的边界，这台对象没有。

v0.2 的数字原样保留而不是改写：那是那个版本测出来的东西，`assets/tuning.gif` 就是那次运行。
"""

p = ROOT / "docs" / "STEP4_RESULTS.md"
s = p.read_text(encoding="utf-8")
anchor = "The GIF in `assets/tuning.gif` is this run: every frame is one experiment, with\nthe gains the head chose and the response it produced."
assert anchor in s
s = s.replace(anchor, anchor + "\n" + CORR_EN, 1)

anchor_zh = "`assets/tuning.gif` 就是这次运行：每一帧是一次实验，画的是决策头选出的增益和它产生的响应。"
if anchor_zh in s:
    s = s.replace(anchor_zh, anchor_zh + "\n" + CORR_ZH, 1)
    print("zh correction inserted")
else:
    print("ZH anchor missing - check STEP4 zh section")
p.write_text(s, encoding="utf-8")
print("STEP4: correction added")
