"""Monitoring (P3 · FR-5) — deterministic alert rules + the background scanner.

`alerts.py` is pure functions: a brief in, notable conditions out. No AI, no
network. `scanner.py` ticks that engine over the watchlist in Active mode;
`state.py` holds the file-backed mode/watchlist/feed stores it shares with the
`/monitor/*` routes. Browser push (service worker + Push API) and grading +
calibration (Fable-tier, §F5) are separate, later steps.
"""
