"""CIO synthesis (§B5 · ADR-0006 headless mode · ADR-0015) — one desk, one call.

The LLM's job here is judgment-in-prose: weigh the surviving mandate reads,
resolve the disagreement the divergence detector measured, and commit to ONE
plan in the head-trader voice. Everything numeric is either computed in code
or guard-railed against numbers the panel already published:

  * direction   — the CIO may take the panel's plurality direction or STAND
                  ASIDE. It may never counter-trade the panel (vetoing OUT of
                  a trade is safe; vetoing INTO one is how models lose money).
  * levels      — entry/stop/targets must fall within the span the AGREEING
                  analysts published (± 0.5 ATR tolerance for rounding /
                  tightening). The CIO refines the panel's numbers; it cannot
                  invent new ones. Ordering is enforced (long: stop below the
                  zone, targets above it; short mirrored).
  * R:R         — recomputed in code from the final levels. Model arithmetic
                  is never trusted (deterministic before generative).
  * confidence  — ADR-0007's formula, computed in code. The model is not even
                  asked for one.
  * sizing      — risk-based Decimal math (app/desk/sizing.py).
  * evidence    — dot-paths locked against the brief, same as every analyst.

Failure ladder (invariant 2, NFR-3): schema/evidence/guardrail failure gets
ONE corrective retry naming the exact violation; a second failure — or no LLM
configured at all — falls back to `deterministic_fallback`, which assembles a
plan purely from the strongest agreeing analyst's published levels (stop
widened to the panel's most conservative). A desk run with >= 2 survivors
therefore ALWAYS yields a plan; if even the fallback's levels are incoherent,
it emits STAND ASIDE rather than publish garbage.
"""

import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.core.llm import LLMError, LLMGateway
from app.desk.calibration import CalibrationParams
from app.desk.confidence import compute_confidence
from app.desk.divergence import anchor_atr
from app.desk.quick_read import QuickReadConfig, _strip_fences
from app.desk.sizing import position_size
from app.models.analyst import AnalystThesis
from app.models.brief import MarketBrief
from app.models.quickread import (
    EntryZone,
    EvidenceError,
    Invalidation,
    Target,
    check_evidence,
)
from app.models.tradeplan import DivergenceReport, TradePlan

LEVEL_PAD_ATR = Decimal("0.5")  # tolerance around the panel's published span
_RR_Q = Decimal("0.01")


class GuardrailError(ValueError):
    """The draft's numbers stepped outside the panel's published levels."""


class _DraftTarget(BaseModel):
    price: Decimal


class _CIODraft(BaseModel):
    """What the model is allowed to say. No confidence, no rr — those are ours."""

    direction: Literal["long", "short", "no_trade"]
    entry_zone: EntryZone | None = None
    stop_loss: Decimal | None = None
    targets: list[_DraftTarget] = Field(default_factory=list, max_length=3)
    confirmation: list[str] = Field(default_factory=list, max_length=3)
    thesis: str = Field(min_length=20, max_length=900)
    failure_mode: str = Field(min_length=10, max_length=400)
    alternative_scenario: str = Field(min_length=10, max_length=400)
    thesis_bn: str | None = Field(default=None, max_length=1400)
    failure_mode_bn: str | None = Field(default=None, max_length=700)
    invalidation: Invalidation | None = None
    evidence: list[str] = Field(min_length=2, max_length=12)


def _agreeing(theses: list[AnalystThesis], direction: str) -> list[AnalystThesis]:
    return [t for t in theses if t.read.direction == direction]


def _check_guardrails(
    draft: _CIODraft,
    report: DivergenceReport,
    theses: list[AnalystThesis],
    atr: Decimal | None,
) -> None:
    """Raise GuardrailError naming every violation (fed back on retry)."""
    plurality = report.plurality_direction
    problems: list[str] = []

    if draft.direction not in (plurality, "no_trade"):
        raise GuardrailError(
            f"direction must be the panel plurality ({plurality!r}) or 'no_trade' — "
            f"the CIO never counter-trades the panel (got {draft.direction!r})"
        )

    if draft.direction == "no_trade":
        if draft.entry_zone or draft.stop_loss or draft.targets:
            raise GuardrailError("a no_trade call must carry no levels")
        return

    if draft.entry_zone is None or draft.stop_loss is None or not draft.targets or draft.invalidation is None:
        raise GuardrailError(
            "a directional call requires entry_zone, stop_loss, targets and invalidation"
        )

    agree = _agreeing(theses, draft.direction)
    lows = [t.read.entry_zone.low for t in agree]     # directional reads always
    highs = [t.read.entry_zone.high for t in agree]   # carry levels (schema)
    stops = [t.read.stop_loss for t in agree]
    tps = [tgt.price for t in agree for tgt in t.read.targets]
    pad = (LEVEL_PAD_ATR * atr) if atr else Decimal("0")

    ez = draft.entry_zone
    if ez.low > ez.high:
        problems.append("entry_zone.low must be <= entry_zone.high")
    if ez.low < min(lows) - pad or ez.high > max(highs) + pad:
        problems.append(
            f"entry_zone must sit within the agreeing analysts' published span "
            f"[{min(lows)}, {max(highs)}] (±{pad})"
        )
    if draft.stop_loss < min(stops) - pad or draft.stop_loss > max(stops) + pad:
        problems.append(
            f"stop_loss must sit within the panel's published stops "
            f"[{min(stops)}, {max(stops)}] (±{pad})"
        )
    if tps:
        lo_tp, hi_tp = min(tps) - pad, max(tps) + pad
        for i, tgt in enumerate(draft.targets):
            if tgt.price < lo_tp or tgt.price > hi_tp:
                problems.append(
                    f"targets[{i}] must sit within the panel's published targets "
                    f"[{min(tps)}, {max(tps)}] (±{pad})"
                )

    # Ordering: the plan must be geometrically coherent.
    if draft.direction == "long":
        if not draft.stop_loss < ez.low:
            problems.append("long: stop_loss must be below the entry zone")
        for i, tgt in enumerate(draft.targets):
            if not tgt.price > ez.high:
                problems.append(f"long: targets[{i}] must be above the entry zone")
    else:
        if not draft.stop_loss > ez.high:
            problems.append("short: stop_loss must be above the entry zone")
        for i, tgt in enumerate(draft.targets):
            if not tgt.price < ez.low:
                problems.append(f"short: targets[{i}] must be below the entry zone")

    if problems:
        raise GuardrailError("; ".join(problems))


def _targets_with_rr(
    prices: list[Decimal], entry_mid: Decimal, stop: Decimal
) -> list[Target]:
    """R:R recomputed in code from the final levels — never model arithmetic."""
    risk = abs(entry_mid - stop)
    if risk == 0:
        raise GuardrailError("entry midpoint equals stop — no risk distance")
    return [
        Target(
            price=p,
            rr=float((abs(p - entry_mid) / risk).quantize(_RR_Q, rounding=ROUND_HALF_UP)),
        )
        for p in prices
    ]


class CIOSynthesizer:
    def __init__(
        self,
        gateway: LLMGateway,
        config: QuickReadConfig,
        prompt: str,
        risk_pct: Decimal = Decimal("1.0"),
        max_position_pct: Decimal = Decimal("100.0"),
    ) -> None:
        self._gateway = gateway
        self._config = config
        self._prompt = prompt
        self._risk_pct = risk_pct
        self._max_position_pct = max_position_pct

    @property
    def model_id(self) -> str:
        return self._config.model_id

    async def synthesize(
        self,
        brief: MarketBrief,
        theses: list[AnalystThesis],
        report: DivergenceReport,
        calibration: "CalibrationParams | None" = None,
        lessons: dict | None = None,
    ) -> TradePlan:
        """LLM synthesis with guardrails; falls back deterministically. Never
        raises on model failure — a >= 2-survivor desk always gets a plan.
        `calibration` (ADR-0018) adjusts the published confidence only.
        `lessons` (ADR-0019) is the desk's post-mortem memory — it rides the
        payload BESIDE the brief (the brief stays pure market facts) and only
        shapes the prose/judgment; the level guardrails are unchanged by it."""
        brief_data = brief.model_dump(mode="json")
        payload = {
            "brief": brief_data,
            "panel": [t.model_dump(mode="json") for t in theses],
            "divergence": report.model_dump(mode="json"),
        }
        if lessons:
            payload["lessons"] = lessons
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._prompt},
            {"role": "user", "content": "DESK INPUT:\n" + json.dumps(payload)},
        ]
        atr = anchor_atr(brief)

        for _attempt in range(2):  # one shot + one corrective retry
            try:
                raw = await self._gateway.chat(
                    provider=self._config.provider,
                    model=self._config.model,
                    messages=messages,
                    temperature=self._config.temperature,
                    max_tokens=self._config.max_tokens,
                    json_mode=self._config.json_mode,
                )
            except LLMError:
                break  # provider down — straight to the deterministic floor
            try:
                draft = _CIODraft.model_validate(json.loads(_strip_fences(raw)))
                check_evidence(draft.evidence, brief_data)
                _check_guardrails(draft, report, theses, atr)
                return self._plan_from_draft(draft, brief, theses, report, calibration)
            except (json.JSONDecodeError, ValidationError, EvidenceError, GuardrailError) as exc:
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your synthesis was rejected:\n"
                            f"{exc}\n"
                            "Return the corrected JSON object only — no fences, "
                            "no commentary."
                        ),
                    }
                )

        return deterministic_fallback(
            brief, theses, report, self._risk_pct, self._max_position_pct, calibration
        )

    def _plan_from_draft(
        self,
        draft: _CIODraft,
        brief: MarketBrief,
        theses: list[AnalystThesis],
        report: DivergenceReport,
        calibration: "CalibrationParams | None" = None,
    ) -> TradePlan:
        confidence = compute_confidence(brief, draft.direction, theses, report, calibration)
        built_from = sorted({t.mandate for t in _agreeing(theses, draft.direction)})

        if draft.direction == "no_trade":
            return TradePlan(
                symbol=brief.symbol,
                direction="no_trade",
                consensus_state=report.consensus_state,
                confidence=confidence,
                divergence=report,
                thesis=draft.thesis,
                failure_mode=draft.failure_mode,
                alternative_scenario=draft.alternative_scenario,
                thesis_bn=draft.thesis_bn,
                failure_mode_bn=draft.failure_mode_bn,
                evidence=draft.evidence,
                built_from=built_from,
                synthesizer=self.model_id,
            )

        entry_mid = (draft.entry_zone.low + draft.entry_zone.high) / 2
        targets = _targets_with_rr(
            [t.price for t in draft.targets], entry_mid, draft.stop_loss
        )
        sizing = position_size(
            entry_mid, draft.stop_loss, self._risk_pct, self._max_position_pct
        )
        return TradePlan(
            symbol=brief.symbol,
            direction=draft.direction,
            consensus_state=report.consensus_state,
            confidence=confidence,
            divergence=report,
            entry_zone=draft.entry_zone,
            confirmation=draft.confirmation,
            stop_loss=draft.stop_loss,
            targets=targets,
            invalidation=draft.invalidation,
            sizing=sizing,
            thesis=draft.thesis,
            failure_mode=draft.failure_mode,
            alternative_scenario=draft.alternative_scenario,
            thesis_bn=draft.thesis_bn,
            failure_mode_bn=draft.failure_mode_bn,
            evidence=draft.evidence,
            built_from=built_from,
            synthesizer=self.model_id,
        )


def _stand_aside(
    brief: MarketBrief,
    theses: list[AnalystThesis],
    report: DivergenceReport,
    why: str,
    calibration: "CalibrationParams | None" = None,
) -> TradePlan:
    confidence = compute_confidence(brief, "no_trade", theses, report, calibration)
    evidence = []
    for t in theses:
        for e in t.read.evidence:
            if e not in evidence:
                evidence.append(e)
    votes = ", ".join(f"{k} {v}" for k, v in report.votes.items() if v)
    return TradePlan(
        symbol=brief.symbol,
        direction="no_trade",
        consensus_state=report.consensus_state,
        confidence=confidence,
        divergence=report,
        thesis=(
            f"Deterministic synthesis: the desk stands aside on {brief.symbol}. "
            f"{why} Panel votes: {votes}."
        ),
        failure_mode="Standing aside costs nothing but missed opportunity.",
        alternative_scenario=(
            "Re-run the desk when structure resolves or the panel re-aligns."
        ),
        evidence=evidence[:12] or ["alignment.score"],
        built_from=sorted({t.mandate for t in theses}),
        synthesizer="deterministic_fallback",
    )


def deterministic_fallback(
    brief: MarketBrief,
    theses: list[AnalystThesis],
    report: DivergenceReport,
    risk_pct: Decimal = Decimal("1.0"),
    max_position_pct: Decimal = Decimal("100.0"),
    calibration: "CalibrationParams | None" = None,
) -> TradePlan:
    """No-LLM synthesis floor: adopt the strongest agreeing analyst's published
    levels wholesale (coherent by construction), widen the stop to the panel's
    most conservative, recompute rr/sizing. Incoherent levels -> STAND ASIDE."""
    direction = report.plurality_direction

    if direction == "no_trade":
        return _stand_aside(
            brief, theses, report,
            "No directional plurality survived the panel.", calibration,
        )

    agree = _agreeing(theses, direction)
    best = max(agree, key=lambda t: t.read.conviction)  # ties -> seat order
    read = best.read
    stops = [t.read.stop_loss for t in agree]
    stop = min(stops) if direction == "long" else max(stops)  # panel-widest

    ez = read.entry_zone
    entry_mid = (ez.low + ez.high) / 2
    coherent = (
        (direction == "long" and stop < ez.low and all(t.price > ez.high for t in read.targets))
        or (direction == "short" and stop > ez.high and all(t.price < ez.low for t in read.targets))
    )
    if not coherent or entry_mid == stop:
        return _stand_aside(
            brief,
            theses,
            report,
            "The agreeing seats' levels are not geometrically coherent; "
            "no plan is published on incoherent numbers.",
            calibration,
        )

    targets = _targets_with_rr([t.price for t in read.targets], entry_mid, stop)
    sizing = position_size(entry_mid, stop, risk_pct, max_position_pct)
    confidence = compute_confidence(brief, direction, theses, report, calibration)
    invalidation = read.invalidation or Invalidation(
        price=stop, condition="price closes beyond the panel's widest stop"
    )
    n_agree = len(agree)
    return TradePlan(
        symbol=brief.symbol,
        direction=direction,
        consensus_state=report.consensus_state,
        confidence=confidence,
        divergence=report,
        entry_zone=ez,
        confirmation=[],
        stop_loss=stop,
        targets=targets,
        invalidation=invalidation,
        sizing=sizing,
        thesis=(
            f"Deterministic synthesis (no model available): {n_agree} of "
            f"{len(theses)} surviving seats read {brief.symbol} {direction}; "
            f"levels adopted from the {best.mandate} seat (conviction "
            f"{read.conviction}/5), stop widened to the panel's most "
            f"conservative. Panel thesis: {read.thesis[:300]}"
        )[:900],
        failure_mode=read.failure_mode,
        alternative_scenario=(
            "The dissenting/abstaining seats' case plays out — re-run the desk "
            "if structure breaks against the plan."
        ),
        evidence=read.evidence,
        built_from=sorted({t.mandate for t in agree}),
        synthesizer="deterministic_fallback",
    )


__all__ = ["CIOSynthesizer", "deterministic_fallback", "GuardrailError"]
