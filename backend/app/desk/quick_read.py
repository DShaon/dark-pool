"""Quick Read service — one model, one pass, strictly validated (FR-3 tier 1).

Flow: Market Brief → versioned prompt → gateway → parse → QuickRead schema →
evidence lock. Any failure gets exactly ONE corrective retry (the validator's
complaint is appended to the conversation); a second failure raises
QuickReadError and the caller degrades gracefully — a dropped read never
blocks a run (CLAUDE.md invariant 2, NFR-3).
"""

import json
from dataclasses import dataclass

from pydantic import ValidationError

from app.core.llm import LLMError, LLMGateway
from app.models.brief import MarketBrief
from app.models.quickread import EvidenceError, QuickRead, check_evidence


class QuickReadError(RuntimeError):
    """The model failed twice to produce a valid, evidence-locked read."""


@dataclass(frozen=True)
class QuickReadConfig:
    provider: str
    model: str
    temperature: float = 0.3
    max_tokens: int = 1200
    json_mode: bool = True

    @property
    def model_id(self) -> str:
        return f"{self.provider}/{self.model}"


def _strip_fences(raw: str) -> str:
    """Tolerate models that wrap JSON in markdown fences despite instructions."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


class QuickReadService:
    def __init__(self, gateway: LLMGateway, config: QuickReadConfig, prompt: str) -> None:
        self._gateway = gateway
        self._config = config
        self._prompt = prompt

    @property
    def model_id(self) -> str:
        return self._config.model_id

    async def run(self, brief: MarketBrief) -> QuickRead:
        brief_data = brief.model_dump(mode="json")
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._prompt},
            {"role": "user", "content": "MARKET BRIEF:\n" + json.dumps(brief_data)},
        ]

        last_error: Exception | None = None
        for _attempt in range(2):  # one shot + one corrective retry
            raw = await self._gateway.chat(
                provider=self._config.provider,
                model=self._config.model,
                messages=messages,
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
                json_mode=self._config.json_mode,
            )
            try:
                parsed = json.loads(_strip_fences(raw))
                read = QuickRead.model_validate(parsed)
                check_evidence(read.evidence, brief_data)
                return read
            except (json.JSONDecodeError, ValidationError, EvidenceError) as exc:
                last_error = exc
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your output failed validation and was rejected:\n"
                            f"{exc}\n"
                            "Return the corrected JSON object only — no fences, "
                            "no commentary."
                        ),
                    }
                )

        raise QuickReadError(f"dropped after retry: {last_error}")


__all__ = ["QuickReadConfig", "QuickReadError", "QuickReadService", "LLMError"]
