import pandas as pd


def _write_inputs(home, uni, dam):
    d = home / "repos/global-stock-screener"
    (d / "cache_seed").mkdir(parents=True)
    (d / "reference_seed").mkdir(parents=True)
    pd.DataFrame(uni).to_parquet(d / "cache_seed/company_list.parquet")
    pd.DataFrame(dam).to_parquet(d / "reference_seed/damodaran_companies.parquet")


def _uni(rows):
    return [dict(Market=m, Symbol=s, Name=f"N{s}", Close=10.0, Turnover_USD=t, Above200DMA=a, Ret252=r)
            for (m, s, t, a, r) in rows]


def _dam(rows):
    return [dict(Ticker=t, Country=c, **{"Industry Group": g}, **{"Company Name": f"C{t}"}, Exchange="X")
            for (t, c, g) in rows]


def test_screen_thresholds_and_regions(load_script, capsys):
    _write_inputs(load_script.home,
        _uni([("IN", "A", 250_000, True, None),          # exactly the floor, above 200dma
              ("IN", "B", 249_999, True, 1.0),           # below floor
              ("US", "C", 1_000_000, False, 0.01),       # momentum only
              ("US", "D", 1_000_000, False, 0.0),        # neither (Ret252 must be > 0)
              ("US", "E", 1_000_000, False, None),       # NaN return, below 200dma
              ("US", "F", 5_000_000, True, -0.5),        # above 200dma wins
              ("JP", "G", 9e9, True, 1.0)]),             # sector not in focus
        _dam([("A", "India", "Steel"), ("B", "India", "Steel"), ("C", "United States", "Auto Parts"),
              ("D", "United States", "Auto Parts"), ("E", "United States", "Auto Parts"),
              ("F", "United States", "Auto Parts"), ("G", "Japan", "Banks")]))
    mod, _ = load_script("build_screen.py")
    mod.main()
    out = pd.read_csv(load_script.data / "focus_sector_screen.csv")
    by = out.set_index("Symbol")
    assert by.loc["A", "Region"] == "India" and by.loc["C", "Region"] == "Foreign"
    assert by.loc["A", "FocusSector"] == "Specialty Steel & Metals"
    assert by.loc["F", "FocusSector"] == "Auto, EV & Components"
    # sorted by sector, region, then turnover descending
    assert out["Symbol"].tolist() == ["F", "C", "A"]
    text = capsys.readouterr().out
    assert "universe joined to focus sectors: 6" in text
    assert "screened (liquidity + market validation): 3" in text
    assert "shortlist for profitability verification: 3" in text


def test_screen_drops_unmapped_country_and_duplicates(load_script):
    _write_inputs(load_script.home,
        _uni([("IN", "A", 1e6, True, 1.0), ("IN", "A", 2e6, True, 1.0), ("XX", "Z", 1e6, True, 1.0)]),
        _dam([("A", "India", "Steel"), ("Z", "Atlantis", "Steel")]))
    mod, _ = load_script("build_screen.py")
    mod.main()
    out = pd.read_csv(load_script.data / "focus_sector_screen.csv")
    assert out["Symbol"].tolist() == ["A"] and len(out) == 1
    assert list(out.columns) == ["FocusSector", "Region", "Market", "Symbol", "Name", "Industry Group",
                                 "Country", "Close", "Turnover_USD", "Above200DMA", "Ret252"]


def test_screen_shortlist_is_top_8_per_sector_region(load_script):
    uni = _uni([("US", f"S{i:02d}", 1e6 + i, True, 1.0) for i in range(12)]
               + [("IN", f"I{i}", 1e6 + i, True, 1.0) for i in range(3)])
    dam = _dam([(f"S{i:02d}", "United States", "Steel") for i in range(12)]
               + [(f"I{i}", "India", "Steel") for i in range(3)])
    _write_inputs(load_script.home, uni, dam)
    mod, _ = load_script("build_screen.py")
    mod.main()
    sl = pd.read_csv(load_script.data / "shortlist_for_enrichment.csv")
    foreign = sl[sl.Region == "Foreign"]
    assert len(foreign) == 8 and len(sl[sl.Region == "India"]) == 3
    # the 8 most liquid names survive
    assert sorted(foreign.Symbol) == [f"S{i:02d}" for i in range(4, 12)]
    assert len(pd.read_csv(load_script.data / "focus_sector_screen.csv")) == 15


def test_screen_constants(load_script):
    mod, _ = load_script("build_screen.py")
    assert mod.MIN_TURNOVER_USD == 250_000
    assert len(mod.FOCUS) == 12 and mod.COUNTRY_TO_MARKET["India"] == "IN"


def test_screen_unmapped_country_dropped_even_if_universe_market_is_missing(load_script):
    # NaN keys join to NaN keys in pandas, so only the explicit dropna keeps unmapped countries out
    _write_inputs(load_script.home,
        _uni([(None, "Z", 1e6, True, 1.0), ("IN", "A", 1e6, True, 1.0)]),
        _dam([("Z", "Atlantis", "Steel"), ("A", "India", "Steel")]))
    mod, _ = load_script("build_screen.py")
    mod.main()
    assert pd.read_csv(load_script.data / "focus_sector_screen.csv")["Symbol"].tolist() == ["A"]


def test_screen_same_symbol_in_two_markets_is_kept_twice(load_script):
    _write_inputs(load_script.home,
        _uni([("IN", "A", 1e6, True, 1.0), ("US", "A", 2e6, True, 1.0)]),
        _dam([("A", "India", "Steel"), ("A", "United States", "Steel")]))
    mod, _ = load_script("build_screen.py")
    mod.main()
    out = pd.read_csv(load_script.data / "focus_sector_screen.csv")
    assert sorted(out["Market"]) == ["IN", "US"]
