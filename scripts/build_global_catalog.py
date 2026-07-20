#!/usr/bin/env python3
"""
build_global_catalog.py — the COVERAGE layer: every company in the global
Damodaran universe (48,156 names, all exchanges/countries) mapped to the 12
sectors the Indian government is incentivizing. No profitability gate, no
liquidity gate — the question here is "which companies exist, where, in the
sectors India is courting", so the base is the full classification universe.

Market-layer columns (liquidity, momentum) and profitability fields are
LEFT-JOINED where available from the 20-market tradable universe and the
enriched shortlist — attributes, not filters.

Outputs:
  data/focus_sector_global_catalog.csv      (one row per company)
  data/focus_sector_country_matrix.csv      (sector x country counts)
"""
import pandas as pd
from pathlib import Path

HOME = Path.home()
OUT = Path(__file__).resolve().parent.parent / "data"

FOCUS = {
 "Electronics & Semiconductors": ["Semiconductor", "Semiconductor Equip", "Electronics (Consumer & Office)", "Electronics (General)", "Computers/Peripherals", "Telecom. Equipment"],
 "Pharma & Bulk Drugs": ["Drugs (Pharmaceutical)", "Drugs (Biotechnology)"],
 "Medical Devices": ["Healthcare Products"],
 "Auto, EV & Components": ["Auto & Truck", "Auto Parts"],
 "Specialty Steel & Metals": ["Steel", "Metals & Mining"],
 "Chemicals & Plastics": ["Chemical (Basic)", "Chemical (Diversified)", "Chemical (Specialty)", "Rubber& Tires", "Packaging & Container"],
 "White Goods & Electricals": ["Electrical Equipment", "Furn/Home Furnishings", "Household Products"],
 "Aerospace & Defence": ["Aerospace/Defense"],
 "Shipbuilding & Marine": ["Shipbuilding & Marine"],
 "Textiles & Apparel": ["Apparel", "Shoe"],
 "Food Processing": ["Food Processing"],
 "Green Energy & Fuels": ["Green & Renewable Energy", "Oil/Gas (Production and Exploration)", "Power", "Coal & Related Energy"],
}

COUNTRY_TO_MARKET = {
 "India": "IN", "United States": "US", "Japan": "JP", "South Korea": "KR",
 "Taiwan": "TW", "China": "CN", "Germany": "DE", "Canada": "CA",
 "Australia": "AU", "United Kingdom": "UK", "Hong Kong": "HK",
 "Singapore": "SG", "Sweden": "SE", "Brazil": "BR", "Switzerland": "CH",
 "Denmark": "DK", "Finland": "FI", "South Africa": "ZA", "Saudi Arabia": "SA",
}


def main():
    dam = pd.read_parquet(HOME / "repos/global-stock-screener/reference_seed/damodaran_companies.parquet")
    ind_to_focus = {ind: sec for sec, inds in FOCUS.items() for ind in inds}
    cat = dam[dam["Industry Group"].isin(ind_to_focus)].copy()
    cat["FocusSector"] = cat["Industry Group"].map(ind_to_focus)
    cat["Market"] = cat["Country"].map(COUNTRY_TO_MARKET)

    # market layer (attributes, not filters)
    uni = pd.read_parquet(HOME / "repos/global-stock-screener/cache_seed/company_list.parquet")
    cat = cat.merge(uni[["Market", "Symbol", "Turnover_USD", "Above200DMA", "Ret252", "Close"]],
                    left_on=["Ticker", "Market"], right_on=["Symbol", "Market"], how="left") \
             .drop(columns=["Symbol"])

    # profitability layer where enriched (attribute)
    try:
        enr = pd.read_csv(OUT / "shortlist_enriched.csv")[["Market", "Symbol", "profit_margin", "roe", "revenue_growth", "verified"]]
        cat = cat.merge(enr, left_on=["Ticker", "Market"], right_on=["Symbol", "Market"], how="left") \
                 .drop(columns=["Symbol"])
    except FileNotFoundError:
        pass

    cols = ["FocusSector", "Industry Group", "Country", "Exchange", "Ticker", "Company Name",
            "Market", "Turnover_USD", "Above200DMA", "Ret252",
            "profit_margin", "roe", "revenue_growth", "verified"]
    cols = [c for c in cols if c in cat.columns]
    cat = cat.sort_values(["FocusSector", "Country", "Company Name"])
    cat[cols].to_csv(OUT / "focus_sector_global_catalog.csv", index=False)

    matrix = cat.groupby(["FocusSector", "Country"]).size().rename("Companies").reset_index()
    matrix.to_csv(OUT / "focus_sector_country_matrix.csv", index=False)

    print(f"global catalog: {len(cat):,} companies in focus sectors, {cat['Country'].nunique()} countries")
    top = (cat.groupby("FocusSector")["Country"]
           .apply(lambda s: ", ".join(f"{c} {n}" for c, n in s.value_counts().head(5).items())))
    for sec, t in top.items():
        print(f"  {sec:<32} {len(cat[cat.FocusSector==sec]):>5}  | top: {t}")


if __name__ == "__main__":
    main()
