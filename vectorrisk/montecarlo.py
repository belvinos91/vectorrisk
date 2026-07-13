"""Monte Carlo uncertainty propagation.

- ``monte_carlo_point``  : fast ensemble for a single climate state (API/dashboard).
- ``monte_carlo_raster`` : online accumulators over full rasters (map pipeline),
  sampling one parameter vector per draw and computing the whole array
  vectorized, exactly as in the manuscript.
"""
from __future__ import annotations

from typing import Dict, Mapping, Tuple

import numpy as np

from .config import PARAM_RANGES
from .model import compute_metrics, METRIC_KEYS


def sample_params(rng: np.random.Generator,
                  ranges: Mapping[str, Tuple[float, float]] = PARAM_RANGES
                  ) -> Dict[str, float]:
    return {k: float(rng.uniform(lo, hi)) for k, (lo, hi) in ranges.items()}


def monte_carlo_point(T: float, R: float, xc: float = 500.0, n: int = 5000,
                      ranges: Mapping[str, Tuple[float, float]] = PARAM_RANGES,
                      seed: int = 20260611,
                      keep_draws: int = 2000) -> Dict:
    """Ensemble summary for one climate state.

    Returns per-metric mean, ensemble SD, and 95% Monte Carlo interval on the
    mean (mean +/- 1.96 * SD/sqrt(n)), plus a sample of raw draws.
    """
    rng = np.random.default_rng(seed)
    keys = ("r", "delta", "K", "sigma", "Lambda",
            "stationary_mean", "stationary_var", "exceed", "persist")
    acc = {k: dict(s=0.0, ss=0.0, n=0) for k in keys}
    draws = {k: [] for k in ("Lambda", "exceed", "stationary_mean", "persist")}

    for i in range(n):
        p = sample_params(rng, ranges)
        m = compute_metrics(T, R, p, xc)
        for k in keys:
            v = m[k]
            if np.isfinite(v):
                acc[k]["s"] += v
                acc[k]["ss"] += v * v
                acc[k]["n"] += 1
        if i < keep_draws:
            for k in draws:
                draws[k].append(float(m[k]))

    summary = {}
    for k in keys:
        s, ss, cnt = acc[k]["s"], acc[k]["ss"], acc[k]["n"]
        mean = s / cnt if cnt else float("nan")
        var = (ss - s * s / cnt) / (cnt - 1) if cnt > 1 else 0.0
        sd = float(np.sqrt(max(0.0, var)))
        mcse = sd / np.sqrt(cnt) if cnt else float("nan")
        summary[k] = dict(mean=mean, sd=sd,
                          ci_low=mean - 1.96 * mcse, ci_high=mean + 1.96 * mcse)
    return dict(T=T, R=R, xc=xc, n=n, summary=summary, draws=draws)


def monte_carlo_raster(T: np.ndarray, R: np.ndarray, xc: float = 500.0,
                       n: int = 10000,
                       ranges: Mapping[str, Tuple[float, float]] = PARAM_RANGES,
                       seed: int = 20260611,
                       metrics=("Lambda", "exceed", "stationary_mean", "persist"),
                       progress=None) -> Dict[str, Dict[str, np.ndarray]]:
    """Uncertainty-averaged maps via online accumulators.

    For each of ``n`` draws a single parameter vector is sampled and applied to
    the whole raster; per-pixel mean / SD / 95% interval are accumulated without
    storing every field.  Cost ~ n * n_pixels, so prefer coarse resolution for
    large n (see README for tractability notes).
    """
    rng = np.random.default_rng(seed)
    valid = np.isfinite(T) & np.isfinite(R)
    shape = T.shape
    acc = {m: dict(s=np.zeros(shape), ss=np.zeros(shape),
                   c=np.zeros(shape, dtype=np.int32)) for m in metrics}

    for i in range(n):
        p = sample_params(rng, ranges)
        vals = compute_metrics(T, R, p, xc)
        for m in metrics:
            arr = np.asarray(vals[m], dtype="float64")
            ok = np.isfinite(arr) & valid
            acc[m]["s"] += np.where(ok, arr, 0.0)
            acc[m]["ss"] += np.where(ok, arr * arr, 0.0)
            acc[m]["c"] += ok.astype(np.int32)
        if progress and (i + 1) % max(1, n // 20) == 0:
            progress((i + 1) / n)

    out = {}
    for m in metrics:
        c = acc[m]["c"].astype("float64")
        with np.errstate(divide="ignore", invalid="ignore"):
            mean = acc[m]["s"] / c
            var = (acc[m]["ss"] - acc[m]["s"] ** 2 / c) / np.maximum(c - 1, 1)
            sd = np.sqrt(np.maximum(var, 0.0))
        for a in (mean, sd):
            a[c == 0] = np.nan
        out[m] = dict(mean=mean.astype("float32"), sd=sd.astype("float32"))
        if m in ("exceed", "persist"):
            out[m]["mean"] = np.clip(out[m]["mean"], 0, 1)
    return out
