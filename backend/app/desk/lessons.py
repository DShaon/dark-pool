"""Trade lessons (ADR-0019) — the desk's post-mortem memory.

When a journaled trade grades SL (or the owner invalidates it), the journal
asks WHY — a structured tag + a free-text note ("what info was missing").
Those records aggregate into:

  * per-variant/per-source performance (n, wins, win rate) — surfaced on the
    setup cards and the journal's strategy card, so the owner sees which
    styles actually earn;
  * a lessons digest injected into the CIO's DESK INPUT (cio.py) — the desk
    literally reads its own post-mortems before the next call. Lessons are
    desk memory, NOT market facts, so they ride the synthesis payload beside
    the brief — never inside it (the brief stays pure market data).

This is the honest half of "auto-improve strategy". The dishonest half —
automatically mutating the variants' stop/target multipliers from a handful
of outcomes — was considered and REJECTED (ADR-0019 §4): silent self-tuning
on small samples compounds overfit quietly. Numbers change via ADRs, informed
by these surfaced stats, or via P5 backtesting.

File-backed, single-user P1, same pattern as monitor/state.py. Wins are also
recorded (tag-less) so win rates are honest, not loss-only.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

MAX_RECORDS = 500
DIGEST_RECENT_NOTES = 8
DIGEST_NOTE_CHARS = 160

# Curated failure taxonomy — stable keys (stored), bilingual labels (UI).
FAILURE_TAGS: dict[str, dict[str, str]] = {
    "against_trend": {"en": "fought the bigger trend", "bn": "বড় ট্রেন্ডের বিপরীতে গেছি"},
    "news_event": {"en": "news/event hit the trade", "bn": "খবর/ইভেন্টে ধাক্কা"},
    "funding_crowded": {"en": "crowded funding side", "bn": "ফান্ডিংয়ে ভিড়ের দিকে ছিলাম"},
    "late_entry": {"en": "entered too late", "bn": "দেরিতে ঢুকেছি"},
    "stop_too_tight": {"en": "stop too tight", "bn": "স্টপ খুব কাছে ছিল"},
    "target_too_far": {"en": "target too ambitious", "bn": "টার্গেট বেশি দূরে ছিল"},
    "low_liquidity_session": {"en": "dead session / low liquidity", "bn": "নিস্তেজ সেশন / কম লিকুইডিটি"},
    "missing_context": {"en": "info was missing (say what, in the note)", "bn": "তথ্য ঘাটতি ছিল (নোটে লিখুন কী)"},
    "bad_signal": {"en": "the signal itself was wrong", "bn": "সিগন্যালটাই ভুল ছিল"},
    "other": {"en": "other (explain in the note)", "bn": "অন্য কারণ (নোটে লিখুন)"},
}


class LessonRecord(BaseModel):
    symbol: str
    source: Literal["cio", "setup", "quick_read", "manual"]
    variant: str | None = None  # setup key when source == "setup"
    direction: Literal["long", "short"]
    outcome: Literal["tp", "sl", "invalidated"]
    tags: list[str] = Field(default_factory=list, max_length=4)
    note: str = Field(default="", max_length=500)
    closed_at: datetime

    def key(self) -> str:
        return f"{self.symbol}:{self.closed_at.isoformat()}"


class VariantStats(BaseModel):
    n: int
    wins: int
    losses: int
    win_rate: float | None  # None below MIN_N_FOR_RATE (don't fake a signal)


class LessonsDigest(BaseModel):
    """What the CIO sees + what the journal renders."""

    n_records: int
    by_variant: dict[str, VariantStats]  # keyed "setup:scalp", "cio", ...
    top_tags: list[tuple[str, int]]  # tag -> count, desc
    recent_notes: list[str]  # trimmed, newest first


MIN_N_FOR_RATE = 3  # a win rate over 1-2 trades is noise, not a signal


def _bucket(r: LessonRecord) -> str:
    return f"setup:{r.variant}" if r.source == "setup" and r.variant else r.source


def digest(records: list[LessonRecord]) -> LessonsDigest:
    by_variant: dict[str, dict[str, int]] = {}
    tag_counts: dict[str, int] = {}
    notes: list[str] = []
    for r in records:
        b = by_variant.setdefault(_bucket(r), {"n": 0, "wins": 0, "losses": 0})
        if r.outcome in ("tp", "sl"):
            b["n"] += 1
            b["wins" if r.outcome == "tp" else "losses"] += 1
        if r.outcome != "tp":
            for t in r.tags:
                if t in FAILURE_TAGS:
                    tag_counts[t] = tag_counts.get(t, 0) + 1
            if r.note.strip():
                notes.append(
                    f"[{r.symbol} {r.direction} {_bucket(r)} → {r.outcome}] "
                    + r.note.strip()[:DIGEST_NOTE_CHARS]
                )
    return LessonsDigest(
        n_records=len(records),
        by_variant={
            k: VariantStats(
                n=v["n"], wins=v["wins"], losses=v["losses"],
                win_rate=round(v["wins"] / v["n"], 3) if v["n"] >= MIN_N_FOR_RATE else None,
            )
            for k, v in by_variant.items()
        },
        top_tags=sorted(tag_counts.items(), key=lambda kv: -kv[1])[:5],
        recent_notes=list(reversed(notes))[:DIGEST_RECENT_NOTES],
    )


def cio_payload(d: LessonsDigest) -> dict | None:
    """The compact slice injected into the CIO synthesis input. None when the
    desk has nothing learned yet — an empty lessons block would be noise."""
    if d.n_records == 0:
        return None
    return {
        "note": (
            "The desk's own graded history and the owner's failure post-mortems. "
            "Weigh them; do not repeat named mistakes. These are lessons, not market data."
        ),
        "performance": {
            k: {"n": v.n, "win_rate": v.win_rate}
            for k, v in d.by_variant.items() if v.n > 0
        },
        "recurring_failure_causes": [
            {"cause": FAILURE_TAGS[t]["en"], "count": c} for t, c in d.top_tags
        ],
        "recent_post_mortems": d.recent_notes,
    }


def _atomic_write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class LessonsStore:
    """Rolling record log. Re-posting the same (symbol, closed_at) UPDATES the
    record (the owner may refine a post-mortem note) rather than duplicating."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def _load(self) -> list[LessonRecord]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        out: list[LessonRecord] = []
        for row in raw:
            with contextlib.suppress(Exception):
                out.append(LessonRecord.model_validate(row))
        return out

    def record(self, lesson: LessonRecord) -> LessonsDigest:
        records = [r for r in self._load() if r.key() != lesson.key()]
        records.append(lesson)
        records = records[-MAX_RECORDS:]
        _atomic_write_json(self._path, [r.model_dump(mode="json") for r in records])
        return digest(records)

    def digest(self) -> LessonsDigest:
        return digest(self._load())

    def cio_payload(self) -> dict | None:
        return cio_payload(self.digest())


__all__ = [
    "FAILURE_TAGS",
    "LessonRecord",
    "LessonsDigest",
    "LessonsStore",
    "VariantStats",
    "digest",
    "cio_payload",
]
