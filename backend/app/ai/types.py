"""Provider-neutral request and response types for the AI Gateway."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool as a model sees it: a name, a description and a JSON Schema."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A tool call requested by the model.

    ``arguments_error`` is set when the provider sent arguments that are not valid
    JSON (providers document this can happen); the call is then refused, never
    guessed at.
    """

    id: str
    name: str
    arguments: dict[str, Any]
    arguments_error: str | None = None


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class ModelRequest:
    messages: tuple[ModelMessage, ...]
    tools: tuple[ToolSpec, ...]
    max_output_tokens: int
    timeout_seconds: float
    request_id: str
    temperature: float = 0.0


@dataclass(frozen=True, slots=True)
class ModelResponse:
    content: str
    tool_calls: tuple[ToolCall, ...]
    usage: Usage
    finish_reason: str
    provider: str
    model: str
    attempts: int = 1
    estimated_usage: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)


def estimate_tokens(text: str) -> int:
    """A deliberately rough, provider-independent estimate (about 4 characters a token)."""
    return max(1, (len(text) + 3) // 4)


def estimate_request_tokens(request: ModelRequest) -> int:
    """Estimated input tokens of a request, including the tool definitions."""
    total = 0
    for message in request.messages:
        total += estimate_tokens(message.content) + 4
        for call in message.tool_calls:
            total += estimate_tokens(call.name) + estimate_tokens(str(call.arguments))
    for tool in request.tools:
        total += estimate_tokens(tool.name + tool.description + str(tool.parameters))
    return total
