# ADR-0013 — Typography amendment (Space Grotesk) + readability lift

**Status:** accepted · 2026-07-08
**Amends:** ADR-0010 (DARKPOOL tokens / MASTER_PLAN §C1–C2) — the UI typeface and
two text tokens only. Motion, color semantics, gold-for-AI, and the banned list
are unchanged.

## Context
The desk owner reviewed the running P1 UI and asked for a typeface that feels
like a "brand, futuristic" trading product yet stays comfortable and instantly
legible — and flagged that several important labels (entry / stop / target /
conviction, and the setup edge sentences) were too faint to read on the obsidian
ground. MASTER_PLAN §C2 had specified Instrument Sans for UI; §C1 set
`--text-mid #93a0b4` / `--text-dim #5a6778`. These are the settled decisions this
ADR revisits (per the process rule: a change needs an ADR, not silent drift).

## Decision
- **UI typeface: Space Grotesk** (weights 400–700) replaces Instrument Sans as
  `--font-sans`. Geometric and distinctive enough to read as a brand, still calm
  at label sizes. IBM Plex / Geist Mono stays for all numerics (tabular
  alignment is non-negotiable); Instrument Serif Italic stays for the one
  emotional moment — the gold verdict word (§C2 unchanged in spirit).
- **Contrast lift:** `--text-mid` → `#aeb9cb`, `--text-dim` → `#7c8698`. Trade-
  plan labels (entry/stop/tp/invalid/conv) and setup edge lines are additionally
  promoted from `dim` to `mid`. Chrome stays quiet; the money-critical words no
  longer whisper.

## Consequences
- Purely presentational: no engine, schema, or data-contract change. The obsidian
  palette, teal/red semantics, and gold-only-for-AI rule are untouched, so the
  "fact vs. judgment" read still holds.
- One font swap in `layout.tsx` + two token values in `globals.css` — trivially
  reversible if the owner prefers a different brand face later.
- MASTER_PLAN §C1/§C2 are now aliased through the tokens; treat this ADR as the
  source of truth for the typeface and the two lifted values.
