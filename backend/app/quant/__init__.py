"""Deterministic quant/SMC engine (FR-2).

Everything in this package is a pure function of candle data — no I/O, no LLMs,
fully unit-tested against golden fixtures. Its output (the Market Brief) is the
only source of numbers the AI layer is ever allowed to cite (invariant 7).
"""
