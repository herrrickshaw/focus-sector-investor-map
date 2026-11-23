import pandas as pd


def _write(home, uni, dam):
    d = home / "repos/global-stock-screener"
    (d / "cache_seed").mkdir(parents=True)
    (d / "reference_seed").mkdir(parents=True)
    pd.DataFrame(uni).to_parquet(d / "cache_seed/company_list.parquet")
    pd.DataFrame(dam).to_parquet(d / "reference_seed/damodaran_companies.parquet")


DAM = [
    {"Ticker": "AAA", "Company Name": "Alpha", "Country": "India", "Exchange": "NSEI", "Industry Group": "Steel"},
    {"Ticker": "BBB", "Company Name": "Beta", "Country": "India", "Exchange": "NSEI", "Industry Group": "Steel"},
    {"Ticker": "CCC", "Company Name": "Gamma", "Country": "Japan", "Exchange": "TSE", "Industry Group": "Power"},
    {"Ticker": "DDD", "Company Name": "Delta", "Country": "Atlantis", "Exchange": "ATL", "Industry Group": "Auto Parts"},
    {"Ticker": "EEE", "Company Name": "Eps", "Country": "India", "Exchange": "NSEI", "Industry Group": "Banks"},
]
DUMMY = {"Market": "ZZ", "Symbol": "none", "Turnover_USD": 0.0, "Above200DMA": False, "Ret252": 0.0, "Close": 0.0}
UNI = [
    {"Market": "IN", "Symbol": "AAA", "Turnover_USD": 5e5, "Above200DMA": True, "Ret252": 0.3, "Close": 10.0},
    {"Market": "JP", "Symbol": "CCC", "Turnover_USD": 7e5, "Above200DMA": False, "Ret252": -0.1, "Close": 5.0},
]


def test_catalog_keeps_every_focus_company_no_gates(load_script, capsys):
    _write(load_script.home, UNI, DAM)
    mod, _ = load_script("build_global_catalog.py")
    mod.main()
    cat = pd.read_csv(load_script.data / "focus_sector_global_catalog.csv")
    assert sorted(cat["Ticker"]) == ["AAA", "BBB", "CCC", "DDD"]          # EEE (Banks) dropped, DDD kept w/o a market
    by = cat.set_index("Ticker")
    assert by.loc["AAA", "Turnover_USD"] == 5e5 and pd.isna(by.loc["BBB", "Turnover_USD"])
    assert pd.isna(by.loc["DDD", "Market"]) and by.loc["CCC", "Market"] == "JP"
    assert by.loc["AAA", "FocusSector"] == "Specialty Steel & Metals"
    # sorted by sector then country then name
    assert cat["Ticker"].tolist() == ["DDD", "CCC", "AAA", "BBB"]
    text = capsys.readouterr().out
    assert "global catalog: 4 companies in focus sectors, 3 countries" in text
    assert "Specialty Steel & Metals" in text and "India 2" in text


def test_catalog_matrix_counts(load_script):
    _write(load_script.home, UNI, DAM)
    mod, _ = load_script("build_global_catalog.py")
    mod.main()
    m = pd.read_csv(load_script.data / "focus_sector_country_matrix.csv")
    got = {(r.FocusSector, r.Country): r.Companies for r in m.itertuples()}
    assert got == {("Specialty Steel & Metals", "India"): 2, ("Green Energy & Fuels", "Japan"): 1,
                   ("Auto, EV & Components", "Atlantis"): 1}


def test_catalog_joins_enriched_when_present(load_script):
    _write(load_script.home, UNI, DAM)
    pd.DataFrame([{"Market": "IN", "Symbol": "AAA", "profit_margin": 0.2, "roe": 0.3, "revenue_growth": 0.1,
                   "verified": "PROFITABLE"}]).to_csv(load_script.data / "shortlist_enriched.csv", index=False)
    mod, _ = load_script("build_global_catalog.py")
    mod.main()
    cat = pd.read_csv(load_script.data / "focus_sector_global_catalog.csv").set_index("Ticker")
    assert cat.loc["AAA", "verified"] == "PROFITABLE" and cat.loc["AAA", "roe"] == 0.3
    assert pd.isna(cat.loc["BBB", "verified"])


def test_catalog_without_enriched_has_no_profit_columns(load_script):
    _write(load_script.home, UNI, DAM)
    mod, _ = load_script("build_global_catalog.py")
    mod.main()
    cols = list(pd.read_csv(load_script.data / "focus_sector_global_catalog.csv").columns)
    assert cols == ["FocusSector", "Industry Group", "Country", "Exchange", "Ticker", "Company Name",
                    "Market", "Turnover_USD", "Above200DMA", "Ret252"]


def test_catalog_sorts_by_country_before_company_name(load_script):
    dam = [{"Ticker": "T1", "Company Name": "Zed", "Country": "Brazil", "Exchange": "B3", "Industry Group": "Steel"},
           {"Ticker": "T2", "Company Name": "Alpha", "Country": "India", "Exchange": "NSEI", "Industry Group": "Steel"}]
    _write(load_script.home, [DUMMY], dam)
    mod, _ = load_script("build_global_catalog.py")
    mod.main()
    assert pd.read_csv(load_script.data / "focus_sector_global_catalog.csv")["Ticker"].tolist() == ["T1", "T2"]


def test_catalog_maps_coal_and_taiwan(load_script):
    dam = [{"Ticker": "C1", "Company Name": "Coal Co", "Country": "Taiwan", "Exchange": "TWSE",
            "Industry Group": "Coal & Related Energy"}]
    uni = [{"Market": "TW", "Symbol": "C1", "Turnover_USD": 9.0, "Above200DMA": True, "Ret252": 0.1, "Close": 1.0}]
    _write(load_script.home, uni, dam)
    mod, _ = load_script("build_global_catalog.py")
    mod.main()
    row = pd.read_csv(load_script.data / "focus_sector_global_catalog.csv").iloc[0]
    assert row["FocusSector"] == "Green Energy & Fuels" and row["Market"] == "TW" and row["Turnover_USD"] == 9.0


def test_catalog_summary_lists_only_top_five_countries(load_script, capsys):
    countries = ["India", "Japan", "Germany", "Canada", "Brazil", "Sweden"]
    dam = [{"Ticker": f"T{i}", "Company Name": f"N{i}", "Country": c, "Exchange": "X", "Industry Group": "Steel"}
           for i, c in enumerate(countries) for _ in range(1)]
    dam += [{"Ticker": "E1", "Company Name": "E", "Country": "India", "Exchange": "X", "Industry Group": "Steel"}]
    _write(load_script.home, [DUMMY], dam)
    mod, _ = load_script("build_global_catalog.py")
    mod.main()
    line = [l for l in capsys.readouterr().out.splitlines() if l.strip().startswith("Specialty Steel")][0]
    assert line.count(",") == 4 and "India 2" in line and line.split("top: ")[1].startswith("India 2")
