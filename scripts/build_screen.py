#!/usr/bin/env python3
"""
build_screen.py — screen the multi-market equity universe into the trade-policy
program's focus sectors, keep liquid + market-validated names, and (separately)
verify profitability for the shortlist.

Inputs (local, from the user's market-data stack; override with --gss-root or $GSS_ROOT):
  <gss-root>/cache_seed/company_list.parquet        38,495 names,
      20 markets: Market, Symbol, Name, Close, Turnover_USD, Above200DMA, Ret252
  <gss-root>/reference_seed/damodaran_companies.parquet
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
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run as a script without installing

from focus_sector_map import paths  # noqa: E402
from focus_sector_map.screen import (  # noqa: E402
    SCREEN_COLUMNS,
    apply_screen,
    join_universe,
    sector_region_counts,
    select_shortlist,
)
from focus_sector_map.sectors import tag_focus_sectors  # noqa: E402


def build_screen(universe_path: Path, damodaran_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load both parquet layers and return (joined, screened, shortlist)."""
    universe = pd.read_parquet(universe_path)
    damodaran = pd.read_parquet(damodaran_path)
    joined = join_universe(universe, tag_focus_sectors(damodaran))
    screened = apply_screen(joined)
    return joined, screened, select_shortlist(screened)


def write_outputs(screened: pd.DataFrame, shortlist: pd.DataFrame, data_dir: Path) -> None:
    data_dir.mkdir(exist_ok=True)
    screened[SCREEN_COLUMNS].to_csv(data_dir / paths.SCREEN_CSV, index=False)
    shortlist[SCREEN_COLUMNS].to_csv(data_dir / paths.SHORTLIST_CSV, index=False)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gss-root", type=Path, default=paths.GSS_ROOT,
                        help="global-stock-screener checkout holding the two input parquets")
    parser.add_argument("--data-dir", type=Path, default=paths.DATA_DIR, help="output directory")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    joined, screened, shortlist = build_screen(args.gss_root / "cache_seed" / "company_list.parquet",
                                               args.gss_root / "reference_seed" / "damodaran_companies.parquet")
    write_outputs(screened, shortlist, args.data_dir)

    print(f"universe joined to focus sectors: {len(joined):,}")
    print(f"screened (liquidity + market validation): {len(screened):,}")
    print(f"shortlist for profitability verification: {len(shortlist):,}")
    print(sector_region_counts(screened).to_string())


if __name__ == "__main__":
    main()
