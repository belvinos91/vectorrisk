"""FastAPI backend for the VectorRisk console.

Endpoints
---------
GET  /health
GET  /config                      parameter ranges, resolutions, xc set
GET  /countries                   focus countries + metadata
GET  /climate?country&resolution  monthly zonal-mean T,R (falls back to
                                   representative climatology if geo/data absent)
GET  /metrics?country&month&xc&resolution   deterministic country readout
POST /montecarlo                  ensemble summary for a climate state
POST /girsanov                    finite-horizon reweighting + ESS
POST /simulate                    multi-year daily series (+ optional CSV)
GET  /admin?country&level         GADM sub-national polygons (GeoJSON)
GET  /choropleth?country&month&xc&resolution&level
                                  per-admin-unit metric FeatureCollection
POST /pipeline/country            heavy GeoTIFF batch (background-friendly)

Model / Monte Carlo / Girsanov / simulate endpoints need only numpy+scipy.
The geo endpoints lazily import rasterio/geopandas and return HTTP 503 with a
clear message if the stack or cached data is unavailable, so the API always
boots.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from . import config as C
from .model import compute_metrics
from .montecarlo import monte_carlo_point
from .girsanov import girsanov_validate
from .simulate import simulate_series

app = FastAPI(title="VectorRisk API", version="1.0.0",
              description="Stochastic mosquito-abundance risk backend.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

CACHE = "vectorrisk_cache"


# ----- request bodies ----------------------------------------------------
class MCBody(BaseModel):
    T: float; R: float
    xc: float = C.DEFAULT_XC
    n: int = Field(5000, ge=100, le=50000)
    ranges: Optional[Dict[str, List[float]]] = None


class GirBody(BaseModel):
    T: float = 26.0; R: float = 50.0
    xc: float = C.DEFAULT_XC
    lam: float = 0.15; u: float = 0.04; tau: float = 20.0
    n: int = Field(6000, ge=500, le=40000)


class SimBody(BaseModel):
    country: Optional[str] = None
    T: Optional[List[float]] = None
    R: Optional[List[float]] = None
    years: int = Field(4, ge=1, le=8)
    xc: float = C.DEFAULT_XC
    interp: str = "linear"
    every: int = 1


class PipeBody(BaseModel):
    country: str
    resolution: str = "10m"
    xc: float = C.DEFAULT_XC
    n: int = Field(10000, ge=500, le=20000)
    months: Optional[List[int]] = None


# ----- basic ------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}


@app.get("/config")
def get_config():
    return {"resolutions": C.RESOLUTIONS, "default_resolution": C.DEFAULT_RESOLUTION,
            "xc_set": list(C.XC_SET), "param_ranges": C.PARAM_RANGES,
            "central_params": C.central_params(), "months": list(C.MONTH_NAMES)}


@app.get("/countries")
def countries(region: str = Query(None), subsaharan_only: bool = Query(False)):
    names = C.filter_countries(region, subsaharan_only)
    return {name: {"iso3": c.iso3, "lat": c.lat, "lng": c.lng,
                   "region": c.region, "subsaharan": c.subsaharan,
                   "place": c.place, "admin_level": c.admin_level}
            for name, c in C.COUNTRIES.items() if name in names}


@app.get("/regions")
def regions():
    return {"regions": list(C.REGIONS)}


# ----- climate (real zonal means, fallback to representative) ------------
def _fallback_climate(country: str):
    fb = C.FALLBACK_CLIMATOLOGY.get(country)
    if fb is None:
        return {"country": country, "T": None, "R": None, "source": "pending",
                "detail": "No representative climate; run `vectorrisk fetch` and use live."}
    return {"country": country, "T": list(fb["T"]), "R": list(fb["R"]),
            "source": "fallback"}


@app.get("/climate")
def climate(country: str = Query(...),
            resolution: str = Query(C.DEFAULT_RESOLUTION),
            live: bool = Query(True), temp: str = Query("mean")):
    if country not in C.COUNTRIES:
        raise HTTPException(404, f"Unknown country '{country}'")
    if live:
        try:
            from .zonal import country_monthly_climatology
            return country_monthly_climatology(country, resolution, CACHE,
                                               C.temp_var_of(temp))
        except Exception as e:  # geo stack or data unavailable
            fb = _fallback_climate(country)
            fb["resolution"] = resolution
            fb["detail"] = str(e)
            return fb
    return _fallback_climate(country)


@app.get("/climate/all")
def climate_all(region: str = Query(None), subsaharan_only: bool = Query(False),
                resolution: str = Query(C.DEFAULT_RESOLUTION),
                live: bool = Query(True), temp: str = Query("mean")):
    """Climate for many countries at once (drives the multi-country dashboard)."""
    names = C.filter_countries(region, subsaharan_only)
    out = {}
    for name in names:
        try:
            out[name] = climate(name, resolution, live, temp)
        except Exception as e:
            out[name] = {"country": name, "T": None, "R": None,
                         "source": "error", "detail": str(e)}
    return {"resolution": resolution, "temp": temp, "count": len(out), "climate": out}


@app.get("/metrics")
def metrics(country: str = Query(...), month: int = Query(1, ge=1, le=12),
            xc: float = Query(C.DEFAULT_XC),
            resolution: str = Query(C.DEFAULT_RESOLUTION),
            live: bool = Query(True), temp: str = Query("mean"),
            vector: str = Query("Anopheles")):
    cl = climate(country, resolution, live, temp)
    from .diseases import params_for_vector
    p = params_for_vector(vector, C.central_params())
    if cl.get("T") is None or cl.get("R") is None:
        return {"country": country, "month": C.MONTH_NAMES[month - 1],
                "T": None, "R": None, "xc": xc,
                "climate_source": cl.get("source", "pending"),
                "metrics": None,
                "detail": cl.get("detail", "climate not available; fetch WorldClim first")}
    T, R = cl["T"][month - 1], cl["R"][month - 1]
    m = compute_metrics(T, R, p, xc)
    return {"country": country, "month": C.MONTH_NAMES[month - 1], "vector": vector,
            "T": T, "R": R, "xc": xc, "climate_source": cl.get("source", "live"),
            "metrics": {k: (float(v) if v is not None else None) for k, v in m.items()}}


# ----- compute-only endpoints (numpy/scipy) ------------------------------
@app.post("/montecarlo")
def montecarlo(body: MCBody):
    ranges = C.PARAM_RANGES
    if body.ranges:
        ranges = {**C.PARAM_RANGES, **{k: tuple(v) for k, v in body.ranges.items()}}
    return monte_carlo_point(body.T, body.R, body.xc, body.n, ranges)


@app.post("/girsanov")
def girsanov(body: GirBody):
    return girsanov_validate(body.T, body.R, body.xc, body.lam, body.u,
                             body.tau, body.n)


@app.post("/simulate")
def simulate(body: SimBody):
    if body.T and body.R:
        Tm, Rm = body.T, body.R
    elif body.country and body.country in C.FALLBACK_CLIMATOLOGY:
        # try live zonal climatology, else fallback
        cl = climate(body.country, C.DEFAULT_RESOLUTION, True)
        Tm, Rm = cl["T"], cl["R"]
    else:
        raise HTTPException(400, "Provide country or explicit T,R monthly arrays.")
    return simulate_series(Tm, Rm, None, body.years, body.xc, body.interp,
                           every=body.every)


# ----- geo endpoints (lazy; 503 if unavailable) --------------------------
@app.get("/admin")
def admin(country: str = Query(...), level: Optional[int] = None):
    if country not in C.COUNTRIES:
        raise HTTPException(404, f"Unknown country '{country}'")
    try:
        import geopandas as gpd
        from .data import ensure_admin
        c = C.COUNTRIES[country]
        lvl = c.admin_level if level is None else level
        gj = ensure_admin(c.iso3, lvl, CACHE)
        gdf = gpd.read_file(gj).to_crs("EPSG:4326")
        return gdf.__geo_interface__
    except Exception as e:
        raise HTTPException(503, f"Boundary data unavailable: {e}")


@app.get("/choropleth")
def choropleth(country: str = Query(...), month: int = Query(1, ge=1, le=12),
               xc: float = Query(C.DEFAULT_XC),
               resolution: str = Query(C.DEFAULT_RESOLUTION),
               level: Optional[int] = None, temp: str = Query("mean"),
               vector: str = Query("Anopheles")):
    try:
        from .zonal import admin_metric_featurecollection
        from .diseases import params_for_vector
        p = params_for_vector(vector, C.central_params())
        return admin_metric_featurecollection(country, month, xc, resolution,
                                              level, CACHE, params=p,
                                              temp_var=C.temp_var_of(temp))
    except Exception as e:
        raise HTTPException(503,
            f"Choropleth needs the geo stack + WorldClim/GADM cache: {e}")


@app.post("/pipeline/country")
def pipeline_country(body: PipeBody):
    try:
        from .pipeline import run_country_maps
        months = tuple(body.months) if body.months else C.MONTHS
        return run_country_maps(body.country, body.resolution, months,
                                body.xc, body.n, CACHE)
    except Exception as e:
        raise HTTPException(503, f"Pipeline unavailable: {e}")


# ======================================================================
# Serve the dashboard from the API itself, so one URL works for a donor.
# The injected snippet auto-connects the dashboard to this same origin.
# ======================================================================
_DASH = Path(__file__).resolve().parent.parent / "dashboard" / "vector_abundance_dashboard.html"
_AUTOCONNECT = """
<script>window.addEventListener('load',function(){var n=0,t=setInterval(function(){
var el=document.getElementById('apiUrl'),b=document.getElementById('apiConnect');
if((el&&b)|| ++n>40){clearInterval(t); if(el&&b){el.value=location.origin; b.click();}}},250);});</script>
"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    if _DASH.exists():
        html = _DASH.read_text(encoding="utf-8")
        return HTMLResponse(html.replace("</body>", _AUTOCONNECT + "</body>"))
    return HTMLResponse("<h2>VectorRisk API</h2><p>Dashboard file not bundled. "
                        "See <a href='/docs'>/docs</a>.</p>")


# ======================================================================
# Incidence ingestion (WHO GHO) + normalization + export
# ======================================================================
@app.get("/incidence/indicators")
def incidence_indicators(keyword: str = "malaria"):
    try:
        from .incidence import discover_indicators
        return {"indicators": discover_indicators(keyword, CACHE)}
    except Exception as e:
        from .incidence import GHO_INDICATORS
        return {"indicators": [], "detail": f"live discovery failed ({e}); "
                "known codes below", "known": GHO_INDICATORS}


@app.get("/incidence")
def incidence(indicator: str = Query("MALARIA_EST_INCIDENCE"),
              countries: str = Query("KEN,CMR,MOZ"),
              year_min: int = Query(2000), live: bool = Query(True),
              fmt: str = Query("json")):
    from .incidence import tidy_incidence, export_table
    iso = [c.strip() for c in countries.split(",") if c.strip()]
    rows = tidy_incidence(indicator, iso, year_min, CACHE, live)
    if fmt == "csv":
        import io, csv as _csv
        buf = io.StringIO()
        if rows:
            w = _csv.DictWriter(buf, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")
    return {"indicator": indicator, "count": len(rows),
            "source": rows[0]["source"] if rows else None, "rows": rows}


# ======================================================================
# Environmental data import -> model outputs
# ======================================================================
class ImportBody(BaseModel):
    csv: str | None = None
    units: dict | None = None      # {unit: {"T":[12], "R":[12]}}
    xc: float = C.DEFAULT_XC


@app.post("/import/climate")
def import_climate(body: ImportBody):
    from .envio import parse_climate_csv, metrics_table
    if body.csv:
        units = parse_climate_csv(body.csv)
    elif body.units:
        units = body.units
    else:
        raise HTTPException(400, "Provide 'csv' text or 'units' mapping.")
    if not units:
        raise HTTPException(400, "No units parsed. Expected columns unit,month,T,R "
                                 "or unit,T1..T12,R1..R12.")
    return metrics_table(units, body.xc)


# ======================================================================
# Validation: correlate model metrics with incidence over a panel
# ======================================================================
class CorrBody(BaseModel):
    panel: list | None = None        # rows with keys + climate {"T":[12],"R":[12]} OR precomputed features
    units: dict | None = None        # {key: {"T":[12],"R":[12], "iso3":..}}
    incidence: list | None = None    # rows: {<keys>, "value": float}
    keys: list = ["iso3"]
    use_builtin: bool = False


@app.post("/validate/correlation")
def validate_correlation(body: CorrBody):
    from .validation import build_panel, correlate
    from .incidence import tidy_incidence
    if body.use_builtin:
        units = {name: {"T": list(v["T"]), "R": list(v["R"]),
                        "iso3": C.COUNTRIES[name].iso3}
                 for name, v in C.FALLBACK_CLIMATOLOGY.items()}
        panel = build_panel(units)
        inc = [{"iso3": r["iso3"], "value": r["value"]}
               for r in tidy_incidence("MALARIA_EST_INCIDENCE",
                                       [c.iso3 for c in C.COUNTRIES.values()],
                                       live=True)]
        # collapse multi-year incidence to a mean per country for the demo
        agg = {}
        for r in inc:
            agg.setdefault(r["iso3"], []).append(r["value"])
        inc = [{"iso3": k, "value": sum(v) / len(v)} for k, v in agg.items()]
        out = correlate(panel, inc, keys=("iso3",))
        out["note_demo"] = ("Built-in demo uses 3 national points and climatology; "
                            "underpowered by design. Supply sub-national units for real validation.")
        return out
    if body.units is not None:
        panel = build_panel(body.units)
    elif body.panel is not None:
        panel = body.panel
    else:
        raise HTTPException(400, "Provide 'units', 'panel', or use_builtin=true.")
    if not body.incidence:
        raise HTTPException(400, "Provide 'incidence' rows with a 'value' field.")
    return correlate(panel, body.incidence, keys=tuple(body.keys))


# ======================================================================
# Sub-national incidence (Malaria Atlas Project raster) + validation
# ======================================================================
class SubIncBody(BaseModel):
    country: str
    level: int | None = None
    raster_path: str                 # a MAP GeoTIFF already on disk
    year: int | None = None
    disease: str = "malaria"


@app.post("/incidence/subnational/from-raster")
def incidence_subnational(body: SubIncBody):
    try:
        from .map_incidence import zonal_incidence_from_raster
        return {"rows": zonal_incidence_from_raster(
            body.raster_path, body.country, body.level, CACHE,
            disease=body.disease, year=body.year)}
    except Exception as e:
        raise HTTPException(503, f"Sub-national incidence needs geo stack + "
                                 f"a MAP raster + GADM cache: {e}")


class SubValBody(BaseModel):
    country: str
    month: int = 1
    xc: float = C.DEFAULT_XC
    resolution: str = C.DEFAULT_RESOLUTION
    level: int | None = None
    raster_path: str                 # MAP incidence GeoTIFF for the same country
    disease: str = "malaria"


@app.post("/validate/subnational")
def validate_subnational(body: SubValBody):
    """Correlate per-admin-unit model metrics with per-admin MAP incidence."""
    try:
        from .zonal import admin_metric_featurecollection
        from .map_incidence import zonal_incidence_from_raster
        from .validation import panel_from_featurecollection, correlate
        fc = admin_metric_featurecollection(body.country, body.month, body.xc,
                                            body.resolution, body.level, CACHE)
        panel = panel_from_featurecollection(fc)
        inc = zonal_incidence_from_raster(body.raster_path, body.country,
                                          body.level, CACHE, disease=body.disease)
        res = correlate(panel, inc, keys=("unit",),
                        feature_prefixes=("Lambda", "exceed", "stationary",
                                          "sigma", "persist"))
        res["country"] = body.country
        res["month"] = C.MONTH_NAMES[body.month - 1]
        res["units_scored"] = len(panel)
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Sub-national validation unavailable "
                                 f"(needs geo stack + WorldClim/GADM cache + MAP raster): {e}")


# ======================================================================
# Year-specific climate + space-time validation panel (the powered path)
# ======================================================================
@app.get("/climate/timeseries")
def climate_timeseries(country: str = Query(...), year: int = Query(...),
                       rainfall_source: str = Query("terraclimate")):
    if country not in C.COUNTRIES:
        raise HTTPException(404, f"Unknown country '{country}'")
    try:
        from .climate_ts import country_year_climate
        return country_year_climate(country, year, CACHE, rainfall_source)
    except Exception as e:
        raise HTTPException(503, f"Time-series climate needs the geo+ts stack "
                                 f"(xarray/rioxarray/netCDF4) and network: {e}")


class PanelBody(BaseModel):
    countries: list | None = None          # ISO3 names of focus countries (defaults to all)
    years: list                            # [start, end] or explicit list of years
    rainfall_source: str = "terraclimate"
    indicator: str = "MALARIA_EST_INCIDENCE"
    incidence: list | None = None          # optional override rows {iso3, year, value}


@app.post("/validate/panel")
def validate_panel(body: PanelBody):
    try:
        from .climate_ts import climate_fn_factory
        from .validation import build_spacetime_panel, correlate
        from .incidence import tidy_incidence
        names = body.countries or list(C.COUNTRIES)
        units = {n: {"iso3": C.COUNTRIES[n].iso3, "country": n} for n in names}
        yrs = body.years
        years = list(range(int(yrs[0]), int(yrs[1]) + 1)) if len(yrs) == 2 else [int(y) for y in yrs]
        fn = climate_fn_factory(CACHE, body.rainfall_source)
        panel = build_spacetime_panel(units, years, fn)
        if not panel:
            raise HTTPException(503, "No climate could be assembled for the requested "
                                     "country-years (check network / geo stack).")
        if body.incidence:
            inc = body.incidence
        else:
            inc = [{"iso3": r["iso3"], "year": r["year"], "value": r["value"]}
                   for r in tidy_incidence(body.indicator,
                                           [u["iso3"] for u in units.values()],
                                           year_min=min(years), cache_dir=CACHE, live=True)]
        res = correlate(panel, inc, keys=("iso3", "year"))
        res["panel_rows"] = len(panel)
        res["years"] = [years[0], years[-1]]
        res["indicator"] = body.indicator
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Panel validation unavailable "
                                 f"(needs geo+ts stack + WHO network): {e}")


# ======================================================================
# Sub-national x year panel — the fully powered validation
# ======================================================================
class SubPanelBody(BaseModel):
    country: str
    years: list                              # [start, end] or explicit list
    raster_template: str                     # e.g. "/data/map/pf_incidence_{year}.tif"
    level: int | None = None
    rainfall_source: str = "terraclimate"


@app.post("/validate/subnational-panel")
def validate_subnational_panel(body: SubPanelBody):
    try:
        from .panel_geo import subnational_panel
        from .validation import correlate
        yrs = body.years
        years = list(range(int(yrs[0]), int(yrs[1]) + 1)) if len(yrs) == 2 else [int(y) for y in yrs]
        panel, inc = subnational_panel(body.country, years, body.raster_template,
                                       body.level, CACHE, body.rainfall_source)
        if not panel:
            raise HTTPException(503, "No sub-national climate assembled (check geo/ts stack + network).")
        if not inc:
            raise HTTPException(503, "No incidence rasters matched the template for these years; "
                                     "check raster_template and file paths on the server.")
        res = correlate(panel, inc, keys=("unit", "year"),
                        feature_prefixes=("Lambda", "persist", "abundance", "exceed"))
        res["country"] = body.country
        res["years"] = [years[0], years[-1]]
        res["panel_rows"] = len(panel)
        res["units_scored"] = len({r["unit"] for r in panel})
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Sub-national panel unavailable "
                                 f"(needs geo+ts stack + GADM + TerraClimate + MAP rasters): {e}")


# ======================================================================
# Vector-borne disease & species reference (Africa-focused, corrected)
# ======================================================================
@app.get("/diseases")
def diseases(african_only: bool = Query(True)):
    from .diseases import list_diseases, VECTOR_GROUPS
    return {"vector_groups": VECTOR_GROUPS, "diseases": list_diseases(african_only)}


@app.get("/diseases/{name}")
def disease_detail(name: str):
    from .diseases import DISEASES
    if name not in DISEASES:
        raise HTTPException(404, f"Unknown disease '{name}'")
    return {"name": name, **DISEASES[name]}


# ======================================================================
# Sub-national validation from an uploaded MAP admin CSV (no rasters needed)
# ======================================================================
class SubCsvBody(BaseModel):
    country: str
    year: int
    incidence: list            # rows: {"unit": <admin name>, "value": <number>}
    level: int | None = None
    vector: str = "Anopheles"
    rainfall_source: str = "terraclimate"


@app.post("/validate/subnational-csv")
def validate_subnational_csv(body: SubCsvBody):
    """Validate per-admin-unit model metrics against per-unit incidence supplied
    from a Malaria Atlas Project admin-level CSV export."""
    try:
        from .panel_geo import subnational_panel_from_csv
        from .validation import correlate
        from .diseases import params_for_vector
        p = params_for_vector(body.vector, C.central_params())
        panel, inc, report = subnational_panel_from_csv(
            body.country, body.year, body.incidence, body.level,
            CACHE, body.rainfall_source, p)
        if report["matched"] < 3:
            return {"n": report["matched"], "results": [],
                    "warning": f"Only {report['matched']} admin units matched by name "
                               f"between the climate boundaries and your CSV. Check the "
                               f"admin level and country.", "match_report": report}
        res = correlate(panel, inc, keys=("unit_key",),
                        feature_prefixes=("Lambda", "persist", "abundance", "exceed"))
        res["country"] = body.country
        res["year"] = body.year
        res["units_scored"] = report["matched"]
        res["match_report"] = report
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Sub-national CSV validation unavailable "
                                 f"(needs geo+ts stack + boundaries + TerraClimate): {e}")
