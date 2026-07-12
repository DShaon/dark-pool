"""Backtest data + job orchestration (P5 · ADR-0020).

The engine (quant/backtest.py) is pure CPU; this module feeds it. Historical
candles are paged through the existing BinanceAdapter (invariant 1 — all
external I/O through adapters/), the simulation runs off the event loop in a
worker thread (a 90-day replay is minutes of pandas work; the API must keep
serving), and finished reports land in a small atomic file store under
data/ (gitignored), one report per symbol.

One job at a time (single-user P1): a second POST while running gets an
honest 409, not a queue.
"""

import asyncio
import contextlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.adapters.binance import BinanceAdapter
from app.models.backtest import BacktestJobStatus, BacktestReport
from app.models.market import Candle
from app.quant.backtest import (
    ANALYSIS_TFS,
    WARMUP_BARS,
    BacktestConfig,
    run_backtest,
)

_TF_DELTA = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "4h": timedelta(hours=4)}
_PAGE_LIMIT = 1000
_MAX_STORED_SYMBOLS = 12


class BacktestBusy(Exception):
    """A run is already in progress."""


class BacktestStore:
    """Last report per symbol, atomic tempfile+replace writes (same pattern as
    the calibration/lessons stores)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, dict]) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self._path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def put(self, report: BacktestReport) -> None:
        data = self._load()
        data[report.symbol] = json.loads(report.model_dump_json())
        if len(data) > _MAX_STORED_SYMBOLS:
            oldest = sorted(data, key=lambda s: data[s].get("generated_at", ""))
            for sym in oldest[: len(data) - _MAX_STORED_SYMBOLS]:
                del data[sym]
        self._save(data)

    def get(self, symbol: str) -> BacktestReport | None:
        raw = self._load().get(symbol.upper())
        return BacktestReport.model_validate(raw) if raw else None


class BacktestRunner:
    def __init__(self, spot: BinanceAdapter, store: BacktestStore, config: BacktestConfig) -> None:
        self._spot = spot
        self._store = store
        self._config = config
        self._task: asyncio.Task | None = None
        self._status = BacktestJobStatus(state="idle")

    @property
    def config(self) -> BacktestConfig:
        return self._config

    def status(self) -> BacktestJobStatus:
        return self._status

    def start(self, symbol: str, days: int) -> None:
        if self._status.state == "running":
            raise BacktestBusy()
        self._status = BacktestJobStatus(
            state="running", symbol=symbol, days=days, progress=0.0,
            message="fetching history",
        )
        self._task = asyncio.create_task(self._run(symbol, days))

    async def _run(self, symbol: str, days: int) -> None:
        try:
            window_end = datetime.now(timezone.utc)
            window_start = window_end - timedelta(days=days)
            candles_by_tf: dict[str, list[Candle]] = {}
            for tf in ANALYSIS_TFS:
                self._status = self._status.model_copy(
                    update={"message": f"fetching {tf} history"}
                )
                # +2 bars of padding: Binance snaps startTime forward to its
                # candle grid, which can eat a bar off an unaligned window —
                # the engine slices to exactly WARMUP_BARS anyway (_visible).
                fetch_start = window_start - (WARMUP_BARS + 2) * _TF_DELTA[tf]
                candles_by_tf[tf] = await self._fetch_range(
                    symbol, tf, fetch_start, window_end
                )

            self._status = self._status.model_copy(
                update={"message": "simulating", "progress": 0.0}
            )

            def on_progress(done: int, total: int) -> None:
                # Called from the worker thread; a single attribute swap of an
                # immutable model is safe to read from the event loop.
                self._status = self._status.model_copy(
                    update={"progress": round(done / max(total, 1), 3)}
                )

            report = await asyncio.to_thread(
                run_backtest,
                symbol,
                candles_by_tf,
                window_start,
                window_end,
                self._config,
                days,
                on_progress,
            )
            self._store.put(report)
            self._status = BacktestJobStatus(
                state="done", symbol=symbol, days=days, progress=1.0,
                message=f"{report.n_decisions} decisions simulated",
            )
        except Exception as exc:  # noqa: BLE001 — job boundary: fail honestly, never crash the app
            self._status = BacktestJobStatus(
                state="error", symbol=symbol, days=days,
                message=str(exc)[:300] or exc.__class__.__name__,
            )

    async def _fetch_range(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> list[Candle]:
        """Page forward through get_klines until `end`. Binance returns up to
        1000 bars from startTime; the cursor advances past the last OPEN time
        so pages never overlap."""
        out: list[Candle] = []
        cursor = start
        delta = _TF_DELTA[interval]
        while cursor < end:
            batch = await self._spot.get_klines(
                symbol, interval, _PAGE_LIMIT, start_time=cursor, end_time=end
            )
            if not batch:
                break
            out.extend(batch)
            next_cursor = batch[-1].open_time + delta
            if next_cursor <= cursor:  # no forward progress — stop, don't spin
                break
            cursor = next_cursor
            if len(batch) < _PAGE_LIMIT:
                break
        # Drop the still-forming last bar if present (close_time in the future):
        # the engine must only ever see CLOSED candles (ADR-0020 §2).
        now = datetime.now(timezone.utc)
        return [c for c in out if c.close_time <= now]


__all__ = ["BacktestRunner", "BacktestStore", "BacktestBusy"]
