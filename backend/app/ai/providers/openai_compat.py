"""OpenAI-compatible chat-completions adapter.

Wire format (documented by DeepSeek and OpenAI): ``POST {base}/chat/completions``
with ``Authorization: Bearer``, ``tools[].function`` definitions, assistant
``tool_calls[].function.arguments`` as a JSON *string* that may be invalid, and
``role: "tool"`` messages carrying ``tool_call_id``. Verified against the provider's
public documentation and a local stub (``tests/test_ai_providers.py``); a live call
needs a credential and is reported separately (``REAL_PROVIDER_BLOCKED`` until then).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import SecretStr

from app.ai.errors import ProviderBadResponseError
from app.ai.providers.base import parse_arguments, post_json
from app.ai.types import ModelMessage, ModelRequest, ModelResponse, ToolCall, ToolSpec, Usage


def _message_payload(message: ModelMessage) -> dict[str, Any]:
    if message.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id or "",
            "content": message.content,
        }
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.role == "assistant" and message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
        if not message.content:
            payload["content"] = None
    return payload


def _tool_payload(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


class OpenAICompatibleProvider:
    name = "openai_compatible"
    is_external = True

    def __init__(self, *, base_url: str, api_key: SecretStr, model: str) -> None:
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self.model = model

    def build_payload(self, request: ModelRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [_message_payload(message) for message in request.messages],
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if request.tools:
            payload["tools"] = [_tool_payload(tool) for tool in request.tools]
            payload["tool_choice"] = "auto"
        return payload

    def complete(self, request: ModelRequest) -> ModelResponse:
        data = post_json(
            self._url,
            headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
            payload=self.build_payload(request),
            timeout=request.timeout_seconds,
        )
        return self.parse_response(data)

    def parse_response(self, data: dict[str, Any]) -> ModelResponse:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderBadResponseError()
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ProviderBadResponseError()
        calls: list[ToolCall] = []
        for raw in message.get("tool_calls") or []:
            function = raw.get("function") if isinstance(raw, dict) else None
            if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                raise ProviderBadResponseError()
            arguments, error = parse_arguments(function.get("arguments"))
            calls.append(
                ToolCall(
                    id=str(raw.get("id") or f"call_{len(calls) + 1}"),
                    name=function["name"],
                    arguments=arguments,
                    arguments_error=error,
                )
            )
        usage_value = data.get("usage")
        usage_raw: dict[str, Any] = usage_value if isinstance(usage_value, dict) else {}
        usage = Usage(
            input_tokens=int(usage_raw.get("prompt_tokens") or 0),
            output_tokens=int(usage_raw.get("completion_tokens") or 0),
        )
        content = message.get("content")
        return ModelResponse(
            content=content if isinstance(content, str) else "",
            tool_calls=tuple(calls),
            usage=usage,
            finish_reason=str(choice.get("finish_reason") or "stop"),
            provider=self.name,
            model=str(data.get("model") or self.model),
            estimated_usage=not usage_raw,
        )
