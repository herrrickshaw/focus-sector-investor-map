import pandas as pd
import pytest


@pytest.fixture
def mod(load_script):
    return load_script("enrich_profitability.py")[0]


@pytest.mark.parametrize("market,sym,expected", [
    ("IN", "TCS", "TCS.NS"), ("JP", "7203", "7203.T"), ("US", "AAPL", "AAPL"), ("HK", "5", "0005.HK"),
    ("HK", "12345", "12345.HK"), ("CN", "600519", "600519.SS"), ("CN", "000001", "000001.SZ"),
    ("UK", "RIO", "RIO.L"), ("EU", "X", None), ("ZZ", "X", None),
])
def test_yf_ticker(mod, market, sym, expected):
    assert mod.yf_ticker({"Market": market, "Symbol": sym}) == expected


def test_yf_ticker_numeric_symbol_coerced(mod):
    assert mod.yf_ticker({"Market": "HK", "Symbol": 700}) == "0700.HK"


def _shortlist(data):
    rows = [
        dict(FocusSector="Steel", Region="Foreign", Market="US", Symbol="PROF", Turnover_USD=5.0, Ret252=0.0),
        dict(FocusSector="Steel", Region="Foreign", Market="US", Symbol="LOSS", Turnover_USD=4.0, Ret252=0.3),
        dict(FocusSector="Steel", Region="India", Market="IN", Symbol="GAP", Turnover_USD=3.0, Ret252=None),
        dict(FocusSector="Steel", Region="Foreign", Market="US", Symbol="ERR", Turnover_USD=2.0, Ret252=None),
        dict(FocusSector="Steel", Region="Foreign", Market="EU", Symbol="NOTK", Turnover_USD=1.0, Ret252=None),
        dict(FocusSector="Steel", Region="Foreign", Market="US", Symbol="ZERO", Turnover_USD=9.0, Ret252=None),
    ]
    pd.DataFrame(rows).to_csv(data / "shortlist_for_enrichment.csv", index=False)


def test_main_classifies_and_writes_outputs(load_script, fake_yf, capsys):
    _shortlist(load_script.data)
    fake_yf.infos = {
        "PROF": {"profitMargins": 0.2, "returnOnEquity": 0.1, "revenueGrowth": 0.10},    # growth exactly at threshold
        "LOSS": {"profitMargins": -0.1, "returnOnEquity": 0.5, "revenueGrowth": 0.0},
        "GAP.NS": {"profitMargins": 0.3},                                                  # roe missing
        "ERR": RuntimeError("boom"),
        "ZERO": {"profitMargins": 0.0, "returnOnEquity": 0.4},                              # margin must be > 0
    }
    mod, _ = load_script("enrich_profitability.py")
    mod.main()
    enriched = pd.read_csv(load_script.data / "shortlist_enriched.csv").set_index("Symbol")
    assert enriched["verified"].to_dict() == {"PROF": "PROFITABLE", "LOSS": "NOT-PROFITABLE", "GAP": "UNVERIFIED",
                                              "ERR": "UNVERIFIED", "NOTK": "UNVERIFIED", "ZERO": "NOT-PROFITABLE"}
    assert enriched.loc["GAP", "profit_margin"] == 0.3 and pd.isna(enriched.loc["GAP", "roe"])
    assert pd.isna(enriched.loc["NOTK", "yf"])
    assert bool(enriched.loc["PROF", "expansion_signal"]) is True       # revenue_growth >= 0.10
    assert bool(enriched.loc["LOSS", "expansion_signal"]) is True       # Ret252 >= 0.25 (0.3)
    assert bool(enriched.loc["ERR", "expansion_signal"]) is False
    assert fake_yf.calls == ["PROF", "LOSS", "GAP.NS", "ERR", "ZERO"]    # EU has no ticker: no lookup
    final = pd.read_csv(load_script.data / "focus_sector_companies_final.csv")
    assert final["Symbol"].tolist() == ["PROF"]
    js = pd.read_json(load_script.data / "focus_sector_companies_final.json")
    assert js["Symbol"].tolist() == ["PROF"]
    out = capsys.readouterr().out
    assert "enriched 6 | PROFITABLE 1 | NOT-PROFITABLE 2 | UNVERIFIED 3" in out
    assert "with expansion signal: 1" in out


def test_main_final_sorted_by_turnover_desc(load_script, fake_yf):
    rows = [dict(FocusSector="B", Region="Foreign", Market="US", Symbol="LOW", Turnover_USD=1.0, Ret252=None),
            dict(FocusSector="A", Region="Foreign", Market="US", Symbol="HI", Turnover_USD=2.0, Ret252=None),
            dict(FocusSector="A", Region="Foreign", Market="US", Symbol="TOP", Turnover_USD=9.0, Ret252=None)]
    pd.DataFrame(rows).to_csv(load_script.data / "shortlist_for_enrichment.csv", index=False)
    ok = {"profitMargins": 0.1, "returnOnEquity": 0.1}
    fake_yf.infos = {"LOW": ok, "HI": ok, "TOP": ok}
    mod, _ = load_script("enrich_profitability.py")
    mod.main()
    assert pd.read_csv(load_script.data / "focus_sector_companies_final.csv")["Symbol"].tolist() == ["TOP", "HI", "LOW"]


def test_expansion_signal_boundaries(load_script, fake_yf):
    rows = [dict(FocusSector="A", Region="F", Market="US", Symbol=s, Turnover_USD=1.0, Ret252=r)
            for s, r in (("R25", 0.25), ("R24", 0.2499), ("RNAN", None))]
    pd.DataFrame(rows).to_csv(load_script.data / "shortlist_for_enrichment.csv", index=False)
    ok = {"profitMargins": 0.1, "returnOnEquity": 0.1, "revenueGrowth": 0.0999}
    fake_yf.infos = {"R25": ok, "R24": ok, "RNAN": ok}
    mod, _ = load_script("enrich_profitability.py")
    mod.main()
    e = pd.read_csv(load_script.data / "shortlist_enriched.csv").set_index("Symbol")["expansion_signal"].astype(bool)
    assert e.to_dict() == {"R25": True, "R24": False, "RNAN": False}


def test_roe_exactly_zero_is_not_profitable_and_json_layout(load_script, fake_yf):
    rows = [dict(FocusSector="A", Region="Foreign", Market="US", Symbol="R0", Turnover_USD=1.0, Ret252=None),
            dict(FocusSector="A", Region="Foreign", Market="US", Symbol="OK", Turnover_USD=2.0, Ret252=None)]
    pd.DataFrame(rows).to_csv(load_script.data / "shortlist_for_enrichment.csv", index=False)
    fake_yf.infos = {"R0": {"profitMargins": 0.2, "returnOnEquity": 0.0}, "OK": {"profitMargins": 0.2, "returnOnEquity": 0.1}}
    mod, _ = load_script("enrich_profitability.py")
    mod.main()
    e = pd.read_csv(load_script.data / "shortlist_enriched.csv").set_index("Symbol")["verified"].to_dict()
    assert e == {"R0": "NOT-PROFITABLE", "OK": "PROFITABLE"}
    assert (load_script.data / "focus_sector_companies_final.json").read_text().startswith('[\n {\n  "FocusSector"')


def test_final_sorted_by_region_ascending_within_sector(load_script, fake_yf):
    rows = [dict(FocusSector="A", Region="Foreign", Market="US", Symbol="F1", Turnover_USD=5.0, Ret252=None),
            dict(FocusSector="A", Region="India", Market="IN", Symbol="I1", Turnover_USD=1.0, Ret252=None)]
    pd.DataFrame(rows).to_csv(load_script.data / "shortlist_for_enrichment.csv", index=False)
    ok = {"profitMargins": 0.1, "returnOnEquity": 0.1}
    fake_yf.infos = {"F1": ok, "I1.NS": ok}
    mod, _ = load_script("enrich_profitability.py")
    mod.main()
    assert pd.read_csv(load_script.data / "focus_sector_companies_final.csv")["Symbol"].tolist() == ["F1", "I1"]
