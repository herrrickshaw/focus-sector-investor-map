"""Repository and external-data locations, overridable from the CLI or environment."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# The market and sector layers live in the sibling global-stock-screener checkout.
GSS_ROOT = Path(os.environ.get("GSS_ROOT", str(Path.home() / "repos" / "global-stock-screener")))
UNIVERSE_PARQUET = GSS_ROOT / "cache_seed" / "company_list.parquet"
DAMODARAN_PARQUET = GSS_ROOT / "reference_seed" / "damodaran_companies.parquet"

# File names written under DATA_DIR.
SCREEN_CSV = "focus_sector_screen.csv"
SHORTLIST_CSV = "shortlist_for_enrichment.csv"
SHORTLIST_ENRICHED_CSV = "shortlist_enriched.csv"
FINAL_CSV = "focus_sector_companies_final.csv"
FINAL_JSON = "focus_sector_companies_final.json"
CATALOG_CSV = "focus_sector_global_catalog.csv"
COUNTRY_MATRIX_CSV = "focus_sector_country_matrix.csv"
