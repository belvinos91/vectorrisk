"""Temperature--rainfall stochastic logistic abundance model.

Pure numpy + scipy. Works on scalars or numpy arrays (rasters) identically.
Every function corresponds one-to-one with an equation in the manuscript and
with the in-browser dashboard implementation.
"""
from __future__ import annotations

from typing import Dict, Mapping, Union

import numpy as np
from scipy.special import gammaincc  # regularized upper incomplete gamma Q(a,x)

from .config import central_params

Arr = Union[float, np.ndarray]

METRIC_KEYS = (
    "r", "delta", "K", "sigma", "a", "b", "Lambda", "alpha", "beta",
    "stationary_mean", "stationary_var", "exceed", "persist",
)


# ---- ecological response functions --------------------------------------
def rainfall_suitability(R: Arr, R_L: float) -> Arr:
    raw = np.maximum(0.0, 4.0 * R * (R_L - R) / (R_L * R_L))
    return raw ** 3


def stage_survival(T: Arr, T_opt: float, w: float, p_max: float) -> Arr:
    return p_max * np.exp(-0.5 * ((T - T_opt) / w) ** 2)


def development_response(T: Arr, c1: float, c2: float) -> Arr:
    z = np.maximum(1e-6, c1 * T + c2)
    return (z * np.exp(-z)) / (2.0 * z + 1.0)


def adult_mortality(T: Arr, Lmax: float, q_delta: float,
                    T_delta_opt: float, L_min: float) -> Arr:
    L_A = np.maximum(L_min, Lmax - q_delta * (T - T_delta_opt) ** 2)
    return 1.0 / L_A


def carrying_capacity(T: Arr, R: Arr, p: Mapping[str, float]) -> Arr:
    S_R = rainfall_suitability(R, p["R_L"])
    S_K = np.exp(-0.5 * ((T - p["T_K_opt"]) / p["omega_T"]) ** 2)
    return p["K_min"] + p["K_max"] * S_R * S_K


def volatility(T: Arr, R: Arr, p: Mapping[str, float]) -> Arr:
    R_opt = p["R_L"] / 2.0
    s = (p["sigma0"]
         + p["sigma_T"] * ((T - p["T_K_opt"]) / p["omega_T"]) ** 2
         + p["sigma_R"] * ((R - R_opt) / p["R_L"]) ** 2)
    return np.minimum(p["sigma_max"], s)


def recruitment(T: Arr, R: Arr, p: Mapping[str, float]) -> Arr:
    S_R = rainfall_suitability(R, p["R_L"])
    pE = stage_survival(T, p["T_E_opt"], p["w_E"], p["pE_max"])
    pL = stage_survival(T, p["T_L_opt"], p["w_L"], p["pL_max"])
    pP = stage_survival(T, p["T_P_opt"], p["w_P"], p["pP_max"])
    D_T = development_response(T, p["c1"], p["c2"])
    return p["rho"] * p["beta_E"] * pE * pL * pP * S_R * D_T


# ---- full metric bundle --------------------------------------------------
def compute_metrics(T: Arr, R: Arr,
                    params: Mapping[str, float] | None = None,
                    xc: float = 500.0,
                    eps: float = 1e-9) -> Dict[str, Arr]:
    """Return every model quantity for climate state(s) (T, R).

    Non-persistent cells (Lambda<=0) get 0 for stationary_mean/var/exceed,
    matching the manuscript's unconditional convention.
    """
    p = dict(central_params() if params is None else params)
    T = np.asarray(T, dtype="float64")
    R = np.asarray(R, dtype="float64")

    r = recruitment(T, R, p)
    delta = adult_mortality(T, p["Lmax"], p["q_delta"], p["T_delta_opt"], p["L_min"])
    K = carrying_capacity(T, R, p)
    sigma = volatility(T, R, p)

    a = r - delta
    b = r / np.maximum(K, eps)
    s2 = np.maximum(sigma * sigma, eps)
    Lambda = a - 0.5 * s2
    alpha = 2.0 * a / s2 - 1.0
    beta = 2.0 * b / s2

    persist = (Lambda > 0.0) & (alpha > 0.0) & (beta > 0.0)
    persist = np.asarray(persist)

    stationary_mean = np.where(persist, alpha / np.where(beta == 0, np.nan, beta), 0.0)
    stationary_var = np.where(persist, alpha / np.where(beta == 0, np.nan, beta) ** 2, 0.0)
    # exceedance via regularized upper incomplete gamma; guard non-persistent
    a_safe = np.where(persist, alpha, 1.0)
    x_safe = np.where(persist, beta * xc, 0.0)
    exceed = np.where(persist, gammaincc(a_safe, x_safe), 0.0)

    out = dict(r=r, delta=delta, K=K, sigma=sigma, a=a, b=b, Lambda=Lambda,
               alpha=alpha, beta=beta, stationary_mean=stationary_mean,
               stationary_var=stationary_var, exceed=exceed,
               persist=persist.astype("float64"))
    # collapse 0-d arrays to python floats for scalar inputs
    if T.ndim == 0:
        out = {k: float(np.asarray(v)) for k, v in out.items()}
    return out
