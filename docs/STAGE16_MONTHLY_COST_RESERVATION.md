# Stage 16B — per-company monthly AI USD reservation gate

**Implemented code:** optional, fail-closed server-side reservation of estimated
maximum API cost for each AI run, using the existing PostgreSQL database to
serialize simultaneous submissions across user sessions and API workers.

**This is not approval to place paid calls.** The owner requires a maximum
DeepSeek spend of USD 10/month across the staff of **one operating company**.
The ledger is tenant-scoped, not a global provider-account ledger across
unrelated companies or separate Commerce deployments.

## Configuration

```text
TOUCHE_AI_MONTHLY_COST_CAP_ENABLED=true
TOUCHE_AI_MONTHLY_COST_CAP_USD=10.00
TOUCHE_AI_PRICE_INPUT_PER_MILLION_USD=<verified current DeepSeek USD rate>
TOUCHE_AI_PRICE_OUTPUT_PER_MILLION_USD=<verified current DeepSeek USD rate>
```

External AI in production now refuses to start unless the monthly cap is
enabled with positive current prices and cap. The default local/mock pipeline
remains unchanged.

Admission transaction acquires a company-specific PostgreSQL advisory
transaction lock. It sums the current UTC month's actual recorded AI run costs
and outstanding run reservations, rejects a new run if the conservative
reservation would exceed the cap, then inserts the run in the same transaction.
On run completion, actual usage cost replaces **only the actual cost** and the
separate reservation is zeroed. An abandoned in-flight reservation remains
conservatively counted until investigated, rather than silently permitting
more paid requests. All operations inherit company row-level security.

A conservative upper bound uses the configured maximum request tokens plus the
maximum output tokens per permitted model step, charged at the larger
configured per-million-token price, rounded up to 1 micro-dollar.
Charges ultimately reported by DeepSeek may differ from those prices or
limits; this is an **application-level safeguard**, not a billing-provider
guarantee. Operators must also use an independent DeepSeek prepaid account or
provider spending limit and check usage.

**Remaining Stage 16 blockers:** DeepSeek credentials, current provider rates,
live billing acceptance, remote Ollama via authenticated on-prem connector,
actual provider origin per model step, fallback on exhaustion of the
application budget, real customer-data privacy review and provider-side
monthly spend cap. Do not claim that an unavailable or unpaid local model
will answer when the budget stops API calls.

## Test requirements

- [ ] Ruff, mypy, Alembic isolated PostgreSQL, full pytest and build pass CI.
- [ ] Two simultaneous tenant user requests cannot both reserve the last USD.
- [ ] Invalid price or zero cap is blocked at startup when enabled.
- [ ] Real external production AI without monthly control is rejected.
- [ ] A completed run has actual cost and zero outstanding reservation.
- [ ] A live DeepSeek test is separately consented, and API spend is verified.
