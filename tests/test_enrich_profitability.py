"""enrich_profitability.py: yfinance ticker construction, profitability verdicts, expansion signal.
yfinance is faked (conftest.fake_yf); all rows synthetic."""
import math

import pandas as pd
import pytest

from conftest import load

ep = load("enrich_profitability")


@pytest.mark.parametrize("market,symbol,yf", [
    ("IN", "TCS", "TCS.NS"), ("US", "AAPL", "AAPL"), ("JP", "7203", "7203.T"), ("UK", "RR", "RR.L"),
    ("HK", "5", "0005.HK"), ("HK", "700", "0700.HK"),
    ("CN", "600519", "600519.SS"), ("CN", "000001", "000001.SZ"),
    ("EU", "ASML", None), ("XX", "ABC", None),
])
def test_yf_ticker(market, symbol, yf):
    assert ep.yf_ticker({"Market": market, "Symbol": symbol}) == yf


def test_yf_ticker_null_market_is_unresolvable():
    # documented limitation (enrich_medical_devices_unswept.py docstring): NULL Market -> UNVERIFIED
    assert ep.yf_ticker({"Market": float("nan"), "Symbol": "SAN"}) is None


ROWS = [  # Market, Symbol, Ret252 (percent, as in data/focus_sector_screen.csv), yfinance info
    ("US", "PROF", 30.0, {"profitMargins": 0.2, "returnOnEquity": 0.15, "revenueGrowth": 0.02}),   # expansion via return
    ("US", "GROW", -5.0, {"profitMargins": 0.1, "returnOnEquity": 0.1, "revenueGrowth": 0.12}),    # expansion via growth
    ("US", "FLAT", 5.0, {"profitMargins": 0.1, "returnOnEquity": 0.1, "revenueGrowth": 0.01}),     # +5% return: NO expansion
    ("US", "LOSS", 40.0, {"profitMargins": -0.1, "returnOnEquity": 0.2, "revenueGrowth": 0.5}),
    ("US", "GAP", 10.0, {"profitMargins": 0.1}),                                                  # ROE missing
    ("US", "GONE", 10.0, None),                                                                   # yfinance error
    ("EU", "NOSFX", 10.0, None),                                                                  # no ticker
]


@pytest.fixture
def run(tmp_path, monkeypatch, fake_yf):
    pd.DataFrame([dict(FocusSector="Medical Devices", Region="Foreign", Market=m, Symbol=s, Name=s, Turnover_USD=1e6 - i,
                       Ret252=r) for i, (m, s, r, _) in enumerate(ROWS)]).to_csv(tmp_path / "shortlist_for_enrichment.csv", index=False)
    for m, s, _, info in ROWS:
        if info is not None:
            fake_yf[s] = info
    monkeypatch.setattr(ep, "OUT", tmp_path)
    ep.main()
    return (pd.read_csv(tmp_path / "shortlist_enriched.csv").set_index("Symbol"),
            pd.read_csv(tmp_path / "focus_sector_companies_final.csv"))


def test_verdicts(run):
    df, final = run
    assert df.verified.to_dict() == {"PROF": "PROFITABLE", "GROW": "PROFITABLE", "FLAT": "PROFITABLE",
                                     "LOSS": "NOT-PROFITABLE", "GAP": "UNVERIFIED", "GONE": "UNVERIFIED",
                                     "NOSFX": "UNVERIFIED"}
    assert list(final.Symbol) == ["PROF", "GROW", "FLAT"]     # only PROFITABLE, sorted by turnover


def test_expansion_signal_reads_ret252_as_percent(run):
    """Docstring: expansion = revenueGrowth >= 10% OR Ret252 >= 25%. Ret252 is stored in percent
    (data/focus_sector_screen.csv median ~16.6, max ~256), so a +5% one-year return is not expansion.
    The original `Ret252 >= 0.25` flagged any return above +0.25%."""
    df, _ = run
    assert bool(df.loc["PROF", "expansion_signal"]) is True
    assert bool(df.loc["GROW", "expansion_signal"]) is True
    assert bool(df.loc["FLAT", "expansion_signal"]) is False
