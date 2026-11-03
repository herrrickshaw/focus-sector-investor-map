"""Smoke tests: each script runs end to end on synthetic parquet/CSV inputs with a stubbed yfinance."""
import importlib.util
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake_yfinance(monkeypatch):
    class Ticker:
        def __init__(self, t):
            self.info = {"profitMargins": 0.1, "returnOnEquity": 0.2, "revenueGrowth": 0.3}

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=Ticker))
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)


@pytest.fixture
def gss(tmp_path):
    root = tmp_path / "gss"
    (root / "cache_seed").mkdir(parents=True)
    (root / "reference_seed").mkdir()
    pd.DataFrame({"Ticker": ["AAA", "BBB", "CCC"], "Country": ["India", "United States", "France"],
                  "Industry Group": ["Semiconductor", "Healthcare Products", "Healthcare Products"],
                  "Company Name": ["Alpha", "Beta", "Gamma"], "Exchange": ["NSEI", "NYSE", "ENXTPA"]}
                 ).to_parquet(root / "reference_seed" / "damodaran_companies.parquet")
    pd.DataFrame({"Market": ["IN", "US"], "Symbol": ["AAA", "BBB"], "Name": ["Alpha", "Beta"],
                  "Close": [1.0, 2.0], "Turnover_USD": [500_000, 600_000],
                  "Above200DMA": [True, True], "Ret252": [0.3, 0.1]}
                 ).to_parquet(root / "cache_seed" / "company_list.parquet")
    return root


def test_full_pipeline(gss, tmp_path, fake_yfinance):
    data = tmp_path / "data"
    load("build_screen").main(["--gss-root", str(gss), "--data-dir", str(data)])
    screen = pd.read_csv(data / "focus_sector_screen.csv")
    assert set(screen["Symbol"]) == {"AAA", "BBB"}

    load("enrich_profitability").main(["--data-dir", str(data)])
    final = pd.read_csv(data / "focus_sector_companies_final.csv")
    assert len(final) == 2 and final["expansion_signal"].all()
    assert (data / "focus_sector_companies_final.json").exists()

    load("build_global_catalog").main(["--gss-root", str(gss), "--data-dir", str(data)])
    catalog = pd.read_csv(data / "focus_sector_global_catalog.csv")
    assert len(catalog) == 3
    assert (data / "focus_sector_country_matrix.csv").exists()

    load("enrich_medical_devices_unswept").main(["--data-dir", str(data)])
    out = pd.read_csv(data / "medical_devices_unswept_enriched.csv")
    assert list(out["Ticker"]) == ["CCC"] and out["yf"].item() == "CCC.PA"
