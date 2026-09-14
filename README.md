# Focus-Sector Investor Map

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/herrrickshaw/focus-sector-investor-map/blob/main/notebooks/colab_test.ipynb)

Pairs India's **focus-sector policy machinery** with the **equity universe**: which listed companies operate in the twelve focus sectors, which of them are verified profitable and showing global-expansion signals, and which **foreign investing companies pair with which government initiative** — every pairing grounded in the PIB-verified record of the companion policy program.

Built from two existing data programs:
- **Policy layer**: [`india-trade-sector-policy-recommendations`](https://github.com/herrrickshaw/india-trade-sector-policy-recommendations) — the 122,141-release PIB register, scheme registry, ministry catalog, matured-cohort verdicts, decade report card.
- **Market layer**: the multi-market screener stack — 38,495-company universe (20 markets, liquidity/momentum) + Damodaran's 48,156-company industry classification.

## Method (and its stated limits)

1. **Sector layer**: Damodaran Industry Groups mapped to the program's 12 focus sectors (electronics/semis, pharma, medical devices, auto/EV, specialty steel, chemicals/plastics, white goods, aerospace, shipbuilding, textiles, food processing, green energy/fuels).
2. **Join**: ticker × country to the tradable universe — conservative by design (2,217 of 38k joined; unmatched tickers are dropped, not guessed).
3. **Screen**: liquidity floor ($250k/day turnover) + market validation (above 200DMA or positive 1-year return). *This is not profitability.*
4. **Profitability is verified per name** (yfinance: profit margin > 0 AND ROE > 0) on the sector×region shortlist; names failing or unresolvable are **excluded from the final list** — nothing is silently assumed profitable.
5. **Expansion signal** (stated proxy): revenue growth ≥ 10% y/y or 1-year return ≥ 25%.
6. **Pairings**: [`data/foreign_investor_initiative_pairs.json`](data/foreign_investor_initiative_pairs.json) — verified pairs carry PRIDs (Foxconn/Samsung→LSEM→MPMS, Micron/PSMC/Renesas→ISM, First Solar→PLI-T2/ALMM, AM/NS→Specialty Steel), prospective pairs name the Cabinet-approved lane (Semicon 2.0 equipment pillar→AMAT/LRCX, shipbuilding package, NIPU-2026), and **negative findings are kept** (POSCO-JSW's missing EC application, Hyundai's lapsed ACC award, White Goods 85→80 attrition).

## Outputs

| File | Contents |
|---|---|
| `data/focus_sector_global_catalog.csv` | **The coverage layer: 19,795 companies, 107 countries** — every Damodaran-classified company in the 12 incentivized sectors; market/profitability fields as attributes, not gates |
| `data/focus_sector_country_matrix.csv` | Sector × country counts (the courting map) |
| `data/focus_sector_screen.csv` | 894 liquid, market-validated companies across 12 focus sectors × India/Foreign |
| `data/shortlist_enriched.csv` | 175-name shortlist with per-name profitability fields |
| `data/focus_sector_companies_final.csv` / `.json` | The final list: **verified-profitable** names, with expansion signals |
| `data/foreign_investor_initiative_pairs.json` | Foreign investors ↔ government initiatives (verified + prospective + stalled) |

## Reproduce

```bash
python3 scripts/build_screen.py            # sector join + liquidity/momentum screen
python3 scripts/enrich_profitability.py    # per-name verification (yfinance, ~3 min)
```

## Honest caveats

- The ticker×country join under-covers (conservative matching); EU-aggregate and some CN listings drop out.
- Profitability is trailing (yfinance `.info`), not point-in-time audited; UNVERIFIED ≠ unprofitable — it means the data source couldn't resolve the name.
- "Expansion" is a stated proxy, not a declaration of intent; the pairing file is where intent is evidenced (Cabinet approvals, PIB-credited production).
- Scheme-side facts inherit the policy program's corrections discipline — see its scheme registry for displayed revisions.

*Companion: the [investor workflow](https://herrrickshaw.github.io/india-trade-sector-policy-recommendations/charts/investor_workflow.html) (NSWS route, ministry connects) and the [decade report card](https://herrrickshaw.github.io/india-trade-sector-policy-recommendations/charts/decade_report_card.html) (which designs actually pay).*
