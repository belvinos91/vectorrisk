"""Finite-horizon Girsanov change of measure + stationary Gamma densities."""
from __future__ import annotations

from typing import Dict

import numpy as np
from scipy.special import gammaln

from .model import compute_metrics


def gamma_params(a: float, b: float, sigma: float):
    s2 = sigma * sigma
    return 2.0 * a / s2 - 1.0, 2.0 * b / s2  # alpha, beta


def gamma_pdf(x: np.ndarray, alpha: float, beta: float) -> np.ndarray:
    x = np.asarray(x, dtype="float64")
    out = np.zeros_like(x)
    m = (x > 0) & (alpha > 0)
    out[m] = np.exp(alpha * np.log(beta) + (alpha - 1) * np.log(x[m])
                    - beta * x[m] - gammaln(alpha))
    return out


def girsanov_validate(T: float, R: float, xc: float = 500.0,
                      lam: float = 0.15, u: float = 0.04, tau: float = 20.0,
                      n: int = 6000, steps: int = 800,
                      params=None, seed: int = 20260611) -> Dict:
    """Reweight one baseline path ensemble toward high-abundance (a+lam*sigma)
    and intervention (a-u) drifts; compare with direct Q-simulation.

    Verifies E_Q[X_tau] = E_P[Z_tau X_tau] and reports effective sample size.
    """
    m = compute_metrics(T, R, params, xc)
    a, b, sigma, K = m["a"], m["b"], m["sigma"], m["K"]
    rng = np.random.default_rng(seed)
    dt = tau / steps
    sdt = np.sqrt(dt)
    X0 = max(1.0, 0.25 * K)

    def run(drift, record_W=False):
        X = np.full(n, X0)
        W = np.zeros(n) if record_W else None
        for _ in range(steps):
            xi = rng.standard_normal(n)
            if record_W:
                W += sdt * xi
            X = X * np.exp((drift - b * X - 0.5 * sigma * sigma) * dt + sigma * sdt * xi)
        return (X, W) if record_W else X

    # baseline paths (record terminal Brownian increment)
    Xp, W = run(a, record_W=True)

    # high-abundance: theta=-lam  ->  Z=exp(lam*W - .5 lam^2 tau)
    zH = np.exp(lam * W - 0.5 * lam * lam * tau)
    wH = zH / zH.sum()
    mean_H_weighted = float(np.sum(wH * Xp))
    ess_H = float(1.0 / np.sum(wH ** 2))

    # intervention: theta=u/sigma  ->  Z=exp(-(u/sigma)W - .5(u/sigma)^2 tau)
    k = u / sigma
    zI = np.exp(-k * W - 0.5 * k * k * tau)
    wI = zI / zI.sum()
    mean_I_weighted = float(np.sum(wI * Xp))
    ess_I = float(1.0 / np.sum(wI ** 2))

    mean_H_direct = float(run(a + lam * sigma).mean())
    mean_I_direct = float(run(a - u).mean())

    return dict(
        env=dict(T=T, R=R, a=a, b=b, sigma=sigma),
        high=dict(weighted_mean=mean_H_weighted, direct_mean=mean_H_direct,
                  abs_diff=abs(mean_H_weighted - mean_H_direct),
                  ess=ess_H, ess_frac=ess_H / n),
        intervention=dict(weighted_mean=mean_I_weighted, direct_mean=mean_I_direct,
                          abs_diff=abs(mean_I_weighted - mean_I_direct),
                          ess=ess_I, ess_frac=ess_I / n),
    )
