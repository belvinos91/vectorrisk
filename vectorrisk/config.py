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
    region: str = "East"          # North | West | Central | East | Southern
    place: str = ""
    admin_level: int = 1          # geoBoundaries/GADM level used as sub-national unit

    @property
    def subsaharan(self) -> bool:
        return self.region != "North"


REGIONS = ("North", "West", "Central", "East", "Southern")


def _c(name, iso3, lat, lng, region, place="", admin=1):
    return Country(name, iso3, lat, lng, region, place, admin)


COUNTRIES: Dict[str, Country] = {c.name: c for c in [
    # --- North Africa (not sub-Saharan) ---
    _c("Algeria", "DZA", 28.03, 1.66, "North"),
    _c("Egypt", "EGY", 26.82, 30.80, "North"),
    _c("Libya", "LBY", 26.34, 17.23, "North"),
    _c("Morocco", "MAR", 31.79, -7.09, "North"),
    _c("Sudan", "SDN", 12.86, 30.22, "North"),
    _c("Tunisia", "TUN", 33.89, 9.54, "North"),
    # --- West Africa ---
    _c("Benin", "BEN", 9.31, 2.32, "West"),
    _c("Burkina Faso", "BFA", 12.24, -1.56, "West"),
    _c("Cabo Verde", "CPV", 16.00, -24.01, "West"),
    _c("Cote d'Ivoire", "CIV", 7.54, -5.55, "West"),
    _c("Gambia", "GMB", 13.44, -15.31, "West"),
    _c("Ghana", "GHA", 7.95, -1.02, "West"),
    _c("Guinea", "GIN", 9.95, -9.70, "West"),
    _c("Guinea-Bissau", "GNB", 11.80, -15.18, "West"),
    _c("Liberia", "LBR", 6.43, -9.43, "West"),
    _c("Mali", "MLI", 17.57, -4.00, "West"),
    _c("Mauritania", "MRT", 21.01, -10.94, "West"),
    _c("Niger", "NER", 17.61, 8.08, "West"),
    _c("Nigeria", "NGA", 9.08, 8.68, "West"),
    _c("Senegal", "SEN", 14.50, -14.45, "West"),
    _c("Sierra Leone", "SLE", 8.46, -11.78, "West"),
    _c("Togo", "TGO", 8.62, 0.82, "West"),
    # --- Central Africa ---
    _c("Angola", "AGO", -11.20, 17.87, "Central"),
    _c("Cameroon", "CMR", 3.87, 11.52, "Central", "Central plateau (Yaounde)", 2),
    _c("Central African Republic", "CAF", 6.61, 20.94, "Central"),
    _c("Chad", "TCD", 15.45, 18.73, "Central"),
    _c("Congo", "COG", -0.23, 15.83, "Central"),
    _c("DR Congo", "COD", -4.04, 21.76, "Central"),
    _c("Equatorial Guinea", "GNQ", 1.65, 10.27, "Central"),
    _c("Gabon", "GAB", -0.80, 11.61, "Central"),
    _c("Sao Tome and Principe", "STP", 0.19, 6.61, "Central"),
    # --- East Africa ---
    _c("Burundi", "BDI", -3.37, 29.92, "East"),
    _c("Comoros", "COM", -11.65, 43.33, "East"),
    _c("Djibouti", "DJI", 11.83, 42.59, "East"),
    _c("Eritrea", "ERI", 15.18, 39.78, "East"),
    _c("Ethiopia", "ETH", 9.15, 40.49, "East"),
    _c("Kenya", "KEN", -0.10, 34.75, "East", "Lake Victoria basin (west)", 2),
    _c("Madagascar", "MDG", -18.77, 46.87, "East"),
    _c("Malawi", "MWI", -13.25, 34.30, "East"),
    _c("Mauritius", "MUS", -20.35, 57.55, "East"),
    _c("Mozambique", "MOZ", -19.84, 34.84, "East", "Central coast (Beira)", 2),
    _c("Rwanda", "RWA", -1.94, 29.87, "East"),
    _c("Seychelles", "SYC", -4.68, 55.49, "East"),
    _c("Somalia", "SOM", 5.15, 46.20, "East"),
    _c("South Sudan", "SSD", 6.88, 31.31, "East"),
    _c("Tanzania", "TZA", -6.37, 34.89, "East"),
    _c("Uganda", "UGA", 1.37, 32.29, "East"),
    _c("Zambia", "ZMB", -13.13, 27.85, "East"),
    _c("Zimbabwe", "ZWE", -19.02, 29.15, "East"),
    # --- Southern Africa ---
    _c("Botswana", "BWA", -22.33, 24.68, "Southern"),
    _c("Eswatini", "SWZ", -26.52, 31.47, "Southern"),
    _c("Lesotho", "LSO", -29.61, 28.23, "Southern"),
    _c("Namibia", "NAM", -22.96, 18.49, "Southern"),
    _c("South Africa", "ZAF", -30.56, 22.94, "Southern"),
]}


def filter_countries(region: str = None, subsaharan_only: bool = False):
    """Country names filtered by region and/or sub-Saharan flag."""
    out = []
    for name, c in COUNTRIES.items():
        if region and region not in ("All", "all") and c.region != region:
            continue
        if subsaharan_only and not c.subsaharan:
            continue
        out.append(name)
    return out

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
