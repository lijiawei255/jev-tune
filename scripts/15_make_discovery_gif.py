"""Render assets/discover.gif: what jev-tune discover actually does, step by step.

Every node, edge, label and number in the animation comes from two files:

    matlab/jev_dump_graph.m    the top-level signal graph of the model
    jev-tune discover --json   the verdict, the evidence and the probe effects

Regenerate with a real model (MATLAB required, once):

    matlab -batch "addpath('matlab'); jev_dump_graph('path/Model.slx','graph.json')"
    jev-tune discover --model path/Model.slx --json > discover.json
    python scripts/15_make_discovery_gif.py graph.json discover.json assets/discover.gif

The default paths use the project's generated public demo model. Private-model
graphs and discovery exports are private inputs and are not release defaults.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

INK = "#1b2430"
MUTED = "#95a5a6"
BAD = "#c0392b"
ACCENT = "#2e86c1"
GOOD = "#27ae60"
ORANGE = "#e67e22"
PAPER = "#ffffff"
PANEL = "#f5f7f9"
RULE = "#dde3e8"

FPS = 8
W, H = 10.0, 5.0
DPI = 90


# --------------------------------------------------------------------------- #
# model graph -> geometry
# --------------------------------------------------------------------------- #
def load(graph_path: Path, discover_path: Path):
    return (
        json.loads(graph_path.read_text(encoding="utf-8")),
        json.loads(discover_path.read_text(encoding="utf-8")),
    )


def children(edges, node):
    return [e["dst"] for e in edges if e["src"] == node]


def subtree(edges, start, skip):
    seen, stack = set(), [start]
    while stack:
        b = stack.pop()
        if b in seen:
            continue
        seen.add(b)
        for e in edges:
            if e["src"] == b and not (
                skip and e["src"] == skip["src"] and e["dst"] == skip["dst"]
            ):
                stack.append(e["dst"])
    return seen


def find_feedback(edges, junction):
    reach = subtree(edges, junction, None)
    for e in edges:
        if e["dst"] == junction and e["src"] in reach:
            return e
    return None


def depth_map(nodes, edges, skip):
    parents = {n["id"]: [] for n in nodes}
    for e in edges:
        if skip and e["src"] == skip["src"] and e["dst"] == skip["dst"]:
            continue
        if e["src"] in parents and e["dst"] in parents:
            parents[e["dst"]].append(e["src"])
    depth = {}

    def d(node, seen=()):
        if node in depth:
            return depth[node]
        if node in seen or not parents[node]:
            depth[node] = 0
            return 0
        depth[node] = 1 + max(d(p, seen + (node,)) for p in parents[node])
        return depth[node]

    for n in parents:
        d(n)
    return depth


def place(nodes, edges, disc):
    """Controller branches get their own row; the main path stays in the middle.

    A control loop is not a tree, but it reads like one: reference on the left,
    the parallel terms stacked in reading order (P, I, D), plant on the right,
    feedback underneath.
    """
    junction = disc.get("error_junction", "")
    fb = find_feedback(edges, junction)
    depth = depth_map(nodes, edges, fb)
    types = {n["id"]: n["type"] for n in nodes}
    linked = {e["src"] for e in edges} | {e["dst"] for e in edges}

    ctrl = disc.get("controller") or {}
    rank = {ctrl.get("kp_block"): 0, ctrl.get("ki_block"): 1, ctrl.get("kd_block"): 2}
    branches = [
        c
        for c in children(edges, junction)
        if types.get(c) not in ("Scope", "To Workspace", "Terminator")
    ]

    # order the rows P, I, D: a branch head is an Integrator or a Derivative, so
    # the rank comes from the *gain* the branch contains, not from its head
    def branch_rank(b):
        nodes_in = subtree(edges, b, fb)
        return min([rank[n] for n in nodes_in if n in rank] or [9])

    branches.sort(key=lambda b: (branch_rank(b), b))

    subs = [subtree(edges, b, fb) for b in branches]
    common = set.intersection(*subs) if subs else set()
    branch_of = {}
    for k, sub_nodes in enumerate(subs):
        for node in sub_nodes - common:  # after the merge, it is main path
            branch_of.setdefault(node, k)

    nb = max(len(branches), 1)
    dy = 0.145
    centre = 0.585

    def y_of(node):
        if node in branch_of:
            return centre + ((nb - 1) / 2 - branch_of[node]) * dy
        return centre

    scopes = {n["id"] for n in nodes if types[n["id"]] in ("Scope", "To Workspace")}
    # a block with no signal edges at all (a physical connection, an annotation)
    # is not part of what discovery reasoned about
    drawn = {n["id"] for n in nodes if n["id"] not in scopes and n["id"] in linked}
    ncol = max(depth[c] for c in drawn) + 1 if drawn else 1
    pos = {}
    for node in drawn:
        pos[node] = (0.055 + 0.80 * (depth[node] / max(ncol - 1, 1)), y_of(node))
    for i, s in enumerate(sorted(scopes)):
        pos[s] = (0.945, 0.20 - i * 0.045)
    return pos, fb, depth, scopes, drawn


def ancestors(edges, junction, skip):
    """Everything upstream of the junction: the reference branch."""
    parents = {}
    for e in edges:
        if skip and e["src"] == skip["src"] and e["dst"] == skip["dst"]:
            continue
        parents.setdefault(e["dst"], []).append(e["src"])
    seen, stack = set(), list(parents.get(junction, []))
    while stack:
        b = stack.pop()
        if b in seen:
            continue
        seen.add(b)
        stack.extend(parents.get(b, []))
    return seen


# --------------------------------------------------------------------------- #
# frames
# --------------------------------------------------------------------------- #
def frame(fig, graph, disc, pos, fb, depth, scopes, drawn, t, total):
    fig.clf()
    ax = fig.add_axes([0.015, 0.06, 0.60, 0.86])
    axl = fig.add_axes([0.645, 0.09, 0.34, 0.80])
    for a in (ax, axl):
        a.set_axis_off()
        a.set_xlim(0, 1)
        a.set_ylim(0, 1)

    edges = graph["edges"]
    junction = disc.get("error_junction", "")
    measure = disc.get("measure_block", "")
    ctrl = disc.get("controller") or {}
    named = {
        ctrl.get("kp_block"): "Kp",
        ctrl.get("ki_block"): "Ki",
        ctrl.get("kd_block"): "Kd",
    }

    t_ref, t_gain, t_fb, t_card = 1.5, 3.0, 4.6, 1.2
    reveal = min(1.0, t / 1.1)
    deepest = max(depth.get(x, 0) for x in drawn) or 1

    fig.text(
        0.02,
        0.945,
        "jev-tune discover",
        fontsize=12.5,
        color=INK,
        ha="left",
        va="center",
    )
    fig.text(
        0.60,
        0.945,
        "an unseen model, no block names used",
        fontsize=7.5,
        color=MUTED,
        ha="right",
        va="center",
    )

    # ---- edges: reference branch blue, controller green, feedback orange
    ref_nodes = ancestors(edges, junction, fb)
    for e in edges:
        s, d = e["src"], e["dst"]
        if s not in pos or d not in pos or s in scopes or d in scopes:
            continue
        if depth.get(s, 0) / deepest > reveal:
            continue
        rad = 0.0
        style = dict(color=MUTED, lw=1.0, alpha=0.28)
        if fb and (s, d) == (fb["src"], fb["dst"]):
            if t < t_fb:
                continue
            style.update(color=ORANGE, lw=2.3, alpha=1.0)
            rad = -0.32
        elif (s in ref_nodes or d in ref_nodes) and t >= t_ref:
            style.update(color=ACCENT, lw=2.1, alpha=1.0)
        elif t >= t_gain:
            style.update(color=GOOD, lw=1.8, alpha=0.9)
        ax.annotate(
            "",
            xy=pos[d],
            xytext=pos[s],
            arrowprops=dict(
                arrowstyle="-|>",
                shrinkA=14,
                shrinkB=14,
                connectionstyle=f"arc3,rad={rad}",
                **style,
            ),
        )

    # ---- nodes
    for node, (x, y) in pos.items():
        if node in scopes:
            if reveal > 0.85:
                ax.scatter(
                    [x],
                    [y],
                    s=16,
                    facecolor=MUTED,
                    edgecolor="none",
                    alpha=0.30,
                    zorder=2,
                )
            continue
        if depth.get(node, 0) / deepest > reveal:
            continue
        role = (
            "junction"
            if node == junction
            else "measure"
            if node == measure
            else named.get(node, "other")
        )
        colour = {
            "junction": ACCENT,
            "measure": ORANGE,
            "Kp": GOOD,
            "Ki": GOOD,
            "Kd": GOOD,
        }.get(role, INK)
        lit = (
            (role == "junction" and t >= t_ref)
            or (role in ("Kp", "Ki", "Kd") and t >= t_gain)
            or (role == "measure" and t >= t_fb)
        )
        if role == "other" and node in ref_nodes and t >= t_ref:
            colour = ACCENT  # the reference branch is part of the answer
        ax.scatter(
            [x],
            [y],
            s=140,
            facecolor=PAPER,
            edgecolor=colour if lit else MUTED,
            linewidth=1.9 if lit else 1.0,
            zorder=3,
        )
        # the measured block sits in the last column, with nothing above it, so
        # its label goes up; everything else goes below and stays clear of the
        # next column
        above = role == "measure"
        ax.text(
            x,
            y + (0.042 if above else -0.047),
            node.replace("_", " "),
            ha="center",
            va="bottom" if above else "top",
            fontsize=6.2,
            color=colour if lit else INK,
            zorder=4,
            fontweight="bold" if lit else "normal",
        )

    # one caption under the graph: three highlights, three collisions fewer
    parts = []
    if t >= t_ref:
        parts.append(("error junction  " + junction, ACCENT))
    if t >= t_fb:
        parts.append(
            (f"measured  {measure} port {disc.get('measure_port', 1)}", ORANGE)
        )
    x = 0.02
    for text, colour in parts:
        ax.text(
            x, 0.035, text, fontsize=7.4, color=colour, va="bottom", fontweight="bold"
        )
        x += 0.04 + 0.0105 * len(text)

    # ---- result card, revealed decision by decision
    axl.add_patch(plt.Rectangle((0, 0), 1, 1, facecolor=PANEL, edgecolor=RULE, lw=0.8))
    rows = []
    if t >= t_card:
        rows.append(("ok", "junction", junction, ""))
        ref = disc.get("reference")
        if ref:
            rows.append(("ok", "reference", f"{ref:.4g}", ""))
    if t >= t_gain:
        rows.append(("gap", "", "", ""))
        rows.append(("ok", "controller", f"{len(named)} scalar gains", ""))
        reasons = {"Kp": "direct", "Ki": "via Integrator", "Kd": "via Derivative"}
        probe = {p["role"]: p for p in (disc.get("probe") or [])}
        for role in ("Kp", "Ki", "Kd"):
            block = ctrl.get(role.lower() + "_block")
            if not block:
                continue
            eff = probe.get(role.lower(), {}).get("effect")
            tail = reasons[role] + (f"   x2 -> {eff:.2f}" if eff is not None else "")
            rows.append(("sub", role, block, tail))
    if t >= t_fb:
        rows.append(("gap", "", "", ""))
        rows.append(("ok", "measured", measure, f"port {disc.get('measure_port', 1)}"))

    y = 0.93
    for kind, key, val, tail in rows:
        if kind == "gap":
            y -= 0.045
            continue
        if kind == "ok":
            axl.text(0.05, y, key, fontsize=7.2, color=MUTED, va="top")
            axl.text(
                0.34,
                y,
                str(val),
                fontsize=7.6,
                color=INK,
                va="top",
                family="monospace",
                fontweight="bold",
            )
            if tail:
                axl.text(0.66, y, tail, fontsize=6.8, color=MUTED, va="top")
        else:
            axl.text(0.075, y, key, fontsize=6.8, color=GOOD, va="top")
            axl.text(
                0.15, y, str(val), fontsize=7.0, color=INK, va="top", family="monospace"
            )
            axl.text(0.50, y, tail, fontsize=6.4, color=MUTED, va="top")
        y -= 0.072

    if t >= t_fb + 1.2:
        axl.add_patch(
            plt.Rectangle(
                (0.045, 0.03), 0.91, 0.10, facecolor=GOOD, alpha=0.14, edgecolor="none"
            )
        )
        axl.text(
            0.5,
            0.078,
            f"confidence: {disc.get('confidence', '?')}",
            ha="center",
            fontsize=9.0,
            color=GOOD,
            fontweight="bold",
        )

    fig.patches.append(
        plt.Rectangle(
            (0, 0.012),
            min(1.0, t / total),
            0.006,
            transform=fig.transFigure,
            color=ACCENT,
            figure=fig,
        )
    )
    fig.canvas.draw()
    return Image.frombytes(
        "RGBA", fig.canvas.get_width_height(), fig.canvas.buffer_rgba()
    ).convert("RGB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("graph", nargs="?", default="research/results/demo_discovery_graph_v0100.json")
    ap.add_argument("discover", nargs="?", default="research/results/demo_discovery_v0100.json")
    ap.add_argument("out", nargs="?", default="assets/discover.gif")
    ap.add_argument("--seconds", type=float, default=7.5)
    args = ap.parse_args()

    graph, disc = load(Path(args.graph), Path(args.discover))
    pos, fb, depth, scopes, drawn = place(graph["nodes"], graph["edges"], disc)

    fig = plt.figure(figsize=(W, H), dpi=DPI)
    fig.patch.set_facecolor(PAPER)
    n = int(args.seconds * FPS)
    frames = [
        frame(fig, graph, disc, pos, fb, depth, scopes, drawn, i / FPS, args.seconds)
        for i in range(n)
    ]
    plt.close(fig)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / FPS),
        loop=0,
        optimize=True,
    )
    print(f"[gif] {out} ({out.stat().st_size / 1024:.0f} KB, {n} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
