from __future__ import annotations

from typing import Protocol

from briefing.config import Config


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str, tier: str) -> str:
        """Return the model's text response. `tier` is 'score' or 'generate'."""


def get_provider(config: Config, override: str | None = None) -> Provider:
    name = override or config.get("llm.provider")
    if name == "stub":
        from briefing.llm.stub import StubProvider

        return StubProvider(config)
    if name == "gemini":
        from briefing.llm.gemini import GeminiProvider

        return GeminiProvider(config)
    raise ValueError(f"unsupported llm provider: {name!r}")


def model_for(config: Config, provider_name: str, tier: str) -> str:
    return config.get(f"llm.tiers.{tier}.{provider_name}")
