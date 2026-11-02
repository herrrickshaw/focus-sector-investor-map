"""Coverage layer: every focus-sector company, with market/profitability fields as attributes, not gates."""
from __future__ import annotations

import pandas as pd

MARKET_LAYER_COLUMNS = ["Market", "Symbol", "Turnover_USD", "Above200DMA", "Ret252", "Close"]
PROFITABILITY_COLUMNS = ["Market", "Symbol", "profit_margin", "roe", "revenue_growth", "verified"]
CATALOG_COLUMNS = ["FocusSector", "Industry Group", "Country", "Exchange", "Ticker", "Company Name",
                   "Market", "Turnover_USD", "Above200DMA", "Ret252",
                   "profit_margin", "roe", "revenue_growth", "verified"]
CATALOG_SORT_KEYS = ["FocusSector", "Country", "Company Name"]


def _left_join_on_ticker(catalog: pd.DataFrame, attrs: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return (catalog.merge(attrs[columns], left_on=["Ticker", "Market"], right_on=["Symbol", "Market"], how="left")
            .drop(columns=["Symbol"]))


def attach_market_layer(catalog: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    """Left-join liquidity/momentum attributes from the tradable universe."""
    return _left_join_on_ticker(catalog, universe, MARKET_LAYER_COLUMNS)


def attach_profitability(catalog: pd.DataFrame, enriched: pd.DataFrame) -> pd.DataFrame:
    """Left-join per-name profitability fields from the enriched shortlist."""
    return _left_join_on_ticker(catalog, enriched, PROFITABILITY_COLUMNS)


def finalize_catalog(catalog: pd.DataFrame) -> pd.DataFrame:
    """Sort by sector/country/name and keep the catalog columns that are present."""
    columns = [c for c in CATALOG_COLUMNS if c in catalog.columns]
    return catalog.sort_values(CATALOG_SORT_KEYS)[columns]


def country_matrix(catalog: pd.DataFrame) -> pd.DataFrame:
    """FocusSector x Country company counts (the courting map)."""
    return catalog.groupby(["FocusSector", "Country"]).size().rename("Companies").reset_index()


def top_countries_by_sector(catalog: pd.DataFrame, n: int = 5) -> pd.Series:
    """Per sector, a 'Country count, ...' string of the `n` most represented countries."""
    return (catalog.groupby("FocusSector")["Country"]
            .apply(lambda s: ", ".join(f"{c} {k}" for c, k in s.value_counts().head(n).items())))


def unswept_rows(catalog: pd.DataFrame, sector: str) -> pd.DataFrame:
    """Rows of one focus sector whose `verified` field is blank (never swept by an enrichment pass)."""
    in_sector = catalog[catalog["FocusSector"] == sector].copy()
    blank = in_sector["verified"].isna() | (in_sector["verified"].astype(str).str.strip() == "")
    return in_sector[blank].copy()
