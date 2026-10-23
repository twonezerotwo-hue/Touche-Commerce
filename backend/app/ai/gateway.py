"""The AI Gateway: timeouts, bounded retries, budgets, concurrency and cancellation.

One class sits between the Trade Director and any :class:`ModelProvider`. It adds no
business logic: it enforces limits, maps failures and records usage. Prompts and
completions are never logged — only sizes, counts and identifiers.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from decimal import Decimal
from uuid import UUID

from app.ai.errors import (
    AIBudgetExceededError,
    AIRunCancelledError,
    AITooManyRunsError,
    ProviderError,
    ProviderRateLimitedError,
)
from app.ai.providers.base import ModelProvider
from app.ai.types import (
    ModelRequest,
    ModelResponse,
    Usage,
    estimate_request_tokens,
    estimate_tokens,
)
from app.core.config import Settings

logger = logging.getLogger("app.ai.gateway")

_MAX_BACKOFF_SECONDS = 5.0


class CancelToken:
    """Cooperative cancellation, checked between every model step and tool call."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise AIRunCancelledError()

    def wait(self, seconds: float) -> None:
        """Sleep for ``seconds`` but wake at once when cancelled."""
        if self._event.wait(seconds):
            raise AIRunCancelledError()


@dataclass(slots=True)
class RunBudget:
    """Per-request ceilings: tokens, model steps and tool calls."""

    max_tokens: int
    max_steps: int
    max_tool_calls: int
    used_input_tokens: int = 0
    used_output_tokens: int = 0
    steps: int = 0
    tool_calls: int = 0
    provider_calls: int = 0
    estimated: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def used_tokens(self) -> int:
        return self.used_input_tokens + self.used_output_tokens

    def ensure_can_spend(self, estimated_input: int) -> None:
        if self.used_tokens + estimated_input > self.max_tokens:
            raise AIBudgetExceededError("The token budget for this request has been reached.")

    def charge(self, usage: Usage) -> None:
        self.used_input_tokens += usage.input_tokens
        self.used_output_tokens += usage.output_tokens

    def start_step(self) -> None:
        if self.steps >= self.max_steps:
            raise AIBudgetExceededError("The model-step limit for this request has been reached.")
        self.steps += 1

    def reserve_tool_call(self) -> bool:
        """True when another tool call fits inside the per-request limit."""
        if self.tool_calls >= self.max_tool_calls:
            return False
        self.tool_calls += 1
        return True


class RunLimiter:
    """Bounded number of concurrent AI runs per process (a non-blocking semaphore)."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._semaphore = threading.BoundedSemaphore(limit)

    @property
    def limit(self) -> int:
        return self._limit

    def acquire(self) -> None:
        """Take a slot without waiting, or raise ``AITooManyRunsError``."""
        if not self._semaphore.acquire(blocking=False):
            raise AITooManyRunsError()

    def release(self) -> None:
        self._semaphore.release()

    @contextmanager
    def slot(self) -> Iterator[None]:
        self.acquire()
        try:
            yield
        finally:
            self.release()


class RunRegistry:
    """In-process registry of running requests so the owner can cancel one safely."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[UUID, tuple[UUID, UUID, CancelToken]] = {}

    def register(self, run_id: UUID, *, company_id: UUID, user_id: UUID) -> CancelToken:
        token = CancelToken()
        with self._lock:
            self._runs[run_id] = (company_id, user_id, token)
        return token

    def release(self, run_id: UUID) -> None:
        with self._lock:
            self._runs.pop(run_id, None)

    def cancel(self, run_id: UUID, *, company_id: UUID, user_id: UUID) -> bool:
        """Cancel a run only for the user and company that started it."""
        with self._lock:
            entry = self._runs.get(run_id)
        if entry is None or entry[0] != company_id or entry[1] != user_id:
            return False
        entry[2].cancel()
        return True

    def active(self) -> int:
        with self._lock:
            return len(self._runs)


def usage_cost_usd(settings: Settings, usage: Usage) -> Decimal:
    """Estimated cost in USD from the configured per-million-token prices."""
    million = Decimal(1_000_000)
    return (
        Decimal(usage.input_tokens) * settings.ai_price_input_per_million_usd / million
        + Decimal(usage.output_tokens) * settings.ai_price_output_per_million_usd / million
    )


class AIGateway:
    """Calls a provider with retry, timeout, budget and cancellation applied."""

    def __init__(
        self,
        settings: Settings,
        provider: ModelProvider,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self.provider = provider
        self._clock = clock

    def complete(
        self, request: ModelRequest, *, budget: RunBudget, cancel: CancelToken
    ) -> ModelResponse:
        settings = self._settings
        attempt = 0
        while True:
            attempt += 1
            cancel.check()
            estimated_input = estimate_request_tokens(request)
            budget.ensure_can_spend(estimated_input)
            started = self._clock()
            try:
                budget.provider_calls += 1
                response = self.provider.complete(request)
            except ProviderError as exc:
                logger.warning(
                    "ai.provider.error",
                    extra={
                        "provider": self.provider.name,
                        "error_code": str(exc.code),
                        "attempt": attempt,
                        "request_id": request.request_id,
                    },
                )
                if not exc.retryable or attempt > settings.ai_max_retries:
                    raise
                delay = settings.ai_retry_backoff_seconds * (2 ** (attempt - 1))
                if isinstance(exc, ProviderRateLimitedError) and exc.retry_after:
                    delay = max(delay, exc.retry_after)
                cancel.wait(min(delay, _MAX_BACKOFF_SECONDS))
                continue

            usage = response.usage
            estimated = response.estimated_usage or usage.total == 0
            if estimated:
                usage = Usage(
                    input_tokens=estimated_input,
                    output_tokens=estimate_tokens(response.content)
                    + sum(estimate_tokens(str(c.arguments)) for c in response.tool_calls),
                )
                budget.estimated = True
            budget.charge(usage)
            logger.info(
                "ai.provider.call",
                extra={
                    "provider": response.provider,
                    "model": response.model,
                    "attempts": attempt,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "estimated_usage": estimated,
                    "duration_ms": round((self._clock() - started) * 1000, 1),
                    "request_id": request.request_id,
                },
            )
            return replace(response, usage=usage, attempts=attempt, estimated_usage=estimated)
