#!/usr/bin/env python3
"""
enrich_profitability.py — verify profitability per shortlisted company via
yfinance (.info: profitMargins, returnOnEquity, revenueGrowth, totalRevenue).
Names that fail verification (margin<=0 or ROE<=0) are DROPPED from the final
list; names yfinance cannot resolve are marked UNVERIFIED and kept out of the
final list too — nothing is silently assumed profitable.

Expansion signal (stated proxy): revenueGrowth >= 10% y/y OR Ret252 >= 25%.
Output: data/focus_sector_companies_final.csv (+ .json)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run as a script without installing

from focus_sector_map import paths  # noqa: E402
from focus_sector_map.fundamentals import (  # noqa: E402
    NOT_PROFITABLE,
    UNVERIFIED,
    Fundamentals,
    add_expansion_signal,
    enrich_records,
    fetch_fundamentals,
    select_final,
)
from focus_sector_map.tickers import market_ticker  # noqa: E402

PAUSE_SECONDS = 0.5  # between yfinance calls


def yf_ticker(row: pd.Series) -> Optional[str]:
    """Yahoo Finance ticker for a shortlist row (Market + Symbol); None when unresolvable."""
    return market_ticker(row["Market"], row["Symbol"])


def yfinance_fetcher():
    """Default fetcher: one `.info` call per ticker, no retries (yfinance imported lazily)."""
    import yfinance as yf

    def fetch(ticker: str) -> Fundamentals:
        return fetch_fundamentals(ticker, info_getter=lambda t: yf.Ticker(t).info)

    return fetch


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=paths.DATA_DIR,
                        help="directory holding shortlist_for_enrichment.csv and receiving the outputs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.WARNING, format="  [%(message)s]")
    args = parse_args(argv)
    shortlist = pd.read_csv(args.data_dir / paths.SHORTLIST_CSV)

    rows = []
    for rec in enrich_records(shortlist, build_ticker=lambda r: (yf_ticker(r), None),
                              fetch=yfinance_fetcher(), pause_seconds=PAUSE_SECONDS, reason_column=None):
        rows.append(rec)
        print(f"  {rec['Market']}:{rec['Symbol']:<12} {rec['verified']:<15} pm={rec['profit_margin']}")

    df = add_expansion_signal(pd.DataFrame(rows))
    final = select_final(df)
    df.to_csv(args.data_dir / paths.SHORTLIST_ENRICHED_CSV, index=False)
    final.to_csv(args.data_dir / paths.FINAL_CSV, index=False)
    final.to_json(args.data_dir / paths.FINAL_JSON, orient="records", indent=1)
    print(f"\nenriched {len(df)} | PROFITABLE {len(final)} | "
          f"NOT-PROFITABLE {(df['verified'] == NOT_PROFITABLE).sum()} | "
          f"UNVERIFIED {(df['verified'] == UNVERIFIED).sum()}")
    print(f"with expansion signal: {int(final['expansion_signal'].sum())}")


if __name__ == "__main__":
    main()
