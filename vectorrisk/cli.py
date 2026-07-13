"""Command-line interface: ``python -m vectorrisk ...`` or ``vectorrisk ...``."""
from __future__ import annotations

import argparse
import json
import sys

from . import config as C


def cmd_serve(a):
    import uvicorn
    uvicorn.run("vectorrisk.api:app", host=a.host, port=a.port, reload=a.reload)


def cmd_fetch(a):
    from .data import ensure_worldclim, ensure_admin, ensure_natural_earth
    ensure_worldclim(a.resolution, a.cache)
    if a.natural_earth:
        ensure_natural_earth(a.cache)
    for name in (a.countries or list(C.COUNTRIES)):
        c = C.COUNTRIES[name]
        for lvl in sorted({0, c.admin_level, a.level} - {None}):
            ensure_admin(c.iso3, lvl, a.cache)
    print("Fetched WorldClim", a.resolution, "and GADM boundaries into", a.cache)


def cmd_maps(a):
    from .pipeline import run_country_maps
    res = run_country_maps(a.country, a.resolution, C.MONTHS, a.xc, a.n,
                           a.cache, a.out,
                           progress=lambda f: print(f"  {f*100:4.0f}%", end="\r"))
    print("\n" + json.dumps({"files": len(res["files"]), "out": a.out}, indent=2))


def cmd_metrics(a):
    from .model import compute_metrics
    m = compute_metrics(a.T, a.R, None, a.xc)
    print(json.dumps({k: (float(v)) for k, v in m.items()}, indent=2))


def cmd_incidence(a):
    from .incidence import tidy_incidence, export_table
    rows = tidy_incidence(a.indicator, a.countries, a.year_min, a.cache, not a.offline)
    print(f"{len(rows)} rows  (source: {rows[0]['source'] if rows else 'none'})")
    if a.out:
        print("wrote", export_table(rows, a.out))


def cmd_validate(a):
    from .validation import build_panel, correlate
    from .incidence import tidy_incidence
    from . import config as CC
    units = {name: {"T": list(v["T"]), "R": list(v["R"]), "iso3": CC.COUNTRIES[name].iso3}
             for name, v in CC.FALLBACK_CLIMATOLOGY.items()}
    panel = build_panel(units)
    inc = tidy_incidence("MALARIA_EST_INCIDENCE",
                         [c.iso3 for c in CC.COUNTRIES.values()], live=not a.offline)
    agg = {}
    for r in inc:
        agg.setdefault(r["iso3"], []).append(r["value"])
    inc = [{"iso3": k, "value": sum(v) / len(v)} for k, v in agg.items()]
    print(json.dumps(correlate(panel, inc, keys=("iso3",)), indent=2))


def cmd_panel(a):
    from .climate_ts import climate_fn_factory
    from .validation import build_spacetime_panel, correlate
    from .incidence import tidy_incidence
    from . import config as CC
    names = a.countries or list(CC.COUNTRIES)
    units = {n: {"iso3": CC.COUNTRIES[n].iso3, "country": n} for n in names}
    years = list(range(a.years[0], a.years[1] + 1))
    fn = climate_fn_factory(a.cache, a.rainfall)
    print(f"building {len(units)}x{len(years)} country-year panel "
          f"(TerraClimate; first run downloads subsets)...")
    panel = build_spacetime_panel(units, years, fn)
    inc = [{"iso3": r["iso3"], "year": r["year"], "value": r["value"]}
           for r in tidy_incidence("MALARIA_EST_INCIDENCE",
                                   [u["iso3"] for u in units.values()],
                                   year_min=years[0], cache_dir=a.cache, live=True)]
    res = correlate(panel, inc, keys=("iso3", "year"))
    print(json.dumps({"panel_rows": len(panel), "n_matched": res["n"],
                      "best_metric": res.get("best_metric"),
                      "best_exceedance_threshold": res.get("best_exceedance_threshold")},
                     indent=2))
    if a.out:
        import csv
        with open(a.out, "w", newline="") as f:
            if panel:
                w = csv.DictWriter(f, fieldnames=list(panel[0].keys())); w.writeheader(); w.writerows(panel)
        print("wrote panel to", a.out)


def cmd_subpanel(a):
    from .panel_geo import subnational_panel
    from .validation import correlate
    years = list(range(a.years[0], a.years[1] + 1))
    print(f"building {a.country} sub-national x {len(years)}-year panel "
          f"(heavy; downloads climate + reads MAP rasters)...")
    panel, inc = subnational_panel(a.country, years, a.raster_template, a.level,
                                   a.cache, a.rainfall,
                                   progress=lambda f: print(f"  {f*100:4.0f}%", end="\r"))
    res = correlate(panel, inc, keys=("unit", "year"))
    print("\n" + json.dumps({"panel_rows": len(panel),
                             "units": len({r['unit'] for r in panel}),
                             "n_matched": res["n"], "best_metric": res.get("best_metric"),
                             "best_exceedance_threshold": res.get("best_exceedance_threshold")},
                            indent=2))
    if a.out:
        import csv
        with open(a.out, "w", newline="") as f:
            if panel:
                w = csv.DictWriter(f, fieldnames=list(panel[0].keys())); w.writeheader(); w.writerows(panel)
        print("wrote panel to", a.out)


def cmd_check(a):
    from .diagnostics import check, format_report
    print(format_report(check(a.resolution)))


def main(argv=None):
    p = argparse.ArgumentParser(prog="vectorrisk",
                                description="Stochastic mosquito-abundance risk toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the FastAPI backend")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true"); s.set_defaults(func=cmd_serve)

    f = sub.add_parser("fetch", help="download & cache climate + boundary data")
    f.add_argument("--resolution", default=C.DEFAULT_RESOLUTION, choices=list(C.RESOLUTIONS))
    f.add_argument("--countries", nargs="*"); f.add_argument("--level", type=int, default=None)
    f.add_argument("--natural-earth", action="store_true")
    f.add_argument("--cache", default="vectorrisk_cache"); f.set_defaults(func=cmd_fetch)

    m = sub.add_parser("maps", help="produce GeoTIFF maps for a country")
    m.add_argument("country", choices=list(C.COUNTRIES))
    m.add_argument("--resolution", default="10m", choices=list(C.RESOLUTIONS))
    m.add_argument("--n", type=int, default=10000); m.add_argument("--xc", type=float, default=C.DEFAULT_XC)
    m.add_argument("--cache", default="vectorrisk_cache"); m.add_argument("--out", default="vectorrisk_outputs")
    m.set_defaults(func=cmd_maps)

    q = sub.add_parser("metrics", help="print metrics for one T,R state")
    q.add_argument("T", type=float); q.add_argument("R", type=float)
    q.add_argument("--xc", type=float, default=C.DEFAULT_XC); q.set_defaults(func=cmd_metrics)

    i = sub.add_parser("incidence", help="fetch + normalize WHO GHO incidence")
    i.add_argument("--indicator", default="MALARIA_EST_INCIDENCE")
    i.add_argument("--countries", nargs="*", default=["KEN", "CMR", "MOZ"])
    i.add_argument("--year-min", type=int, default=2000)
    i.add_argument("--offline", action="store_true", help="use bundled sample instead of network")
    i.add_argument("--out", help="write CSV/XLSX to this path")
    i.add_argument("--cache", default="vectorrisk_cache"); i.set_defaults(func=cmd_incidence)

    v = sub.add_parser("validate", help="correlate model metrics with malaria incidence (demo)")
    v.add_argument("--offline", action="store_true"); v.set_defaults(func=cmd_validate)

    pn = sub.add_parser("panel", help="build country-year panel + correlate with incidence")
    pn.add_argument("--countries", nargs="*")
    pn.add_argument("--years", type=int, nargs=2, default=[2001, 2020], metavar=("START", "END"))
    pn.add_argument("--rainfall", default="terraclimate", choices=["terraclimate", "chirps"])
    pn.add_argument("--out", help="write the panel table to CSV")
    pn.add_argument("--cache", default="vectorrisk_cache"); pn.set_defaults(func=cmd_panel)

    sp = sub.add_parser("subpanel", help="sub-national x year panel + MAP incidence correlation")
    sp.add_argument("country", choices=list(C.COUNTRIES))
    sp.add_argument("--years", type=int, nargs=2, default=[2015, 2020], metavar=("START", "END"))
    sp.add_argument("--raster-template", required=True, dest="raster_template",
                    help="MAP GeoTIFF path template, e.g. /data/map/pf_incidence_{year}.tif")
    sp.add_argument("--level", type=int, default=None)
    sp.add_argument("--rainfall", default="terraclimate", choices=["terraclimate", "chirps"])
    sp.add_argument("--out", help="write the panel table to CSV")
    sp.add_argument("--cache", default="vectorrisk_cache"); sp.set_defaults(func=cmd_subpanel)

    ck = sub.add_parser("check", help="test connectivity to every data source + show licences")
    ck.add_argument("--resolution", default=None, choices=list(C.RESOLUTIONS))
    ck.set_defaults(func=cmd_check)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
