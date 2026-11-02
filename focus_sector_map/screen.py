"""Liquidity + market-validation screen over the sector-tagged tradable universe (pure functions)."""
from __future__ import annotations

import pandas as pd

from focus_sector_map.sectors import region_of

MIN_TURNOVER_USD = 250_000  # liquidity floor, USD/day
SHORTLIST_PER_GROUP = 8  # top names per FocusSector x Region, by turnover

SECTOR_JOIN_COLUMNS = ["Ticker", "Market", "FocusSector", "Industry Group", "Country"]
SCREEN_COLUMNS = ["FocusSector", "Region", "Market", "Symbol", "Name", "Industry Group",
                  "Country", "Close", "Turnover_USD", "Above200DMA", "Ret252"]
SORT_KEYS = ["FocusSector", "Region", "Turnover_USD"]
SORT_ASCENDING = [True, True, False]


def join_universe(universe: pd.DataFrame, sectors: pd.DataFrame) -> pd.DataFrame:
    """Inner-join the tradable universe to sector-tagged Damodaran rows on (Symbol, Market).

    Rows without a mapped `Market` are dropped before the join; unmatched tickers are dropped, not guessed.
    """
    sectors = sectors.dropna(subset=["Market"])
    return (universe.merge(sectors[SECTOR_JOIN_COLUMNS],
                           left_on=["Symbol", "Market"], right_on=["Ticker", "Market"], how="inner")
            .drop(columns=["Ticker"])
            .drop_duplicates(subset=["Market", "Symbol"]))


def apply_screen(joined: pd.DataFrame, min_turnover_usd: float = MIN_TURNOVER_USD) -> pd.DataFrame:
    """Keep liquid (turnover >= floor) and market-validated (above 200DMA OR positive 1y return) names."""
    liquid = joined["Turnover_USD"] >= min_turnover_usd
    validated = joined["Above200DMA"].eq(True) | (joined["Ret252"] > 0)
    screened = joined[liquid & validated].copy()
    screened["Region"] = screened["Market"].map(region_of)
    return screened.sort_values(SORT_KEYS, ascending=SORT_ASCENDING)


def select_shortlist(screened: pd.DataFrame, per_group: int = SHORTLIST_PER_GROUP) -> pd.DataFrame:
    """Top `per_group` rows per FocusSector x Region (input must already be sorted by turnover desc)."""
    return screened.groupby(["FocusSector", "Region"], group_keys=False).head(per_group)


def sector_region_counts(screened: pd.DataFrame) -> pd.DataFrame:
    """FocusSector x Region count table for the CLI summary."""
    return screened.groupby(["FocusSector", "Region"]).size().unstack(fill_value=0)
