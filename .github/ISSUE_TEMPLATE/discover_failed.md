---
name: Discovery failed on a real model
about: A model where jev-tune discover got it wrong, got stuck, or refused
title: "[discover] "
labels: discovery
assignees: ""
---

Discovery is the part that has to work on models it has never seen, and the only
way to find what it misses is to collect the cases. **A model that makes it fail
is more useful to this project than one it handles** — please open this even if
you do not have time to reduce it.

## What happened

- [ ] refused: `cascade_suspect` / `cascade_unsupported` / `ambiguous_junction` / `no_loop`
- [ ] picked the wrong blocks (say which, if you can see it)
- [ ] crashed
- [ ] ran, but the tuned gains were wrong

## The JSON output

```json
// jev-tune discover --model YourModel.slx --json
```

It lists every candidate junction, the confidence, and the reason. That alone
usually explains the failure.

## Please do not attach a company model

You do not have to. This is enough to reproduce most failures:

1. the block list, with names changed if they are sensitive:
   ```matlab
   b = find_system('YourModel', 'SearchDepth', 1, 'LookUnderMasks', 'none');
   for k = 1:numel(b)
       fprintf('%s   %s\n', b{k}, get_param(b{k}, 'BlockType'));
   end
   ```
2. one sentence on the topology: one loop, cascade, MIMO, Stateflow, referenced
   models, protected blocks.

## Topology

<!-- one loop? cascade (which loop is inside which)? what is measured? where does the reference come from? -->

## Environment

| | |
| :--- | :--- |
| MATLAB | `jev-tune matlab --probe --json` |
| Model source | Simulink / Simscape / referenced models / protected (.slxp) |
| Simulates on its own | yes / needs workspace variables / no |
| Solver | variable step / fixed step |
