"""Malaria (and other vector-borne disease) incidence ingestion + normalization.

Primary source: WHO Global Health Observatory (GHO) OData API
    https://ghoapi.azureedge.net/api/
GHO malaria estimates are national and annual, ~2000-present.  Sub-national and
longer historical series are best obtained from the Malaria Atlas Project (MAP);
a hook is provided but not fetched here.

Everything is normalized to one tidy schema so it can be re-exported to CSV/Excel
and joined against model outputs:

    {iso3, country, year, indicator, disease, value, low, high, unit, source}

Network is required for a live pull; results are cached. A small clearly-labelled
SAMPLE table is returned offline so the pipeline is demonstrable without internet.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

GHO_BASE = "https://ghoapi.azureedge.net/api"

# Candidate WHO GHO indicator codes. Names/codes can change; use
# discover_indicators() to confirm the live codes on your machine.
GHO_INDICATORS: Dict[str, Dict[str, str]] = {
    "MALARIA_EST_INCIDENCE": {"disease": "malaria",
        "label": "Estimated malaria incidence (per 1000 pop at risk)", "unit": "per 1000 PAR"},
    "MALARIA_EST_CASES": {"disease": "malaria",
        "label": "Estimated malaria cases", "unit": "cases"},
    "MALARIA_EST_DEATHS": {"disease": "malaria",
        "label": "Estimated malaria deaths", "unit": "deaths"},
    "MALARIA_CONF_CASES": {"disease": "malaria",
        "label": "Confirmed malaria cases", "unit": "cases"},
}

# Illustrative offline sample (NOT official numbers) so endpoints work without net.
_SAMPLE = {
    "MALARIA_EST_INCIDENCE": {
        "KEN": {2015: 78, 2017: 74, 2019: 68, 2021: 61},
        "CMR": {2015: 300, 2017: 292, 2019: 285, 2021: 279},
        "MOZ": {2015: 340, 2017: 331, 2019: 322, 2021: 315},
    }
}
_ISO_NAME = {"KEN": "Kenya", "CMR": "Cameroon", "MOZ": "Mozambique"}


def _cache_path(cache_dir: str, indicator: str) -> Path:
    return Path(cache_dir) / "incidence" / f"{indicator}.json"


def discover_indicators(keyword: str = "malaria",
                        cache_dir: str = "vectorrisk_cache") -> List[dict]:
    """List GHO indicators whose name matches a keyword (needs network)."""
    import requests
    r = requests.get(f"{GHO_BASE}/Indicator", timeout=60)
    r.raise_for_status()
    out = [d for d in r.json().get("value", [])
           if keyword.lower() in str(d.get("IndicatorName", "")).lower()]
    return out


def fetch_gho(indicator: str, countries: Optional[Sequence[str]] = None,
              year_min: int = 2000, cache_dir: str = "vectorrisk_cache",
              refresh: bool = False) -> List[dict]:
    """Fetch raw GHO records for one indicator, cached. Returns GHO 'value' list."""
    import requests
    cp = _cache_path(cache_dir, indicator)
    if cp.exists() and not refresh:
        return json.loads(cp.read_text())
    flt = [f"TimeDim ge {year_min}"]
    if countries:
        flt.append("(" + " or ".join(f"SpatialDim eq '{c.upper()}'" for c in countries) + ")")
    url = f"{GHO_BASE}/{indicator}?$filter=" + " and ".join(flt)
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    val = r.json().get("value", [])
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(val))
    return val


def tidy_incidence(indicator: str = "MALARIA_EST_INCIDENCE",
                   countries: Optional[Sequence[str]] = None,
                   year_min: int = 2000, cache_dir: str = "vectorrisk_cache",
                   live: bool = True) -> List[dict]:
    """Return normalized tidy rows. Falls back to labelled sample if offline."""
    meta = GHO_INDICATORS.get(indicator, {"disease": "unknown", "unit": ""})
    rows: List[dict] = []
    if live:
        try:
            for rec in fetch_gho(indicator, countries, year_min, cache_dir):
                if rec.get("SpatialDimType") != "COUNTRY":
                    continue
                # prefer overall (no sex/residence split) when Dim1 present
                if rec.get("Dim1") not in (None, "", "SEX_BTSX", "TOTL"):
                    continue
                iso3 = rec.get("SpatialDim")
                rows.append(dict(
                    iso3=iso3, country=_ISO_NAME.get(iso3, iso3),
                    year=int(rec.get("TimeDim")), indicator=indicator,
                    disease=meta["disease"],
                    value=_num(rec.get("NumericValue")),
                    low=_num(rec.get("Low")), high=_num(rec.get("High")),
                    unit=meta["unit"], source="WHO GHO"))
            if rows:
                return sorted(rows, key=lambda r: (r["iso3"], r["year"]))
            # self-heal: the code may have changed -> discover a malaria incidence code
            if "MALARIA" in indicator.upper():
                for d in discover_indicators("malaria incidence", cache_dir):
                    code = d.get("IndicatorCode")
                    if code and code != indicator:
                        alt = tidy_incidence(code, countries, year_min, cache_dir, live=True)
                        if alt:
                            return alt
        except Exception:
            pass  # fall through to sample
    smp = _SAMPLE.get(indicator, {})
    for iso3, yv in smp.items():
        if countries and iso3.upper() not in {c.upper() for c in countries}:
            continue
        for yr, v in yv.items():
            rows.append(dict(iso3=iso3, country=_ISO_NAME.get(iso3, iso3), year=yr,
                             indicator=indicator, disease=meta["disease"], value=float(v),
                             low=None, high=None, unit=meta["unit"], source="SAMPLE (offline)"))
    return sorted(rows, key=lambda r: (r["iso3"], r["year"]))


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def export_table(rows: List[dict], path: str) -> str:
    """Write tidy rows to CSV or XLSX (xlsx needs pandas; else falls back to CSV)."""
    p = Path(path)
    if p.suffix.lower() == ".xlsx":
        try:
            import pandas as pd
            pd.DataFrame(rows).to_excel(p, index=False)
            return str(p)
        except Exception:
            p = p.with_suffix(".csv")
    import csv
    if rows:
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    return str(p)
