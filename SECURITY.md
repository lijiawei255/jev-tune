# Security policy

> [English](#security-policy) · [简体中文](#安全策略中文)


## Scope

This project runs locally. It does **not** open a network port, does not call a
remote service, and does not collect telemetry. The MCP server speaks JSON-RPC
over stdin/stdout to the client that launched it — it has no listening socket.

The one genuinely privileged operation is that the MATLAB bridge **executes
Simulink models you point it at**, and `jev-tune matlab --model` runs inside
your MATLAB installation with your licence. Treat a `.slx` file like any other
executable content: models can contain callbacks (`PreLoadFcn`, `StartFcn`) that
run arbitrary MATLAB code when loaded.

## Supported versions

| Version | Supported |
| :--- | :--- |
| `main` | yes |
| tagged releases | best effort |
| older forks | no |

## Reporting a vulnerability

Please do **not** open a public issue for anything that could be exploited.
Instead use GitHub's private vulnerability reporting on this repository
(**Security → Report a vulnerability**), or contact the maintainer through the
address on their GitHub profile.

Include: affected file or command, MATLAB/Python version, a minimal reproduction,
and what an attacker would gain.

You can expect an acknowledgement within a few days. There is no bug bounty.

## Hardening notes for users

* The tuner copies the model into a scratch directory before loading it; the
  original file is never modified. Keep that behaviour if you fork it.
* `matlab -batch` runs whatever code string the CLI builds. Do not pass
  untrusted text as `--model`; it is interpolated into a MATLAB command.
* Trained weights are loaded with `torch.load` / `map_location="cpu"`. Only use
  `.pt` files from this repository or ones you produced yourself.
* The decision head never receives network input, so prompt-injection style
  attacks do not apply to it.

---

## 安全策略（中文）

### 适用范围

本项目完全在本地运行：**不开放端口、不请求远程服务、不收集遥测**。MCP 服务器
通过 stdin/stdout 与启动它的客户端通信，没有监听套接字。

唯一有"特权"的操作是 MATLAB 桥接**执行你指定的 Simulink 模型**，并在你的 MATLAB
许可下运行。请像对待可执行内容一样对待 `.slx`：模型可以带回调（`PreLoadFcn`、
`StartFcn`），加载时会执行任意 MATLAB 代码。

### 支持版本

`main` 分支持续支持；打标签的版本尽力而为；老的分支不支持。

### 报告漏洞

**不要**为可被利用的问题开公开 issue。请使用本仓库的 GitHub 私密漏洞报告
（**Security → Report a vulnerability**），或通过维护者 GitHub 主页上的邮箱联系。

请附：受影响的文件或命令、MATLAB/Python 版本、最小复现、攻击者能获得什么。
会在几天内回复；本项目没有漏洞赏金。

### 给使用者的加固建议

* 调参器会把模型复制到临时目录再加载，**原文件不会被修改**；fork 时请保留此行为。
* `matlab -batch` 会执行 CLI 拼接出的代码字符串。不要把不可信文本当作 `--model`
  传入，它会被插入 MATLAB 命令。
* 权重用 `torch.load(..., map_location="cpu")` 加载。只使用本仓库的 `.pt` 或你
  自己产出的文件。
* 决策头不接收网络输入，因此不适用提示注入类攻击。
