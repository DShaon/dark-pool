"""LLM gateway — the single place model calls leave the process.

Speaks the OpenAI chat-completions dialect, which Groq, OpenRouter and
Google's Gemini-compat endpoint all share, so one tiny httpx client covers
the whole free roster (ADR-0012). Providers and models come from
config/models.yaml; keys come from Settings fields — never from YAML.

This module transports text; it validates nothing. Schema enforcement is the
caller's job (CLAUDE.md invariant 2 lives at the desk layer, not here).
"""

from dataclasses import dataclass

import httpx


class LLMError(RuntimeError):
    """A provider call failed (network, auth, quota, or malformed response)."""

    def __init__(self, provider: str, detail: str) -> None:
        self.provider = provider
        self.detail = detail
        super().__init__(f"{provider}: {detail}")


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str


class LLMGateway:
    """Async chat-completions client over any OpenAI-compatible provider."""

    def __init__(self, providers: dict[str, ProviderConfig], timeout_s: float = 60.0) -> None:
        self._providers = providers
        self._client = httpx.AsyncClient(timeout=timeout_s)

    @property
    def provider_names(self) -> list[str]:
        return sorted(self._providers)

    async def chat(
        self,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1200,
        json_mode: bool = False,
    ) -> str:
        cfg = self._providers.get(provider)
        if cfg is None:
            raise LLMError(provider, "provider not configured (missing API key?)")

        payload: dict[str, object] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = await self._client.post(
                f"{cfg.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {cfg.api_key}"},
            )
        except httpx.HTTPError as exc:
            raise LLMError(provider, f"transport error: {exc}") from exc

        if resp.status_code != 200:
            # Body may carry provider error text; keys never appear in it.
            raise LLMError(provider, f"HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(provider, f"malformed completion payload: {exc}") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMError(provider, "empty completion")
        return content

    async def aclose(self) -> None:
        await self._client.aclose()
