"""Stage 16A API-primary provider with fail-closed local model fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

import pytest
from pydantic import SecretStr
from pydantic_core import ValidationError

from app.ai.errors import (
    ProviderAuthError,
    ProviderQuotaError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.ai.providers import build_provider
from app.ai.providers.fallback import FallbackExhaustedError, PrimaryThenLocalProvider
from app.ai.types import ModelRequest, ModelResponse, Usage
from app.core.config import Settings


@dataclass
class FakeModel:
    name: str
    is_external: bool
    model: str = "fake"
    failure: Exception | None = None
    calls: int = 0
    warnings: ClassVar[tuple[str, ...]] = ()

    def complete(self, _request: ModelRequest) -> ModelResponse:
        self.calls += 1
        if self.failure:
            raise self.failure
        return ModelResponse(
            content="test reply",
            tool_calls=(),
            usage=Usage(10, 5),
            finish_reason="stop",
            provider=self.name,
            model=self.model,
        )


def request() -> ModelRequest:
    return ModelRequest(
        messages=(), tools=(), max_output_tokens=100, timeout_seconds=1,
        request_id="stage16-test",
    )


def test_primary_success_never_contacts_local_model() -> None:
    primary = FakeModel("deepseek", True)
    local = FakeModel("ollama", False)
    switched = PrimaryThenLocalProvider(primary, local)
    response = switched.complete(request())
    assert response.provider == "deepseek"
    assert primary.calls == 1
    assert local.calls == 0


@pytest.mark.parametrize(
    "failure",
    [
        ProviderQuotaError(),
        ProviderRateLimitedError(),
        ProviderTimeoutError(),
        ProviderUnavailableError(),
    ],
)
def test_documented_outages_use_local_fallback(failure: Exception) -> None:
    primary = FakeModel("deepseek", True, failure=failure)
    local = FakeModel("ollama", False, model="qwen3:8b")
    response = PrimaryThenLocalProvider(primary, local).complete(request())
    assert response.provider == "ollama"
    assert response.model == "qwen3:8b"
    assert "LOCAL_FALLBACK_USED" in response.warnings
    assert primary.calls == local.calls == 1


def test_bad_credentials_never_use_unapproved_local_fallback() -> None:
    primary = FakeModel("deepseek", True, failure=ProviderAuthError())
    local = FakeModel("ollama", False)
    with pytest.raises(ProviderAuthError):
        PrimaryThenLocalProvider(primary, local).complete(request())
    assert local.calls == 0


def test_two_failures_emit_nonretryable_generic_unavailable() -> None:
    primary = FakeModel("deepseek", True, failure=ProviderTimeoutError())
    local = FakeModel("ollama", False, failure=ProviderUnavailableError())
    with pytest.raises(FallbackExhaustedError) as captured:
        PrimaryThenLocalProvider(primary, local).complete(request())
    assert captured.value.retryable is False
    assert primary.calls == 1
    assert local.calls == 1


def test_misconfigured_provider_pair_is_rejected() -> None:
    with pytest.raises(ValueError):
        PrimaryThenLocalProvider(FakeModel("a", False), FakeModel("b", False))
    with pytest.raises(ValueError):
        PrimaryThenLocalProvider(FakeModel("a", True), FakeModel("b", True))


def valid_settings(**changes: object) -> Settings:
    defaults: dict[str, object] = {
        "environment": "test",
        "ai_enabled": True,
        "ai_provider": "openai_compatible",
        "ai_model": "deepseek-chat",
        "ai_base_url": "https://api.deepseek.com",
        "ai_api_key": SecretStr("test-key-not-real"),
        "ai_external_processing_acknowledged": True,
        "ai_local_fallback_enabled": True,
    }
    return Settings(**(defaults | changes))


def test_factory_wires_only_opt_in_loopback_fallback() -> None:
    provider = build_provider(valid_settings())
    assert isinstance(provider, PrimaryThenLocalProvider)
    assert provider.local.is_external is False
    assert provider.local.model == "qwen3:8b"
    assert provider.primary.is_external is True
    assert build_provider(valid_settings(ai_local_fallback_enabled=False)).name == "openai_compatible"


@pytest.mark.parametrize(
    "bad",
    [
        "https://api.example.com/v1",
        "http://192.168.1.2:11434/v1",
        "http://localhost:11434/v1",
        "http://127.0.0.1:11434/",
        "http://user:password@127.0.0.1:11434/v1",
        "http://127.0.0.1:11434/v1?q=x",
        "http://127.0.0.1:99999/v1",
    ],
)
def test_local_fallback_rejects_non_loopback_or_untrusted_urls(bad: str) -> None:
    with pytest.raises(ValidationError):
        valid_settings(ai_local_fallback_base_url=bad)


def test_fallback_refused_when_primary_disabled_or_mock() -> None:
    with pytest.raises(ValidationError):
        valid_settings(ai_enabled=False)
    with pytest.raises(ValidationError):
        valid_settings(ai_provider="mock")
