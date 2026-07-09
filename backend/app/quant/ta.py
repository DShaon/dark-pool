"""Technical indicators — hand-rolled, dependency-free, golden-tested.

Chosen over pandas-ta for transparency and zero heavy dependencies (ADR-0001
spirit: pure Python everywhere). Indicator values are *analytics*, not money, so
they are computed in float; every tradable **level** elsewhere in the engine
stays Decimal. Lists are index-aligned with the input; positions before an
indicator's warm-up period are None.

Conventions: EMA seeds with the SMA of the first n values. RSI and ATR use
Wilder smoothing. Bollinger uses population standard deviation. VWAP cumulates
from the start of the supplied window (caller controls the session).
"""

import statistics

from app.models.market import Candle


def closes(candles: list[Candle]) -> list[float]:
    return [float(c.close) for c in candles]


def ema(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    out[n - 1] = sum(values[:n]) / n
    k = 2.0 / (n + 1)
    for i in range(n, len(values)):
        prev = out[i - 1]
        assert prev is not None
        out[i] = values[i] * k + prev * (1 - k)
    return out


def rsi(values: list[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < n + 1:
        return out
    gains = [max(values[i] - values[i - 1], 0.0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0.0) for i in range(1, len(values))]
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n

    def _rsi(g: float, l: float) -> float:
        if l == 0:
            return 100.0 if g > 0 else 50.0
        return 100.0 - 100.0 / (1.0 + g / l)

    out[n] = _rsi(avg_gain, avg_loss)
    for i in range(n + 1, len(values)):
        avg_gain = (avg_gain * (n - 1) + gains[i - 1]) / n
        avg_loss = (avg_loss * (n - 1) + losses[i - 1]) / n
        out[i] = _rsi(avg_gain, avg_loss)
    return out


def macd(
    values: list[float], fast: int = 12, slow: int = 26, signal_n: int = 9
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    line: list[float | None] = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    first = next((i for i, v in enumerate(line) if v is not None), None)
    signal: list[float | None] = [None] * len(values)
    if first is not None:
        seg = [v for v in line[first:] if v is not None]
        seg_signal = ema(seg, signal_n)
        for offset, v in enumerate(seg_signal):
            signal[first + offset] = v
    hist: list[float | None] = [
        (m - s) if m is not None and s is not None else None
        for m, s in zip(line, signal)
    ]
    return line, signal, hist


def atr(candles: list[Candle], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(candles)
    if len(candles) < n:
        return out
    trs: list[float] = []
    for i, c in enumerate(candles):
        h, l = float(c.high), float(c.low)
        if i == 0:
            trs.append(h - l)
        else:
            pc = float(candles[i - 1].close)
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    out[n - 1] = sum(trs[:n]) / n
    for i in range(n, len(candles)):
        prev = out[i - 1]
        assert prev is not None
        out[i] = (prev * (n - 1) + trs[i]) / n
    return out


def bollinger(
    values: list[float], n: int = 20, mult: float = 2.0
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    upper: list[float | None] = [None] * len(values)
    mid: list[float | None] = [None] * len(values)
    lower: list[float | None] = [None] * len(values)
    for i in range(n - 1, len(values)):
        window = values[i - n + 1 : i + 1]
        m = sum(window) / n
        sd = statistics.pstdev(window)
        mid[i] = m
        upper[i] = m + mult * sd
        lower[i] = m - mult * sd
    return upper, mid, lower


def vwap(candles: list[Candle]) -> list[float | None]:
    out: list[float | None] = [None] * len(candles)
    cum_pv = 0.0
    cum_v = 0.0
    for i, c in enumerate(candles):
        tp = (float(c.high) + float(c.low) + float(c.close)) / 3.0
        v = float(c.volume)
        cum_pv += tp * v
        cum_v += v
        out[i] = cum_pv / cum_v if cum_v > 0 else None
    return out


def last(series: list[float | None]) -> float | None:
    """Final value of an indicator series (None during warm-up)."""
    return series[-1] if series else None
