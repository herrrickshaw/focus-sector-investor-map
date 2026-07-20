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
import json, time, math
import pandas as pd
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data"
SUFFIX = {"IN": ".NS", "JP": ".T", "KR": ".KS", "TW": ".TW", "DE": ".DE",
          "UK": ".L", "HK": ".HK", "AU": ".AX", "CA": ".TO", "SE": ".ST",
          "CH": ".SW", "DK": ".CO", "FI": ".HE", "SG": ".SI", "BR": ".SA",
          "ZA": ".JO", "SA": ".SR", "US": "", "CN": None, "EU": None}


def yf_ticker(row):
    s = SUFFIX.get(row["Market"])
    if s is None:
        sym = str(row["Symbol"])
        if row["Market"] == "CN":
            return sym + (".SS" if sym.startswith("6") else ".SZ")
        return None
    sym = str(row["Symbol"])
    if row["Market"] == "HK":
        sym = sym.zfill(4)
    return sym + s


def main():
    import yfinance as yf
    sl = pd.read_csv(OUT / "shortlist_for_enrichment.csv")
    rows = []
    for _, r in sl.iterrows():
        t = yf_ticker(r)
        rec = dict(r)
        rec.update({"yf": t, "profit_margin": None, "roe": None,
                    "revenue_growth": None, "verified": "UNVERIFIED"})
        if t:
            try:
                info = yf.Ticker(t).info
                pm = info.get("profitMargins"); roe = info.get("returnOnEquity")
                rg = info.get("revenueGrowth")
                rec.update({"profit_margin": pm, "roe": roe, "revenue_growth": rg})
                if pm is not None and roe is not None:
                    rec["verified"] = "PROFITABLE" if (pm > 0 and roe > 0) else "NOT-PROFITABLE"
            except Exception:
                pass
            time.sleep(0.5)
        rows.append(rec)
        print(f"  {r['Market']}:{r['Symbol']:<12} {rec['verified']:<15} pm={rec['profit_margin']}")
    df = pd.DataFrame(rows)
    df["expansion_signal"] = ((df["revenue_growth"].fillna(-1) >= 0.10)
                              | (df["Ret252"].fillna(-1) >= 0.25))
    final = df[df["verified"] == "PROFITABLE"].copy()
    final = final.sort_values(["FocusSector", "Region", "Turnover_USD"], ascending=[True, True, False])
    df.to_csv(OUT / "shortlist_enriched.csv", index=False)
    final.to_csv(OUT / "focus_sector_companies_final.csv", index=False)
    final.to_json(OUT / "focus_sector_companies_final.json", orient="records", indent=1)
    print(f"\nenriched {len(df)} | PROFITABLE {len(final)} | "
          f"NOT-PROFITABLE {(df['verified']=='NOT-PROFITABLE').sum()} | "
          f"UNVERIFIED {(df['verified']=='UNVERIFIED').sum()}")
    print(f"with expansion signal: {int(final['expansion_signal'].sum())}")


if __name__ == "__main__":
    main()
