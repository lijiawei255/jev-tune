# Security policy

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
