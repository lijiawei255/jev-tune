"""Deterministic two-parameter offline denoising task.

The hidden reference signal is used only to measure raw mean squared error.
The policy sees the measured cost and noisy/output/residual summaries, never
the reference waveform or its generating parameters. Each object is immutable;
the caller owns evaluation accounting and previous-cost feedback.

确定性的二参数离线去噪任务。参考信号仅用于计算原始均方误差；策略只能
看到已测代价与带噪信号、输出和残差摘要。对象不可变，调用方负责计账及历史反馈。
"""
from __future__ import annotations

import operator

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import butter, sosfiltfilt


L = 192


def _nonnegative_integer(value, name: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a nonnegative integer")
    try:
        result = operator.index(value)
    except TypeError as exc:
        raise ValueError(f"{name} must be a nonnegative integer") from exc
    if result < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return result


def _theta(value) -> np.ndarray:
    theta = np.asarray(value, dtype=np.float64)
    if theta.shape != (2,) or not np.isfinite(theta).all():
        raise ValueError("theta must contain two finite values")
    if np.any(theta < 0) or np.any(theta > 1):
        raise ValueError("theta must lie in [0, 1]^2")
    return theta


def _lag1corr(values: np.ndarray) -> float:
    """Pearson correlation of adjacent slices; zero for a constant slice."""
    left, right = values[:-1], values[1:]
    left = left - np.mean(left)
    right = right - np.mean(right)
    denominator = np.sqrt(np.dot(left, left) * np.dot(right, right))
    return 0.0 if denominator == 0 else float(np.dot(left, right) / denominator)


def _signal_features(values: np.ndarray) -> list[float]:
    return [float(np.mean(values)), float(np.std(values, ddof=0)),
            float(np.std(np.diff(values), ddof=0)), _lag1corr(values)]


def _immutable_array(values: np.ndarray) -> np.ndarray:
    # Immutable bytes also prevent callers from re-enabling ndarray writes.
    return np.frombuffer(np.asarray(values, dtype=np.float64).tobytes(), dtype=np.float64)


class DenoiseTask:
    """One fixed signal from SeedSequence([seed, index]); no cache or counter.

    ``theta`` is in [0, 1]^2. Its first coordinate sets the local clipping
    multiplier k=1+5*theta[0]; its second sets the log-spaced low-pass cutoff
    fc=.02*(.35/.02)**theta[1], in cycles per sample.

    一个固定信号对象。theta第一维控制局部截断倍数，第二维控制对数间隔的
    低通截止频率；重复测量完全重算，不维护缓存或计数器。
    """

    __slots__ = ("_splitseed", "_index", "_clean", "_noisy")

    def __init__(self, seed: int, index: int):
        seed = _nonnegative_integer(seed, "seed")
        index = _nonnegative_integer(index, "index")
        rng = np.random.default_rng(np.random.SeedSequence([seed, index]))
        amp = rng.uniform(0.5, 1.5)
        f1 = rng.uniform(0.005, 0.03)
        f2 = rng.uniform(0.03, 0.09)
        phase1 = rng.uniform(0, 2 * np.pi)
        phase2 = rng.uniform(0, 2 * np.pi)
        drift = rng.uniform(-0.3, 0.3)
        step = rng.uniform(-0.5, 0.5)
        step_idx = rng.integers(L // 4, 3 * L // 4)
        sigma = rng.uniform(0.05, 0.4)
        outlier_p = rng.uniform(0.005, 0.04)
        outlier_amp = rng.uniform(1, 4)
        noise = rng.normal(0, sigma, L)
        mask = rng.random(L) < outlier_p
        signs = rng.choice([-1, 1], L)
        t = np.arange(L, dtype=np.float64)
        clean = (amp * (np.sin(2 * np.pi * f1 * t + phase1)
                        + 0.35 * np.sin(2 * np.pi * f2 * t + phase2))
                 + drift * (t / (L - 1)) + step * (t >= step_idx))
        noisy = clean + noise + mask * signs * outlier_amp
        object.__setattr__(self, "_splitseed", seed)
        object.__setattr__(self, "_index", index)
        object.__setattr__(self, "_clean", _immutable_array(clean))
        object.__setattr__(self, "_noisy", _immutable_array(noisy))

    def __setattr__(self, name, value):
        raise AttributeError("DenoiseTask is immutable")

    @property
    def splitseed(self) -> int:
        return self._splitseed

    @property
    def index(self) -> int:
        return self._index

    def _filter_output(self, theta) -> np.ndarray:
        theta = _theta(theta)
        k = 1 + 5 * theta[0]
        fc = 0.02 * (0.35 / 0.02) ** theta[1]
        local_median = median_filter(self._noisy, size=9, mode="reflect")
        local_scale = np.maximum(
            1.4826 * median_filter(np.abs(self._noisy - local_median), size=9, mode="reflect"),
            0.02,
        )
        clipped = np.clip(self._noisy, local_median - k * local_scale,
                          local_median + k * local_scale)
        sos = butter(2, Wn=2 * fc, output="sos")
        return sosfiltfilt(sos, clipped)

    def evaluate(self, theta) -> dict[str, float | list[float]]:
        """Measure J and 16 features; feature[3] is a caller-owned placeholder.

        Layout: theta[2], log1p(J), 0, noisy[4], output[4], residual[4].
        The first two signal groups are mean/std/difference-std/lag-1 Pearson
        correlation; residual=noisy-output uses mean/std/absolute-p90/lag-1.
        Standard deviations use ddof=0. The runner replaces feature[3] with
        its measured before/after log1p(J) difference.

        返回J和16维特征。第3号特征由调用方填入前后实测log1p(J)差；
        信号标准差使用ddof=0，零方差相邻片段的相关系数取0。
        """
        theta = _theta(theta)
        output = self._filter_output(theta)
        cost = float(np.mean((output - self._clean) ** 2))
        residual = self._noisy - output
        features = [float(theta[0]), float(theta[1]), float(np.log1p(cost)), 0.0]
        features += _signal_features(self._noisy)
        features += _signal_features(output)
        features += [float(np.mean(residual)), float(np.std(residual, ddof=0)),
                     float(np.percentile(np.abs(residual), 90)), _lag1corr(residual)]
        return {"cost": cost, "features": features}
