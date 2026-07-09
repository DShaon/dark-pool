# ADR-0001: Stack — Python/FastAPI backend, Next.js/TypeScript frontend

**Status:** Accepted (2026-07-06)

**Context.** The quant/trading ecosystem (ccxt, pandas, pandas-ta, smartmoneyconcepts,
vectorbt, LiteLLM) is Python-native; the premium UI target and the user's skills favor React.

**Decision.** Backend = Python 3.12 + FastAPI (async). Frontend = Next.js 15 + TypeScript.
One clean REST/WS contract between them; both sides typed.

**Consequences.** Two languages, mitigated by a stable API contract. No TA-Lib (C ext) —
pure-Python deps only, so Windows dev == Linux ARM prod.
