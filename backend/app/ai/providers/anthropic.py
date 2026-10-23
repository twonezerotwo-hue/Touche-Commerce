"""Anthropic Messages adapter.

Wire format (Anthropic public documentation): ``POST {base}/v1/messages`` with
``x-api-key`` and ``anthropic-version: 2023-06-01``; tools carry an
``input_schema``; the model answers with ``tool_use`` content blocks
(``stop_reason: "tool_use"``) and results go back in a ``user`` message as
``tool_result`` blocks. Verified against the documentation and a local stub; a live
call needs a credential and is reported separately.
"""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr

from app.ai.errors import ProviderBadResponseError
from app.ai.providers.base import post_json
from app.ai.types import ModelMessage, ModelRequest, ModelResponse, ToolCall, Usage

ANTHROPIC_VERSION = "2023-06-01"


def _blocks_for(message: ModelMessage) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if message.content:
        blocks.append({"type": "text", "text": message.content})
    for call in message.tool_calls:
        blocks.append(
            {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
        )
    return blocks


class AnthropicProvider:
    name = "anthropic"
    is_external = True

    def __init__(self, *, base_url: str, api_key: SecretStr, model: str) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/messages"
        self._api_key = api_key
        self.model = model

    def build_payload(self, request: ModelRequest) -> dict[str, Any]:
        system_parts = [m.content for m in request.messages if m.role == "system"]
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "system":
                continue
            if message.role == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id or "",
                    "content": message.content,
                }
                # Consecutive tool results are one user turn, as the API requires.
                if messages and messages[-1]["role"] == "user" and _is_tool_turn(messages[-1]):
                    messages[-1]["content"].append(block)
                else:
                    messages.append({"role": "user", "content": [block]})
            elif message.role == "assistant":
                messages.append({"role": "assistant", "content": _blocks_for(message) or ""})
            else:
                messages.append({"role": "user", "content": message.content})
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request.tools:
            payload["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in request.tools
            ]
            payload["tool_choice"] = {"type": "auto"}
        return payload

    def complete(self, request: ModelRequest) -> ModelResponse:
        data = post_json(
            self._url,
            headers={
                "x-api-key": self._api_key.get_secret_value(),
                "anthropic-version": ANTHROPIC_VERSION,
            },
            payload=self.build_payload(request),
            timeout=request.timeout_seconds,
        )
        return self.parse_response(data)

    def parse_response(self, data: dict[str, Any]) -> ModelResponse:
        content = data.get("content")
        if not isinstance(content, list):
            raise ProviderBadResponseError()
        text: list[str] = []
        calls: list[ToolCall] = []
        for block in content:
            if not isinstance(block, dict):
                raise ProviderBadResponseError()
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                text.append(block["text"])
            elif block.get("type") == "tool_use":
                arguments = block.get("input")
                calls.append(
                    ToolCall(
                        id=str(block.get("id") or f"toolu_{len(calls) + 1}"),
                        name=str(block.get("name") or ""),
                        arguments=arguments if isinstance(arguments, dict) else {},
                        arguments_error=None
                        if isinstance(arguments, dict)
                        else "arguments are not a JSON object",
                    )
                )
        usage_value = data.get("usage")
        usage_raw: dict[str, Any] = usage_value if isinstance(usage_value, dict) else {}
        return ModelResponse(
            content="".join(text),
            tool_calls=tuple(calls),
            usage=Usage(
                input_tokens=int(usage_raw.get("input_tokens") or 0),
                output_tokens=int(usage_raw.get("output_tokens") or 0),
            ),
            finish_reason=str(data.get("stop_reason") or "end_turn"),
            provider=self.name,
            model=str(data.get("model") or self.model),
            estimated_usage=not usage_raw,
        )


def _is_tool_turn(message: dict[str, Any]) -> bool:
    content = message.get("content")
    return isinstance(content, list) and all(
        isinstance(block, dict) and block.get("type") == "tool_result" for block in content
    )
