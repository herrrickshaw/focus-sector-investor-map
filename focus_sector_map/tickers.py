"""Yahoo Finance ticker construction from the universe's market code."""
from __future__ import annotations

from typing import Optional

# Market code -> Yahoo Finance suffix. "" = US-style bare ticker; None = no single suffix
# (CN is split by ticker prefix below, EU aggregates are not resolvable).
MARKET_SUFFIX: dict[str, Optional[str]] = {
    "IN": ".NS", "JP": ".T", "KR": ".KS", "TW": ".TW", "DE": ".DE",
    "UK": ".L", "HK": ".HK", "AU": ".AX", "CA": ".TO", "SE": ".ST",
    "CH": ".SW", "DK": ".CO", "FI": ".HE", "SG": ".SI", "BR": ".SA",
    "ZA": ".JO", "SA": ".SR", "US": "", "CN": None, "EU": None,
}
HK_TICKER_WIDTH = 4  # HK tickers are zero-padded to 4 digits


def china_ticker(symbol: str) -> str:
    """Shanghai (.SS) for 6xxxxx codes, Shenzhen (.SZ) otherwise."""
    return symbol + (".SS" if symbol.startswith("6") else ".SZ")


def market_ticker(market: object, symbol: object) -> Optional[str]:
    """Build a yfinance ticker from a market code and bare symbol; None when the market has no suffix."""
    suffix = MARKET_SUFFIX.get(market)  # type: ignore[arg-type]
    sym = str(symbol)
    if suffix is None:
        if market == "CN":
            return china_ticker(sym)
        return None
    if market == "HK":
        sym = sym.zfill(HK_TICKER_WIDTH)
    return sym + suffix
