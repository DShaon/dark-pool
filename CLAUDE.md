# DARKPOOL — Standing Orders

AI trading intelligence desk. Crypto (Binance) first, forex later. Advisory only in v1.
**Master plan (single source of truth): `docs/MASTER_PLAN.md`** — read it before large work.
Current phase and per-phase exit criteria: see `docs/MASTER_PLAN.md` PART D + `docs/STATUS.md`.

## Non-negotiable invariants
1. **All external data-source I/O goes through `backend/app/adapters/`** (market,
   on-chain, macro, sentiment, news). Infrastructure clients (cache, DB, LLM gateway)
   live in `backend/app/core/`. No ad-hoc HTTP anywhere else.
2. **Every LLM boundary is Pydantic-validated.** One retry on failure, then drop the
   analyst — never hand-patch model output. A dropped analyst never blocks a run.
3. **`Decimal` for all money/price math** (parse from `str`, never `float`). Never compare
   floats for equality. **All timestamps are UTC** (`datetime` with `timezone.utc`).
4. **Secrets live server-side** in env only — never in frontend code, git, or logs.
5. **No live-execution code paths in v1.** The `Broker` interface stays paper/stub.
6. **Config over code:** models, providers, thresholds, mandates live in YAML/env — not constants.
7. **Deterministic before generative:** an LLM may only cite numbers that already exist in
   the Market Brief. LLMs interpret facts; they never invent them.

## Process rules
- Settled decisions live in `docs/decisions/` (ADRs). Do not relitigate them; a change
  requires a new ADR, not silent divergence.
- Ambiguity → ask the user. Never improvise architecture.
- Definition of done: typed + schema-validated + unit-tested (golden fixtures for quant
  code) + error paths handled + module docstring updated.
- Dev on Windows, deploy on Linux ARM: dependencies stay pure-Python (`pandas-ta`, never
  TA-Lib). CI on Linux is the drift check.

## Design rules (frontend)
Implement `docs/MASTER_PLAN.md` PART C ("DARKPOOL") exactly: tokens in C1, type in C2,
motion + performance budget in C4/C5, **user-taste amendments in C6a / ADR-0011** (glow
discipline: live data may glow, chrome never; card radius 12px; Desk Pipeline Map; hero
tiles; Desk Tape; arc dials). **Banned:** purple gradients, glassmorphism, drop shadows,
bouncing easings, spinners. Market data = obsidian monochrome + teal/red semantics;
**AI judgment is always gold (`--ai-gold`)**. All numerics tabular mono.

## Session protocol
Read this file → the relevant ADRs → `docs/STATUS.md` → work the current phase checklist
top-down. Escalate ambiguity as a question. Money-risk logic (consensus/CIO, SMC
correctness, sizing/risk, grading/calibration/backtest math) is **Fable-tier work** —
flag it rather than improvising on a lighter model.
