# DARKPOOL MCP server — the interactive-CIO seam

The MCP server (ADR-0006) lets **Claude Code act as the desk's Chief Investment
Officer**. It exposes the desk's data + actions as tools; *you* (whatever model
you run in Claude Code — Fable for the money-math, per the standing orders) read
the analyst debate and make the final call. The server serves facts and records
your decision — it never fabricates a verdict.

Runs as a separate stdio process on your dev machine, with its own adapters +
desk. It reads keys from `backend/.env` (never from this config).

## Connect it

A project config already exists at repo root — [`.mcp.json`](../.mcp.json):

```json
{ "mcpServers": { "darkpool": {
  "command": "backend/.venv/Scripts/python.exe",
  "args": ["-m", "app.mcp.server"],
  "env": { "PYTHONPATH": "backend" }
}}}
```

Launch Claude Code from the repo root (`E:\AI Trade`) and approve the `darkpool`
server when prompted (`/mcp` lists it). If the relative path isn't picked up,
register it explicitly with an absolute python path:

```
claude mcp add darkpool -- "E:\AI Trade\backend\.venv\Scripts\python.exe" -m app.mcp.server
```

- **Windows** python: `backend\.venv\Scripts\python.exe`
- **Linux/macOS** python: `backend/.venv/bin/python`

Smoke-test the process directly (should print JSON-RPC handshake, then Ctrl-C):
`cd backend && .venv/Scripts/python.exe -m app.mcp.server`

## Tools

| Tool | What it does |
|---|---|
| `desk_health()` | Which AI tiers are wired + the analyst-panel seats. |
| `get_market_brief(symbol)` | The deterministic Market Brief (5m/15m/1h/4h/1d): structure, zones, liquidity, indicators, derivatives, sentiment. No AI. |
| `quick_read(symbol)` | Tier-1: one fast, evidence-locked AI read. |
| `run_full_desk(symbol)` | Tier-2: the 4 mandate analysts' evidence-locked theses **for you to synthesize**. |
| `save_trade_plan(...)` | Persist your CIO plan (file store now → Postgres later). Advisory only. |
| `list_trade_plans(symbol?, limit)` | Recent CIO plans, newest first. |

## The CIO loop (how you use it)

1. `run_full_desk("BTCUSDT")` → four theses (Trend / Contrarian / Derivatives /
   Risk) + a direction tally. Some seats may be rate-limited and dropped — the
   run continues with the survivors.
2. **You** weigh the debate — this is the Fable-tier synthesis the desk
   deliberately does not automate: resolve the conflict, set conviction, size
   the risk, define invalidation.
3. `save_trade_plan(...)` → records your call. (Grading + calibration land in P3.)

Every analyst number is evidence-locked to the brief, so you're synthesizing
verified facts, never model hallucinations. Nothing here executes a trade — the
`Broker` stays paper in v1 (ADR-0008); the future approval-gated
`propose_order` flow will plug into this same MCP surface.
