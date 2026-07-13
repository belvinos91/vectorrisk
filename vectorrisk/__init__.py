"""VectorRisk — stochastic mosquito-abundance risk toolkit.

The model / Monte Carlo / Girsanov / simulation layers need only numpy + scipy.
Geo (rasterio, geopandas) and the API (fastapi) are optional extras imported
lazily, so ``import vectorrisk`` always works.
"""
from __future__ import annotations

from . import config
from .config import (COUNTRIES, PARAM_RANGES, central_params, MONTH_NAMES,
                     RESOLUTIONS, XC_SET, Config)
from .model import compute_metrics
from .montecarlo import monte_carlo_point, monte_carlo_raster, sample_params
from .girsanov import girsanov_validate, gamma_pdf, gamma_params
from .simulate import simulate_series

__version__ = "1.0.0"

__all__ = [
    "config", "Config", "COUNTRIES", "PARAM_RANGES", "central_params",
    "MONTH_NAMES", "RESOLUTIONS", "XC_SET",
    "compute_metrics", "monte_carlo_point", "monte_carlo_raster",
    "sample_params", "girsanov_validate", "gamma_pdf", "gamma_params",
    "simulate_series",
]
