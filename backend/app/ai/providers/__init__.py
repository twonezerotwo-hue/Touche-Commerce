"""Provider adapters and the factory that builds the configured one."""

from __future__ import annotations

from pydantic import SecretStr

from app.ai.errors import AIDisabledError
from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.base import ModelProvider
from app.ai.providers.fallback import LocalOllamaProvider, PrimaryThenLocalProvider
from app.ai.providers.mock import MockProvider
from app.ai.providers.openai_compat import OpenAICompatibleProvider
from app.core.config import Settings


def build_provider(settings: Settings) -> ModelProvider:
    """Create the provider the settings select (credentials stay server-side)."""
    if not settings.ai_enabled:
        raise AIDisabledError()
    if settings.ai_provider == "mock":
        return MockProvider(settings.ai_model)
    base_url = settings.ai_effective_base_url
    if settings.ai_api_key is None or base_url is None:  # pragma: no cover - Settings validates
        raise AIDisabledError("The AI provider is not configured.")
    if settings.ai_provider == "anthropic":
        return AnthropicProvider(
            base_url=base_url, api_key=settings.ai_api_key, model=settings.ai_model
        )
    primary = OpenAICompatibleProvider(
        base_url=base_url, api_key=settings.ai_api_key, model=settings.ai_model
    )
    if not settings.ai_local_fallback_enabled:
        return primary
    local = LocalOllamaProvider(
        base_url=settings.ai_local_fallback_base_url,
        api_key=SecretStr("local-ollama-no-credential"),
        model=settings.ai_local_fallback_model,
    )
    return PrimaryThenLocalProvider(primary, local)


__all__ = [
    "AnthropicProvider",
    "MockProvider",
    "ModelProvider",
    "OpenAICompatibleProvider",
    "LocalOllamaProvider",
    "PrimaryThenLocalProvider",
    "build_provider",
]
