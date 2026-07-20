#!/usr/bin/env python3
"""
build_screen.py — screen the multi-market equity universe into the trade-policy
program's focus sectors, keep liquid + market-validated names, and (separately)
verify profitability for the shortlist.

Inputs (local, from the user's market-data stack):
  ~/repos/global-stock-screener/cache_seed/company_list.parquet   38,495 names,
      20 markets: Market, Symbol, Name, Close, Turnover_USD, Above200DMA, Ret252
  ~/repos/global-stock-screener/reference_seed/damodaran_companies.parquet
      48,156 names: Ticker, Country, Industry Group (the sector layer)

Method (stated limits, per house rules):
  1. Sector layer: Damodaran Industry Group -> the program's 12 focus sectors.
  2. Join by (Ticker, Country) to the tradable universe.
  3. Screen: liquidity (Turnover_USD >= $250k/day) + market validation
     (Above200DMA true OR Ret252 > 0). This is NOT profitability.
  4. Shortlist: top names per sector x region by turnover; profitability is
     then verified per-name via yfinance (profit margin, ROE) in
     enrich_profitability.py -- names failing verification are dropped from
     the final list, not silently kept.

Outputs: data/focus_sector_screen.csv (full screened set)
         data/shortlist_for_enrichment.csv
"""
import pandas as pd
from pathlib import Path

HOME = Path.home()
OUT = Path(__file__).resolve().parent.parent / "data"
OUT.mkdir(exist_ok=True)

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

MIN_TURNOVER_USD = 250_000  # liquidity floor per day


def main():
    uni = pd.read_parquet(HOME / "repos/global-stock-screener/cache_seed/company_list.parquet")
    dam = pd.read_parquet(HOME / "repos/global-stock-screener/reference_seed/damodaran_companies.parquet")

    ind_to_focus = {ind: sec for sec, inds in FOCUS.items() for ind in inds}
    dam = dam[dam["Industry Group"].isin(ind_to_focus)].copy()
    dam["FocusSector"] = dam["Industry Group"].map(ind_to_focus)
    dam["Market"] = dam["Country"].map(COUNTRY_TO_MARKET)
    dam = dam.dropna(subset=["Market"])

    j = uni.merge(
        dam[["Ticker", "Market", "FocusSector", "Industry Group", "Country"]],
        left_on=["Symbol", "Market"], right_on=["Ticker", "Market"], how="inner",
    ).drop(columns=["Ticker"]).drop_duplicates(subset=["Market", "Symbol"])

    screened = j[(j["Turnover_USD"] >= MIN_TURNOVER_USD)
                 & ((j["Above200DMA"] == True) | (j["Ret252"] > 0))].copy()
    screened["Region"] = screened["Market"].map(lambda m: "India" if m == "IN" else "Foreign")
    screened = screened.sort_values(["FocusSector", "Region", "Turnover_USD"], ascending=[True, True, False])

    cols = ["FocusSector", "Region", "Market", "Symbol", "Name", "Industry Group",
            "Country", "Close", "Turnover_USD", "Above200DMA", "Ret252"]
    screened[cols].to_csv(OUT / "focus_sector_screen.csv", index=False)

    shortlist = (screened.groupby(["FocusSector", "Region"], group_keys=False)
                 .head(8))
    shortlist[cols].to_csv(OUT / "shortlist_for_enrichment.csv", index=False)

    print(f"universe joined to focus sectors: {len(j):,}")
    print(f"screened (liquidity + market validation): {len(screened):,}")
    print(f"shortlist for profitability verification: {len(shortlist):,}")
    print(screened.groupby(["FocusSector", "Region"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
