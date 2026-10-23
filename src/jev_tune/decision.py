"""The typed decision layer: questions in, ``Choice`` / ``Score`` / ``Noul`` out.

The protocol and answer objects are reusable. The concrete numeric backends,
question registry and checkpoints below implement the PID testbed's three
axes and feature tensor schema. A port must supply its own backend and adapter.

This is the contract ``docs/ARCHITECTURE.md`` describes, and it is on the
execution path: ``evaluate.evaluate_head`` (and therefore the CLI, the demo and
the MCP server) asks a backend for typed answers, never for raw logits.

What is and is not Jev-like here
--------------------------------
Jev takes ``(state, {question_id: question})`` and returns the same map with
typed answers.  This module keeps that shape -- a fixed registry of question
slots, answers keyed by id, an error for a question the backend was not trained
to answer -- but the state is a tensor pair and the backend is a 200 KB
convolutional encoder, not a text model.  There is no text input and no Jev
weight in this repository.  See ``docs/JEV_MAPPING.md``.

Temperature
-----------
``models/calibration.json`` holds one fitted temperature per gain axis.  They
are fitted on a fresh plant-level split independent of CP fitting/evaluation.
They change probabilities and expectation-decoded actions; the ablation measures
this effect. Split-CP metadata is loaded alongside them for label-set monitoring;
its historical hard-hold intervention remains an explicit option.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

import numpy as np

from .decode import ActionSpace, ConformalPolicy
from .primitives import Answer, Choice, Noul, Option, Score, softmax

AXES = ("Kp", "Ki", "Kd")


def _temperature(value):
    t = np.ones(len(AXES)) if value is None else np.asarray(value, dtype=float)
    if t.shape != (len(AXES),) or not np.isfinite(t).all() or (t <= 0).any():
        raise ValueError("need three finite positive temperatures")
    return t


def _inputs(feats, curves):
    f, c = np.asarray(feats, dtype=np.float32), np.asarray(curves, dtype=np.float32)
    if f.ndim != 2 or c.ndim != 3 or f.shape[0] != c.shape[0]:
        raise ValueError("expected features (N,F) and curves (N,C,L)")
    if not np.isfinite(f).all() or not np.isfinite(c).all():
        raise ValueError("features and curves must be finite")
    return f, c

SCORE_LEVELS = ("J<0.8", "0.8<=J<1.5", "1.5<=J<3", "3<=J<6", "J>=6")
"""The five cost bands the expert labels, cheapest first (0 is the best band)."""


class UnknownQuestion(KeyError):
    """The backend was asked something it was not trained to answer."""


def read_temperature(models_dir: str | Path) -> list[float] | None:
    """The choice temperatures stored next to a checkpoint, if any."""
    cal = Path(models_dir) / "calibration.json"
    if not cal.is_file():
        return None
    blob = json.loads(cal.read_text(encoding="utf-8-sig"))
    t = blob.get("choice_temperature")
    return None if t is None else [float(x) for x in t]


def read_conformal(models_dir: str | Path, *, mode: str | None = None) -> ConformalPolicy | None:
    """Load set calibration; intervention is opt-in through the policy mode."""
    if mode is not None and mode not in ("monitor", "hard_hold"):
        raise ValueError("conformal mode must be 'monitor' or 'hard_hold'")
    path = Path(models_dir) / "calibration.json"
    policy = None if not path.is_file() else ConformalPolicy.from_calibration(json.loads(path.read_text(encoding="utf-8-sig")))
    if mode is not None:
        if policy is None:
            raise ValueError("an explicit conformal mode requires calibration metadata")
        policy = replace(policy, mode=mode)
    return policy


@dataclass(frozen=True)
class Question:
    id: str
    kind: str  # "choice" | "score" | "noul"
    prompt: str
    options: tuple[str, ...] = ()
    levels: tuple[str, ...] = ()


def tuner_questions(space: ActionSpace | None = None) -> tuple[Question, ...]:
    """The fixed question set the tuner asks on every iteration."""
    space = space or ActionSpace()
    labels = tuple(f"x{m:g}" for m in space.multipliers)
    qs = [
        Question(
            f"step:{a}", "choice", f"Which multiplicative step should {a} take?", labels
        )
        for a in AXES
    ]
    qs.append(
        Question(
            "quality",
            "score",
            "Which cost band is the current response in?",
            levels=SCORE_LEVELS,
        )
    )
    qs.append(Question("healthy", "noul", "Will this step keep the loop healthy?"))
    return tuple(qs)


@runtime_checkable
class DecisionBackend(Protocol):
    """Anything that can answer the tuner's typed questions."""

    def answer(
        self,
        feats: np.ndarray,
        curves: np.ndarray,
        questions: Sequence[Question] | None = None,
    ) -> Answer: ...

    def action_value(self, deltas: np.ndarray) -> np.ndarray: ...


# --------------------------------------------------------------------------- #
# Numeric backend (torch)
# --------------------------------------------------------------------------- #


class NumericBackend:
    """The shipped head, exposed only through typed answers."""

    name = "numeric-head"

    def __init__(
        self,
        model,
        *,
        space: ActionSpace | None = None,
        temperature: Sequence[float] | None = None,
        calibrate: bool = True,
        conformal: ConformalPolicy | None = None,
    ):
        import torch  # local import keeps `numpy`-only users out of the torch path

        self._torch = torch
        self.model = model
        self.space = space or ActionSpace()
        self.questions = {q.id: q for q in tuner_questions(self.space)}
        self.calibrate = calibrate
        self.conformal = conformal if calibrate else None
        self.temperature = _temperature(temperature)
        if self.temperature.shape != (len(AXES),):
            raise ValueError(
                f"expected {len(AXES)} temperatures, got {self.temperature.shape}"
            )
        self._h = None
        self._options = [
            [
                Option(label=f"x{m:g}", delta=float(np.log10(m)))
                for m in self.space.multipliers
            ]
            for _ in AXES
        ]

    def _choice_probs(self, logits: np.ndarray) -> np.ndarray:
        """(N, 3, K) logits -> (N, 3, K) probabilities in one softmax call."""
        z = np.asarray(logits, dtype=np.float64)
        return softmax(z, axis=-1, temperature=self.temperature[None, :, None] if self.calibrate else 1.0)

    @classmethod
    def from_checkpoint(cls, models_dir: str | Path, **kwargs) -> NumericBackend:
        import torch

        from .model import JevHead

        d = Path(models_dir)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8-sig"))
        model = JevHead(
            n_feats=meta.get("n_feats", 20),
            n_curve=meta.get("n_curve", 64),
            n_actions=meta.get("n_actions", 7),
        )
        model.load_state_dict(torch.load(d / "jev_head.pt", map_location="cpu"))
        model.eval()
        temperature = read_temperature(d)
        model.conformal = read_conformal(d, mode=kwargs.pop("conformal_mode", None))
        if temperature is not None:
            # carry provenance with the model so `as_backend()` can apply the
            # same temperatures when a script passes a bare `JevHead`
            model.temperature = tuple(temperature)
        kwargs.setdefault("calibrate", True)
        kwargs.setdefault("conformal", model.conformal)
        return cls(model, temperature=temperature, **kwargs)

    def _check(self, questions: Sequence[Question] | None) -> list[Question]:
        if questions is None:
            return list(self.questions.values())
        missing = [q.id for q in questions if q.id not in self.questions]
        if missing:
            raise UnknownQuestion(
                f"{self.name} cannot answer {missing}; supported ids are "
                f"{sorted(self.questions)}"
            )
        return list(questions)

    def answer(
        self,
        feats: np.ndarray,
        curves: np.ndarray,
        questions: Sequence[Question] | None = None,
    ) -> Answer:
        qs = self._check(questions)
        feats, curves = _inputs(feats, curves)
        f = self._torch.as_tensor(feats, dtype=self._torch.float32)
        c = self._torch.as_tensor(curves, dtype=self._torch.float32)
        with self._torch.no_grad():
            out = self.model(f, c)
        if any(not self._torch.isfinite(out[key]).all() for key in ("choice", "score", "noul")):
            raise ValueError("backend logits must be finite")
        self._h = out["h"]

        steps, dist, p_true = {}, None, None
        noul_prompt = "healthy"
        choice_p = self._choice_probs(out["choice"].numpy())
        for q in qs:
            if q.kind == "choice":
                axis = AXES.index(q.id.split(":", 1)[1])
                steps[q.id] = Choice(
                    question=q.prompt,
                    options=self._options[axis],
                    probs=choice_p[:, axis],
                )
            elif q.kind == "score":
                dist = Score(
                    q.prompt, list(q.levels), softmax(out["score"].numpy(), axis=-1)
                )
            elif q.kind == "noul":
                p_true = self._torch.sigmoid(out["noul"]).numpy()
                noul_prompt = q.prompt
        if len(steps) != len(AXES):
            raise UnknownQuestion(
                f"a complete step needs all of {list(AXES)}; got {sorted(steps)}"
            )
        return Answer(
            choice=[steps[f"step:{a}"] for a in AXES],
            score=dist,
            noul=Noul(noul_prompt, p_true),
        )

    def action_value(self, deltas: np.ndarray) -> np.ndarray:
        d = self._torch.as_tensor(np.asarray(deltas), dtype=self._torch.float32)
        if d.dim() == 2:
            d = d.unsqueeze(1)
        with self._torch.no_grad():
            return self.model.action_value(self._h, d).numpy()


# --------------------------------------------------------------------------- #
# Numeric backend (ONNX)
# --------------------------------------------------------------------------- #


class OnnxBackend:
    """Same contract, no torch at inference time (one CPU thread)."""

    name = "onnx-head"

    def __init__(
        self,
        path: str | Path,
        *,
        space: ActionSpace | None = None,
        temperature: Sequence[float] | None = None,
        calibrate: bool = True,
        threads: int = 1,
        conformal: ConformalPolicy | None = None,
    ):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = threads
        self.sess = ort.InferenceSession(
            str(path), so, providers=["CPUExecutionProvider"]
        )
        self.space = space or ActionSpace()
        self.questions = {q.id: q for q in tuner_questions(self.space)}
        self.calibrate = calibrate
        self.conformal = conformal if calibrate else None
        self.temperature = _temperature(temperature)
        self._options = [
            [
                Option(label=f"x{m:g}", delta=float(np.log10(m)))
                for m in self.space.multipliers
            ]
            for _ in AXES
        ]

    def _choice_probs(self, logits: np.ndarray) -> np.ndarray:
        z = np.asarray(logits, dtype=np.float64)
        return softmax(z, axis=-1, temperature=self.temperature[None, :, None] if self.calibrate else 1.0)

    def _check(self, questions):
        if questions is None:
            return list(self.questions.values())
        missing = [q.id for q in questions if q.id not in self.questions]
        if missing:
            raise UnknownQuestion(f"{self.name} cannot answer {missing}")
        return list(questions)

    def answer(self, feats, curves, questions=None) -> Answer:
        qs = self._check(questions)
        feats, curves = _inputs(feats, curves)
        out = self.sess.run(
            None,
            {
                "feats": np.asarray(feats, dtype=np.float32),
                "curves": np.asarray(curves, dtype=np.float32),
            },
        )
        logits = {"choice": out[0], "score": out[1], "noul": out[2]}
        if any(not np.isfinite(z).all() for z in logits.values()):
            raise ValueError("backend logits must be finite")
        steps, dist, p_true = {}, None, None
        noul_prompt = "healthy"
        choice_p = self._choice_probs(logits["choice"])
        for q in qs:
            if q.kind == "choice":
                axis = AXES.index(q.id.split(":", 1)[1])
                steps[q.id] = Choice(
                    question=q.prompt,
                    options=self._options[axis],
                    probs=choice_p[:, axis],
                )
            elif q.kind == "score":
                dist = Score(
                    q.prompt, list(q.levels), softmax(logits["score"], axis=-1)
                )
            elif q.kind == "noul":
                p_true = 1.0 / (1.0 + np.exp(-logits["noul"]))
                noul_prompt = q.prompt
        return Answer(
            choice=[steps[f"step:{a}"] for a in AXES],
            score=dist,
            noul=Noul(noul_prompt, p_true),
        )

    def action_value(self, deltas):
        raise NotImplementedError(
            "the exported ONNX graph has no value head; the lookahead filter is off by default"
        )


# --------------------------------------------------------------------------- #
# Adapters
# --------------------------------------------------------------------------- #


def as_backend(obj, *, space: ActionSpace | None = None) -> DecisionBackend:
    """Accept a backend, a ``JevHead`` or a legacy ``TorchBackend``.

    A bare ``JevHead`` that came from ``NumericBackend.from_checkpoint`` carries
    its fitted temperatures on ``model.temperature``; those are applied here so
    every entry point (benchmark scripts, CLI, MCP) calibrates the same way.
    A head of unknown provenance is used uncalibrated rather than with someone
    else's temperatures.
    """
    if isinstance(obj, (NumericBackend, OnnxBackend)):
        return obj
    if hasattr(obj, "answer"):
        return obj
    if hasattr(obj, "model") and hasattr(obj, "probs"):  # legacy TorchBackend
        obj = obj.model
    temperature = getattr(obj, "temperature", None)
    return NumericBackend(
        obj,
        space=space,
        temperature=None if temperature is None else list(temperature),
        calibrate=temperature is not None,
        conformal=getattr(obj, "conformal", None),
    )


def load_backend(
    models_dir: str | Path = "models",
    *,
    kind: str = "torch",
    calibrate: bool = True,
    space: ActionSpace | None = None,
    conformal_mode: str | None = None,
) -> NumericBackend | OnnxBackend:
    """The one loader every entry point should use.

    ``kind="onnx"`` uses the exported graph (0.19 ms forward, no torch);
    ``kind="torch"`` loads the checkpoint.  Both read ``calibration.json`` and
    apply it unless ``calibrate=False``. CP defaults to monitoring;
    ``conformal_mode="hard_hold"`` explicitly enables its intervention policy.
    """
    d = Path(models_dir)
    if kind == "onnx":
        return OnnxBackend(
            d / "jev_head.onnx",
            space=space,
            temperature=read_temperature(d),
            calibrate=calibrate,
            conformal=read_conformal(d, mode=conformal_mode),
        )
    if kind != "torch":
        raise ValueError("kind must be 'torch' or 'onnx'")
    return NumericBackend.from_checkpoint(d, space=space, calibrate=calibrate,
                                         conformal_mode=conformal_mode)


__all__ = [
    "AXES",
    "SCORE_LEVELS",
    "Answer",
    "Choice",
    "DecisionBackend",
    "Noul",
    "NumericBackend",
    "OnnxBackend",
    "Question",
    "Score",
    "UnknownQuestion",
    "as_backend",
    "load_backend",
    "read_temperature",
    "read_conformal",
    "tuner_questions",
]
