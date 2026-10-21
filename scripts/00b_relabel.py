"""Relabel a rollout chunk with the "best improving candidate, else hold" rule.

The CMA-ES expert anneals its step size, so the plain argmin label collapses to
"hold the gains" in most rows.  What we actually want the head to learn is
*which step improved the cost*; when nothing improves, holding is the right
answer and the label is honest.
"""

from __future__ import annotations

import argparse

import numpy as np

from jev_tune.decode import ActionSpace


def relabel_chunk(path: str, out: str):
    z = dict(np.load(path))
    act_state = z["act_state"]
    n_states = len(z["feats"])
    lam = len(act_state) // n_states

    # block layout is (gen, candidate, plant): find the plant count from the
    # first run of consecutive state indices
    n = int(np.argmax(act_state != np.arange(len(act_state))))
    gens = n_states // n
    assert gens * n == n_states, (gens, n, n_states)

    cost = z["cost"]
    cur = cost.reshape(gens, 1, n)  # cost of the state each candidate starts from
    act_cost = z["act_cost"].reshape(gens, lam, n)
    act_delta = z["act_delta"].reshape(gens, lam, n, 3)  # already log10(ratio)

    improved = act_cost < cur - 1e-6
    masked = np.where(improved, act_cost, np.inf)
    best_k = np.argmin(masked, axis=1)  # (gens, n)
    has = np.isfinite(np.take_along_axis(masked, best_k[:, None, :], axis=1)[:, 0, :])

    idx = best_k[:, None, :, None].repeat(3, axis=3)  # (gens,1,n,3)
    best_delta = np.take_along_axis(act_delta, idx, axis=1)[:, 0, :, :]  # (gens,n,3)
    best_delta = np.where(has[:, :, None], best_delta, 0.0)

    deltas = ActionSpace().deltas
    cls = np.argmin(
        np.abs(best_delta[:, :, :, None] - deltas[None, None, None, :]), axis=3
    )

    z["choice"] = cls.reshape(n_states, 3).astype(np.int64)
    np.savez_compressed(out, **z)

    counts = np.bincount(z["choice"][:, 0], minlength=5) / n_states
    print(
        f"[relabel] {path}: n={n} gens={gens} improved={has.mean():.1%} "
        f"Kp label dist {np.round(counts, 3)}"
    )
    return z


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--chunks",
        nargs="+",
        default=[
            "data/chunk_0.npz",
            "data/chunk_1.npz",
            "data/chunk_2.npz",
            "data/chunk_3.npz",
        ],
    )
    ap.add_argument("--suffix", default="_rl")
    args = ap.parse_args()
    for p in args.chunks:
        relabel_chunk(p, p.replace(".npz", f"{args.suffix}.npz"))


if __name__ == "__main__":
    main()
