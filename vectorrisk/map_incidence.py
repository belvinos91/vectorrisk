"""Malaria Atlas Project (MAP) sub-national incidence connector.

MAP publishes modeled *Plasmodium falciparum* incidence-rate rasters
(per 1000 population, annual, ~5 km, 2000-present) via a GeoServer (WCS/WMS)
at https://data.malariaatlas.org . Coverage identifiers change with each MAP
release, so this module is parameterized rather than hard-coded.

Two access routes:
  1. LOCAL raster (robust, recommended): download a MAP GeoTIFF from the MAP
     portal, then compute zonal-mean incidence per admin unit here.
  2. WCS auto-download (best-effort): fetch a coverage by id + bbox.

Output uses the same tidy incidence schema as ``incidence.py`` so it joins
directly against model metrics in ``validation.py`` for sub-national validation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

# Defaults are placeholders; confirm the current coverage id via list_coverages()
# or the MAP data portal, then pass it in explicitly.
MAP_WCS_BASE = "https://data.malariaatlas.org/geoserver/ows"
MAP_PF_INCIDENCE_HINT = "Malaria__*_Global_Pf_Incidence_Rate"   # pattern to look for


def list_coverages(wcs_base: str = MAP_WCS_BASE, keyword: str = "Incidence") -> List[str]:
    """WCS GetCapabilities -> coverage ids matching a keyword (needs network)."""
    import requests
    import xml.etree.ElementTree as ET
    params = {"service": "WCS", "version": "2.0.1", "request": "GetCapabilities"}
    r = requests.get(wcs_base, params=params, timeout=90)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ids = [e.text for e in root.iter() if e.tag.endswith("CoverageId") and e.text]
    return [i for i in ids if keyword.lower() in i.lower()] or ids


def download_wcs_geotiff(coverage_id: str, bbox: tuple, out_path: str,
                         wcs_base: str = MAP_WCS_BASE) -> str:
    """Best-effort WCS 2.0.1 GetCoverage download. bbox = (minlon,minlat,maxlon,maxlat)."""
    import requests
    minx, miny, maxx, maxy = bbox
    params = {
        "service": "WCS", "version": "2.0.1", "request": "GetCoverage",
        "coverageId": coverage_id, "format": "image/geotiff",
        "subset": [f"Long({minx},{maxx})", f"Lat({miny},{maxy})"],
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with requests.get(wcs_base, params=params, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for c in r.iter_content(1 << 20):
                if c:
                    f.write(c)
    return out_path


def zonal_incidence_from_raster(raster_path: str, country: str, level: Optional[int],
                                cache_dir: str = "vectorrisk_cache",
                                disease: str = "malaria",
                                indicator: str = "MAP_PF_INCIDENCE_RATE",
                                year: Optional[int] = None) -> List[dict]:
    """Zonal-mean incidence per admin unit from a MAP GeoTIFF -> tidy rows.

    Rows: {unit, iso3, level, year, indicator, disease, value, unit_label, source}.
    Requires rasterio + geopandas and the GADM boundary cache.
    """
    import geopandas as gpd
    from .config import COUNTRIES, admin_name_col
    from .data import ensure_admin
    from .zonal import read_clip

    c = COUNTRIES[country]
    lvl = c.admin_level if level is None else level
    gj = ensure_admin(c.iso3, lvl, cache_dir)
    gdf = gpd.read_file(gj).to_crs("EPSG:4326")
    name_col = admin_name_col(gdf.columns, lvl)
    rows = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        try:
            arr, _, _ = read_clip(Path(raster_path), geom)
            val = float(np.nanmean(arr)) if np.isfinite(arr).any() else None
        except Exception:
            val = None
        rows.append(dict(unit=str(row.get(name_col, "?")), iso3=c.iso3, level=lvl,
                         year=year, indicator=indicator, disease=disease,
                         value=val, unit_label="per 1000 PAR", source="MAP raster"))
    return rows
