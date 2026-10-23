"""Explicit fail-closed API-primary, local-Ollama fallback for Stage 16A.

The local endpoint is fixed by Settings to an actual loopback address. The
fallback never executes a command or launches Ollama and never contacts any
public fallback service. Quota/429/timeout/unavailable failures are the only
switch conditions; authorization or malformed-model output still fail closed.
"""

from __future__ import annotations

from dataclasses import replace

from app.ai.errors import (
    ProviderError,
    ProviderQuotaError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.ai.providers.base import ModelProvider
from app.ai.providers.openai_compat import OpenAICompatibleProvider
from app.ai.types import ModelRequest, ModelResponse


class LocalOllamaProvider(OpenAICompatibleProvider):
    """OpenAI-compatible Ollama at an operator-approved loopback address."""

    name = "ollama_local"
    is_external = False


class FallbackExhaustedError(ProviderError):
    """Both configured providers failed; do not retry and incur extra API calls."""

    status_code = 503
    retryable = False
    default_message = "Neither the primary AI API nor the local model is available."


class PrimaryThenLocalProvider:
    """Use a real remote provider, then local model only for availability failures."""

    name = "primary_with_local_fallback"
    is_external = True

    def __init__(self, primary: ModelProvider, local: ModelProvider) -> None:
        if not primary.is_external or local.is_external:
            raise ValueError("Primary must be external; fallback must be local")
        self.primary = primary
        self.local = local
        self.model = primary.model

    def complete(self, request: ModelRequest) -> ModelResponse:
        try:
            return self.primary.complete(request)
        except (
            ProviderQuotaError,
            ProviderRateLimitedError,
            ProviderTimeoutError,
            ProviderUnavailableError,
        ):
            try:
                response = self.local.complete(request)
            except ProviderError:
                raise FallbackExhaustedError() from None
            return replace(
                response,
                provider=self.local.name,
                model=self.local.model,
                warnings=(*response.warnings, "LOCAL_FALLBACK_USED"),
            )
