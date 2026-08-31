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
  1. Primary: Market column populated -> reuse the exact SUFFIX dict logic
     from scripts/enrich_profitability.py (IN/JP/KR/TW/DE/UK/HK/AU/CA/SE/CH/
     DK/FI/SG/BR/ZA/SA/US/CN/EU), keyed here off the catalog's `Ticker`
     column (that script's shortlist used `Symbol`; same field, different
     name in this catalog).
  2. Fallback: Market is blank (318 of the 3,433 rows) -> derive suffix from
     `Exchange` instead. Mapping below was verified live this session
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
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CATALOG = DATA / "focus_sector_global_catalog.csv"
OUT_CSV = DATA / "electronics_semiconductors_unswept_enriched.csv"
CHECKPOINT_EVERY = 40

# ---- Tier 1: reused verbatim from scripts/enrich_profitability.py ----
SUFFIX = {"IN": ".NS", "JP": ".T", "KR": ".KS", "TW": ".TW", "DE": ".DE",
          "UK": ".L", "HK": ".HK", "AU": ".AX", "CA": ".TO", "SE": ".ST",
          "CH": ".SW", "DK": ".CO", "FI": ".HE", "SG": ".SI", "BR": ".SA",
          "ZA": ".JO", "SA": ".SR", "US": "", "CN": None, "EU": None}

# ---- Tier 2: Exchange-based fallback for blank-Market rows ----
# "" = no suffix (US-primary listing regardless of domicile country)
# None = confirmed live this session: not reliably resolvable via yfinance
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
    # confirmed genuinely unresolvable live this session
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


def yf_ticker(row):
    """Returns (ticker_or_None, reason_if_None)."""
    market = row.get("Market")
    market = None if (pd.isna(market) or str(market).strip() == "") else str(market).strip()
    sym = str(row["Ticker"]).strip().replace(" ", "-")
    exch = row.get("Exchange")
    exch = None if pd.isna(exch) else str(exch).strip()
    country = row.get("Country")
    country = None if pd.isna(country) else str(country).strip()

    if market is not None:
        # ---- Tier 1 ----
        if market not in SUFFIX:
            return None, f"unmapped_market:{market}"
        s = SUFFIX[market]
        if s is None:
            if market == "CN":
                return sym + (".SS" if sym.startswith("6") else ".SZ"), None
            return None, f"market_no_suffix:{market}"
        if market == "HK":
            sym = sym.zfill(4)
        return sym + s, None

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
        sym = sym.zfill(4)

    return sym + suffix, None


def checkpoint(rows):
    df = pd.DataFrame(rows)
    df["expansion_signal"] = (
        (df["revenue_growth"].fillna(-1) >= 0.10) | (df["Ret252"].fillna(-1) >= 0.25)
    )
    df.to_csv(OUT_CSV, index=False)
    return df


def main():
    import yfinance as yf

    catalog = pd.read_csv(CATALOG)
    es = catalog[catalog["FocusSector"] == "Electronics & Semiconductors"].copy()
    unswept_mask = es["verified"].isna() | (es["verified"].astype(str).str.strip() == "")
    unswept = es[unswept_mask].copy()
    n = len(unswept)
    print(f"Electronics & Semiconductors total: {len(es)} | unswept target: {n}", flush=True)

    rows = []
    start = time.time()
    for i, (_, r) in enumerate(unswept.iterrows(), 1):
        t, unmapped_reason = yf_ticker(r)
        rec = dict(r)
        rec.update({
            "yf": t, "profit_margin": None, "roe": None, "revenue_growth": None,
            "verified": "UNVERIFIED", "unverified_reason": unmapped_reason,
        })
        if t:
            attempt = 0
            while attempt < 3:
                attempt += 1
                try:
                    info = yf.Ticker(t).info
                    pm = info.get("profitMargins")
                    roe = info.get("returnOnEquity")
                    rg = info.get("revenueGrowth")
                    rec.update({"profit_margin": pm, "roe": roe, "revenue_growth": rg})
                    if pm is not None and roe is not None:
                        rec["verified"] = "PROFITABLE" if (pm > 0 and roe > 0) else "NOT-PROFITABLE"
                        rec["unverified_reason"] = None
                    else:
                        rec["unverified_reason"] = "yfinance_data_gap"
                    break
                except Exception as e:
                    msg = str(e)
                    if "429" in msg or "Too Many Requests" in msg:
                        backoff = 8 * attempt
                        print(f"  [rate-limited on {t}, backing off {backoff}s, attempt {attempt}/3]", flush=True)
                        time.sleep(backoff)
                        continue
                    rec["unverified_reason"] = f"yfinance_error:{msg[:80]}"
                    break
            time.sleep(0.7)
        rows.append(rec)
        if i % 10 == 0 or i == n:
            elapsed = time.time() - start
            rate = i / elapsed if elapsed > 0 else 0
            eta_min = (n - i) / rate / 60 if rate > 0 else float("nan")
            print(f"  [{i}/{n}] {r['Country']}:{r.get('Exchange')}:{r['Ticker']:<14} yf={str(t):<16} "
                  f"{rec['verified']:<15} pm={rec['profit_margin']}  (elapsed={elapsed/60:.1f}m eta={eta_min:.1f}m)", flush=True)
        if i % CHECKPOINT_EVERY == 0:
            checkpoint(rows)
            print(f"  -- checkpointed {i} rows --", flush=True)

    df = checkpoint(rows)

    profitable = (df["verified"] == "PROFITABLE").sum()
    not_profitable = (df["verified"] == "NOT-PROFITABLE").sum()
    unverified = (df["verified"] == "UNVERIFIED").sum()
    unmapped = df["yf"].isna().sum()
    data_gap = ((df["verified"] == "UNVERIFIED") & df["yf"].notna()).sum()

    print(f"\nWrote {len(df)} rows -> {OUT_CSV}")
    print(f"PROFITABLE {profitable} | NOT-PROFITABLE {not_profitable} | UNVERIFIED {unverified}")
    print(f"  of which UNVERIFIED, no ticker built at all (unmapped/unsupported exchange or market): {unmapped}")
    print(f"  of which UNVERIFIED, ticker built but yfinance had no financial data: {data_gap}")
    print(f"with expansion signal (PROFITABLE only): "
          f"{int(df[df['verified']=='PROFITABLE']['expansion_signal'].sum())}")


if __name__ == "__main__":
    main()
