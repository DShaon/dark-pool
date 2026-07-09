# ADR-0004: LLM access via LiteLLM, roster in config

**Status:** Accepted (2026-07-06)

**Context.** The user must be able to swap any AI model (API or local Ollama) at will;
prices/quality shift monthly.

**Decision.** All model calls go through LiteLLM. The analyst roster, synthesizer, and
per-model params live in `models.yaml` (+ env for keys). No model ID is hardcoded.

**Consequences.** Model swaps are config edits, zero code change. Spend caps are enforced
where calls are made (one choke point).
