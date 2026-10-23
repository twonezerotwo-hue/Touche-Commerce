"""Stage 6 provider abstraction and AI Gateway tests.

A local HTTP server speaks the documented OpenAI-compatible and Anthropic wire
formats. It is not a real provider: it proves request shape, response parsing,
error mapping, retries, timeouts and credential hygiene without a network or a key.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from pydantic import SecretStr

from app.ai.errors import (
    AIBudgetExceededError,
    AIDisabledError,
    AIRunCancelledError,
    AITooManyRunsError,
    ProviderAuthError,
    ProviderBadResponseError,
    ProviderQuotaError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.ai.gateway import AIGateway, CancelToken, RunBudget, RunLimiter, RunRegistry
from app.ai.providers import build_provider
from app.ai.providers.anthropic import ANTHROPIC_VERSION, AnthropicProvider
from app.ai.providers.base import MAX_RESPONSE_BYTES
from app.ai.providers.mock import MockProvider
from app.ai.providers.openai_compat import OpenAICompatibleProvider
from app.ai.types import ModelMessage, ModelRequest, ToolCall, ToolSpec
from app.core.config import Settings

KEY = "sk-test-NEVER-LOG-THIS-123456"
_TOOL = ToolSpec(
    name="list_active_deals",
    description="List deals",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)


@dataclass
class Reply:
    status: int = 200
    body: bytes = b"{}"
    headers: dict[str, str] = field(default_factory=dict)
    delay: float = 0.0


@dataclass
class Recorded:
    path: str
    headers: dict[str, str]
    body: dict[str, Any]


class StubServer:
    def __init__(self) -> None:
        self.replies: list[Reply] = []
        self.requests: list[Recorded] = []
        self.hits_elsewhere = 0
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args: object) -> None:  # silence
                return

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                if self.path.startswith("/elsewhere"):
                    stub.hits_elsewhere += 1
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    body = {}
                stub.requests.append(
                    Recorded(self.path, {k.lower(): v for k, v in self.headers.items()}, body)
                )
                reply = stub.replies.pop(0) if stub.replies else Reply()
                if reply.delay:
                    time.sleep(reply.delay)
                try:
                    self.send_response(reply.status)
                    for name, value in reply.headers.items():
                        self.send_header(name, value)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(reply.body)))
                    self.end_headers()
                    self.wfile.write(reply.body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture()
def stub() -> Iterator[StubServer]:
    server = StubServer()
    yield server
    server.close()


def request(
    *, tools: bool = True, messages: tuple[ModelMessage, ...] | None = None
) -> ModelRequest:
    return ModelRequest(
        messages=messages
        or (
            ModelMessage("system", "You are helpful."),
            ModelMessage("user", "Analyse my deals"),
        ),
        tools=(_TOOL,) if tools else (),
        max_output_tokens=500,
        timeout_seconds=2.0,
        request_id="req-1",
    )


def openai(stub: StubServer) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(base_url=stub.base, api_key=SecretStr(KEY), model="test-model")


def anthropic(stub: StubServer) -> AnthropicProvider:
    return AnthropicProvider(base_url=stub.base, api_key=SecretStr(KEY), model="test-model")


def body(data: dict[str, Any]) -> bytes:
    return json.dumps(data).encode()


# ------------------------------------------------------------ OpenAI-compatible
def test_openai_compatible_request_and_tool_call_response(stub: StubServer) -> None:
    stub.replies.append(
        Reply(
            body=body(
                {
                    "model": "test-model",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "list_active_deals",
                                            "arguments": '{"limit": 5}',
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 120, "completion_tokens": 30},
                }
            )
        )
    )
    history = (
        ModelMessage("system", "sys"),
        ModelMessage("user", "q"),
        ModelMessage(
            "assistant", "", (ToolCall("call_0", "list_active_deals", {"limit": 2}),)
        ),
        ModelMessage("tool", '{"ok": true}', tool_call_id="call_0", tool_name="list_active_deals"),
    )
    response = openai(stub).complete(request(messages=history))

    sent = stub.requests[0]
    assert sent.path == "/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {KEY}"
    assert sent.body["model"] == "test-model"
    assert sent.body["tool_choice"] == "auto"
    assert sent.body["tools"][0]["function"]["name"] == "list_active_deals"
    assistant = sent.body["messages"][2]
    assert assistant["tool_calls"][0]["function"]["arguments"] == '{"limit": 2}'
    assert sent.body["messages"][3] == {
        "role": "tool",
        "tool_call_id": "call_0",
        "content": '{"ok": true}',
    }
    assert response.tool_calls[0].name == "list_active_deals"
    assert response.tool_calls[0].arguments == {"limit": 5}
    assert response.tool_calls[0].arguments_error is None
    assert (response.usage.input_tokens, response.usage.output_tokens) == (120, 30)
    assert response.estimated_usage is False


def test_openai_compatible_invalid_tool_arguments_are_flagged_not_guessed(
    stub: StubServer,
) -> None:
    stub.replies.append(
        Reply(
            body=body(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "id": "c",
                                        "function": {
                                            "name": "list_active_deals",
                                            "arguments": '{"limit": ',
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            )
        )
    )
    response = openai(stub).complete(request())
    call = response.tool_calls[0]
    assert call.arguments == {}
    assert call.arguments_error == "arguments are not valid JSON"
    assert response.estimated_usage is True  # no usage block: the gateway must estimate


def test_openai_compatible_text_answer(stub: StubServer) -> None:
    stub.replies.append(
        Reply(body=body({"choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}]}))
    )
    response = openai(stub).complete(request(tools=False))
    assert response.content == "hello"
    assert response.tool_calls == ()
    assert "tools" not in stub.requests[0].body


# ------------------------------------------------------------------ Anthropic
def test_anthropic_request_and_tool_use_response(stub: StubServer) -> None:
    stub.replies.append(
        Reply(
            body=body(
                {
                    "model": "test-model",
                    "stop_reason": "tool_use",
                    "content": [
                        {"type": "text", "text": "Checking."},
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "list_active_deals",
                            "input": {"limit": 3},
                        },
                    ],
                    "usage": {"input_tokens": 200, "output_tokens": 40},
                }
            )
        )
    )
    history = (
        ModelMessage("system", "sys"),
        ModelMessage("user", "q"),
        ModelMessage("assistant", "", (ToolCall("toolu_0", "list_active_deals", {}),)),
        ModelMessage("tool", "r1", tool_call_id="toolu_0", tool_name="list_active_deals"),
        ModelMessage("tool", "r2", tool_call_id="toolu_00", tool_name="list_active_deals"),
    )
    response = anthropic(stub).complete(request(messages=history))

    sent = stub.requests[0]
    assert sent.path == "/v1/messages"
    assert sent.headers["x-api-key"] == KEY
    assert sent.headers["anthropic-version"] == ANTHROPIC_VERSION
    assert "authorization" not in sent.headers
    assert sent.body["system"] == "sys"
    assert sent.body["max_tokens"] == 500
    assert sent.body["tools"][0]["input_schema"]["type"] == "object"
    roles = [m["role"] for m in sent.body["messages"]]
    assert roles == ["user", "assistant", "user"]  # consecutive tool results are one turn
    results = sent.body["messages"][2]["content"]
    assert [r["type"] for r in results] == ["tool_result", "tool_result"]
    assert response.content == "Checking."
    assert response.tool_calls[0].arguments == {"limit": 3}
    assert (response.usage.input_tokens, response.usage.output_tokens) == (200, 40)


# -------------------------------------------------------------- error mapping
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (402, ProviderQuotaError),
        (429, ProviderRateLimitedError),
        (408, ProviderTimeoutError),
        (500, ProviderUnavailableError),
        (503, ProviderUnavailableError),
        (400, ProviderBadResponseError),
        (404, ProviderBadResponseError),
    ],
)
@pytest.mark.parametrize("factory", [openai, anthropic])
def test_http_failures_map_to_provider_errors_without_leaking(
    stub: StubServer,
    status: int,
    expected: type[Exception],
    factory: Callable[[StubServer], Any],
) -> None:
    stub.replies.append(
        Reply(
            status=status,
            body=body({"error": {"message": f"SECRET-BODY {KEY} prompt text"}}),
            headers={"Retry-After": "7"},
        )
    )
    with pytest.raises(expected) as caught:
        factory(stub).complete(request())
    rendered = f"{caught.value!s} {caught.value!r} {getattr(caught.value, 'message', '')}"
    assert KEY not in rendered
    assert "SECRET-BODY" not in rendered
    assert "prompt text" not in rendered
    if status == 429:
        assert isinstance(caught.value, ProviderRateLimitedError)
        assert caught.value.retry_after == 7.0


def test_retryability_is_declared_per_error() -> None:
    assert ProviderUnavailableError().retryable
    assert ProviderTimeoutError().retryable
    assert ProviderRateLimitedError().retryable
    assert not ProviderAuthError().retryable
    assert not ProviderQuotaError().retryable
    assert not ProviderBadResponseError().retryable


@pytest.mark.parametrize(
    "reply",
    [
        Reply(body=b"not json"),
        Reply(body=b"[1, 2, 3]"),
        Reply(body=body({"choices": []})),
        Reply(body=body({"choices": [{"message": "text"}]})),
        Reply(body=body({"choices": [{"message": {"tool_calls": [{"function": {}}]}}]})),
    ],
)
def test_malformed_provider_bodies_are_rejected(stub: StubServer, reply: Reply) -> None:
    stub.replies.append(reply)
    with pytest.raises(ProviderBadResponseError):
        openai(stub).complete(request())


def test_oversized_provider_response_is_rejected(stub: StubServer) -> None:
    stub.replies.append(Reply(body=b'{"choices": [], "pad": "' + b"x" * MAX_RESPONSE_BYTES + b'"}'))
    with pytest.raises(ProviderBadResponseError):
        openai(stub).complete(request())


def test_redirects_are_never_followed_so_the_key_cannot_travel(stub: StubServer) -> None:
    stub.replies.append(Reply(status=307, headers={"Location": f"{stub.base}/elsewhere"}))
    with pytest.raises(ProviderBadResponseError):
        openai(stub).complete(request())
    assert stub.hits_elsewhere == 0
    assert len(stub.requests) == 1


def test_slow_provider_times_out(stub: StubServer) -> None:
    stub.replies.append(Reply(delay=1.5, body=body({"choices": []})))
    slow = ModelRequest(
        messages=(ModelMessage("user", "q"),),
        tools=(),
        max_output_tokens=10,
        timeout_seconds=0.3,
        request_id="r",
    )
    with pytest.raises(ProviderTimeoutError):
        openai(stub).complete(slow)


def test_unreachable_provider_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error
    import urllib.request

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError(ConnectionRefusedError(10061, "refused"))

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", refuse)
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:9", api_key=SecretStr(KEY), model="m"
    )
    with pytest.raises(ProviderUnavailableError):
        provider.complete(request())


# --------------------------------------------------------------- the gateway
def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "database_url": None,
        "database_migration_url": None,
        "_env_file": None,
        "ai_retry_backoff_seconds": 0.0,
    }
    values.update(overrides)
    return Settings(**values)


def budget(
    *, max_tokens: int = 100_000, max_steps: int = 6, max_tool_calls: int = 10
) -> RunBudget:
    return RunBudget(max_tokens=max_tokens, max_steps=max_steps, max_tool_calls=max_tool_calls)


def ok_reply() -> Reply:
    return Reply(
        body=body(
            {
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        )
    )


def test_gateway_retries_transient_failures_within_a_bound(stub: StubServer) -> None:
    stub.replies += [Reply(status=503), Reply(status=503), ok_reply()]
    gateway = AIGateway(settings(ai_max_retries=2), openai(stub))
    run = budget()
    response = gateway.complete(request(), budget=run, cancel=CancelToken())
    assert response.attempts == 3
    assert len(stub.requests) == 3
    assert run.used_tokens == 15


def test_gateway_stops_after_the_retry_bound(stub: StubServer) -> None:
    stub.replies += [Reply(status=503)] * 5
    gateway = AIGateway(settings(ai_max_retries=1), openai(stub))
    with pytest.raises(ProviderUnavailableError):
        gateway.complete(request(), budget=budget(), cancel=CancelToken())
    assert len(stub.requests) == 2


def test_gateway_does_not_retry_auth_or_quota_failures(stub: StubServer) -> None:
    stub.replies += [Reply(status=401), Reply(status=401)]
    gateway = AIGateway(settings(ai_max_retries=3), openai(stub))
    with pytest.raises(ProviderAuthError):
        gateway.complete(request(), budget=budget(), cancel=CancelToken())
    assert len(stub.requests) == 1


def test_gateway_honours_retry_after_for_rate_limits(stub: StubServer) -> None:
    stub.replies += [Reply(status=429, headers={"Retry-After": "0.2"}), ok_reply()]
    gateway = AIGateway(settings(ai_max_retries=1), openai(stub))
    started = time.monotonic()
    response = gateway.complete(request(), budget=budget(), cancel=CancelToken())
    assert response.attempts == 2
    assert time.monotonic() - started >= 0.19


def test_cancellation_interrupts_the_retry_wait(stub: StubServer) -> None:
    stub.replies += [Reply(status=429, headers={"Retry-After": "4"})] * 2
    gateway = AIGateway(settings(ai_max_retries=2), openai(stub))
    cancel = CancelToken()
    threading.Timer(0.2, cancel.cancel).start()
    started = time.monotonic()
    with pytest.raises(AIRunCancelledError):
        gateway.complete(request(), budget=budget(), cancel=cancel)
    assert time.monotonic() - started < 2.0


def test_gateway_refuses_a_request_that_exceeds_the_token_budget(stub: StubServer) -> None:
    gateway = AIGateway(settings(), openai(stub))
    with pytest.raises(AIBudgetExceededError):
        gateway.complete(request(), budget=budget(max_tokens=20), cancel=CancelToken())
    assert stub.requests == []  # refused before any data left the process


def test_gateway_estimates_usage_when_the_provider_omits_it(stub: StubServer) -> None:
    stub.replies.append(Reply(body=body({"choices": [{"message": {"content": "answer"}}]})))
    gateway = AIGateway(settings(), openai(stub))
    run = budget()
    response = gateway.complete(request(), budget=run, cancel=CancelToken())
    assert response.estimated_usage is True
    assert run.estimated is True
    assert response.usage.input_tokens > 0 and response.usage.output_tokens > 0


def test_budget_limits_steps_and_tool_calls() -> None:
    run = budget(max_steps=2, max_tool_calls=2)
    run.start_step()
    run.start_step()
    with pytest.raises(AIBudgetExceededError):
        run.start_step()
    assert run.reserve_tool_call() and run.reserve_tool_call()
    assert not run.reserve_tool_call()


def test_run_limiter_is_bounded_and_releases() -> None:
    limiter = RunLimiter(2)
    limiter.acquire()
    limiter.acquire()
    with pytest.raises(AITooManyRunsError):
        limiter.acquire()
    limiter.release()
    with limiter.slot(), pytest.raises(AITooManyRunsError):
        limiter.acquire()
    limiter.release()


def test_run_registry_cancels_only_for_the_owner() -> None:
    from uuid import uuid4

    registry = RunRegistry()
    run, company, user = uuid4(), uuid4(), uuid4()
    token = registry.register(run, company_id=company, user_id=user)
    assert not registry.cancel(run, company_id=uuid4(), user_id=user)
    assert not registry.cancel(run, company_id=company, user_id=uuid4())
    assert [token.cancelled] == [False]
    assert registry.cancel(run, company_id=company, user_id=user)
    assert [token.cancelled] == [True]
    registry.release(run)
    assert not registry.cancel(run, company_id=company, user_id=user)
    assert registry.active() == 0


# ----------------------------------------------------------- factory & config
def test_factory_selects_the_configured_provider() -> None:
    with pytest.raises(AIDisabledError):
        build_provider(settings())
    assert isinstance(build_provider(settings(ai_enabled=True)), MockProvider)
    real = build_provider(
        settings(
            ai_enabled=True,
            ai_provider="openai_compatible",
            ai_base_url="https://api.example.com/v1",
            ai_api_key=SecretStr(KEY),
            ai_external_processing_acknowledged=True,
        )
    )
    assert isinstance(real, OpenAICompatibleProvider) and real.is_external
    claude = build_provider(
        settings(
            ai_enabled=True,
            ai_provider="anthropic",
            ai_api_key=SecretStr(KEY),
            ai_external_processing_acknowledged=True,
        )
    )
    assert isinstance(claude, AnthropicProvider)
    assert claude._url == "https://api.anthropic.com/v1/messages"
    assert not MockProvider().is_external


def test_credentials_never_appear_in_settings_repr() -> None:
    config = settings(
        ai_enabled=True,
        ai_provider="openai_compatible",
        ai_base_url="https://api.example.com/v1",
        ai_api_key=SecretStr(KEY),
        ai_external_processing_acknowledged=True,
    )
    assert KEY not in repr(config)
    assert KEY not in str(config.model_dump())
    assert KEY not in config.model_dump_json()
    provider = build_provider(config)
    assert KEY not in repr(provider.__dict__)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"ai_provider": "openai_compatible"}, "ai_api_key is required"),
        (
            {"ai_provider": "openai_compatible", "ai_api_key": SecretStr("k")},
            "ai_base_url is required",
        ),
        (
            {
                "ai_provider": "openai_compatible",
                "ai_api_key": SecretStr("k"),
                "ai_base_url": "https://api.example.com/v1",
            },
            "ADR-048",
        ),
        ({"ai_provider": "anthropic"}, "ai_api_key is required"),
        ({"ai_base_url": "ftp://x.example.com"}, "http"),
        ({"ai_base_url": "http://api.example.com"}, "https unless"),
        ({"ai_base_url": "https://user:pw@api.example.com"}, "credentials"),
        ({"ai_base_url": "https://api.example.com/v1?key=1"}, "query"),
    ],
)
def test_unsafe_ai_configuration_is_refused(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        settings(ai_enabled=True, **overrides)


def test_loopback_http_is_allowed_for_local_stubs_only() -> None:
    config = settings(
        ai_enabled=True,
        ai_provider="openai_compatible",
        ai_base_url="http://127.0.0.1:8099/v1",
        ai_api_key=SecretStr("k"),
        ai_external_processing_acknowledged=True,
    )
    assert config.ai_effective_base_url == "http://127.0.0.1:8099/v1"


def test_mock_provider_is_refused_in_production() -> None:
    with pytest.raises(ValueError, match="mock AI provider"):
        Settings(
            environment="production",
            database_url=SecretStr("postgresql+psycopg://u:p@h/db"),
            session_cookie_secure=True,
            cors_allowed_origins=["https://app.example.com"],
            log_format="json",
            ai_enabled=True,
            ai_provider="mock",
            _env_file=None,
        )


def test_ai_is_off_by_default() -> None:
    config = settings()
    assert config.ai_enabled is False
    assert config.ai_provider == "mock"
    assert config.ai_api_key is None
    assert config.ai_external_processing_acknowledged is False


