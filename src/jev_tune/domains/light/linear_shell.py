"""Ordered numeric instance: two additive parameters, expectation decode + Hold.

Contrast with vla_mask.py: ordered numeric payloads may be averaged; categorical
tokens may not. No PID, simulator, pretrained model or hardware.
"""
import numpy as np

from ...core.policy import AbstainPolicy, decide
from ...core.primitives import Answer, Choice, Noul, Option


def toy_step(state):
    # A real port must obtain calibrated distributions from its own backend.
    answer = Answer(choice=[
        Choice("heater offset", [Option("less", -.1), Option("more", .1)], np.array([0., 1.])),
        Choice("fan offset", [Option("less", -.2), Option("more", .2)], np.array([1., 0.])),
    ], noul=Noul("observation valid", .9))
    decision = decide(answer, max_step=.15, abstain=AbstainPolicy())
    # Domain-owned actuator and constraints, outside probabilistic decoding.
    return np.clip(state + decision.step, 0., 1.), decision


if __name__ == "__main__":
    updated, decision = toy_step(np.array([.5, .5]))
    print({"state": updated.tolist(), "axis_held": decision.held.tolist()})
