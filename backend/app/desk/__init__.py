"""The Desk — LLM-facing analysis services (Quick Read now, panel + CIO in P2).

Everything here consumes the deterministic Market Brief and produces
schema-validated output. Deterministic before generative (invariant 7):
nothing in this package computes market facts — it interprets them.
"""
