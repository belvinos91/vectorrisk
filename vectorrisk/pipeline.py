"""Full-raster mapping pipeline: clip -> Monte Carlo -> GeoTIFF export.

This is the heavy, offline batch job (the manuscript's Africa-wide maps). It is
kept separate from the API's fast point/zonal endpoints. See README for the
resolution-vs-cost table before running Monte Carlo at 30 s (~1 km).
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

from .config import COUNTRIES, MONTHS
from .data import ensure_admin
from .montecarlo import monte_carlo_raster
from .zonal import load_month_clip, _gpd


def _write_geotiff(path: Path, arr: np.ndarray, meta: dict, nodata=-9999.0):
    import rasterio
    path.parent.mkdir(parents=True, exist_ok=True)
    out = arr.astype("float32").copy()
    out[~np.isfinite(out)] = nodata
    m = meta.copy()
    m.update(dtype="float32", count=1, nodata=nodata, compress="lzw")
    with rasterio.open(path, "w", **m) as dst:
        dst.write(out, 1)


def country_geometry(country: str, cache_dir: str):
    c = COUNTRIES[country]
    gj = ensure_admin(c.iso3, 0, cache_dir)
    gpd = _gpd()
    from .config import union_geometries
    return union_geometries(gpd.read_file(gj).to_crs("EPSG:4326"))


def run_country_maps(country: str, resolution: str = "10m",
                     months: Sequence[int] = MONTHS, xc: float = 500.0,
                     n: int = 10000, cache_dir: str = "vectorrisk_cache",
                     out_dir: str = "vectorrisk_outputs",
                     progress=None) -> dict:
    """Produce per-month GeoTIFFs of the principal uncertainty-averaged maps."""
    geom = country_geometry(country, cache_dir)
    written = []
    for month in months:
        T, R, transform, meta = load_month_clip(resolution, month, geom, cache_dir)
        maps = monte_carlo_raster(T, R, xc=xc, n=n, progress=progress)
        for metric, stat in maps.items():
            p = (Path(out_dir) / country / f"{resolution}"
                 / f"{metric}_mean_m{month:02d}.tif")
            _write_geotiff(p, stat["mean"], meta)
            written.append(str(p))
    return {"country": country, "resolution": resolution, "n": n,
            "files": written}
