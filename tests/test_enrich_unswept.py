"""The two *_unswept enrichment scripts: Exchange-based ticker construction and the expansion signal."""
import pandas as pd
import pytest

from conftest import load

md = load("enrich_medical_devices_unswept")
es = load("enrich_electronics_semiconductors_unswept")


@pytest.mark.parametrize("exch,country,ticker,yf", [
    ("ENXTPA", "France", "SAN", ("SAN.PA", None)),
    ("TASE", "Israel", "TEVA", ("TEVA.TA", None)),
    ("KOSDAQ", "South Korea", "A455900", ("455900.KQ", None)),     # vendor 'A' prefix dropped
    ("KOSE", "South Korea", "A005930", ("005930.KS", None)),
    ("SEHK", "Hong Kong", "5", ("0005.HK", None)),
    ("OM", "Sweden", "GTAB B", ("GTAB-B.ST", None)),             # share class space -> hyphen, override
    ("OM", "Denmark", "NOVO B", ("NOVO-B.CO", None)),
    ("NasdaqGS", "United States", "ISRG", ("ISRG", None)),
    ("BUL", "Bulgaria", "X", (None, "exchange_not_on_yfinance:BUL")),
    ("ZZZ", "Nowhere", "X", (None, "unmapped_exchange:ZZZ")),
])
def test_medical_devices_yf_ticker(exch, country, ticker, yf):
    assert md.yf_ticker({"Exchange": exch, "Country": country, "Ticker": ticker}) == yf


@pytest.mark.parametrize("mod,sector", [(md, "Medical Devices"), (es, "Electronics & Semiconductors")])
def test_expansion_signal_reads_ret252_as_percent(tmp_path, monkeypatch, fake_yf, mod, sector):
    """Same rule and same unit error as enrich_profitability: Ret252 is in percent, threshold is 25%."""
    cat = pd.DataFrame([
        dict(FocusSector=sector, verified=None, Market="US", Exchange="NasdaqGS", Country="United States",
             Ticker="FLAT", Name="Flat Co", Ret252=5.0, Turnover_USD=1e6),
        dict(FocusSector=sector, verified=None, Market="US", Exchange="NasdaqGS", Country="United States",
             Ticker="RUN", Name="Run Co", Ret252=30.0, Turnover_USD=1e6),
        dict(FocusSector=sector, verified="PROFITABLE", Market="US", Exchange="NasdaqGS", Country="United States",
             Ticker="DONE", Name="Already swept", Ret252=99.0, Turnover_USD=1e6),
    ])
    cat.to_csv(tmp_path / "catalog.csv", index=False)
    fake_yf.update({"FLAT": {"profitMargins": 0.1, "returnOnEquity": 0.1, "revenueGrowth": 0.0},
                    "RUN": {"profitMargins": 0.1, "returnOnEquity": 0.1, "revenueGrowth": 0.0}})
    monkeypatch.setattr(mod, "CATALOG", tmp_path / "catalog.csv")
    monkeypatch.setattr(mod, "OUT_CSV", tmp_path / "out.csv")
    mod.main()
    out = pd.read_csv(tmp_path / "out.csv").set_index("Ticker")
    assert "DONE" not in out.index                      # only never-swept rows
    assert out.verified.to_dict() == {"FLAT": "PROFITABLE", "RUN": "PROFITABLE"}
    assert bool(out.loc["RUN", "expansion_signal"]) is True
    assert bool(out.loc["FLAT", "expansion_signal"]) is False
