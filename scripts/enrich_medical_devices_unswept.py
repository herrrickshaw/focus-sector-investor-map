#!/usr/bin/env python3
"""
enrich_medical_devices_unswept.py — financial verification pass over the 834
Medical Devices companies in data/focus_sector_global_catalog.csv that have
NEVER been swept (FocusSector == 'Medical Devices' AND verified is blank).

Isolated, standalone script. Reuses the exact yfinance-field-pulling logic
and PROFITABLE/NOT-PROFITABLE/UNVERIFIED screen from scripts/enrich_profitability.py
(profit_margin>0 AND roe>0; expansion_signal = revenue_growth>=0.10 OR Ret252>=0.25)
but:
  - reads ONLY from data/focus_sector_global_catalog.csv (never touches
    shortlist_for_enrichment.csv / shortlist_enriched.csv /
    focus_sector_companies_final.csv[.json] — those are a separate,
    in-progress, uncommitted pipeline owned by someone else in the sibling
    digital-twin-for-ipa repo)
  - writes ONLY to data/medical_devices_unswept_enriched.csv (new file)

Bug fixed here vs enrich_profitability.py: that script's SUFFIX dict is keyed
by a `Market` column that is NULL for a long tail of countries (France,
Israel, Poland, Belgium, Netherlands, Italy, Norway, Indonesia, Bulgaria,
Thailand, Turkey, Bangladesh, New Zealand, Romania, Greece, Iceland, Ireland,
Qatar, Spain, Malaysia) in this catalog — those rows would silently come back
UNVERIFIED regardless of true profitability. This script instead derives the
yfinance suffix from the `Exchange` column (present on every row), which is
the actually-correct basis for a Yahoo Finance ticker suffix (listing venue,
not country of domicile). Spot-checked live against known real tickers before
use: SAN.PA (Sanofi, France/Euronext Paris), ICL.TA / TEVA.TA (Israel/Tel
Aviv), PKN.WA (Poland/Warsaw) all resolved correctly via yfinance.
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
from focus_sector_map.catalog import unswept_rows  # noqa: E402
from focus_sector_map.fundamentals import (  # noqa: E402
    PROFITABLE,
    Fundamentals,
    add_expansion_signal,
    enrich_records,
    fetch_fundamentals,
    verification_counts,
)

SECTOR = "Medical Devices"
OUT_NAME = "medical_devices_unswept_enriched.csv"
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 5  # x attempt number
PAUSE_SECONDS = 0.75
KOREAN_EXCHANGES = ("KOSDAQ", "KOSE", "XKON")
HK_TICKER_WIDTH = 4

# Exchange (MIC-ish code as used in this catalog's `Exchange` column) -> Yahoo
# Finance ticker suffix. '' = US-style (no suffix). None = confirmed not
# resolvable via yfinance (exchange has no Yahoo Finance coverage) -- kept
# explicit so these get counted separately from "still missing mapping" bugs.
EXCHANGE_SUFFIX = {
    # Americas
    "NYSE": "", "NYSEAM": "", "NasdaqCM": "", "NasdaqGM": "", "NasdaqGS": "",
    "OTCPK": "", "TSX": ".TO", "TSXV": ".V", "CNSX": ".CN",
    # Greater China / HK
    "SHSE": ".SS", "SZSE": ".SZ", "SEHK": ".HK",
    # Japan / Korea / Taiwan
    "TSE": ".T", "KOSDAQ": ".KQ", "KOSE": ".KS", "XKON": ".KQ",
    "TPEX": ".TWO", "TWSE": ".TW",
    # India
    "BSE": ".BO", "NSEI": ".NS",
    # UK / Ireland
    "LSE": ".L", "AIM": ".L",
    # DACH
    "XTRA": ".DE", "DB": ".DE", "BST": ".DE", "SWX": ".SW",
    # Nordics
    "CPSE": ".CO", "HLSE": ".HE", "OB": ".OL",
    # Benelux / France
    "ENXTPA": ".PA", "ENXTBR": ".BR", "ENXTAM": ".AS",
    # Southern / Eastern Europe
    "BIT": ".MI", "BME": ".MC", "WSE": ".WA", "BVB": ".RO",
    "ATSE": ".AT", "IBSE": ".IS",
    "BUL": None,  # Bulgarian Stock Exchange -- not covered by yfinance
    # Middle East / Israel
    "TASE": ".TA", "SASE": ".SR", "DSM": None,  # Qatar -- not covered
    # SE Asia / Oceania
    "SGX": ".SI", "Catalist": ".SI", "KLSE": ".KL", "IDX": ".JK",
    "SET": ".BK", "ASX": ".AX", "NZSE": ".NZ",
    "DSE": None,  # Dhaka Stock Exchange, Bangladesh -- not covered
}

# A handful of exchange codes are shared by more than one country in this
# catalog with genuinely different suffixes (OM/NGM/XSAT are Nordic boards
# used by both Sweden and Denmark/UK listings). Country disambiguates those.
COUNTRY_EXCHANGE_OVERRIDE = {
    ("OM", "Sweden"): ".ST",
    ("OM", "Denmark"): ".CO",
    ("NGM", "Sweden"): ".ST",
    ("NGM", "United Kingdom"): ".ST",
    ("XSAT", "Sweden"): ".ST",
}


def yf_ticker(row: pd.Series) -> tuple[Optional[str], Optional[str]]:
    """Build a yfinance ticker from Exchange + Ticker (+ Country for a few
    ambiguous Nordic exchange codes). Returns (ticker_or_None, reason_if_None)."""
    exch = row["Exchange"]
    country = row["Country"]
    sym = str(row["Ticker"]).strip()

    if (exch, country) in COUNTRY_EXCHANGE_OVERRIDE:
        suffix = COUNTRY_EXCHANGE_OVERRIDE[(exch, country)]
    elif exch in EXCHANGE_SUFFIX:
        suffix = EXCHANGE_SUFFIX[exch]
    else:
        return None, f"unmapped_exchange:{exch}"

    if suffix is None:
        return None, f"exchange_not_on_yfinance:{exch}"

    # Share-class tickers stored with a space ("GTAB B") -> hyphenated form
    # ("GTAB-B") is what Yahoo Finance expects.
    sym = sym.replace(" ", "-")

    # Korean tickers in this catalog carry a leading 'A' market-data-vendor
    # prefix (e.g. A455900) that yfinance does not use (455900.KQ).
    if exch in KOREAN_EXCHANGES and sym.startswith("A") and sym[1:].isdigit():
        sym = sym[1:]

    # HK tickers should be 4-digit zero-padded.
    if exch == "SEHK" and sym.isdigit():
        sym = sym.zfill(HK_TICKER_WIDTH)

    return sym + suffix, None


def yfinance_fetcher():
    """Default fetcher: `.info` with 3 attempts and linear backoff on HTTP 429."""
    import yfinance as yf

    def fetch(ticker: str) -> Fundamentals:
        return fetch_fundamentals(ticker, info_getter=lambda t: yf.Ticker(t).info,
                                  max_attempts=MAX_ATTEMPTS, backoff_seconds=BACKOFF_SECONDS)

    return fetch


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=paths.DATA_DIR,
                        help="directory holding focus_sector_global_catalog.csv and receiving the output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.WARNING, format="  [%(message)s]")
    args = parse_args(argv)
    out_csv = args.data_dir / OUT_NAME

    catalog = pd.read_csv(args.data_dir / paths.CATALOG_CSV)
    unswept = unswept_rows(catalog, SECTOR)
    n = len(unswept)
    print(f"{SECTOR} total: {(catalog['FocusSector'] == SECTOR).sum()} | unswept (target for this run): {n}")

    records = enrich_records(unswept, build_ticker=yf_ticker, fetch=yfinance_fetcher(), pause_seconds=PAUSE_SECONDS)
    rows = []
    for i, rec in enumerate(records, 1):
        rows.append(rec)
        print(f"  [{i}/{n}] {rec['Country']}:{rec['Exchange']}:{rec['Ticker']:<14} yf={str(rec['yf']):<16} "
              f"{rec['verified']:<15} pm={rec['profit_margin']} roe={rec['roe']}")

    df = add_expansion_signal(pd.DataFrame(rows))
    df.to_csv(out_csv, index=False)

    counts = verification_counts(df)
    print(f"\nWrote {len(df)} rows -> {out_csv}")
    print(f"PROFITABLE {counts['profitable']} | NOT-PROFITABLE {counts['not_profitable']} | "
          f"UNVERIFIED {counts['unverified']}")
    print(f"  of which UNVERIFIED due to unmapped/unsupported exchange (no ticker built): {counts['unmapped']}")
    print(f"  of which UNVERIFIED due to genuine yfinance data gap (ticker built, no financials): {counts['data_gap']}")
    print(f"with expansion signal ({PROFITABLE} only): {counts['expansion_profitable']}")


if __name__ == "__main__":
    main()
