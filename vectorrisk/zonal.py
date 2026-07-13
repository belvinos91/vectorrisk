"""Raster clipping and zonal statistics (rasterio + geopandas, imported lazily).

The key sub-national capability lives here: ``admin_metric_featurecollection``
computes, for every admin unit (e.g. Kenyan sub-county) the zonal-mean
temperature and rainfall from the (up to 1 km) WorldClim raster, runs the model
on those means, and returns a GeoJSON FeatureCollection ready to drop into a
Leaflet choropleth.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np

from .config import COUNTRIES, MONTH_NAMES, central_params, admin_name_col, union_geometries
from .data import (ensure_worldclim, worldclim_month_path, ensure_admin,
                   ensure_natural_earth)
from .model import compute_metrics


def _rio():
    import rasterio                      # noqa
    from rasterio.mask import mask
    return rasterio, mask


def _gpd():
    import geopandas as gpd              # noqa
    return gpd


def _scale_TR(T, R):
    T = T.astype("float64")
    R = R.astype("float64")
    if np.nanmedian(T) > 80:            # some builds store deg*10
        T = T / 10.0
    R[R < 0] = np.nan
    return T, R


def read_clip(path: Path, geom):
    """Return (array, transform, meta) clipped to a shapely geometry."""
    rasterio, mask = _rio()
    with rasterio.open(path) as src:
        arr, transform = mask(src, [geom], crop=True, filled=True, nodata=src.nodata)
        meta = src.meta.copy()
        nod = src.nodata
    a = arr[0].astype("float64")
    if nod is not None:
        a[a == nod] = np.nan
    meta.update(height=a.shape[0], width=a.shape[1], transform=transform,
                count=1, dtype="float32", crs="EPSG:4326")
    return a, transform, meta


def load_month_clip(resolution: str, month: int, geom, cache_dir: str):
    ensure_worldclim(resolution, cache_dir)
    tp = worldclim_month_path("tavg", month, resolution, cache_dir)
    rp = worldclim_month_path("prec", month, resolution, cache_dir)
    T, transform, meta = read_clip(tp, geom)
    R, _, _ = read_clip(rp, geom)
    T, R = _scale_TR(T, R)
    return T, R, transform, meta


def zonal_mean_TR(path_t: Path, path_r: Path, geom):
    """Area-mean T and R inside one geometry (nan-safe)."""
    T, _, _ = read_clip(path_t, geom)
    R, _, _ = read_clip(path_r, geom)
    T, R = _scale_TR(T, R)
    return (float(np.nanmean(T)) if np.isfinite(T).any() else float("nan"),
            float(np.nanmean(R)) if np.isfinite(R).any() else float("nan"))


def country_monthly_climatology(country: str, resolution: str,
                                 cache_dir: str, temp_var: str = "tavg") -> Dict[str, list]:
    """Zonal-mean monthly T,R for a whole country. temp_var in tavg|tmin|tmax."""
    c = COUNTRIES[country]
    gj = ensure_admin(c.iso3, 0, cache_dir)          # admin-0 outline
    gpd = _gpd()
    geom = union_geometries(gpd.read_file(gj).to_crs("EPSG:4326"))
    ensure_worldclim(resolution, cache_dir, temp_var)
    T, R = [], []
    for m in range(1, 13):
        tp = worldclim_month_path(temp_var, m, resolution, cache_dir)
        rp = worldclim_month_path("prec", m, resolution, cache_dir)
        t, r = zonal_mean_TR(tp, rp, geom)
        T.append(round(t, 2) if np.isfinite(t) else None)
        R.append(round(r, 1) if np.isfinite(r) else None)
    return {"country": country, "resolution": resolution, "temp_var": temp_var, "T": T, "R": R}


def admin_metric_featurecollection(country: str, month: int, xc: float,
                                   resolution: str, level: int | None,
                                   cache_dir: str,
                                   params=None, temp_var: str = "tavg") -> dict:
    """Per-admin-unit choropleth: zonal-mean climate -> model -> GeoJSON."""
    c = COUNTRIES[country]
    lvl = c.admin_level if level is None else level
    gj = ensure_admin(c.iso3, lvl, cache_dir)
    gpd = _gpd()
    gdf = gpd.read_file(gj).to_crs("EPSG:4326")
    ensure_worldclim(resolution, cache_dir, temp_var)
    tp = worldclim_month_path(temp_var, month, resolution, cache_dir)
    rp = worldclim_month_path("prec", month, resolution, cache_dir)
    p = central_params() if params is None else params
    name_col = admin_name_col(gdf.columns, lvl)

    def _safe(x):
        try:
            xf = float(x)
            return xf if np.isfinite(xf) else None
        except (TypeError, ValueError):
            return None

    feats = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        try:
            T, R = zonal_mean_TR(tp, rp, geom)
        except Exception:
            T = R = float("nan")
        m = compute_metrics(T, R, p, xc) if np.isfinite(T) and np.isfinite(R) else None
        props = {"unit": str(row.get(name_col, "?")), "level": lvl,
                 "month": MONTH_NAMES[month - 1], "T_C": _safe(T), "R_mm": _safe(R)}
        if m:
            props.update({k: _safe(m[k]) for k in
                          ("Lambda", "exceed", "stationary_mean", "sigma", "persist")})
        feats.append({"type": "Feature",
                      "geometry": geom.__geo_interface__,
                      "properties": props})
    return {"type": "FeatureCollection", "country": country, "level": lvl,
            "features": feats}
