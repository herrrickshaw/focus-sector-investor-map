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
import json, time, sys
import pandas as pd

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CATALOG = DATA / "focus_sector_global_catalog.csv"
OUT_CSV = DATA / "medical_devices_unswept_enriched.csv"

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


def yf_ticker(row):
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
    if exch in ("KOSDAQ", "KOSE", "XKON") and sym.startswith("A") and sym[1:].isdigit():
        sym = sym[1:]

    # HK tickers should be 4-digit zero-padded.
    if exch == "SEHK" and sym.isdigit():
        sym = sym.zfill(4)

    return sym + suffix, None


def main():
    import yfinance as yf

    catalog = pd.read_csv(CATALOG)
    md = catalog[catalog["FocusSector"] == "Medical Devices"].copy()
    unswept_mask = md["verified"].isna() | (md["verified"].astype(str).str.strip() == "")
    unswept = md[unswept_mask].copy()
    print(f"Medical Devices total: {len(md)} | unswept (target for this run): {len(unswept)}")

    rows = []
    n = len(unswept)
    for i, (_, r) in enumerate(unswept.iterrows(), 1):
        t, unmapped_reason = yf_ticker(r)
        rec = dict(r)
        rec.update({
            "yf": t,
            "profit_margin": None,
            "roe": None,
            "revenue_growth": None,
            "verified": "UNVERIFIED",
            "unverified_reason": unmapped_reason,  # set if suffix couldn't be built at all
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
                        backoff = 5 * attempt
                        print(f"  [rate-limited on {t}, backing off {backoff}s, attempt {attempt}/3]")
                        time.sleep(backoff)
                        continue
                    rec["unverified_reason"] = f"yfinance_error:{msg[:80]}"
                    break
            time.sleep(0.75)
        rows.append(rec)
        print(f"  [{i}/{n}] {r['Country']}:{r['Exchange']}:{r['Ticker']:<14} yf={str(t):<16} "
              f"{rec['verified']:<15} pm={rec['profit_margin']} roe={rec['roe']}")

    df = pd.DataFrame(rows)
    df["expansion_signal"] = (
        (df["revenue_growth"].fillna(-1) >= 0.10) | (df["Ret252"].fillna(-1) >= 0.25)
    )
    df.to_csv(OUT_CSV, index=False)

    profitable = (df["verified"] == "PROFITABLE").sum()
    not_profitable = (df["verified"] == "NOT-PROFITABLE").sum()
    unverified = (df["verified"] == "UNVERIFIED").sum()
    unmapped = df["yf"].isna().sum()
    data_gap = ((df["verified"] == "UNVERIFIED") & df["yf"].notna()).sum()

    print(f"\nWrote {len(df)} rows -> {OUT_CSV}")
    print(f"PROFITABLE {profitable} | NOT-PROFITABLE {not_profitable} | UNVERIFIED {unverified}")
    print(f"  of which UNVERIFIED due to unmapped/unsupported exchange (no ticker built): {unmapped}")
    print(f"  of which UNVERIFIED due to genuine yfinance data gap (ticker built, no financials): {data_gap}")
    print(f"with expansion signal (PROFITABLE only): "
          f"{int(df[df['verified']=='PROFITABLE']['expansion_signal'].sum())}")


if __name__ == "__main__":
    main()
