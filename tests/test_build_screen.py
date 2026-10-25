"""build_screen.main on a synthetic universe + Damodaran layer (HOME and OUT redirected to tmp)."""
import pandas as pd

from conftest import load

bs = load("build_screen")


def test_screen(tmp_path, monkeypatch):
    seed = tmp_path / "repos/global-stock-screener"
    (seed / "cache_seed").mkdir(parents=True); (seed / "reference_seed").mkdir(parents=True)
    uni = [  # Market, Symbol, Turnover_USD, Above200DMA, Ret252
        ("IN", "LIQ", 5e6, True, None),        # kept
        ("IN", "ILLIQ", 1e5, True, 50.0),      # below $250k/day
        ("US", "DOWN", 9e6, False, -10.0),     # fails market validation
        ("US", "MOM", 9e6, False, 12.0),       # kept via Ret252 > 0
        ("FR", "NOMKT", 9e6, True, 10.0),      # country not in COUNTRY_TO_MARKET
        ("US", "BANK", 9e6, True, 10.0),       # not a focus industry
    ] + [("US", f"S{i}", 1e6 + i, True, 1.0) for i in range(10)]   # 10 semis: shortlist keeps top 8
    pd.DataFrame([dict(Market=m, Symbol=s, Name=s, Close=1.0, Turnover_USD=t, Above200DMA=a, Ret252=r)
                  for m, s, t, a, r in uni]).to_parquet(seed / "cache_seed/company_list.parquet")
    dam = [("LIQ", "India", "Steel"), ("ILLIQ", "India", "Steel"), ("DOWN", "United States", "Steel"),
           ("MOM", "United States", "Power"), ("NOMKT", "France", "Steel"), ("BANK", "United States", "Banks (Regional)"),
           ("MOM", "United States", "Power")]  # duplicate Damodaran row must not duplicate the company
    dam += [(f"S{i}", "United States", "Semiconductor") for i in range(10)]
    pd.DataFrame([dict(Ticker=t, Country=c, **{"Industry Group": g}) for t, c, g in dam]
                 ).to_parquet(seed / "reference_seed/damodaran_companies.parquet")
    monkeypatch.setattr(bs, "HOME", tmp_path)
    monkeypatch.setattr(bs, "OUT", tmp_path)
    bs.main()
    sc = pd.read_csv(tmp_path / "focus_sector_screen.csv")
    assert set(sc.Symbol) == {"LIQ", "MOM"} | {f"S{i}" for i in range(10)}
    assert sc.set_index("Symbol").loc["LIQ", "Region"] == "India"
    assert sc.set_index("Symbol").loc["MOM", "FocusSector"] == "Green Energy & Fuels"
    sl = pd.read_csv(tmp_path / "shortlist_for_enrichment.csv")
    semis = sl[sl.FocusSector == "Electronics & Semiconductors"]
    assert list(semis.Symbol) == [f"S{i}" for i in range(9, 1, -1)]   # top 8 by turnover
