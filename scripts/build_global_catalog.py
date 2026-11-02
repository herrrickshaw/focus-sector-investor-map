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
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run as a script without installing

from focus_sector_map import paths  # noqa: E402
from focus_sector_map.catalog import (  # noqa: E402
    PROFITABILITY_COLUMNS,
    attach_market_layer,
    attach_profitability,
    country_matrix,
    finalize_catalog,
    top_countries_by_sector,
)
from focus_sector_map.sectors import tag_focus_sectors  # noqa: E402

log = logging.getLogger(__name__)


def build_catalog(damodaran_path: Path, universe_path: Path, enriched_path: Path) -> pd.DataFrame:
    """Sector-tag the full Damodaran universe and left-join market + profitability attributes."""
    catalog = tag_focus_sectors(pd.read_parquet(damodaran_path))
    catalog = attach_market_layer(catalog, pd.read_parquet(universe_path))
    try:
        enriched = pd.read_csv(enriched_path)[PROFITABILITY_COLUMNS]
    except FileNotFoundError:
        log.info("no enriched shortlist at %s; profitability columns left out", enriched_path)
    else:
        catalog = attach_profitability(catalog, enriched)
    return finalize_catalog(catalog)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gss-root", type=Path, default=paths.GSS_ROOT,
                        help="global-stock-screener checkout holding the two input parquets")
    parser.add_argument("--data-dir", type=Path, default=paths.DATA_DIR,
                        help="directory holding shortlist_enriched.csv and receiving the outputs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)
    catalog = build_catalog(args.gss_root / "reference_seed" / "damodaran_companies.parquet",
                            args.gss_root / "cache_seed" / "company_list.parquet",
                            args.data_dir / paths.SHORTLIST_ENRICHED_CSV)
    catalog.to_csv(args.data_dir / paths.CATALOG_CSV, index=False)
    country_matrix(catalog).to_csv(args.data_dir / paths.COUNTRY_MATRIX_CSV, index=False)

    print(f"global catalog: {len(catalog):,} companies in focus sectors, {catalog['Country'].nunique()} countries")
    for sector, top in top_countries_by_sector(catalog).items():
        print(f"  {sector:<32} {len(catalog[catalog.FocusSector == sector]):>5}  | top: {top}")


if __name__ == "__main__":
    main()
