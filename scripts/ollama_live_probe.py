"""Live check of the local Ollama fallback (Stage 16): no business data, loopback only.

It runs the real ``PrimaryThenLocalProvider``: the primary is an OpenAI-compatible adapter
pointed at a closed loopback port (so it fails with "unavailable", exactly like an outage or
exhausted quota), and the fallback is the real local Ollama server and model. Nothing here
contacts a public service; the prompt is a fixed synthetic sentence.

    backend\\.venv\\Scripts\\python.exe scripts\\ollama_live_probe.py [--model qwen3:8b]

Exit 0 = FALLBACK_VERIFIED (answered by the local model, flagged LOCAL_FALLBACK_USED);
exit 2 = the local server or model is not available (not a failure of the code);
exit 1 = the fallback path misbehaved.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from pydantic import SecretStr  # noqa: E402

from app.ai.errors import ProviderError  # noqa: E402
from app.ai.providers.fallback import LocalOllamaProvider, PrimaryThenLocalProvider  # noqa: E402
from app.ai.providers.openai_compat import OpenAICompatibleProvider  # noqa: E402
from app.ai.types import ModelMessage, ModelRequest  # noqa: E402

PROMPT = "Reply with exactly one word: the Turkish word for 'yes'."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    if not args.base_url.startswith(("http://127.0.0.1", "http://localhost")):
        print("Refusing: the local fallback must be a loopback address.")
        return 1

    primary = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:9/v1",  # closed port: simulates an unavailable API
        api_key=SecretStr("not-a-real-key"),
        model="primary-unavailable",
    )
    local = LocalOllamaProvider(
        base_url=args.base_url, api_key=SecretStr("ollama"), model=args.model
    )
    provider = PrimaryThenLocalProvider(primary, local)
    request = ModelRequest(
        messages=(ModelMessage(role="user", content=PROMPT),),
        tools=(),
        max_output_tokens=600,
        timeout_seconds=args.timeout,
        request_id="ollama-live-probe",
    )
    started = time.monotonic()
    try:
        response = provider.complete(request)
    except ProviderError as exc:
        print(f"LOCAL_MODEL_UNAVAILABLE: {type(exc).__name__}. Is Ollama running with {args.model}?")
        return 2
    seconds = time.monotonic() - started

    answered_locally = response.provider == "ollama_local" and response.model == args.model
    flagged = "LOCAL_FALLBACK_USED" in response.warnings
    print(
        f"provider={response.provider} model={response.model} warnings={list(response.warnings)} "
        f"tokens_in={response.usage.input_tokens} tokens_out={response.usage.output_tokens} "
        f"seconds={seconds:.1f}"
    )
    print(f"answer (first 120 chars): {response.content.strip()[:120]!r}")
    if answered_locally and flagged and response.content.strip():
        print("FALLBACK_VERIFIED: the unavailable primary was replaced by the local model.")
        return 0
    print("FALLBACK_FAILED: the response was not clearly produced and flagged by the local model.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
