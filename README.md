# VectorRisk

Stochastic temperature–rainfall **mosquito-abundance risk** toolkit, API, and
data pipeline — the backend for the VectorRisk console.

It implements the manuscript model exactly: recruitment `r(T,R)`, mortality
`δ(T)`, carrying capacity `K(T,R)`, climate-stress volatility `σ(T,R)`, the
persistence index `Λ = a − ½σ²`, the closed-form **stationary Gamma law**,
threshold exceedance `P(X>x_c)`, finite-horizon **Girsanov** reweighting, and
multi-year daily simulation. Real climate comes from **WorldClim v2.1** (down to
**30 s ≈ 1 km**) and sub-national units from **GADM** (e.g. Kenyan sub-counties).

> Outputs are a relative **abundance-risk index**, not mosquito counts and not
> malaria/dengue incidence.

## Install

```bash
pip install -e .            # core: model, Monte Carlo, Girsanov, simulation (numpy+scipy)
pip install -e ".[api]"     # + FastAPI backend
pip install -e ".[geo]"     # + real WorldClim / GADM ingestion (rasterio, geopandas)
pip install -e ".[full]"    # everything (recommended for the live dashboard)
```

`rasterio`/`geopandas` pull in GDAL. If pip struggles, use conda:
`conda install -c conda-forge rasterio geopandas`.

## Quick start

```bash
# 1. cache climate (1 km) + boundaries for the three focus countries
vectorrisk fetch --resolution 30s

# 2. run the API
vectorrisk serve --port 8000        # http://127.0.0.1:8000/docs

# 3. one-off metrics for a climate state
vectorrisk metrics 27 150 --xc 500

# 4. GeoTIFF maps for a country (heavy; see cost table)
vectorrisk maps Kenya --resolution 10m --n 10000
```

Python:

```python
import vectorrisk as vr
vr.compute_metrics(27, 150, xc=500)                 # deterministic
vr.monte_carlo_point(27, 150, xc=500, n=5000)       # ensemble
vr.girsanov_validate(26, 50, lam=0.15, u=0.04)      # change of measure
vr.simulate_series(vr.config.FALLBACK_CLIMATOLOGY["Kenya"]["T"],
                   vr.config.FALLBACK_CLIMATOLOGY["Kenya"]["R"], years=8)
```

## API endpoints

| Method | Path | Purpose | Needs geo stack |
|---|---|---|---|
| GET | `/health`, `/config`, `/countries` | metadata | no |
| GET | `/climate?country&resolution` | monthly zonal-mean T,R (1 km) | falls back if absent |
| GET | `/metrics?country&month&xc&resolution` | country readout | falls back |
| POST | `/montecarlo` | ensemble summary for a T,R state | no |
| POST | `/girsanov` | reweighting + ESS | no |
| POST | `/simulate` | multi-year daily series | no |
| GET | `/admin?country&level` | GADM polygons (GeoJSON) | **yes** |
| GET | `/choropleth?country&month&xc&resolution&level` | **per-admin-unit risk** FeatureCollection | **yes** |
| POST | `/pipeline/country` | full GeoTIFF batch | **yes** |

The compute endpoints run on numpy+scipy alone; geo endpoints lazily import the
GDAL stack and return HTTP 503 with a clear message if data/deps are missing, so
the server always boots.

## Sub-national ("sub-county") choropleths

`/choropleth` reads the (1 km) WorldClim raster, computes **zonal-mean** T and R
inside each GADM admin polygon, runs the model on those means, and returns a
GeoJSON `FeatureCollection` whose properties carry `Lambda`, `exceed`,
`stationary_mean`, `sigma`, `persist`. Default admin level per country:
Kenya = 2 (sub-counties), Mozambique = 2 (districts), Cameroon = 2. Override with
`&level=1`.

## Resolution vs cost (why 1 km needs care)

WorldClim `30s` ≈ 1 km. Sub-Saharan Africa at 30 s is ~50M pixels.

| Task | 10m (~18 km) | 30s (~1 km) |
|---|---|---|
| Deterministic map (central params) | seconds | ~1–2 min / month |
| **Full Monte Carlo** (N=10,000) | minutes | hours (≈300× heavier) |
| **Zonal choropleth** (per admin unit) | fast | **fast** — recommended at 1 km |

Practical guidance: use **1 km for `/choropleth` and deterministic maps**, and
run **full-raster Monte Carlo at 10m/5m** (or reduce N, or tile by country).
`monte_carlo_raster` uses online accumulators, so memory stays flat regardless
of N.

## "Real-time" behaviour

Data is cached under `vectorrisk_cache/`. The first run downloads the current
published WorldClim/GADM artifacts; later runs reuse the cache. Delete the cache
(or a resolution subfolder) to force a refresh to the latest published rasters.

## Wiring the dashboard to this backend

The dashboard ships with an offline reference model. To make it live:

1. `vectorrisk serve` (CORS is open by default).
2. Open the dashboard, go to **Overview → Live backend**, paste
   `http://127.0.0.1:8000`, and click **Connect**. It pulls real zonal-mean
   climate per country and enables the **Sub-national (live)** choropleth button
   on the Map screen.

## Layout

```
vectorrisk/
  config.py      resolutions, URLs, countries, parameter ranges
  model.py       vectorized model (matches the paper & dashboard)
  montecarlo.py  point + raster uncertainty propagation
  girsanov.py    finite-horizon change of measure
  simulate.py    multi-year daily SDE
  data.py        WorldClim / Natural Earth / GADM download + cache
  zonal.py       clip + zonal stats + choropleth FeatureCollection
  pipeline.py    full-raster GeoTIFF batch
  api.py         FastAPI app
  cli.py         vectorrisk serve|fetch|maps|metrics
tests/test_model.py
```

---

## Run it in Cursor (local)

1. Open the `vectorrisk_pkg` folder in Cursor.
2. Terminal:
   ```bash
   python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
   pip install -e ".[full]"        # if rasterio/geopandas fail, use conda-forge (see Install)
   vectorrisk serve
   ```
3. Open `http://127.0.0.1:8000/` — the API **serves the dashboard**, which
   auto-connects to itself. `http://127.0.0.1:8000/docs` is the API explorer.

## Share a link with a supervisor / donor

The API serves the dashboard at `/`, so you only expose one port.

- **Your own server:** `docker build -t vectorrisk . && docker run -p 8000:8000 vectorrisk`,
  then put nginx in front for a domain + HTTPS. Donor opens `https://your-domain/`.
- **Quick temporary link (no server config):** run locally, then
  `cloudflared tunnel --url http://localhost:8000` (or `ngrok http 8000`) and
  send the printed URL.
- **Managed hosting:** Render / Railway / Fly.io using the included `Dockerfile`.

For a public deployment, restrict CORS (`allow_origins` in `api.py`) and put the
heavy `/pipeline` endpoints behind auth.

## Import your own environmental data (real-time output)

Users don't have to wait for WorldClim. Drop in a CSV and get model output back
immediately, via `POST /import/climate` (or the dashboard's editable climate).

Long format:
```
unit,month,T,R
Kisumu,1,23.4,60
Kisumu,2,23.8,80
...
```
or wide (`unit,T1..T12,R1..R12`), or JSON `{"Kisumu":{"T":[...12],"R":[...12]}}`.
Returns tidy `monthly` and `annual` metric tables you can re-download as CSV/Excel.
This is the slot for station data, seasonal forecasts, or climate-scenario inputs.

## Incidence data + validation

**Fetch & normalize** (WHO Global Health Observatory):
```bash
vectorrisk incidence --countries KEN CMR MOZ --out incidence.csv
```
Everything is normalized to one tidy schema
`{iso3, country, year, indicator, disease, value, low, high, unit, source}` and
cached for re-download. `--offline` uses a bundled illustrative sample.

**Correlate model metrics with incidence** to find which metric — and which
exceedance threshold — best tracks the disease:
```bash
vectorrisk validate        # demo across the focus countries
# or POST /validate/correlation with your panel + incidence
```
Output ranks every feature (`Lambda_mean`, `persist_frac`, `abundance_mean`,
`abundance_peak`, `exceed_250 … exceed_1500`) by Pearson & Spearman correlation,
and reports the best-correlating `x_c`. That threshold is an **empirical
recalibration** of the operational cutoff for that disease. Swap in dengue /
chikungunya incidence and Aedes thermal parameters to repeat it per disease.

### Honest data notes (read before validating)

- **Time span:** WHO malaria *estimates* are national and run ~2000–present
  (~24 yrs), not 50. There is no standardized 50-year African incidence series.
- **Sample size:** correlation across 3 countries is not meaningful. Use
  **sub-national** units (the `/choropleth` layer gives you dozens per country)
  or a **country-year panel** (3 countries × 24 yrs ≈ 72 points).
- **Year-by-year needs year-specific climate.** WorldClim is a 1970–2000
  *climatology* (one average year), fine for the base risk map. To correlate with
  yearly incidence you need a time series: **CHIRPS** rainfall (1981–present,
  ~5 km) and **ERA5-Land / TerraClimate / CRU** temperature. Feed those through
  `POST /import/climate` per unit-year.
- **Sub-national incidence** is best sourced from the **Malaria Atlas Project**
  (modeled Pf incidence rasters, 2000–present) or national HMIS/DHIS2. A MAP hook
  belongs alongside `incidence.py`.

## Validation screen (dashboard tab 08)

Once connected to the backend, the **Validation** tab runs three modes:

- **WHO national (demo):** `POST /validate/correlation {use_builtin:true}` — 3
  countries; intentionally underpowered, shows the mechanism.
- **Upload incidence CSV (national):** drop a `iso3,value` CSV; it's joined to the
  loaded countries' climate and correlated.
- **Sub-national (live, MAP):** point at a Malaria Atlas Project incidence GeoTIFF
  already on the server; `POST /validate/subnational` computes per-admin-unit
  model metrics *and* per-admin zonal-mean incidence, then correlates across all
  units — the properly powered validation.

Output: a ranked correlation table (Pearson & Spearman), the best-correlating
exceedance threshold, a scatter of the top metric vs incidence, and a CSV export.

### Malaria Atlas Project (sub-national incidence)

`map_incidence.py` turns a MAP *Pf* incidence-rate GeoTIFF into per-admin-unit
incidence via zonal means (`zonal_incidence_from_raster`). Recommended workflow:
download the raster for your year from the MAP portal, place it on the server,
and pass its path. A best-effort WCS auto-download (`download_wcs_geotiff`,
`list_coverages`) is included, but MAP coverage ids change per release — confirm
the current id with `list_coverages()` before relying on auto-download.

## Year-specific climate & the powered validation panel

WorldClim is a 1970–2000 *average*. To validate against yearly incidence you need
time-series climate, so `climate_ts.py` adds:

- **TerraClimate** (default): monthly ppt/tmax/tmin, 1958–present, ~4 km, no auth,
  read via **OPeNDAP** so only the Africa/country subset transfers (not the global
  file). `T = (tmax+tmin)/2`.
- **CHIRPS** (optional): monthly rainfall, 1981–present, ~5 km, higher-res
  rainfall override.

Install the extra: `pip install -e ".[ts]"` (xarray, rioxarray, netCDF4).

Build a **(country × year) panel** and correlate it with WHO incidence by
ISO3+year — the scientifically defensible design (e.g. 3 countries × 20 years =
60 points):

```bash
vectorrisk panel --years 2001 2020 --out panel.csv     # + WHO incidence, ranked
# or POST /validate/panel {"years":[2001,2020]}
# or Validation tab -> "Country-year panel (live · TerraClimate)"
```

`GET /climate/timeseries?country=Kenya&year=2015` returns that year's national
zonal-mean monthly T,R on its own, so you can inspect or re-download any year.

For sub-national × year panels, swap the national geometry for GADM admin units
(admin-2) and MAP incidence per unit-year — the same `build_spacetime_panel` with
`keys=("unit","year")`. That is the end-state validation and needs the most data,
but every piece is now in place.

## Sub-national × year panel (fully powered validation)

The end-state: correlate per-admin-unit model metrics against per-unit MAP
incidence across every admin unit and year — one country becomes thousands of
observations.

```bash
# download per-year MAP Pf incidence GeoTIFFs to a folder first, then:
vectorrisk subpanel Kenya --years 2015 2020 \
    --raster-template "/data/map/pf_incidence_{year}.tif" --out kenya_panel.csv
# or POST /validate/subnational-panel
# or Validation tab -> "Sub-national × year panel (live · MAP)"
```

For each (unit, year) it computes year-specific zonal-mean T,R (TerraClimate)
inside the admin polygon → annual model features, and zonal-mean incidence from
that year's MAP raster inside the same polygon, then correlates over all
unit-years with `keys=("unit","year")`. `{year}` in the template is filled per
year. This is the heaviest job (one climate open per variable per year, one MAP
raster per year, each clipped to every unit) and needs the full `.[full]` +
`.[ts]` stack, GADM cache, TerraClimate access, and MAP rasters on disk.

---

# RUNNING & DEPLOYING — step by step

## A. On your laptop with Cursor

```bash
# 1. get the code open in Cursor, then in the Cursor terminal:
conda env create -f environment.yml     # installs the GDAL stack cleanly
conda activate vectorrisk
#    (no conda? python -m venv .venv && source .venv/bin/activate && pip install -e ".[full]")

# 2. FIRST, check every data link works from your machine:
vectorrisk check
#    -> shows OK/FAIL for WorldClim, GADM/geoBoundaries, WHO, TerraClimate, CHIRPS, MAP

# 3. cache the climate + boundaries (first run only; 30s = 1km is large):
vectorrisk fetch --resolution 10m        # use 30s once you're ready for 1km

# 4. run it — API + dashboard on one URL:
vectorrisk serve
#    open http://127.0.0.1:8000/   (dashboard, auto-connected)
#    open http://127.0.0.1:8000/docs  (API)
```

If temperature/rainfall look empty in the dashboard, run `vectorrisk check`
first: a FAIL on WorldClim means the download link is blocked from your network
(firewall/proxy or provider down), and `/climate` falls back to representative
values until `vectorrisk fetch` has cached the real rasters.

## B. On your server, with a shareable link for a donor

```bash
# with Docker (recommended — bundles GDAL):
docker build -t vectorrisk .
docker run -d -p 8000:8000 -v $PWD/cache:/app/vectorrisk_cache vectorrisk
# then reverse-proxy port 8000 behind your domain + HTTPS (nginx/Caddy).
```

Minimal nginx site:
```nginx
server {
  server_name vectorrisk.example.org;
  location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; }
}
```
Add HTTPS with `certbot --nginx`. Your donor opens `https://vectorrisk.example.org/`.

No server yet? For a quick temporary link: `vectorrisk serve` then
`cloudflared tunnel --url http://localhost:8000` and send the printed URL.

Before a public deployment: set `allow_origins` in `api.py` to your domain, and
protect the heavy `/pipeline*` and `/validate/subnational-panel` routes.

---

# LICENSING FOR COMMERCIAL USE (read before selling)

`vectorrisk check` prints each source's licence. The one that blocks commercial
use out of the box is **GADM (non-commercial only)**. For a commercial product,
switch to **geoBoundaries** (CC BY 4.0, commercial OK with attribution):

```python
# vectorrisk/config.py
ADMIN_SOURCE = "geoboundaries"     # instead of "gadm"
```

All boundary loading routes through this one switch, so the map choropleth,
zonal climate, and sub-national panels all use the commercial-friendly source.

Quick licence summary (verify current terms yourself before selling):
WorldClim — free w/ citation · Natural Earth — public domain · CHIRPS — public
domain · TerraClimate — free w/ citation · WHO GHO — open, follow WHO terms ·
Malaria Atlas Project — CC BY · **GADM — non-commercial** · geoBoundaries — CC BY 4.0.
Always attribute sources in your product and keep the citations in any report.
