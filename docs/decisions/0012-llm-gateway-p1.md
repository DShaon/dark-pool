# ADR-0012 — P1 LLM gateway: minimal OpenAI-compat httpx client (LiteLLM deferred)

**Status:** accepted · 2026-07-07
**Amends:** ADR-0004 (LiteLLM roster) — scope only, not direction.

## Context
P1's Quick Read needs exactly one capability: async chat-completions against
free providers (Groq, OpenRouter, Google AI Studio). All three expose the
OpenAI chat-completions dialect. LiteLLM (ADR-0004's chosen router) delivers
this too, but drags in a large dependency tree — a real cost on the
Windows-dev / Linux-ARM-deploy axis we keep pure and small (§F6), for
functionality P1 doesn't use (routing, fallbacks, cost tracking across 100+
providers).

## Decision
- P1 ships `app/core/llm.py`: a ~90-line httpx client speaking OpenAI
  chat-completions, providers declared in `config/models.yaml`
  (`base_url` + `key_setting` → Settings field; keys only in env).
- The YAML shape (provider/model per seat) is LiteLLM-compatible on purpose:
  when P2's multi-seat panel wants real routing/fallback/cost accounting,
  LiteLLM replaces the gateway's internals behind the same `chat()` surface
  and the same YAML — call sites and config don't change.

## Consequences
- Zero new heavy dependencies in P1 (PyYAML only); the boundary contract
  (Pydantic validation, one-retry-then-drop, evidence lock) lives in
  `app/desk/` and is gateway-agnostic.
- Providers with non-OpenAI dialects (e.g. raw Anthropic API for a headless
  CIO) are NOT reachable until the LiteLLM swap — acceptable: the interactive
  CIO runs over MCP (ADR-0006), not this gateway.
- Re-evaluate at P2 kickoff; adopting LiteLLM then is the default plan, not a
  new debate.
