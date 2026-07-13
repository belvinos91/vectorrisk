"""Year-specific monthly climate for validation panels.

Unlike WorldClim (a 1970-2000 average), these are time series, so you can pair
year Y climate with year Y incidence:

  * TerraClimate (default): monthly ppt/tmax/tmin, 1958-present, ~4 km, no auth.
    Accessed via OPeNDAP so only the Africa/country subset is transferred, not
    the global file.
  * CHIRPS (optional): monthly rainfall, 1981-present, ~5 km, higher-resolution
    rainfall override.

``country_year_climate`` returns national zonal-mean {T:[12], R:[12]} for one
year; ``climate_fn_factory`` yields a cached ``fn(country, year)`` for the panel
builder. Needs xarray + rioxarray + netCDF4 (install ``.[ts]``).
"""
from __future__ import annotations

import gzip
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

from .config import (COUNTRIES, terraclimate_opendap, chirps_month_url)


def _country_geom(country: str, cache_dir: str):
    import geopandas as gpd
    from .data import ensure_admin
    from .config import union_geometries
    c = COUNTRIES[country]
    gj = ensure_admin(c.iso3, 0, cache_dir)
    g = gpd.read_file(gj).to_crs("EPSG:4326")
    return union_geometries(g), tuple(g.total_bounds)  # (minx,miny,maxx,maxy)


def _terraclimate_zonal12(var: str, year: int, geom, bbox) -> np.ndarray:
    """12 monthly zonal means of a TerraClimate variable inside geom."""
    import xarray as xr
    import rioxarray  # noqa: registers .rio accessor
    minx, miny, maxx, maxy = bbox
    ds = xr.open_dataset(terraclimate_opendap(var, year))
    da = ds[var]
    # TerraClimate latitude is descending; slice north->south
    da = da.sel(lat=slice(maxy + 0.5, miny - 0.5), lon=slice(minx - 0.5, maxx + 0.5))
    da = da.rio.set_spatial_dims(x_dim="lon", y_dim="lat").rio.write_crs("EPSG:4326")
    clipped = da.rio.clip([geom.__geo_interface__], "EPSG:4326",
                          drop=True, all_touched=True)
    vals = clipped.mean(dim=("lat", "lon"), skipna=True).values
    return np.asarray(vals, dtype="float64").reshape(-1)[:12]


def _chirps_zonal12(year: int, geom, cache_dir: str) -> np.ndarray:
    """12 monthly CHIRPS rainfall zonal means (downloads+gunzips per month)."""
    from .data import _download
    from .zonal import read_clip
    out = np.full(12, np.nan)
    base = Path(cache_dir) / "chirps" / str(year)
    for m in range(1, 13):
        gz = base / f"chirps-v2.0.{year}.{m:02d}.tif.gz"
        tif = gz.with_suffix("")
        if not tif.exists():
            _download(chirps_month_url(year, m), gz)
            with gzip.open(gz, "rb") as fi, open(tif, "wb") as fo:
                shutil.copyfileobj(fi, fo)
        arr, _, _ = read_clip(tif, geom)
        arr = np.where(arr < 0, np.nan, arr)   # CHIRPS nodata = -9999
        out[m - 1] = float(np.nanmean(arr)) if np.isfinite(arr).any() else np.nan
    return out


def country_year_climate(country: str, year: int, cache_dir: str = "vectorrisk_cache",
                         rainfall_source: str = "terraclimate"
                         ) -> Dict[str, list]:
    """National zonal-mean monthly T (deg C) and R (mm) for a given year."""
    geom, bbox = _country_geom(country, cache_dir)
    tmax = _terraclimate_zonal12("tmax", year, geom, bbox)
    tmin = _terraclimate_zonal12("tmin", year, geom, bbox)
    T = (tmax + tmin) / 2.0
    if rainfall_source == "chirps":
        R = _chirps_zonal12(year, geom, cache_dir)
    else:
        R = _terraclimate_zonal12("ppt", year, geom, bbox)
    return {"country": country, "year": year,
            "T": [round(float(x), 2) for x in T],
            "R": [round(float(x), 1) for x in R],
            "source": f"TerraClimate (T){' + CHIRPS (R)' if rainfall_source=='chirps' else ' + TerraClimate (R)'}"}


def climate_fn_factory(cache_dir: str = "vectorrisk_cache",
                       rainfall_source: str = "terraclimate"):
    """Return a cached fn(country, year) -> (T[12], R[12]) or None on failure."""
    @lru_cache(maxsize=4096)
    def fn(country: str, year: int) -> Optional[Tuple[tuple, tuple]]:
        try:
            cl = country_year_climate(country, year, cache_dir, rainfall_source)
            if not np.isfinite(cl["T"]).any() or not np.isfinite(cl["R"]).any():
                return None
            return tuple(cl["T"]), tuple(cl["R"])
        except Exception:
            return None
    return fn
