import numpy as np
import pandas as pd
import pytest


def row(**kw):
    base = dict(Market=np.nan, Ticker="T", Exchange=np.nan, Country=np.nan)
    base.update(kw)
    return pd.Series(base)


# ======================= electronics / semiconductors =======================
@pytest.fixture
def es(load_script):
    return load_script("enrich_electronics_semiconductors_unswept.py")[0]


@pytest.mark.parametrize("kw,expected", [
    (dict(Market="IN", Ticker="TCS"), ("TCS.NS", None)),
    (dict(Market="US", Ticker="AAPL"), ("AAPL", None)),
    (dict(Market="HK", Ticker="5"), ("0005.HK", None)),
    (dict(Market="HK", Ticker="12345"), ("12345.HK", None)),
    (dict(Market=" JP ", Ticker=" 7203 "), ("7203.T", None)),
    (dict(Market="CN", Ticker="600519"), ("600519.SS", None)),
    (dict(Market="CN", Ticker="300750"), ("300750.SZ", None)),
    (dict(Market="EU", Ticker="X"), (None, "market_no_suffix:EU")),
    (dict(Market="ZZ", Ticker="X"), (None, "unmapped_market:ZZ")),
    (dict(Market="DE", Ticker="A B"), ("A-B.DE", None)),
    (dict(Market="  ", Ticker="X", Exchange="ENXTPA"), ("X.PA", None)),      # blank market -> exchange fallback
    (dict(Ticker="X"), (None, "no_market_no_exchange")),
    (dict(Ticker="X", Exchange="ATSE", Country="Austria"), ("X.VI", None)),
    (dict(Ticker="X", Exchange="ATSE", Country="Greece"), ("X.AT", None)),
    (dict(Ticker="X", Exchange="NasdaqGS"), ("X", None)),
    (dict(Ticker="X", Exchange="BUL"), (None, "exchange_not_covered_by_yfinance")),
    (dict(Ticker="X", Exchange="NGSE"), (None, "exchange_not_covered_by_yfinance")),
    (dict(Ticker="X", Exchange="NOPE"), (None, "unmapped_exchange:NOPE")),
    (dict(Ticker="700", Exchange="SEHK"), ("0700.HK", None)),
    (dict(Ticker="ABC", Exchange="SEHK"), ("ABC.HK", None)),
    (dict(Ticker="X Y", Exchange="KLSE"), ("X-Y.KL", None)),
])
def test_es_yf_ticker(es, kw, expected):
    assert es.yf_ticker(row(**kw)) == expected


def test_es_none_suffix_not_in_obscure_set(es, monkeypatch):
    monkeypatch.setitem(es.EXCHANGE_SUFFIX_FALLBACK, "QQ", None)
    assert es.yf_ticker(row(Ticker="X", Exchange="QQ")) == (None, "exchange_no_suffix:QQ")


def test_es_obscure_set_matches_none_entries(es):
    assert {k for k, v in es.EXCHANGE_SUFFIX_FALLBACK.items() if v is None} == es.OBSCURE_NO_YF_COVERAGE


def test_es_checkpoint_expansion_signal(es, load_script):
    rows = [dict(revenue_growth=0.10, Ret252=None), dict(revenue_growth=0.0999, Ret252=0.25),
            dict(revenue_growth=None, Ret252=0.2499), dict(revenue_growth=None, Ret252=None)]
    df = es.checkpoint(rows)
    assert df["expansion_signal"].astype(bool).tolist() == [True, True, False, False]
    assert (load_script.data / "electronics_semiconductors_unswept_enriched.csv").exists()


def _catalog(data, rows):
    pd.DataFrame(rows).to_csv(data / "focus_sector_global_catalog.csv", index=False)


def _crow(ticker, sector="Electronics & Semiconductors", verified=None, market="US", **kw):
    return dict(FocusSector=sector, Ticker=ticker, Market=market, Exchange="NasdaqGS", Country="United States",
                verified=verified, Ret252=None, **kw)


def test_es_main_flow(load_script, fake_yf, capsys):
    _catalog(load_script.data, [
        _crow("PROF"), _crow("LOSS"), _crow("GAP"), _crow("BLANK", verified="  "), _crow("DONE", verified="PROFITABLE"),
        _crow("OTHER", sector="Pharma & Bulk Drugs"), _crow("NOMAP", market="EU")])
    fake_yf.infos = {"PROF": {"profitMargins": 0.2, "returnOnEquity": 0.2, "revenueGrowth": 0.3},
                     "LOSS": {"profitMargins": 0.2, "returnOnEquity": -0.2},
                     "GAP": {}, "BLANK": {"profitMargins": 0.1, "returnOnEquity": 0.1}}
    mod, _ = load_script("enrich_electronics_semiconductors_unswept.py")
    mod.main()
    out = pd.read_csv(load_script.data / "electronics_semiconductors_unswept_enriched.csv").set_index("Ticker")
    assert set(out.index) == {"PROF", "LOSS", "GAP", "BLANK", "NOMAP"}              # swept + other sector excluded
    assert out["verified"].to_dict() == {"PROF": "PROFITABLE", "LOSS": "NOT-PROFITABLE", "GAP": "UNVERIFIED",
                                         "BLANK": "PROFITABLE", "NOMAP": "UNVERIFIED"}
    assert out.loc["GAP", "unverified_reason"] == "yfinance_data_gap"
    assert out.loc["NOMAP", "unverified_reason"] == "market_no_suffix:EU"
    assert pd.isna(out.loc["PROF", "unverified_reason"])
    assert bool(out.loc["PROF", "expansion_signal"]) is True
    text = capsys.readouterr().out
    assert "Electronics & Semiconductors total: 6 | unswept target: 5" in text
    assert "Wrote 5 rows" in text and "PROFITABLE 2 | NOT-PROFITABLE 1 | UNVERIFIED 2" in text
    assert "no ticker built at all (unmapped/unsupported exchange or market): 1" in text
    assert "ticker built but yfinance had no financial data: 1" in text
    assert "with expansion signal (PROFITABLE only): 1" in text


def test_es_main_rate_limit_retry_then_success(load_script, fake_yf, capsys, monkeypatch):
    _catalog(load_script.data, [_crow("RL")])
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("HTTP Error 429: Too Many Requests")
        return {"profitMargins": 0.1, "returnOnEquity": 0.1}

    fake_yf.infos = {"RL": flaky}
    sleeps = []
    import time
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    mod, _ = load_script("enrich_electronics_semiconductors_unswept.py")
    mod.main()
    assert len(attempts) == 3
    out = pd.read_csv(load_script.data / "electronics_semiconductors_unswept_enriched.csv")
    assert out["verified"].tolist() == ["PROFITABLE"]
    assert [s for s in sleeps if s >= 8] == [8, 16]              # 8 * attempt
    assert "rate-limited on RL, backing off 8s, attempt 1/3" in capsys.readouterr().out


def test_es_main_rate_limit_gives_up_after_three(load_script, fake_yf):
    _catalog(load_script.data, [_crow("RL")])
    n = []
    fake_yf.infos = {"RL": lambda: (n.append(1), (_ for _ in ()).throw(RuntimeError("Too Many Requests")))[1]}
    mod, _ = load_script("enrich_electronics_semiconductors_unswept.py")
    mod.main()
    out = pd.read_csv(load_script.data / "electronics_semiconductors_unswept_enriched.csv")
    assert len(n) == 3 and out["verified"].tolist() == ["UNVERIFIED"]
    assert pd.isna(out["unverified_reason"].iloc[0]) or out["unverified_reason"].iloc[0] is None


def test_es_main_other_errors_not_retried_and_truncated(load_script, fake_yf):
    _catalog(load_script.data, [_crow("E1")])
    n = []
    fake_yf.infos = {"E1": lambda: (n.append(1), (_ for _ in ()).throw(ValueError("x" * 200)))[1]}
    mod, _ = load_script("enrich_electronics_semiconductors_unswept.py")
    mod.main()
    out = pd.read_csv(load_script.data / "electronics_semiconductors_unswept_enriched.csv")
    assert len(n) == 1 and out["unverified_reason"].iloc[0] == "yfinance_error:" + "x" * 80


def test_es_main_checkpoints_every_40_rows(load_script, fake_yf, monkeypatch, capsys):
    _catalog(load_script.data, [_crow(f"T{i:03d}") for i in range(81)])
    mod, ns = load_script("enrich_electronics_semiconductors_unswept.py")
    calls = []
    real = ns["checkpoint"]
    ns["checkpoint"] = lambda rows: (calls.append(len(rows)), real(rows))[1]
    mod.main()
    assert calls == [40, 80, 81]
    text = capsys.readouterr().out
    assert "-- checkpointed 40 rows --" in text and "-- checkpointed 80 rows --" in text
    assert "[10/81]" in text and "[81/81]" in text and "[11/81]" not in text


# ======================= medical devices =======================
@pytest.fixture
def md(load_script):
    return load_script("enrich_medical_devices_unswept.py")[0]


@pytest.mark.parametrize("exch,country,ticker,expected", [
    ("NYSE", "United States", "ABT", ("ABT", None)),
    ("TSX", "Canada", "X", ("X.TO", None)),
    ("SEHK", "Hong Kong", "5", ("0005.HK", None)),
    ("SEHK", "Hong Kong", "ABC", ("ABC.HK", None)),
    ("KOSDAQ", "South Korea", "A455900", ("455900.KQ", None)),
    ("KOSE", "South Korea", "A455900", ("455900.KS", None)),
    ("XKON", "South Korea", "A12", ("12.KQ", None)),
    ("KOSDAQ", "South Korea", "ABC", ("ABC.KQ", None)),
    ("KOSDAQ", "South Korea", "A12B", ("A12B.KQ", None)),
    ("NYSE", "United States", "GTAB B", ("GTAB-B", None)),
    ("OM", "Sweden", "X", ("X.ST", None)),
    ("OM", "Denmark", "X", ("X.CO", None)),
    ("NGM", "United Kingdom", "X", ("X.ST", None)),
    ("XSAT", "Sweden", "X", ("X.ST", None)),
    ("BUL", "Bulgaria", "X", (None, "exchange_not_on_yfinance:BUL")),
    ("DSM", "Qatar", "X", (None, "exchange_not_on_yfinance:DSM")),
    ("ZZZ", "Nowhere", "X", (None, "unmapped_exchange:ZZZ")),
    ("OM", "Norway", "X", (None, "unmapped_exchange:OM")),
    ("BSE", "India", " 500 ", ("500.BO", None)),
])
def test_md_yf_ticker(md, exch, country, ticker, expected):
    assert md.yf_ticker({"Exchange": exch, "Country": country, "Ticker": ticker}) == expected


def _mrow(ticker, exch="NYSE", sector="Medical Devices", verified=None):
    return dict(FocusSector=sector, Ticker=ticker, Exchange=exch, Country="United States",
                verified=verified, Ret252=None)


def test_md_main_flow(load_script, fake_yf, capsys):
    _catalog(load_script.data, [_mrow("PROF"), _mrow("LOSS"), _mrow("GAP"), _mrow("NOMAP", exch="ZZZ"),
                                _mrow("DONE", verified="PROFITABLE"), _mrow("OTHER", sector="Steel"),
                                _mrow("BLANK", verified="")])
    fake_yf.infos = {"PROF": {"profitMargins": 0.2, "returnOnEquity": 0.2, "revenueGrowth": 0.1},
                     "LOSS": {"profitMargins": -0.2, "returnOnEquity": 0.2}, "GAP": {"profitMargins": 0.1},
                     "BLANK": {"profitMargins": 0.0, "returnOnEquity": 0.0}}
    mod, _ = load_script("enrich_medical_devices_unswept.py")
    mod.main()
    out = pd.read_csv(load_script.data / "medical_devices_unswept_enriched.csv").set_index("Ticker")
    assert out["verified"].to_dict() == {"PROF": "PROFITABLE", "LOSS": "NOT-PROFITABLE", "GAP": "UNVERIFIED",
                                         "NOMAP": "UNVERIFIED", "BLANK": "NOT-PROFITABLE"}
    assert out.loc["GAP", "unverified_reason"] == "yfinance_data_gap"
    assert out.loc["NOMAP", "unverified_reason"] == "unmapped_exchange:ZZZ"
    assert bool(out.loc["PROF", "expansion_signal"]) is True and bool(out.loc["LOSS", "expansion_signal"]) is False
    text = capsys.readouterr().out
    assert "Medical Devices total: 6 | unswept (target for this run): 5" in text
    assert "PROFITABLE 1 | NOT-PROFITABLE 2 | UNVERIFIED 2" in text
    assert "(no ticker built): 1" in text and "(ticker built, no financials): 1" in text
    assert "with expansion signal (PROFITABLE only): 1" in text


def test_md_main_rate_limit_backoff_is_5_per_attempt(load_script, fake_yf, monkeypatch, capsys):
    import time
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    _catalog(load_script.data, [_mrow("RL"), _mrow("ERR")])
    n = {"RL": 0}

    def rl():
        n["RL"] += 1
        raise RuntimeError("429")

    fake_yf.infos = {"RL": rl, "ERR": RuntimeError("y" * 200)}
    mod, _ = load_script("enrich_medical_devices_unswept.py")
    mod.main()
    out = pd.read_csv(load_script.data / "medical_devices_unswept_enriched.csv").set_index("Ticker")
    assert n["RL"] == 3 and [s for s in sleeps if s in (5, 10, 15)] == [5, 10, 15]
    assert out.loc["ERR", "unverified_reason"] == "yfinance_error:" + "y" * 80
    assert "rate-limited on RL, backing off 5s, attempt 1/3" in capsys.readouterr().out
    assert sleeps.count(0.75) == 2          # one polite pause per resolved ticker
