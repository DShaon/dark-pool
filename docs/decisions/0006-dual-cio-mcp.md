# ADR-0006: Dual-mode CIO via MCP

**Status:** Accepted (2026-07-06)

**Context.** The heaviest reasoning (final synthesis) is the most valuable and most
expensive step. The user has a Claude subscription (Claude Code) and wants agency, not
just text.

**Decision.** The backend exposes an MCP server (FastMCP) with desk tools
(`get_market_brief`, `run_analysis`, `get_analyst_debate`, `save_trade_plan`,
`journal_add`, `get_performance_stats`, later `run_backtest`, `propose_order`).
INTERACTIVE CIO = Claude Code (Fable 5, Opus fallback) over MCP — subscription-powered.
HEADLESS CIO = any API model via LiteLLM for background runs/alerts. Both emit the same
TradePlan schema.

**Consequences.** Premium reasoning at ~$0 marginal cost; the future approval-gated
execution bot plugs into the same MCP surface.
