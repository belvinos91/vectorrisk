"""Data acquisition & caching: WorldClim climate, Natural Earth + GADM boundaries.

Heavy dependencies (requests is light; rasterio/geopandas are used elsewhere)
are only touched when these functions run, so importing the package never
requires the geo stack.

Network is required the first time each artifact is fetched; everything is
cached under ``cache_dir`` and reused on subsequent runs, which is how the
"real-time / latest-on-run" behaviour works: delete the cache to force a
re-download of the newest published rasters.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import requests

from .config import (worldclim_url, gadm_url, NATURAL_EARTH_ADMIN0,
                     DEFAULT_RESOLUTION)


def _download(url: str, dest: Path, chunk: int = 1 << 20) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for c in r.iter_content(chunk):
                if c:
                    f.write(c)
    tmp.rename(dest)
    return dest


def _unzip(zip_path: Path, out_dir: Path) -> Path:
    marker = out_dir / ".unzipped"
    if marker.exists():
        return out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)
    marker.write_text("ok")
    return out_dir


# ---- WorldClim ----------------------------------------------------------
def ensure_worldclim(resolution: str = DEFAULT_RESOLUTION,
                     cache_dir: str = "vectorrisk_cache",
                     temp_var: str = "tavg") -> dict:
    """Download+extract WorldClim temperature (tavg|tmin|tmax) & prec. Returns dirs."""
    base = Path(cache_dir) / "worldclim" / resolution
    out = {}
    for var in (temp_var, "prec"):
        zp = base / f"wc2.1_{resolution}_{var}.zip"
        _download(worldclim_url(var, resolution), zp)
        out[var] = _unzip(zp, base / var)
    return out


def worldclim_month_path(var: str, month: int, resolution: str,
                         cache_dir: str = "vectorrisk_cache") -> Path:
    base = Path(cache_dir) / "worldclim" / resolution / var
    pattern = f"wc2.1_{resolution}_{var}_{month:02d}.tif"
    hits = list(base.rglob(pattern))
    if not hits:
        raise FileNotFoundError(
            f"{pattern} not found under {base}; run ensure_worldclim('{resolution}') first."
        )
    return hits[0]


# ---- boundaries ---------------------------------------------------------
def ensure_natural_earth(cache_dir: str = "vectorrisk_cache") -> Path:
    base = Path(cache_dir) / "naturalearth"
    zp = base / "ne_110m_admin_0_countries.zip"
    _download(NATURAL_EARTH_ADMIN0, zp)
    d = _unzip(zp, base / "countries")
    shp = list(d.glob("*.shp"))
    if not shp:
        raise FileNotFoundError("Natural Earth shapefile missing after extract.")
    return shp[0]


def ensure_gadm(iso3: str, level: int,
                cache_dir: str = "vectorrisk_cache") -> Path:
    """Download GADM 4.1 GeoJSON for a country/level. Returns the .json path."""
    base = Path(cache_dir) / "gadm"
    zp = base / f"gadm41_{iso3.upper()}_{level}.json.zip"
    _download(gadm_url(iso3, level), zp)
    d = _unzip(zp, base / f"{iso3.upper()}_{level}")
    js = list(d.glob("*.json"))
    if not js:
        raise FileNotFoundError(f"GADM json missing for {iso3} level {level}.")
    return js[0]


def ensure_geoboundaries(iso3: str, level: int,
                         cache_dir: str = "vectorrisk_cache") -> Path:
    """Download geoBoundaries gbOpen GeoJSON (CC BY 4.0; commercial OK)."""
    from .config import geoboundaries_meta_url
    dest = Path(cache_dir) / "geoboundaries" / f"{iso3.upper()}_ADM{level}.geojson"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    meta = requests.get(geoboundaries_meta_url(iso3, level), timeout=60).json()
    if isinstance(meta, list):
        meta = meta[0]
    url = meta.get("gjDownloadURL") or meta.get("staticDownloadLink")
    if not url:
        raise FileNotFoundError(f"geoBoundaries has no GeoJSON for {iso3} ADM{level}.")
    return _download(url, dest)


def ensure_admin(iso3: str, level: int, cache_dir: str = "vectorrisk_cache",
                 source: str | None = None) -> Path:
    """Boundary GeoJSON from the configured source (GADM or geoBoundaries)."""
    from .config import ADMIN_SOURCE
    src = source or ADMIN_SOURCE
    if src == "geoboundaries":
        return ensure_geoboundaries(iso3, level, cache_dir)
    return ensure_gadm(iso3, level, cache_dir)
