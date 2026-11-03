# Focus-Sector Investor Map

Pairs India's focus-sector policy machinery with the global equity universe: which listed companies operate in the twelve
focus sectors, which of them are verified profitable and show global-expansion signals, and which foreign investing
companies pair with which government initiative. Domain: Indian trade/industrial policy and global listed equities.
Outputs are CSV and JSON files under `data/`.

> Status: maintained. Research output, not investment advice. Every pairing is grounded in the PIB-verified record of
> the companion policy program; profitability comes from trailing yfinance data and is not audited.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/herrrickshaw/focus-sector-investor-map/blob/main/notebooks/colab_test.ipynb)
New here? See [How to use this repo with AI](HOW_TO_USE_WITH_AI.md).

## What it does
- Maps Damodaran industry groups to the program's 12 focus sectors and joins them to a 20-market tradable universe.
- Screens for liquidity (turnover of at least $250k/day) and market validation (above 200DMA or positive 1-year return).
- Verifies profitability per shortlisted name via yfinance (profit margin > 0 and ROE > 0); anything else is excluded.
- Flags an expansion signal (revenue growth >= 10% y/y or 1-year return >= 25%).
- Builds a coverage catalog of every Damodaran-classified company in the 12 sectors, plus a sector x country matrix.
- Keeps a hand-curated file pairing foreign investors with government initiatives, including negative findings.

## Quick start
```bash
git clone https://github.com/herrrickshaw/focus-sector-investor-map.git
cd focus-sector-investor-map
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python3 scripts/build_screen.py        # needs the global-stock-screener parquets, see Configuration
```

## How it works
| Stage | Script | Output |
|---|---|---|
| Sector join + liquidity/momentum screen | `scripts/build_screen.py` | `focus_sector_screen.csv`, `shortlist_for_enrichment.csv` |
| Per-name profitability (yfinance, ~3 min) | `scripts/enrich_profitability.py` | `shortlist_enriched.csv`, `focus_sector_companies_final.csv` / `.json` |
| Coverage layer (no gates) | `scripts/build_global_catalog.py` | `focus_sector_global_catalog.csv`, `focus_sector_country_matrix.csv` |
| Sweep of never-verified catalog rows | `scripts/enrich_medical_devices_unswept.py`, `scripts/enrich_electronics_semiconductors_unswept.py` | `medical_devices_unswept_enriched.csv`, `electronics_semiconductors_unswept_enriched.csv` |

The scripts are thin CLI wrappers (load, then transform, then write). The pure logic lives in the `focus_sector_map`
package: `sectors` (industry-to-sector tables), `screen` (join, screen, shortlist), `tickers` (Yahoo suffix rules),
`fundamentals` (classification and a retrying, injectable yfinance fetcher), `catalog` (joins and aggregates) and
`paths` (locations and file names).

### Method (and its stated limits)

1. **Sector layer**: Damodaran Industry Groups mapped to the program's 12 focus sectors (electronics/semis, pharma, medical devices, auto/EV, specialty steel, chemicals/plastics, white goods, aerospace, shipbuilding, textiles, food processing, green energy/fuels).
2. **Join**: ticker × country to the tradable universe — conservative by design (2,217 of 38k joined; unmatched tickers are dropped, not guessed).
3. **Screen**: liquidity floor ($250k/day turnover) + market validation (above 200DMA or positive 1-year return). *This is not profitability.*
4. **Profitability is verified per name** (yfinance: profit margin > 0 AND ROE > 0) on the sector×region shortlist; names failing or unresolvable are **excluded from the final list** — nothing is silently assumed profitable.
5. **Expansion signal** (stated proxy): revenue growth ≥ 10% y/y or 1-year return ≥ 25%.
6. **Pairings**: [`data/foreign_investor_initiative_pairs.json`](data/foreign_investor_initiative_pairs.json) — verified pairs carry PRIDs (Foxconn/Samsung→LSEM→MPMS, Micron/PSMC/Renesas→ISM, First Solar→PLI-T2/ALMM, AM/NS→Specialty Steel), prospective pairs name the Cabinet-approved lane (Semicon 2.0 equipment pillar→AMAT/LRCX, shipbuilding package, NIPU-2026), and **negative findings are kept** (POSCO-JSW's missing EC application, Hyundai's lapsed ACC award, White Goods 85→80 attrition).

## Repository layout
| Path | Purpose |
|---|---|
| `scripts/` | Five CLI entry points (names and flags unchanged) |
| `focus_sector_map/` | I/O-free building blocks used by the scripts |
| `tests/` | pytest suite on synthetic rows; no network, no real inputs |
| `data/` | Tracked outputs (CSV/JSON) and the curated investor-initiative pairing file |
| `notebooks/` | `colab_test.ipynb` |
| `graphify-out/` | Generated knowledge-graph cache |

## Outputs

| File | Contents |
|---|---|
| `data/focus_sector_global_catalog.csv` | The coverage layer: 19,795 companies, 107 countries; market/profitability fields are attributes, not gates |
| `data/focus_sector_country_matrix.csv` | Sector x country counts (the courting map) |
| `data/focus_sector_screen.csv` | 894 liquid, market-validated companies across 12 focus sectors x India/Foreign |
| `data/shortlist_enriched.csv` | 175-name shortlist with per-name profitability fields |
| `data/focus_sector_companies_final.csv` / `.json` | Verified-profitable names, with expansion signals |
| `data/foreign_investor_initiative_pairs.json` | Foreign investors and government initiatives (verified, prospective, stalled) |

## Data sources
| Source | What is taken | Access route | Licence / caveat |
|---|---|---|---|
| [`india-trade-sector-policy-recommendations`](https://github.com/herrrickshaw/india-trade-sector-policy-recommendations) | 122,141-release PIB register, scheme registry, ministry catalog, matured-cohort verdicts, decade report card | Companion repo; informs the pairing file | See that repo |
| Multi-market screener stack (`company_list.parquet`) | 38,495-company universe, 20 markets, liquidity/momentum | Local `global-stock-screener` checkout | Local data, not redistributed here |
| Damodaran industry classification (`damodaran_companies.parquet`) | 48,156 companies, Industry Group and Country | Same checkout | Check Damodaran's terms |
| yfinance `.info` | profitMargins, returnOnEquity, revenueGrowth | Network, per ticker | Unofficial; trailing, not point-in-time |

## Configuration
- `GSS_ROOT` (default `~/repos/global-stock-screener`) or `--gss-root`: checkout holding `cache_seed/company_list.parquet`
  and `reference_seed/damodaran_companies.parquet` (`build_screen.py`, `build_global_catalog.py`).
- `--data-dir` (default `data/`): input and output directory for every script.
- No secrets or API keys are required.

## Testing
```bash
pytest -q
```

## Limitations and known issues
- The ticker x country join under-covers (conservative matching); EU-aggregate and some CN listings drop out.
- Profitability is trailing (yfinance `.info`), not point-in-time audited; UNVERIFIED does not mean unprofitable, it
  means the data source could not resolve the name.
- "Expansion" is a stated proxy, not a declaration of intent; the pairing file is where intent is evidenced
  (Cabinet approvals, PIB-credited production).
- Scheme-side facts inherit the policy program's corrections discipline; see its scheme registry for displayed revisions.
- The two `enrich_*_unswept` scripts call yfinance for thousands of rows and are slow and rate-limit prone.
- `data/` files are tracked outputs; the scripts overwrite them when run with the default `--data-dir`.

## Related repositories
- [`india-trade-sector-policy-recommendations`](https://github.com/herrrickshaw/india-trade-sector-policy-recommendations):
  the [investor workflow](https://herrrickshaw.github.io/india-trade-sector-policy-recommendations/charts/investor_workflow.html)
  (NSWS route, ministry connects) and the
  [decade report card](https://herrrickshaw.github.io/india-trade-sector-policy-recommendations/charts/decade_report_card.html)
  (which designs actually pay).

## Licence
No licence file yet; all rights reserved.
