"""Asset-class registry (P4) — which market a symbol belongs to.

The whole desk is symbol-driven: `BTCUSDT` is crypto (Binance), `EURUSD` is
forex (Twelve Data). This one place decides which, so routes/composer pick the
right data source without threading an explicit flag through every call. The
deterministic quant engine (structure, zones, liquidity, indicators) is
asset-agnostic — it runs identically on either — so "asset class" only changes
the DATA SOURCE and which context layers apply (crypto has funding/OI/F&G;
forex has none of those, and later gains DXY/COT/sessions).
"""

from typing import Literal

AssetClass = Literal["crypto", "forex"]

# The 8 majors — every liquid forex pair is two of these concatenated.
FOREX_CODES = frozenset({"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"})


def asset_class(symbol: str) -> AssetClass:
    s = symbol.upper()
    # A forex pair is exactly two 3-letter ISO codes (e.g. EURUSD, USDJPY).
    # Crypto pairs are longer (BTCUSDT) or carry a non-forex leg (BTCUSD).
    if len(s) == 6 and s[:3] in FOREX_CODES and s[3:] in FOREX_CODES:
        return "forex"
    return "crypto"


def is_forex(symbol: str) -> bool:
    return asset_class(symbol) == "forex"


def to_twelvedata_symbol(symbol: str) -> str:
    """EURUSD -> EUR/USD (Twelve Data's slash-separated pair format)."""
    s = symbol.upper()
    return f"{s[:3]}/{s[3:]}"
