"""Errors of the AI Office.

All of them are :class:`~app.core.errors.ApiError` subclasses, so the standard error
envelope applies. Messages are deliberately generic: a provider response body, a
credential or a prompt never reaches a client or a log line through an error.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import ApiError, ErrorCode


class AIError(ApiError):
    """Base class for every AI Office error."""

    status_code = 502
    code = ErrorCode.INTERNAL_ERROR
    default_message = "The AI Office could not complete the request."


class AIDisabledError(AIError):
    status_code = 503
    code = ErrorCode.AI_DISABLED
    default_message = "The AI Office is disabled for this deployment."


class ProviderError(AIError):
    """A failure on the model-provider side. ``retryable`` drives the bounded retry."""

    retryable: bool = False

    def __init__(self, message: str | None = None, *, details: Any | None = None, **kwargs: Any):
        super().__init__(message, details=details, **kwargs)


class ProviderUnavailableError(ProviderError):
    status_code = 503
    code = ErrorCode.AI_PROVIDER_UNAVAILABLE
    default_message = "The AI provider is currently unavailable."
    retryable = True


class ProviderTimeoutError(ProviderError):
    status_code = 504
    code = ErrorCode.AI_PROVIDER_TIMEOUT
    default_message = "The AI provider did not answer in time."
    retryable = True


class ProviderRateLimitedError(ProviderError):
    status_code = 429
    code = ErrorCode.AI_PROVIDER_RATE_LIMITED
    default_message = "The AI provider is rate limiting requests."
    retryable = True

    def __init__(self, message: str | None = None, *, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderAuthError(ProviderError):
    status_code = 502
    code = ErrorCode.AI_PROVIDER_AUTH_FAILED
    default_message = "The AI provider rejected the configured credentials."


class ProviderQuotaError(ProviderError):
    status_code = 502
    code = ErrorCode.AI_PROVIDER_QUOTA_EXCEEDED
    default_message = "The AI provider account has no remaining quota or balance."


class ProviderBadResponseError(ProviderError):
    status_code = 502
    code = ErrorCode.AI_PROVIDER_BAD_RESPONSE
    default_message = "The AI provider returned a response that could not be used."


class AIBudgetExceededError(AIError):
    status_code = 429
    code = ErrorCode.AI_BUDGET_EXCEEDED
    default_message = "The AI usage budget for this request or day has been reached."


class AITooManyRunsError(AIError):
    status_code = 429
    code = ErrorCode.AI_TOO_MANY_RUNS
    default_message = "Too many AI requests are running at once. Please retry shortly."


class AIRunCancelledError(AIError):
    status_code = 409
    code = ErrorCode.AI_RUN_CANCELLED
    default_message = "The AI request was cancelled."


class AIInputTooLargeError(AIError):
    status_code = 413
    code = ErrorCode.AI_INPUT_TOO_LARGE
    default_message = "The message is too large for the AI Office."


class ProposalStateError(AIError):
    status_code = 409
    code = ErrorCode.AI_PROPOSAL_STATE_INVALID
    default_message = "The proposal is not in a state that allows this action."


class ActionNotSupportedError(AIError):
    status_code = 409
    code = ErrorCode.AI_ACTION_NOT_SUPPORTED
    default_message = "This proposed action is not supported for execution in this release."
