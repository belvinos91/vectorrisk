"""Configuration: resolutions, data URLs, focus countries, parameter ranges.

Nothing in this module imports the heavy geo stack, so it is safe to import
anywhere (the model and Monte Carlo layers depend only on numpy/scipy).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# Resolutions.  WorldClim v2.1 "30s" is ~1 km at the equator ("1km").
# ---------------------------------------------------------------------------
RESOLUTIONS: Dict[str, str] = {
    "10m": "~18 km  (fast, whole-continent Monte Carlo)",
    "5m": "~9 km",
    "2.5m": "~4.5 km",
    "30s": "~1 km   (highest; heavy — use for zonal stats / deterministic maps)",
}
DEFAULT_RESOLUTION = "10m"

WORLDCLIM_BASE = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base"
NATURAL_EARTH_ADMIN0 = (
    "https://naturalearth.s3.amazonaws.com/110m_cultural/"
    "ne_110m_admin_0_countries.zip"
)
# GADM 4.1 per-country GeoJSON (admin levels 0/1/2).  ~1 file per country.
GADM_JSON_BASE = "https://geodata.ucdavis.edu/gadm/gadm4.1/json"


def worldclim_url(var: str, resolution: str) -> str:
    """var in {'tavg','prec'}; resolution key of RESOLUTIONS."""
    return f"{WORLDCLIM_BASE}/wc2.1_{resolution}_{var}.zip"


def gadm_url(iso3: str, level: int) -> str:
    return f"{GADM_JSON_BASE}/gadm41_{iso3.upper()}_{level}.json.zip"


# --- year-specific (time-series) climate sources, for validation panels ---
# TerraClimate: monthly ppt/tmax/tmin, 1958-present, ~4 km, no auth. OPeNDAP lets
# us subset to Africa without downloading the global file. NOTE the :8080 port and
# the #fillmismatch suffix (required for cloud netCDF access, per NKN THREDDS).
TERRACLIMATE_OPENDAP = ("http://thredds.northwestknowledge.net:8080/thredds/dodsC/"
                        "TERRACLIMATE_ALL/data")
# HTTPS direct-download fallback host (whole-year global file):
TERRACLIMATE_HTTP = "https://climate.northwestknowledge.net/TERRACLIMATE-DATA"
# CHIRPS: monthly rainfall, 1981-present, ~5 km (optional higher-res rainfall).
CHIRPS_MONTHLY_BASE = ("https://data.chc.ucsb.edu/products/CHIRPS-2.0/"
                       "global_monthly/tifs")


def terraclimate_opendap(var: str, year: int) -> str:
    return f"{TERRACLIMATE_OPENDAP}/TerraClimate_{var}_{year}.nc#fillmismatch"


def chirps_month_url(year: int, month: int) -> str:
    return f"{CHIRPS_MONTHLY_BASE}/chirps-v2.0.{year}.{month:02d}.tif.gz"


# --- administrative boundaries -------------------------------------------
# GADM is NON-COMMERCIAL only. geoBoundaries "gbOpen" is CC BY 4.0 and allows
# commercial use with attribution -- switch ADMIN_SOURCE to "geoboundaries" for
# a product you intend to sell.
ADMIN_SOURCE = "gadm"          # "gadm" (non-commercial) | "geoboundaries" (CC BY 4.0)
GEOBOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen"


def geoboundaries_meta_url(iso3: str, level: int) -> str:
    return f"{GEOBOUNDARIES_API}/{iso3.upper()}/ADM{level}/"


def admin_name_col(columns, level: int) -> str:
    """Pick the unit-name column across GADM and geoBoundaries schemas."""
    for c in (f"NAME_{level}", "NAME_2", "NAME_1", "NAME_0",
              "shapeName", "shapename", "NAME"):
        if c in columns:
            return c
    return list(columns)[0]


def union_geometries(gdf):
    """union_all() (geopandas>=0.14) with unary_union fallback."""
    try:
        return gdf.geometry.union_all()
    except Exception:
        return gdf.geometry.unary_union


# Source licences (surfaced by `vectorrisk check`; verify before commercial use).
SOURCE_LICENSES = {
    "WorldClim 2.1": "Free to use with citation (Fick & Hijmans 2017).",
    "GADM 4.1": "NON-COMMERCIAL only; commercial use needs permission.",
    "geoBoundaries (gbOpen)": "CC BY 4.0 - commercial OK with attribution.",
    "Natural Earth": "Public domain.",
    "CHIRPS": "Public domain (UCSB/USGS).",
    "TerraClimate": "Free to use with citation (Abatzoglou et al. 2018).",
    "WHO GHO": "Free/open; follow WHO data use terms.",
    "Malaria Atlas Project": "CC BY - check current terms.",
}


# ---------------------------------------------------------------------------
# Focus countries.  Adding a country is one entry here (+ optional climatology).
# admin_level: which GADM level to treat as the "sub-national" unit.
#   Kenya:      ADM1 = counties, ADM2 = sub-counties
#   Mozambique: ADM2 = districts
#   Cameroon:   ADM2 = departments / arrondissements
# ---------------------------------------------------------------------------
@dataclass
class Country:
    name: str
    iso3: str
    lat: float
    lng: float
    place: str
    admin_level: int = 2


COUNTRIES: Dict[str, Country] = {
    "Kenya": Country("Kenya", "KEN", -0.10, 34.75, "Lake Victoria basin (west)", 2),
    "Cameroon": Country("Cameroon", "CMR", 3.87, 11.52, "Central plateau (Yaoundé)", 2),
    "Mozambique": Country("Mozambique", "MOZ", -19.84, 34.84, "Central coast (Beira)", 2),
}

MONTHS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

XC_SET = (250, 500, 700, 1000, 1250, 1500)
DEFAULT_XC = 500
DEFAULT_SEED = 20260611

# ---------------------------------------------------------------------------
# Parameter ranges (manuscript Table 2).  Central values = midpoints.
# ---------------------------------------------------------------------------
PARAM_RANGES: Dict[str, Tuple[float, float]] = {
    "beta_E": (60.0, 160.0), "rho": (0.035, 0.090),
    "pE_max": (0.65, 0.95), "pL_max": (0.55, 0.90), "pP_max": (0.70, 0.98),
    "T_E_opt": (24.0, 29.0), "T_L_opt": (24.0, 30.0), "T_P_opt": (24.0, 30.0),
    "w_E": (5.0, 8.0), "w_L": (5.0, 8.0), "w_P": (5.0, 8.0),
    "R_L": (180.0, 320.0), "c1": (0.035, 0.070), "c2": (0.00, 0.25),
    "Lmax": (14.0, 28.0), "q_delta": (0.035, 0.090),
    "T_delta_opt": (24.0, 28.0), "L_min": (1.5, 3.0),
    "K_min": (20.0, 100.0), "K_max": (1200.0, 6000.0),
    "T_K_opt": (24.0, 29.0), "omega_T": (5.0, 8.0),
    "sigma0": (0.08, 0.22), "sigma_T": (0.005, 0.050),
    "sigma_R": (0.005, 0.060), "sigma_max": (0.45, 0.75),
}


def central_params() -> Dict[str, float]:
    return {k: 0.5 * (lo + hi) for k, (lo, hi) in PARAM_RANGES.items()}


# Representative monthly climatology used as an OFFLINE FALLBACK only.
# When the geo stack + network are available the pipeline replaces these with
# zonal means extracted from the real WorldClim rasters.
FALLBACK_CLIMATOLOGY: Dict[str, Dict[str, Tuple[float, ...]]] = {
    "Kenya": {
        "T": (23, 23.5, 23.5, 23, 22.5, 22, 21.5, 22, 23, 23.5, 23, 22.5),
        "R": (60, 80, 150, 200, 160, 90, 70, 80, 90, 110, 150, 100),
    },
    "Cameroon": {
        "T": (24, 25, 25, 25, 24.5, 24, 23.5, 23.5, 24, 24, 24, 24),
        "R": (20, 50, 140, 170, 200, 160, 80, 100, 250, 290, 120, 30),
    },
    "Mozambique": {
        "T": (27, 27, 26.5, 25, 23, 21, 21, 22, 24, 25.5, 26.5, 27),
        "R": (220, 200, 150, 60, 35, 30, 25, 25, 30, 60, 120, 180),
    },
}


@dataclass
class Config:
    cache_dir: str = "vectorrisk_cache"
    resolution: str = DEFAULT_RESOLUTION
    seed: int = DEFAULT_SEED
    n_sims: int = 10000
    xc: float = DEFAULT_XC
    eps: float = 1e-9
    nodata: float = -9999.0
    months: Tuple[int, ...] = MONTHS
    exclude_north_africa: bool = True
