"""Import user environmental data and turn it into model outputs.

Accepts either:
  * a LONG CSV with columns: unit, month, T, R    (month = 1..12), or
  * a WIDE CSV with columns: unit, T1..T12, R1..R12, or
  * JSON records {unit: {"T":[12], "R":[12]}}.

Returns tidy, re-downloadable tables (per unit-month metrics + annual summary),
so a user can drop in their own station / gridded / scenario climate and see the
model output immediately.
"""
from __future__ import annotations

import csv
import io
from typing import Dict, List

import numpy as np

from .config import MONTH_NAMES, central_params
from .model import compute_metrics
from .validation import annual_summary


def parse_climate_csv(text: str) -> Dict[str, Dict[str, List[float]]]:
    rdr = csv.DictReader(io.StringIO(text))
    cols = [c.strip() for c in (rdr.fieldnames or [])]
    lower = {c.lower(): c for c in cols}
    units: Dict[str, Dict[str, List[float]]] = {}
    if "month" in lower and "t" in lower and "r" in lower:            # long
        ucol = lower.get("unit") or lower.get("country") or cols[0]
        tmp: Dict[str, Dict[int, tuple]] = {}
        for row in rdr:
            u = str(row[ucol]).strip()
            mo = int(float(row[lower["month"]]))
            tmp.setdefault(u, {})[mo] = (float(row[lower["t"]]), float(row[lower["r"]]))
        for u, mv in tmp.items():
            T = [mv.get(m, (np.nan, np.nan))[0] for m in range(1, 13)]
            R = [mv.get(m, (np.nan, np.nan))[1] for m in range(1, 13)]
            units[u] = {"T": T, "R": R}
    else:                                                            # wide
        ucol = lower.get("unit") or lower.get("country") or cols[0]
        for row in rdr:
            u = str(row[ucol]).strip()
            T = [float(row[lower[f"t{m}"]]) for m in range(1, 13)]
            R = [float(row[lower[f"r{m}"]]) for m in range(1, 13)]
            units[u] = {"T": T, "R": R}
    return units


def metrics_table(units: Dict[str, Dict[str, List[float]]], xc: float = 500.0,
                  params=None) -> Dict[str, List[dict]]:
    """Return {'monthly': [...per unit-month...], 'annual': [...per unit...]}."""
    p = central_params() if params is None else params
    monthly, annual = [], []
    for u, cl in units.items():
        for i in range(12):
            m = compute_metrics(float(cl["T"][i]), float(cl["R"][i]), p, xc)
            monthly.append({"unit": u, "month": MONTH_NAMES[i],
                            "T_C": round(float(cl["T"][i]), 2), "R_mm": round(float(cl["R"][i]), 1),
                            "r": round(m["r"], 5), "delta": round(m["delta"], 5),
                            "K": round(m["K"], 1), "sigma": round(m["sigma"], 4),
                            "Lambda": round(m["Lambda"], 5),
                            "stationary_mean": round(m["stationary_mean"], 2),
                            "exceed": round(m["exceed"], 4), "persist": int(m["persist"])})
        s = annual_summary(cl["T"], cl["R"], params=p)
        annual.append({"unit": u, **{k: round(v, 5) for k, v in s.items()}})
    return {"monthly": monthly, "annual": annual}
