"""Application settings.

All configuration comes from environment variables (or backend/.env in dev).
Secrets never appear in code, the frontend, or logs (CLAUDE.md invariant 4).

Paths are anchored to the backend directory so behavior is identical whether
the process starts from the repo root (uvicorn --app-dir backend) or from
backend/ itself (pytest).
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "DARKPOOL"
    environment: str = "dev"

    # Single-user bearer auth (ADR-0009). Empty/None = auth disabled (dev only).
    api_token: str | None = None

    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:3000"

    # Binance public market data (keyless mirror).
    binance_data_base: str = "https://data-api.binance.vision"

    # Twelve Data forex OHLCV (P4). "demo" serves EUR/USD out of the box; a free
    # lifetime key (twelvedata.com, 8 req/min · 800/day) unlocks every pair.
    twelve_data_api_key: str = "demo"

    # Upstash Redis over REST (optional; in-memory fallback when unset).
    redis_rest_url: str | None = None
    redis_rest_token: str | None = None

    # Supabase Postgres — wired in P1 (journal, runs, model_scores).
    database_url: str | None = None

    # LLM provider keys (free tiers). config/models.yaml maps providers to
    # these fields by name (`key_setting`) — keys never appear in YAML.
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None

    # Model roster + prompt locations (config over code, invariant 6).
    models_config_path: str = str(BACKEND_DIR / "config" / "models.yaml")
    prompts_dir: str = str(BACKEND_DIR / "prompts")
    alerts_config_path: str = str(BACKEND_DIR / "config" / "alerts.yaml")
    backtest_config_path: str = str(BACKEND_DIR / "config" / "backtest.yaml")
    broker_config_path: str = str(BACKEND_DIR / "config" / "broker.yaml")
    # User-managed roster (ADR-0016) — overlays models.yaml; holds API keys, so
    # gitignored under data/ (invariant 4). Absent file = pure YAML defaults.
    roster_config_path: str = str(BACKEND_DIR / "data" / "roster.json")

    # Local data (P1 file stores — CIO trade plans via MCP). Gitignored;
    # migrates to Supabase Postgres (B4) without changing call sites.
    data_dir: str = str(BACKEND_DIR / "data")

    # Risk parameters for CIO position sizing (FR-4 · ADR-0015). Advisory
    # percentages only — no execution paths exist in v1 (invariant 5).
    risk_pct_per_trade: float = 1.0  # % of account risked if the stop is hit
    max_position_pct: float = 100.0  # cap on recommended notional (100 = 1x)

    # Background scanner (P3 · FR-5). Active mode ticks this often; the seed
    # watchlist before the frontend has synced its own list at least once.
    scan_interval_seconds: int = 60
    default_watchlist: str = "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT"
    default_forex_watchlist: str = "EURUSD,GBPUSD,USDJPY,AUDUSD"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def default_watchlist_list(self) -> list[str]:
        return [s.strip().upper() for s in self.default_watchlist.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
