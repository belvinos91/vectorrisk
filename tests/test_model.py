"""Model unit tests. Run: pytest -q  (needs only numpy+scipy)."""
import numpy as np
import vectorrisk as vr
from vectorrisk.model import compute_metrics


def test_warm_wet_persists():
    m = compute_metrics(27.0, 150.0, None, 500.0)
    assert m["persist"] == 1
    assert m["Lambda"] > 0.15
    assert m["stationary_mean"] > 1500
    assert m["exceed"] > 0.99


def test_cool_marginal():
    m = compute_metrics(21.5, 70.0, None, 500.0)
    assert m["Lambda"] < 0.01           # near the persistence boundary


def test_flushing_rain_collapses():
    # R above R_L (central R_L = 250) -> zero suitability -> no persistence
    m = compute_metrics(24.0, 290.0, None, 500.0)
    assert m["persist"] == 0


def test_exceedance_monotone_in_threshold():
    ex = [compute_metrics(27.0, 150.0, None, xc)["exceed"]
          for xc in (250, 500, 1000, 1500)]
    assert all(ex[i] >= ex[i + 1] for i in range(len(ex) - 1))


def test_vectorized_matches_scalar():
    T = np.array([27.0, 21.5, 24.0])
    R = np.array([150.0, 70.0, 290.0])
    mv = compute_metrics(T, R, None, 500.0)
    for i, (t, r) in enumerate(zip(T, R)):
        ms = compute_metrics(float(t), float(r), None, 500.0)
        assert np.isclose(mv["Lambda"][i], ms["Lambda"], atol=1e-9)


def test_monte_carlo_runs():
    res = vr.monte_carlo_point(27.0, 150.0, 500.0, n=800)
    assert 0.0 <= res["summary"]["persist"]["mean"] <= 1.0
    assert res["summary"]["exceed"]["mean"] >= 0.0


def test_girsanov_identity_holds():
    r = vr.girsanov_validate(26.0, 50.0, 500.0, lam=0.15, u=0.04, n=4000)
    # weighted-P mean should match direct-Q mean closely
    assert r["high"]["abs_diff"] / max(1.0, r["high"]["direct_mean"]) < 0.05
    assert r["intervention"]["abs_diff"] / max(1.0, r["intervention"]["direct_mean"]) < 0.05


def test_simulation_shapes():
    s = vr.simulate_series(vr.config.FALLBACK_CLIMATOLOGY["Kenya"]["T"],
                           vr.config.FALLBACK_CLIMATOLOGY["Kenya"]["R"],
                           None, years=2)
    assert s["stats"]["days"] == 2 * 365


def test_spacetime_panel_and_correlation():
    import numpy as np
    from vectorrisk.validation import build_spacetime_panel, correlate
    units = {"KEN": {"iso3": "KEN"}, "CMR": {"iso3": "CMR"}, "MOZ": {"iso3": "MOZ"}}
    years = list(range(2005, 2021))
    base = {"KEN": (23, 110), "CMR": (24, 140), "MOZ": (25, 120)}
    def cf(k, y):
        Tb, Rb = base[k]
        T = [Tb + 2 * np.sin(m / 12 * 2 * np.pi) for m in range(12)]
        R = [max(0, Rb + 30 * np.sin((m + 3) / 12 * 2 * np.pi)) for m in range(12)]
        return T, R
    panel = build_spacetime_panel(units, years, cf)
    assert len(panel) == len(units) * len(years)
    inc = [{"iso3": k, "year": y, "value": 6 * base[k][0] + 0.4 * base[k][1]}
           for k in units for y in years]
    res = correlate(panel, inc, keys=("iso3", "year"))
    assert res["n"] == len(panel)
    assert res["best_metric"] is not None
    assert len(res["scatter"]) == res["n"]
