"""DARKPOOL API — application factory and lifespan wiring.

Singletons (adapter, cache) are created at startup on `app.state` and closed on
shutdown; request handlers never construct network clients.
"""

import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.adapters.alternative_me import AlternativeMeAdapter
from app.adapters.binance import BinanceAdapter
from app.adapters.binance_futures import BinanceFuturesAdapter
from app.adapters.binance_ws import BinanceStreamHub
from app.api.routes_analysis import router as analysis_router
from app.api.routes_grading import router as grading_router
from app.api.routes_market import router as market_router
from app.api.routes_monitor import router as monitor_router
from app.api.routes_ws import router as ws_router
from app.config import get_settings
from app.core.cache import build_cache
from app.desk.factory import build_desk
from app.monitor.alerts import load_thresholds
from app.monitor.scanner import Scanner
from app.monitor.state import FeedStore, ModeStore, WatchlistStore
from app.quant.brief import BriefComposer
from app.quant.grading_service import GradingService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.cache = build_cache(settings)
    app.state.binance = BinanceAdapter(base_url=settings.binance_data_base)
    app.state.binance_futures = BinanceFuturesAdapter()
    app.state.sentiment = AlternativeMeAdapter()
    app.state.brief_composer = BriefComposer(
        spot=app.state.binance,
        futures=app.state.binance_futures,
        sentiment=app.state.sentiment,
    )
    # LLM gateway + Quick Read (tier 1) + analyst panel (tier 2). Each is None
    # when its provider key / config is absent — the matching route then answers
    # 503 and the rest of the API is unaffected (NFR-3).
    app.state.llm_gateway, app.state.quick_read, app.state.analyst_panel = build_desk(settings)
    # Alert thresholds (P3) — config over code; defaults if the file is absent.
    app.state.alert_thresholds = load_thresholds(settings.alerts_config_path)
    # Outcome grading (P3 · FR-6) — deterministic TP/SL check, no AI.
    app.state.grading_service = GradingService(app.state.binance)

    # Background scanner (P3 · FR-5): file-backed mode/watchlist/feed stores +
    # an APScheduler tick. "manual" mode (the default) makes every tick a
    # no-op — Active mode is opt-in, never a surprise (ADR-0008 spirit).
    data_dir = Path(settings.data_dir)
    app.state.scanner_mode = ModeStore(data_dir / "scanner_mode.json")
    app.state.scanner_watchlist = WatchlistStore(
        data_dir / "watchlist.json", default=settings.default_watchlist_list
    )
    app.state.scanner_feed = FeedStore(data_dir / "scanner_feed.json")
    app.state.scanner = Scanner(
        composer=app.state.brief_composer,
        thresholds=app.state.alert_thresholds,
        mode_store=app.state.scanner_mode,
        watchlist_store=app.state.scanner_watchlist,
        feed_store=app.state.scanner_feed,
    )
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        app.state.scanner.tick,
        "interval",
        seconds=settings.scan_interval_seconds,
        id="scanner_tick",
        max_instances=1,  # a slow tick must finish before the next one starts
    )
    scheduler.start()
    app.state.scheduler = scheduler

    # Live kline stream (P3) — one shared upstream Binance WS connection,
    # fanned out to however many browser tabs are watching (invariant 1: all
    # external I/O through adapters/). REST still owns historical backfill.
    app.state.stream_hub = BinanceStreamHub()
    stream_task = asyncio.create_task(app.state.stream_hub.run())
    try:
        yield
    finally:
        stream_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stream_task
        await app.state.stream_hub.aclose()
        app.state.scheduler.shutdown(wait=False)
        await app.state.binance.aclose()
        await app.state.binance_futures.aclose()
        await app.state.sentiment.aclose()
        if app.state.llm_gateway is not None:
            await app.state.llm_gateway.aclose()
        await app.state.cache.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="DARKPOOL API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(market_router)
    app.include_router(analysis_router)
    app.include_router(monitor_router)
    app.include_router(grading_router)
    app.include_router(ws_router)
    return app


app = create_app()
