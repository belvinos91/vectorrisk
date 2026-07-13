"""Validation: correlate model metrics with observed disease incidence.

Design
------
Correlation is computed over a PANEL of units (rows), never over a single map.
A "unit" can be a country-year or a sub-national admin unit (preferred, because
you get many observations from one country). For each row we compute annual
model summaries from that unit's monthly climate, including exceedance at every
threshold, then correlate each summary column against the unit's incidence.

The ranked output tells you (a) which metric tracks incidence best and (b) which
exceedance threshold x_c is most predictive -- i.e. an empirical recalibration of
the operational threshold for that disease. Repeat with dengue/chikungunya
incidence and thermal parameters retuned for Aedes to get a disease-specific
threshold.

Caveats surfaced in the output: correlation != causation, requires enough units
(n), and year-by-year validation needs year-specific climate (CHIRPS/ERA5/
TerraClimate), not the WorldClim 1970-2000 climatology.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
from scipy import stats

from .config import XC_SET, central_params
from .model import compute_metrics


def panel_from_featurecollection(fc: dict) -> List[dict]:
    """Convert an admin metric FeatureCollection (from zonal.py) into panel rows."""
    rows = []
    for f in fc.get("features", []):
        p = f.get("properties", {})
        row = {"unit": p.get("unit")}
        for k in ("Lambda", "exceed", "stationary_mean", "sigma", "persist"):
            if p.get(k) is not None:
                row[k] = float(p[k])
        rows.append(row)
    return rows


def annual_summary(T_monthly: Sequence[float], R_monthly: Sequence[float],
                   xc_set: Sequence[int] = XC_SET, params=None) -> Dict[str, float]:
    """Collapse 12 monthly model states into annual summary features."""
    p = central_params() if params is None else params
    lam, persist, mean_ab, exc = [], [], [], {xc: [] for xc in xc_set}
    for T, R in zip(T_monthly, R_monthly):
        m = compute_metrics(float(T), float(R), p, xc_set[0])
        lam.append(m["Lambda"]); persist.append(m["persist"]); mean_ab.append(m["stationary_mean"])
        for xc in xc_set:
            exc[xc].append(compute_metrics(float(T), float(R), p, xc)["exceed"])
    out = {"Lambda_mean": float(np.mean(lam)),
           "persist_frac": float(np.mean(persist)),
           "abundance_mean": float(np.mean(mean_ab)),
           "abundance_peak": float(np.max(mean_ab))}
    for xc in xc_set:
        out[f"exceed_{xc}"] = float(np.mean(exc[xc]))
    return out


def build_panel(units: Dict[str, dict], xc_set: Sequence[int] = XC_SET,
                params=None) -> List[dict]:
    """units: {key: {'T':[12],'R':[12], ...extra keys copied through...}}."""
    rows = []
    for key, u in units.items():
        s = annual_summary(u["T"], u["R"], xc_set, params)
        row = {"unit": key}
        for k in ("iso3", "year", "country"):
            if k in u:
                row[k] = u[k]
        row.update(s)
        rows.append(row)
    return rows


def build_spacetime_panel(units: Dict[str, dict], years: Sequence[int],
                          climate_fn, xc_set: Sequence[int] = XC_SET,
                          params=None) -> List[dict]:
    """Panel over unit x year using year-specific climate.

    units: {key: {'iso3':..,'country':..}}. climate_fn(key, year) -> (T[12],R[12])
    or None. Produces one row per (unit, year) with model summary features,
    tagged with iso3+year so it joins to incidence keyed the same way. This is
    the scientifically defensible validation input (many observations).
    """
    rows = []
    for key, meta in units.items():
        for yr in years:
            cl = climate_fn(key, yr)
            if not cl:
                continue
            T, R = cl
            s = annual_summary(T, R, xc_set, params)
            row = {"unit": key, "year": int(yr)}
            for k in ("iso3", "country"):
                if k in meta:
                    row[k] = meta[k]
            row.update(s)
            rows.append(row)
    return rows


def _join(panel: List[dict], incidence: List[dict], keys: Sequence[str]):
    idx = {tuple(str(r.get(k)) for k in keys): r for r in incidence}
    xs_meta, matched = [], []
    for row in panel:
        kk = tuple(str(row.get(k)) for k in keys)
        if kk in idx and idx[kk].get("value") is not None:
            matched.append((row, float(idx[kk]["value"])))
    return matched


def correlate(panel: List[dict], incidence: List[dict],
              keys: Sequence[str] = ("iso3",),
              feature_prefixes=("Lambda", "persist", "abundance", "exceed")) -> dict:
    """Pearson & Spearman of each model feature vs incidence over the joined panel."""
    matched = _join(panel, incidence, keys)
    n = len(matched)
    if n < 3:
        return {"n": n, "keys": list(keys), "results": [],
                "warning": "Fewer than 3 matched units; correlation not meaningful. "
                           "Use sub-national admin units or country-year panels."}
    inc = np.array([m[1] for m in matched], dtype=float)
    feat_cols = [c for c in matched[0][0]
                 if any(c.startswith(pfx) for pfx in feature_prefixes)]
    results = []
    for col in feat_cols:
        x = np.array([m[0].get(col, np.nan) for m in matched], dtype=float)
        ok = np.isfinite(x) & np.isfinite(inc)
        if ok.sum() < 3 or np.nanstd(x[ok]) == 0:
            continue
        pr, pp = stats.pearsonr(x[ok], inc[ok])
        sr, sp = stats.spearmanr(x[ok], inc[ok])
        results.append({"feature": col, "n": int(ok.sum()),
                        "pearson_r": float(pr), "pearson_p": float(pp),
                        "spearman_r": float(sr), "spearman_p": float(sp)})
    results.sort(key=lambda d: abs(d["pearson_r"]), reverse=True)
    # scatter points for the top feature (for plotting metric vs incidence)
    scatter = []
    if results:
        top = results[0]["feature"]
        for row, y in matched:
            x = row.get(top)
            if x is not None and np.isfinite(x):
                scatter.append({"unit": str(row.get("unit", row.get("iso3", "?"))),
                                "x": float(x), "y": float(y)})
    # best exceedance threshold
    exc = [r for r in results if r["feature"].startswith("exceed_")]
    best_thr = None
    if exc:
        b = max(exc, key=lambda r: abs(r["pearson_r"]))
        best_thr = {"threshold": int(b["feature"].split("_")[1]),
                    "pearson_r": b["pearson_r"], "spearman_r": b["spearman_r"]}
    return {"n": n, "keys": list(keys), "results": results,
            "best_metric": results[0] if results else None,
            "best_exceedance_threshold": best_thr,
            "scatter_feature": results[0]["feature"] if results else None,
            "scatter": scatter,
            "note": "Correlation is associational; validate causally with "
                    "out-of-sample units and disease-specific vector parameters."}
