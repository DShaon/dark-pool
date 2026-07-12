# ADR-0016 — User-managed model roster (providers, keys, roles) from the UI

**Status:** accepted · 2026-07-10 · **authored on Fable** (key-handling is invariant-4
territory; the rules are settled here, the build is Opus work)
**Extends:** ADR-0004 (config roster) · ADR-0012 (gateway). `models.yaml` remains the
shipped DEFAULT; the user's runtime roster OVERLAYS it.

## Context
The desk owner wants to add any provider/model (free or paid) from the Settings UI and
assign each one a role — without editing YAML/.env and "without facing any error."

## Decisions
1. **Store:** `RosterStore` (file-backed, `backend/data/roster.json`, gitignored,
   atomic writes — same pattern as ModeStore). Shape:
   `providers: {name -> {base_url, api_key}}` ·
   `roles: {quick_read|trend|contrarian|derivatives|risk|cio -> {provider, model,
   temperature?, max_tokens?}}`. Any OpenAI-compatible base URL is allowed; the UI
   offers presets (groq/gemini/openrouter/deepseek/together/local Ollama) plus a
   custom field.
2. **Overlay, not replace:** effective config = `models.yaml` deep-merged under the
   store (store wins). Deleting a store entry falls back to YAML. `build_desk` gains a
   merged-config path and services are REBUILT in place on every roster change (no
   restart).
3. **Key security (invariant 4, non-negotiable):**
   - Keys are POSTed once over the local API, written only to the gitignored store.
   - GET endpoints return keys **masked** (`····last4`); the full key never travels
     back to the browser, never appears in logs or error messages.
   - The frontend keeps keys only in the controlled input while typing — never in
     localStorage, never in component state after save.
4. **"Without facing any error" = validate-before-save:** `POST /models/test` makes a
   1-token live call with the candidate (provider, key, model) and returns ok/fail +
   the provider's message. Saving a provider/role runs the same test first; a failing
   entry is rejected with the reason shown — a broken roster can never be persisted.
   Role assignment additionally requires the provider to exist and the prompt file for
   that role to exist.
5. **API:** `GET /models/roster` (masked) · `POST /models/provider` ·
   `DELETE /models/provider/{name}` (refused while a role uses it) ·
   `POST /models/role` · `DELETE /models/role/{role}` (falls back to YAML) ·
   `POST /models/test`. All behind the same bearer auth as the rest.
6. **UI:** Settings → "Model Desk": provider cards (status dot = last test result,
   masked key, re-test button) · add-provider form (preset or custom base URL) · role
   matrix (6 roles, each a provider+model picker with per-role test) · a "source"
   line showing whether each role currently runs from YAML default or user roster.

## Consequences
Any model can hold any seat without code changes; a paid Anthropic/OpenAI-compatible
endpoint drops in the same way. The quota field-notes stay in YAML as documentation.
Misconfiguration is caught at save time, not at the next desk run.
