#!/usr/bin/env python3
"""
enrich_electronics_semiconductors_unswept.py -- financial verification pass
over the 3,433 Electronics & Semiconductors companies in
data/focus_sector_global_catalog.csv that have NEVER been swept
(FocusSector == 'Electronics & Semiconductors' AND verified is blank).

Batch 2 of the sector-by-sector rebuild (Batch 1 was Medical Devices,
scripts/enrich_medical_devices_unswept.py -- untouched by this script).

Isolated, standalone script:
  - reads ONLY data/focus_sector_global_catalog.csv
  - never touches shortlist_for_enrichment.csv / shortlist_enriched.csv /
    focus_sector_companies_final.csv[.json] (separate in-progress pipeline
    owned by someone else, per sibling digital-twin-for-ipa repo)
  - writes ONLY to data/electronics_semiconductors_unswept_enriched.csv,
    checkpointed incrementally every CHECKPOINT_EVERY rows

Two-tier ticker construction:
  1. Primary: Market column populated -> the shared MARKET_SUFFIX logic in
     focus_sector_map/tickers.py (IN/JP/KR/TW/DE/UK/HK/AU/CA/SE/CH/
     DK/FI/SG/BR/ZA/SA/US/CN/EU), keyed here off the catalog's `Ticker`
     column (the shortlist used `Symbol`; same field, different name).
  2. Fallback: Market is blank (318 of the 3,433 rows) -> derive suffix from
     `Exchange` instead. Mapping below was verified live
     against real yfinance calls (see EXCHANGE_SUFFIX_FALLBACK comments) --
     NOT copy-pasted from Batch 1's guesses, several codes behave
     differently for this sector's rows (e.g. IBSE, OB, BVB, RISE, BUSE,
     Catalist, HOSE all resolve fine via yfinance and are NOT treated as
     "obscure" here, contrary to the initial hypothesis; NGSE, KASE, BVMT,
     DSE, ZGSE, BUL confirmed genuinely unresolvable -- BUL bare-ticker
     lookups risk colliding with unrelated US-listed tickers of the same
     symbol, e.g. 'SLYG' bare resolved to a State Street ETF, not the
     Bulgarian company -- so BUL is skipped outright rather than risking a
     fabricated match).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
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
from focus_sector_map.tickers import MARKET_SUFFIX, market_ticker  # noqa: E402

SECTOR = "Electronics & Semiconductors"
OUT_NAME = "electronics_semiconductors_unswept_enriched.csv"
CHECKPOINT_EVERY = 40
PROGRESS_EVERY = 10
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 8  # x attempt number
PAUSE_SECONDS = 0.7

# ---- Tier 2: Exchange-based fallback for blank-Market rows ----
# "" = no suffix (US-primary listing regardless of domicile country)
# None = confirmed live: not reliably resolvable via yfinance
EXCHANGE_SUFFIX_FALLBACK = {
    "KLSE": ".KL", "ENXTPA": ".PA", "TASE": ".TA", "WSE": ".WA", "BIT": ".MI",
    "OB": ".OL", "SET": ".BK", "IBSE": ".IS", "TWSE": ".TW",
    "NasdaqCM": "", "NasdaqGS": "", "NasdaqGM": "", "NYSE": "",
    "IDX": ".JK", "ENXTBR": ".BR", "OTCPK": "", "HNX": ".VN",
    "ENXTAM": ".AS", "PSE": ".PS", "BVB": ".RO", "BME": ".MC",
    "AIM": ".L", "TPEX": ".TWO", "WBAG": ".VI", "SEP": ".PR",
    "TLSE": ".TL", "NZSE": ".NZ", "SWX": ".SW", "BUSE": ".BD",
    "LSE": ".L", "ASX": ".AX", "RISE": ".RG", "SEHK": ".HK",
    "Catalist": ".SI", "HOSE": ".VN",
    # confirmed genuinely unresolvable live
    "BUL": None, "DSE": None, "ZGSE": None, "NGSE": None,
    "KASE": None, "BVMT": None,
}
# ATSE is shared by Austria (WBAG-adjacent -> Vienna) and Greece (Athens) in
# this catalog -- disambiguate by country rather than a single fixed suffix.
COUNTRY_EXCHANGE_OVERRIDE = {
    ("ATSE", "Austria"): ".VI",
    ("ATSE", "Greece"): ".AT",
}
# Exchanges attempted live but confirmed to have no yfinance suffix that
# resolves the specific tickers in this catalog subset (kept explicit /
# reported honestly rather than silently folded into "unmapped").
OBSCURE_NO_YF_COVERAGE = {"BUL", "DSE", "ZGSE", "NGSE", "KASE", "BVMT"}
HK_TICKER_WIDTH = 4


def _clean(value: object) -> Optional[str]:
    return None if (pd.isna(value) or str(value).strip() == "") else str(value).strip()


def yf_ticker(row: pd.Series) -> tuple[Optional[str], Optional[str]]:
    """Returns (ticker_or_None, reason_if_None)."""
    market = _clean(row.get("Market"))
    sym = str(row["Ticker"]).strip().replace(" ", "-")
    exch = _clean(row.get("Exchange"))
    country = _clean(row.get("Country"))

    if market is not None:
        # ---- Tier 1 ----
        if market not in MARKET_SUFFIX:
            return None, f"unmapped_market:{market}"
        ticker = market_ticker(market, sym)
        if ticker is None:
            return None, f"market_no_suffix:{market}"
        return ticker, None

    # ---- Tier 2: blank Market, use Exchange ----
    if exch is None:
        return None, "no_market_no_exchange"

    override = COUNTRY_EXCHANGE_OVERRIDE.get((exch, country))
    if override is not None:
        return sym + override, None

    if exch not in EXCHANGE_SUFFIX_FALLBACK:
        return None, f"unmapped_exchange:{exch}"

    suffix = EXCHANGE_SUFFIX_FALLBACK[exch]
    if suffix is None:
        reason = "exchange_not_covered_by_yfinance" if exch in OBSCURE_NO_YF_COVERAGE else f"exchange_no_suffix:{exch}"
        return None, reason

    if exch == "SEHK" and sym.isdigit():
        sym = sym.zfill(HK_TICKER_WIDTH)

    return sym + suffix, None


def checkpoint(rows: list, out_csv: Path) -> pd.DataFrame:
    df = add_expansion_signal(pd.DataFrame(rows))
    df.to_csv(out_csv, index=False)
    return df


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
    print(f"{SECTOR} total: {(catalog['FocusSector'] == SECTOR).sum()} | unswept target: {n}", flush=True)

    rows: list = []
    start = time.time()
    records = enrich_records(unswept, build_ticker=yf_ticker, fetch=yfinance_fetcher(), pause_seconds=PAUSE_SECONDS)
    for i, rec in enumerate(records, 1):
        rows.append(rec)
        if i % PROGRESS_EVERY == 0 or i == n:
            elapsed = time.time() - start
            rate = i / elapsed if elapsed > 0 else 0
            eta_min = (n - i) / rate / 60 if rate > 0 else float("nan")
            print(f"  [{i}/{n}] {rec['Country']}:{rec.get('Exchange')}:{rec['Ticker']:<14} yf={str(rec['yf']):<16} "
                  f"{rec['verified']:<15} pm={rec['profit_margin']}  (elapsed={elapsed/60:.1f}m eta={eta_min:.1f}m)",
                  flush=True)
        if i % CHECKPOINT_EVERY == 0:
            checkpoint(rows, out_csv)
            print(f"  -- checkpointed {i} rows --", flush=True)

    df = checkpoint(rows, out_csv)
    counts = verification_counts(df)
    print(f"\nWrote {len(df)} rows -> {out_csv}")
    print(f"PROFITABLE {counts['profitable']} | NOT-PROFITABLE {counts['not_profitable']} | "
          f"UNVERIFIED {counts['unverified']}")
    print(f"  of which UNVERIFIED, no ticker built at all (unmapped/unsupported exchange or market): "
          f"{counts['unmapped']}")
    print(f"  of which UNVERIFIED, ticker built but yfinance had no financial data: {counts['data_gap']}")
    print(f"with expansion signal ({PROFITABLE} only): {counts['expansion_profitable']}")


if __name__ == "__main__":
    main()
