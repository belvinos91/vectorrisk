"""Multi-year daily stochastic abundance simulation over the seasonal cycle."""
from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

from .config import DAYS_IN_MONTH, MONTH_NAMES
from .model import compute_metrics


def _daily_climate(T_monthly: Sequence[float], R_monthly: Sequence[float],
                   interp: str = "linear"):
    """Expand 12 monthly values to 365 daily values."""
    cum = np.concatenate([[0], np.cumsum(DAYS_IN_MONTH)])
    Td, Rd, month_of = [], [], []
    for d in range(365):
        mi = int(np.searchsorted(cum, d, side="right") - 1)
        mi = min(11, max(0, mi))
        month_of.append(mi)
        if interp == "step":
            Td.append(T_monthly[mi]); Rd.append(R_monthly[mi]); continue
        mid_this = cum[mi] + DAYS_IN_MONTH[mi] / 2
        if d < mid_this:
            pm = (mi - 1) % 12
            mid_prev = cum[mi] - DAYS_IN_MONTH[pm] / 2
            frac = (d - mid_prev) / max(mid_this - mid_prev, 1)
            i0, i1 = pm, mi
        else:
            nm = (mi + 1) % 12
            mid_next = cum[mi + 1] + DAYS_IN_MONTH[nm] / 2
            frac = (d - mid_this) / max(mid_next - mid_this, 1)
            i0, i1 = mi, nm
        frac = min(1.0, max(0.0, frac))
        Td.append(T_monthly[i0] + (T_monthly[i1] - T_monthly[i0]) * frac)
        Rd.append(R_monthly[i0] + (R_monthly[i1] - R_monthly[i0]) * frac)
    return np.array(Td), np.array(Rd), month_of


def simulate_series(T_monthly: Sequence[float], R_monthly: Sequence[float],
                    params=None, years: int = 4, xc: float = 500.0,
                    interp: str = "linear", seed: int = 20260611,
                    every: int = 1) -> Dict:
    """Log-Euler daily integration of dX = X(a-bX)dt + sigma X dW.

    Returns a list of daily records plus summary statistics.  Positivity is
    preserved exactly by the log-Euler scheme.
    """
    Td, Rd, month_of = _daily_climate(T_monthly, R_monthly, interp)
    rng = np.random.default_rng(seed)
    p = params
    m0 = compute_metrics(float(Td[0]), float(Rd[0]), p, xc)
    X = max(1.0, 0.25 * m0["K"])

    records: List[dict] = []
    xs = np.empty(years * 365)
    idx = 0
    for d in range(years * 365):
        di = d % 365
        T, R = float(Td[di]), float(Rd[di])
        m = compute_metrics(T, R, p, xc)
        a, b, sigma = m["a"], m["b"], m["sigma"]
        xi = rng.standard_normal()
        X = X * np.exp((a - b * X - 0.5 * sigma * sigma) + sigma * xi)  # dt = 1 day
        if not np.isfinite(X) or X < 1e-6:
            X = 1e-6
        xs[idx] = X; idx += 1
        if d % every == 0:
            records.append(dict(day=d + 1, year=d // 365 + 1,
                                month=MONTH_NAMES[month_of[di]],
                                T_C=round(T, 2), R_mm=round(R, 1),
                                abundance_X=round(float(X), 2),
                                Lambda=round(float(m["Lambda"]), 5),
                                persist=int(m["persist"])))
    xs = xs[:idx]
    stats = dict(days=len(records), mean=float(xs.mean()),
                 peak=float(xs.max()), trough=float(xs.min()),
                 frac_above_xc=float((xs > xc).mean()))
    return dict(years=years, xc=xc, records=records, stats=stats)
