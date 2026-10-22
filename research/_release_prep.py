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


# ---------------------------------------------------------------- doctor copy
patch(
    "README.md",
    [
        (
            """No block renames, no scope called `Scope_Position`, no reference typed by hand.
When the model is ambiguous the command says `confidence: medium` instead of
guessing, and the agent asks you one question.""",
            """No block renames, no scope called `Scope_Position`, no reference typed by hand.
When the model is ambiguous the command says `confidence: medium` instead of
guessing, and the agent asks you one question.

If something refuses or fails, `jev-tune doctor --model <file>` explains why in
nine lines — does it load, does it compile, does it use referenced or protected
models, what solver, can a loop be found at all:

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
```""",
        ),
    ],
)

patch(
    "README.zh-CN.md",
    [
        (
            """如果模型有歧义，命令会如实返回 `confidence: medium` 而不是瞎猜，Agent 只问你一个问题。""",
            """如果模型有歧义，命令会如实返回 `confidence: medium` 而不是瞎猜，Agent 只问你一个问题。

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
```""",
        ),
    ],
)

# ---------------------------------------------------------------- version
patch("pyproject.toml", [('version = "0.2.0"', 'version = "0.3.0"')])
patch(
    "src/jev_tune/mcp_server.py",
    [
        (
            '"serverInfo": {"name": "jev-tune", "version": "0.2.0"}',
            '"serverInfo": {"name": "jev-tune", "version": "0.3.0"}',
        ),
    ],
)

# ---------------------------------------------------------------- changelog
patch(
    "CHANGELOG.md",
    [
        ("## [Unreleased]", "## [0.3.0] - 2026-10-22"),
    ],
)

# the Ku fix and the privacy pass belong in the record
p = ROOT / "CHANGELOG.md"
s = p.read_text(encoding="utf-8")
old = """### Fixed
"""
new = """### Fixed

* The Ku sweep reported the **top of its grid** as the ultimate gain: the grid was
  fixed at 0.5-400, it took the last oscillating point instead of the first, and
  it counted mean crossings so a damped response qualified. It now auto-ranges,
  takes the first gain whose peaks stop decaying, and says when the value is a
  bound. Consequence documented in `docs/STEP4_RESULTS.md#correction-the-ku-sweep-was-wrong`:
  on the motor-valve benchmark model the old start was an artifact, and from the corrected start
  the head makes no further improvement.
* A model whose step block is not called `Step` now still gets its reference: the
  search is by block type. If that fails, one probe run supplies the steady state
  instead of silently assuming a reference of 1.
* A Scope that logs several signals is refused (`wide_signal`) instead of handing
  the tuner column 1 — which, on a two-input scope, is the reference.
* Scope names are passed through `matlab.lang.makeValidName`, so a block called
  `Scope Position` logs instead of silently producing nothing.
* Missing gain blocks are reported as `no_gains` with the names it looked for,
  instead of a Simulink "Invalid object name".
* The instrumentation never deletes a block that is not its own.
* `status` and the pidtune baseline use the same MATLAB lookup as everything else
  instead of a hard-coded `C:\\Program Files\\MATLAB\\R2024b`.
* Repository hygiene: the local username path and benchmark/reference environment names are
  gone from the tree (see the note in NOTICE.md).
"""
assert old in s
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("CHANGELOG: 0.3.0 with the Ku and privacy entries")
