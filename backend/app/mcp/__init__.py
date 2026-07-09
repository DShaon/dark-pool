"""MCP surface (ADR-0006) — the interactive-CIO seam.

`app.mcp.server` runs a FastMCP stdio server exposing the desk's read/run/save
tools so Claude Code can act as CIO. Isolated from the FastAPI app: importing
this package builds its own adapters + desk, so the HTTP service is unaffected.
"""
