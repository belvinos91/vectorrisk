"""Connectivity & licence diagnostics — `vectorrisk check`.

Pings every external data source so you can see, before a run, exactly which
links work from your machine/server (this is what diagnoses a "not working"
data link). It also prints each source's licence, which matters for a commercial
deployment.
"""
from __future__ import annotations

from typing import List

from . import config as C


def _ping(url: str, timeout: int = 25):
    import requests
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400 or r.status_code == 405:      # some servers reject HEAD
            r = requests.get(url, timeout=timeout, stream=True)
        ok = r.status_code < 400
        return ok, f"HTTP {r.status_code}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check(resolution: str = None, year: int = 2020) -> List[dict]:
    from .incidence import GHO_BASE
    from .map_incidence import MAP_WCS_BASE
    res = resolution or C.DEFAULT_RESOLUTION
    tc_file = (f"http://thredds.northwestknowledge.net:8080/thredds/fileServer/"
               f"TERRACLIMATE_ALL/data/TerraClimate_tmax_{year}.nc")
    checks = [
        ("WorldClim 2.1 (temp/rain)", C.worldclim_url("tavg", res)),
        ("GADM 4.1 boundaries", C.gadm_url("KEN", 0)),
        ("geoBoundaries (commercial)", C.geoboundaries_meta_url("KEN", 0)),
        ("Natural Earth", C.NATURAL_EARTH_ADMIN0),
        ("WHO GHO incidence", f"{GHO_BASE}/Indicator?$top=1"),
        ("TerraClimate (panel)", tc_file),
        ("CHIRPS rainfall", C.chirps_month_url(year, 1)),
        ("Malaria Atlas Project WCS", f"{MAP_WCS_BASE}?service=WCS&request=GetCapabilities&version=2.0.1"),
    ]
    out = []
    for name, url in checks:
        ok, detail = _ping(url)
        lic = next((v for k, v in C.SOURCE_LICENSES.items() if k.split()[0] in name), "")
        out.append({"source": name, "url": url, "ok": ok, "detail": detail, "license": lic})
    return out


def format_report(rows: List[dict]) -> str:
    lines = ["", "VectorRisk data-source check", "=" * 60]
    for r in rows:
        mark = "OK  " if r["ok"] else "FAIL"
        lines.append(f"[{mark}] {r['source']:30s} {r['detail']}")
        if r["license"]:
            lines.append(f"        licence: {r['license']}")
    fails = [r for r in rows if not r["ok"]]
    lines += ["-" * 60,
              f"{len(rows) - len(fails)}/{len(rows)} reachable."]
    if fails:
        lines.append("Unreachable links usually mean: no internet, a firewall/proxy, "
                     "or the provider is temporarily down. Retry, or set a proxy.")
    lines.append("Reminder: GADM is non-commercial. For a product you sell, set "
                 "ADMIN_SOURCE='geoboundaries'.")
    return "\n".join(lines)
