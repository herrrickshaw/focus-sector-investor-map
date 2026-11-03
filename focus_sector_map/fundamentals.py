"""Per-name profitability verification: classification rules and a retrying, injectable fetcher."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Iterator, Mapping, Optional

import pandas as pd

log = logging.getLogger(__name__)

PROFITABLE = "PROFITABLE"
NOT_PROFITABLE = "NOT-PROFITABLE"
UNVERIFIED = "UNVERIFIED"

REVENUE_GROWTH_MIN = 0.10  # expansion proxy: revenue growth >= 10% y/y ...
RET252_MIN = 0.25  # ... OR 1-year return >= 25%
RATE_LIMIT_MARKERS = ("429", "Too Many Requests")
ERROR_REASON_WIDTH = 80
FINAL_SORT_KEYS = ["FocusSector", "Region", "Turnover_USD"]
FINAL_SORT_ASCENDING = [True, True, False]

InfoGetter = Callable[[str], Mapping[str, object]]
TickerBuilder = Callable[[pd.Series], "tuple[Optional[str], Optional[str]]"]


@dataclass
class Fundamentals:
    """Fields pulled from yfinance `.info`, plus the verdict and the reason when unverified."""

    profit_margin: Optional[float] = None
    roe: Optional[float] = None
    revenue_growth: Optional[float] = None
    verified: str = UNVERIFIED
    reason: Optional[str] = None

    def as_record(self) -> dict[str, object]:
        return {"profit_margin": self.profit_margin, "roe": self.roe,
                "revenue_growth": self.revenue_growth, "verified": self.verified}


def classify(profit_margin: Optional[float], roe: Optional[float]) -> str:
    """PROFITABLE iff margin > 0 and ROE > 0; UNVERIFIED when either field is missing."""
    if profit_margin is None or roe is None:
        return UNVERIFIED
    return PROFITABLE if (profit_margin > 0 and roe > 0) else NOT_PROFITABLE


def is_rate_limited(exc: BaseException) -> bool:
    message = str(exc)
    return any(marker in message for marker in RATE_LIMIT_MARKERS)


def fetch_fundamentals(ticker: str, info_getter: InfoGetter, max_attempts: int = 1,
                       backoff_seconds: float = 0.0, sleep: Callable[[float], None] = time.sleep) -> Fundamentals:
    """Fetch margin/ROE/revenue growth for `ticker`, retrying rate limits with linear backoff.

    Non-rate-limit errors stop immediately with reason `yfinance_error:<msg>`; exhausting the
    attempts leaves the result UNVERIFIED with no reason, as the original scripts did.
    """
    result = Fundamentals()
    for attempt in range(1, max_attempts + 1):
        try:
            info = info_getter(ticker)
        except Exception as exc:  # yfinance raises a mix of HTTP and parsing errors
            if is_rate_limited(exc):
                backoff = backoff_seconds * attempt
                log.warning("rate-limited on %s, backing off %ss, attempt %d/%d",
                            ticker, backoff, attempt, max_attempts)
                sleep(backoff)
                continue
            log.warning("yfinance error on %s: %s", ticker, exc)
            result.reason = f"yfinance_error:{str(exc)[:ERROR_REASON_WIDTH]}"
            return result
        pm = info.get("profitMargins")
        roe = info.get("returnOnEquity")
        growth = info.get("revenueGrowth")
        verdict = classify(pm, roe)  # type: ignore[arg-type]
        reason = None if verdict != UNVERIFIED else "yfinance_data_gap"
        return Fundamentals(pm, roe, growth, verdict, reason)  # type: ignore[arg-type]
    return result


def enrich_records(frame: pd.DataFrame, build_ticker: TickerBuilder,
                   fetch: Callable[[str], Fundamentals], pause_seconds: float,
                   reason_column: Optional[str] = "unverified_reason",
                   sleep: Callable[[float], None] = time.sleep) -> Iterator[dict[str, object]]:
    """Yield one enriched record per row: input fields + yf ticker + fundamentals + verdict."""
    for _, row in frame.iterrows():
        ticker, reason = build_ticker(row)
        record: dict[str, object] = dict(row)
        record.update({"yf": ticker, "profit_margin": None, "roe": None,
                       "revenue_growth": None, "verified": UNVERIFIED})
        if reason_column:
            record[reason_column] = reason
        if ticker:
            fundamentals = fetch(ticker)
            record.update(fundamentals.as_record())
            if reason_column:
                record[reason_column] = fundamentals.reason
            sleep(pause_seconds)
        yield record


def add_expansion_signal(df: pd.DataFrame) -> pd.DataFrame:
    """Add `expansion_signal`: revenue_growth >= 10% OR Ret252 >= 25% (missing values count as False)."""
    df["expansion_signal"] = ((df["revenue_growth"].fillna(-1) >= REVENUE_GROWTH_MIN)
                              | (df["Ret252"].fillna(-1) >= RET252_MIN))
    return df


def select_final(enriched: pd.DataFrame) -> pd.DataFrame:
    """Verified-profitable names only, sorted by sector, region and turnover."""
    final = enriched[enriched["verified"] == PROFITABLE].copy()
    return final.sort_values(FINAL_SORT_KEYS, ascending=FINAL_SORT_ASCENDING)


def verification_counts(df: pd.DataFrame) -> dict[str, int]:
    """Counts of each verdict plus the two UNVERIFIED sub-causes (no ticker built / data gap)."""
    unverified = df["verified"] == UNVERIFIED
    return {
        "profitable": int((df["verified"] == PROFITABLE).sum()),
        "not_profitable": int((df["verified"] == NOT_PROFITABLE).sum()),
        "unverified": int(unverified.sum()),
        "unmapped": int(df["yf"].isna().sum()),
        "data_gap": int((unverified & df["yf"].notna()).sum()),
        "expansion_profitable": int(df[df["verified"] == PROFITABLE]["expansion_signal"].sum()),
    }
