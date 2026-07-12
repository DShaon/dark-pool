"""Scenario path service (ADR-0017 §2) — resolves an AI-sequenced path over
REAL levels. The model picks which existing price fields to visit and in what
order; this service resolves each to its actual price and assigns future bar
offsets. No price is ever invented (invariant 7).

Same one-corrective-retry-then-drop discipline as every LLM boundary
(invariant 2): a scenario that cites an unresolvable level, or fails schema, is
retried once then reported `unavailable` — never patched, never a 500.
"""

import json
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from app.core.llm import LLMError, LLMGateway
from app.desk.quick_read import QuickReadConfig, _strip_fences
from app.models.quickread import resolve_path
from app.models.scenario import ScenarioPath, Waypoint

# The scenario is drawn across roughly this many future bars.
FUTURE_HORIZON_BARS = 12


class ScenarioError(RuntimeError):
    """The model failed twice to produce a valid, level-locked scenario."""


def _check_refs(context: dict, paths: list[str]) -> None:
    """Every evidence path must resolve inside the context; raise if any don't."""
    bad = []
    for p in paths:
        try:
            resolve_path(context, p)
        except KeyError:
            bad.append(p)
    if bad:
        raise KeyError(f"evidence paths not found in context: {', '.join(bad)}")


def _resolve_price(context: dict, ref: str) -> Decimal:
    """Resolve a dot-path to a real price; raise if it is missing or non-numeric."""
    value = resolve_path(context, ref)  # raises KeyError if the path is absent
    if isinstance(value, bool):
        raise InvalidOperation(f"{ref} is not a price")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise InvalidOperation(f"{ref} does not resolve to a price: {value!r}") from exc


def _assign_offsets(n: int) -> list[int]:
    """Evenly spaced future bar offsets, 1..HORIZON."""
    return [max(1, round((i + 1) * FUTURE_HORIZON_BARS / n)) for i in range(n)]


class ScenarioService:
    def __init__(self, gateway: LLMGateway, config: QuickReadConfig, prompt: str) -> None:
        self._gateway = gateway
        self._config = config
        self._prompt = prompt

    @property
    def model_id(self) -> str:
        return self._config.model_id

    async def build(self, brief_data: dict, plan_data: dict | None) -> ScenarioPath:
        """Return a ScenarioPath with every waypoint resolved to a real price.

        `brief_data` / `plan_data` are JSON-mode dicts. Refs resolve against
        `{"brief": ..., "plan": ...}`; evidence resolves against the brief.
        """
        context: dict = {"brief": brief_data}
        if plan_data is not None:
            context["plan"] = plan_data

        messages = [
            {"role": "system", "content": self._prompt},
            {"role": "user", "content": "CONTEXT:\n" + json.dumps(context)},
        ]

        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                raw = await self._gateway.chat(
                    provider=self._config.provider,
                    model=self._config.model,
                    messages=messages,
                    temperature=self._config.temperature,
                    max_tokens=self._config.max_tokens,
                    json_mode=self._config.json_mode,
                )
            except LLMError as exc:
                raise ScenarioError(str(exc)) from exc
            try:
                path = ScenarioPath.model_validate(json.loads(_strip_fences(raw)))
                # evidence lock — resolved against the same brief/plan context
                _check_refs(context, path.evidence)
                # resolve every waypoint to a REAL price (the anti-forecast lock)
                offsets = _assign_offsets(len(path.waypoints))
                resolved: list[Waypoint] = []
                for wp, off in zip(path.waypoints, offsets):
                    price = _resolve_price(context, wp.level_ref)
                    resolved.append(
                        wp.model_copy(update={"price": price, "bar_offset": off})
                    )
                return path.model_copy(update={"waypoints": resolved})
            except (json.JSONDecodeError, ValidationError, KeyError, InvalidOperation) as exc:
                last_error = exc
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your scenario was rejected:\n"
                            f"{exc}\n"
                            "Every waypoint.level_ref must be a dot-path that resolves "
                            "to a REAL price under `brief.` or `plan.` in the CONTEXT. "
                            "Return corrected JSON only — no fences, no commentary."
                        ),
                    }
                )

        raise ScenarioError(f"dropped after retry: {last_error}")


__all__ = ["ScenarioService", "ScenarioError", "FUTURE_HORIZON_BARS"]
