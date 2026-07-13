"""Sub-national x year validation panel — the end-state, most-powered design.

For one country, a set of admin units (GADM), and a set of years it builds:
  * per (unit, year): year-specific monthly zonal-mean T,R (TerraClimate/CHIRPS)
    -> annual model summary features;
  * per (unit, year): zonal-mean incidence from that year's MAP raster.
Both are computed from the SAME GADM polygons so unit names join exactly.

Turning 3 countries into thousands of (unit x year) observations is what makes
the correlation statistically convincing. It is also the heaviest job in the
package: one TerraClimate open per variable per year and one MAP raster per year,
each clipped to every admin unit. Lazy geo/ts imports keep the rest of the
package light.

MAP rasters are supplied by the user via a path template, e.g.
    raster_template = "/data/map/pf_incidence_{year}.tif"
(download per-year Pf incidence-rate GeoTIFFs from the Malaria Atlas Project).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


def _load_admin(country: str, level: Optional[int], cache_dir: str):
    import geopandas as gpd
    from .config import COUNTRIES, admin_name_col
    from .data import ensure_admin
    c = COUNTRIES[country]
    lvl = c.admin_level if level is None else level
    gj = ensure_admin(c.iso3, lvl, cache_dir)
    gdf = gpd.read_file(gj).to_crs("EPSG:4326")
    name_col = admin_name_col(gdf.columns, lvl)
    return gdf, name_col, lvl, c.iso3


def _year_climate_by_unit(gdf, name_col, year: int, bbox,
                          rainfall_source: str, cache_dir: str
                          ) -> Dict[str, Dict[str, list]]:
    """{unit: {'T':[12],'R':[12]}} for one year, opening each dataset once."""
    from .climate_ts import _terraclimate_zonal12  # reuse single-geom clipper
    import xarray as xr
    import rioxarray  # noqa
    from .config import terraclimate_opendap
    minx, miny, maxx, maxy = bbox

    def open_da(var):
        ds = xr.open_dataset(terraclimate_opendap(var, year))
        da = ds[var].sel(lat=slice(maxy + 0.5, miny - 0.5), lon=slice(minx - 0.5, maxx + 0.5))
        return da.rio.set_spatial_dims(x_dim="lon", y_dim="lat").rio.write_crs("EPSG:4326")

    tmax, tmin = open_da("tmax"), open_da("tmin")
    ppt = None if rainfall_source == "chirps" else open_da("ppt")

    def clip12(da, geom):
        c = da.rio.clip([geom.__geo_interface__], "EPSG:4326", drop=True, all_touched=True)
        return np.asarray(c.mean(dim=("lat", "lon"), skipna=True).values, dtype="float64").reshape(-1)[:12]

    out: Dict[str, Dict[str, list]] = {}
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        try:
            T = (clip12(tmax, geom) + clip12(tmin, geom)) / 2.0
            R = clip12(ppt, geom) if ppt is not None else _chirps_unit(geom, year, cache_dir)
            out[str(row[name_col])] = {"T": [float(x) for x in T], "R": [float(x) for x in R]}
        except Exception:
            continue
    return out


def _chirps_unit(geom, year: int, cache_dir: str) -> np.ndarray:
    from .climate_ts import _chirps_zonal12
    return _chirps_zonal12(year, geom, cache_dir)


def _incidence_by_unit(gdf, name_col, iso3, year: int, raster_path: str) -> List[dict]:
    from .zonal import read_clip
    rows = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        try:
            arr, _, _ = read_clip(Path(raster_path), geom)
            arr = np.where(arr < 0, np.nan, arr)
            val = float(np.nanmean(arr)) if np.isfinite(arr).any() else None
        except Exception:
            val = None
        rows.append({"unit": str(row[name_col]), "iso3": iso3, "year": year, "value": val})
    return rows


def subnational_panel(country: str, years: Sequence[int], raster_template: str,
                      level: Optional[int] = None, cache_dir: str = "vectorrisk_cache",
                      rainfall_source: str = "terraclimate", params=None,
                      progress=None) -> Tuple[List[dict], List[dict]]:
    """Return (panel_rows, incidence_rows) keyed by (unit, year)."""
    from .validation import annual_summary
    gdf, name_col, lvl, iso3 = _load_admin(country, level, cache_dir)
    bbox = tuple(gdf.total_bounds)
    panel, incidence = [], []
    for i, yr in enumerate(years):
        clim = _year_climate_by_unit(gdf, name_col, yr, bbox, rainfall_source, cache_dir)
        for unit, cl in clim.items():
            s = annual_summary(cl["T"], cl["R"], params=params)
            panel.append({"unit": unit, "iso3": iso3, "year": int(yr), **s})
        rp = raster_template.format(year=yr)
        if Path(rp).exists():
            incidence.extend(_incidence_by_unit(gdf, name_col, iso3, yr, rp))
        if progress:
            progress((i + 1) / len(years))
    return panel, incidence
