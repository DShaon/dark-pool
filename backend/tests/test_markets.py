"""Asset-class detection (P4) — the one place that decides crypto vs forex."""

from app.markets import asset_class, is_forex, to_twelvedata_symbol


def test_forex_majors_are_forex():
    for s in ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "eurusd", "UsdChf", "GBPJPY"):
        assert asset_class(s) == "forex", s
        assert is_forex(s)


def test_crypto_symbols_are_crypto():
    for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "BTCUSD", "XRPUSDT"):
        assert asset_class(s) == "crypto", s
        assert not is_forex(s)


def test_to_twelvedata_symbol_inserts_slash():
    assert to_twelvedata_symbol("EURUSD") == "EUR/USD"
    assert to_twelvedata_symbol("usdjpy") == "USD/JPY"
