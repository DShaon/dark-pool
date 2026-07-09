"""File-backed scanner state (P3 · FR-5) — mode, watchlist, alert feed.

Same pattern as `app/desk/plan_store.py`: single-user, atomic JSON writes,
gitignored under `backend/data/`, swaps for Postgres/Redis later (B4) without
changing call sites. The background scanner and the `/monitor/*` routes share
these stores, so flipping the mode toggle takes effect on the very next tick —
no restart required.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from app.models.alerts import AlertEvent

ScannerMode = Literal["manual", "active"]
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{5,20}$")


def _atomic_write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # atomic on the same filesystem
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _read_json(path: Path, fallback: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


class ModeStore:
    """Manual (default, opt-in only) vs Active (background scanning)."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def get(self) -> ScannerMode:
        data = _read_json(self._path, {})
        mode = data.get("mode") if isinstance(data, dict) else None
        return mode if mode in ("manual", "active") else "manual"

    def set(self, mode: ScannerMode) -> ScannerMode:
        if mode not in ("manual", "active"):
            raise ValueError(f"invalid mode {mode!r}; expected 'manual' or 'active'")
        _atomic_write_json(self._path, {"mode": mode})
        return mode


class WatchlistStore:
    """The scanner's symbol list — mirrors the frontend's localStorage board
    (single-user P1: the browser owns the canonical list, this is the server's
    copy so Active-mode ticks know what to scan even with no tab open)."""

    MAX_SYMBOLS = 20

    def __init__(self, path: Path, default: list[str]) -> None:
        self._path = Path(path)
        self._default = list(default)

    def get(self) -> list[str]:
        data = _read_json(self._path, {})
        symbols = data.get("symbols") if isinstance(data, dict) else None
        if isinstance(symbols, list) and symbols and all(isinstance(s, str) for s in symbols):
            return symbols
        return list(self._default)

    def set(self, symbols: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in symbols:
            s = raw.strip().upper()
            if not _SYMBOL_RE.match(s):
                raise ValueError(f"invalid symbol {raw!r} (expected e.g. BTCUSDT)")
            if s not in cleaned:
                cleaned.append(s)
        cleaned = cleaned[: self.MAX_SYMBOLS] or list(self._default)
        _atomic_write_json(self._path, {"symbols": cleaned})
        return cleaned


class FeedStore:
    """Rolling log of scanner-detected conditions across the whole watchlist.

    Dedup is cooldown-based, not permanent: the SAME condition (symbol + kind +
    timeframe + message) is recorded once, then suppressed for `cooldown`
    (default 1h) so an unchanged condition doesn't spam every tick — but a
    genuine re-occurrence after the cooldown surfaces again. This is a
    pragmatic P1 choice, not full alert-lifecycle tracking (no snooze/ack yet).
    """

    def __init__(self, path: Path, max_len: int = 300, cooldown: timedelta | None = None) -> None:
        self._path = Path(path)
        self._max_len = max_len
        self._cooldown = cooldown or timedelta(hours=1)

    def _load(self) -> list[dict]:
        data = _read_json(self._path, [])
        return data if isinstance(data, list) else []

    @staticmethod
    def _key(symbol: str, event: AlertEvent) -> str:
        return f"{symbol}:{event.kind}:{event.timeframe or '-'}:{event.message}"

    def record(self, symbol: str, events: list[AlertEvent]) -> list[dict]:
        """Persist newly-notable events; return only the ones actually added."""
        existing = self._load()
        last_at: dict[str, datetime] = {}
        for r in existing:
            try:
                at = datetime.fromisoformat(r["at"])
            except (KeyError, ValueError):
                continue
            k = r.get("key")
            if k and (k not in last_at or at > last_at[k]):
                last_at[k] = at

        fresh: list[dict] = []
        for event in events:
            key = self._key(symbol, event)
            prior = last_at.get(key)
            if prior is not None and event.at - prior < self._cooldown:
                continue  # unchanged condition, still within cooldown — skip
            fresh.append(
                {
                    "key": key,
                    "symbol": symbol,
                    "kind": event.kind,
                    "timeframe": event.timeframe,
                    "tone": event.tone,
                    "message": event.message,
                    "message_bn": event.message_bn,
                    "ref": event.ref,
                    "at": event.at.isoformat(),
                }
            )

        if fresh:
            merged = (fresh + existing)[: self._max_len]  # newest first
            _atomic_write_json(self._path, merged)
        return fresh

    def recent(self, limit: int = 50) -> list[dict]:
        return self._load()[: max(0, limit)]
