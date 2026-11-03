"""Unit tests on synthetic rows only (no network, no real parquet inputs)."""
import pandas as pd
import pytest

from focus_sector_map import catalog, fundamentals, screen, sectors, tickers


def test_tag_focus_sectors_maps_and_drops_non_focus():
    dam = pd.DataFrame({"Ticker": ["A", "B", "C"], "Country": ["India", "Narnia", "Japan"],
                        "Industry Group": ["Steel", "Steel", "Retail"]})
    tagged = sectors.tag_focus_sectors(dam)
    assert list(tagged["Ticker"]) == ["A", "B"]
    assert tagged.loc[tagged.Ticker == "A", "Market"].item() == "IN"
    assert pd.isna(tagged.loc[tagged.Ticker == "B", "Market"].item())
    assert set(tagged["FocusSector"]) == {"Specialty Steel & Metals"}


def test_region_of():
    assert sectors.region_of("IN") == "India"
    assert sectors.region_of("US") == "Foreign"


@pytest.mark.parametrize("market,symbol,expected", [
    ("IN", "TCS", "TCS.NS"), ("US", "AAPL", "AAPL"), ("HK", "5", "0005.HK"),
    ("CN", "600519", "600519.SS"), ("CN", "000001", "000001.SZ"), ("EU", "X", None), ("XX", "X", None),
])
def test_market_ticker(market, symbol, expected):
    assert tickers.market_ticker(market, symbol) == expected


def _joined():
    return pd.DataFrame({
        "Market": ["IN", "US", "US", "JP"], "Symbol": ["A", "B", "C", "D"],
        "FocusSector": ["S"] * 4,
        "Turnover_USD": [300_000, 100_000, 900_000, 250_000],
        "Above200DMA": [True, True, False, False], "Ret252": [-0.1, 0.5, -0.2, 0.01],
    })


def test_apply_screen_liquidity_and_validation():
    out = screen.apply_screen(_joined())
    assert list(out["Symbol"]) == ["A", "D"] or set(out["Symbol"]) == {"A", "D"}
    assert set(out["Region"]) == {"India", "Foreign"}


def test_select_shortlist_caps_per_group():
    df = pd.DataFrame({"FocusSector": ["S"] * 10, "Region": ["India"] * 10, "Turnover_USD": range(10, 0, -1)})
    assert len(screen.select_shortlist(df, per_group=3)) == 3


def test_join_universe_drops_unmapped_and_dupes():
    uni = pd.DataFrame({"Market": ["IN", "IN"], "Symbol": ["A", "A"], "Turnover_USD": [1, 1]})
    sec = pd.DataFrame({"Ticker": ["A", "A", "Z"], "Market": ["IN", "IN", None], "FocusSector": "S",
                        "Industry Group": "g", "Country": "India"})
    assert len(screen.join_universe(uni, sec)) == 1


@pytest.mark.parametrize("pm,roe,verdict", [
    (0.1, 0.1, "PROFITABLE"), (0.0, 0.1, "NOT-PROFITABLE"), (0.1, -1, "NOT-PROFITABLE"),
    (None, 0.1, "UNVERIFIED"), (0.1, None, "UNVERIFIED"),
])
def test_classify(pm, roe, verdict):
    assert fundamentals.classify(pm, roe) == verdict


def test_fetch_fundamentals_success_and_gap():
    info = {"profitMargins": 0.2, "returnOnEquity": 0.1, "revenueGrowth": 0.3}
    ok = fundamentals.fetch_fundamentals("T", lambda t: info)
    assert ok.verified == "PROFITABLE" and ok.reason is None
    gap = fundamentals.fetch_fundamentals("T", lambda t: {})
    assert gap.verified == "UNVERIFIED" and gap.reason == "yfinance_data_gap"


def test_fetch_fundamentals_retries_rate_limit_then_gives_up():
    calls, sleeps = [], []

    def getter(t):
        calls.append(t)
        raise RuntimeError("HTTP 429 Too Many Requests")

    res = fundamentals.fetch_fundamentals("T", getter, max_attempts=3, backoff_seconds=2, sleep=sleeps.append)
    assert len(calls) == 3 and sleeps == [2, 4, 6]
    assert res.verified == "UNVERIFIED" and res.reason is None


def test_fetch_fundamentals_other_error_stops_with_reason():
    def getter(t):
        raise ValueError("bad payload")

    res = fundamentals.fetch_fundamentals("T", getter, max_attempts=3)
    assert res.reason == "yfinance_error:bad payload"


def test_expansion_signal_and_final_selection():
    df = pd.DataFrame({"revenue_growth": [0.1, None, None, 0.0], "Ret252": [None, 0.25, 0.1, None],
                       "verified": ["PROFITABLE"] * 3 + ["NOT-PROFITABLE"],
                       "FocusSector": "S", "Region": "India", "Turnover_USD": [1, 2, 3, 4]})
    df = fundamentals.add_expansion_signal(df)
    assert list(df["expansion_signal"]) == [True, True, False, False]
    final = fundamentals.select_final(df)
    assert list(final["Turnover_USD"]) == [3, 2, 1]


def test_enrich_records_skips_fetch_when_no_ticker():
    frame = pd.DataFrame({"Market": ["EU"], "Symbol": ["X"]})
    recs = list(fundamentals.enrich_records(frame, lambda r: (None, "unmapped"), lambda t: 1 / 0,
                                            pause_seconds=0, sleep=lambda s: None))
    assert recs[0]["verified"] == "UNVERIFIED" and recs[0]["unverified_reason"] == "unmapped"


def test_catalog_helpers():
    cat = pd.DataFrame({"FocusSector": ["A", "A", "B"], "Country": ["India", "India", "Japan"],
                        "Ticker": ["x", "y", "z"], "Market": ["IN", "IN", "JP"],
                        "verified": [None, "PROFITABLE", " "]})
    assert list(catalog.country_matrix(cat)["Companies"]) == [2, 1]
    assert list(catalog.unswept_rows(cat, "A")["Ticker"]) == ["x"]
    assert list(catalog.unswept_rows(cat, "B")["Ticker"]) == ["z"]
    assert catalog.top_countries_by_sector(cat)["A"] == "India 2"
    enr = pd.DataFrame({"Market": ["IN"], "Symbol": ["y"], "profit_margin": [0.1], "roe": [0.2],
                        "revenue_growth": [0.3], "verified": ["PROFITABLE"]})
    merged = catalog.attach_profitability(cat, enr)
    assert merged.loc[merged.Ticker == "y", "roe"].item() == 0.2
