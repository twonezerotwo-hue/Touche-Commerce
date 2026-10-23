# Stage 16A — optional primary DeepSeek/OpenAI-compatible API → local Ollama fallback

**Code scope:** a bounded fail-closed model-provider wrapper, configured through
server-side settings. No credentials, emails, business records or user accounts
are created. This has not made a real paid DeepSeek request or verified an
actual Windows/macOS Ollama runtime. `AI_PROVIDER_LIVE_ACCEPTANCE` is still
blocked.

## Configuration

The existing OpenAI-compatible provider works with DeepSeek's documented
chat-completions API; recommended server-side values (do not commit the key):

```text
TOUCHE_AI_ENABLED=true
TOUCHE_AI_PROVIDER=openai_compatible
TOUCHE_AI_MODEL=deepseek-chat
TOUCHE_AI_BASE_URL=https://api.deepseek.com
TOUCHE_AI_API_KEY=<from local secrets manager>
TOUCHE_AI_EXTERNAL_PROCESSING_ACKNOWLEDGED=true
TOUCHE_AI_LOCAL_FALLBACK_ENABLED=true
TOUCHE_AI_LOCAL_FALLBACK_BASE_URL=http://127.0.0.1:11434/v1
TOUCHE_AI_LOCAL_FALLBACK_MODEL=qwen3:8b
```

Both endpoints are optional in a disabled-by-default setting; the local address
**must** be a literal loopback with an explicit port and path `/v1`, without
credentials, query or fragment. No browser can supply its own model URL.
A server running in the cloud cannot automatically reach Ollama on the
owner's Windows PC; that requires a separately secured on-prem gateway and
always-available source. Do NOT open Ollama's port to the public internet.

## Error semantics

Primary 402 quota, 429 rate limit, timeout or 5xx/unavailable failures each
trigger at most one attempt through loopback local Ollama for that model step.
Primary auth errors, invalid responses and other failures never activate
fallback. If local fallback also fails, the wrapper emits a non-retryable
`AI_PROVIDER_UNAVAILABLE` response to prevent repeated chargeable retries.
Completed local calls identify `ollama_local` as the provider in returned model
responses and provider-call logs.

**Limitations:** the persisted AI run's initially assigned provider identifies
the wrapper, rather than each completed model-step's origin; full provenance
and fallback cost reconciliation need additional migration/UX. Local service
availability is not guaranteed. The owner asked for a combined **$10/month**
DeepSeek cap; this slice **does not implement an exact, cross-process cost
reservation ledger**. The existing daily cost setting is not a strict monthly
hard limit, and API consumption must stay disabled until a real budget control,
provider-side cap, token prices and test evidence exist. No live commercial
data should be transmitted before reviewing data handling policy.

## Acceptance (not yet run on actual provider)

- [ ] Full Ruff, mypy, backend and provider test matrix passes CI.
- [ ] Primary healthy -> zero calls to local fallback.
- [ ] Eligible 402/429/timeout/5xx -> single local fallback with actual origin reported.
- [ ] Bad primary credentials and malformed answer cannot bypass safety checks.
- [ ] Both providers fail -> terminal unavailable response, no retry storm.
- [ ] Actual DeepSeek account, $10/month prepaid/provider spend limit and app-wide
      concurrency-safe reservation gate tested separately.
- [ ] Real Windows Ollama availability and secure cloud/on-prem transport tested.
