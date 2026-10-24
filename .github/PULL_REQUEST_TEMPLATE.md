## What this changes

<!-- One paragraph. Link the issue if there is one. -->

## Numbers

<!-- Required for anything that touches the tuner or the simulator. -->

| | before | after |
| :--- | ---: | ---: |
| `jev-tune demo --plants 12` median cost | | |
| `scripts/11_robustness.py` median ratio | | |
| decision latency (if touched) | | |

Command used:

```bash
```

## Checklist

- [ ] `python -m jev_tune.cli check` passes
- [ ] No new path that bypasses the `choice` / `score` / `noul` contract
- [ ] The safety gate still holds the veto (rollback stays in deterministic code)
- [ ] Docs updated if behaviour or flags changed
- [ ] If a model is involved: it is not a third party's proprietary model
