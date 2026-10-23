"""Stage 16B: conservative per-run USD reservation to prevent token-budget races.

The rates are operator-configured, not inferred from models. A provider may bill
differently from the estimate; therefore use a second independent prepaid/API
spend limit to enforce the owner's absolute financial cap.
"""

from __future__ import annotations

from decimal import ROUND_UP, Decimal

from app.ai.errors import AIBudgetExceededError
from app.core.config import Settings

DOLLAR_QUANTUM = Decimal("0.000001")


def reservation_for_run(settings: Settings) -> Decimal:
    """Upper-bound configured token usage at the larger price per token.

    We assume compliant providers honor the max-output-token parameter and
    include an entire additional output allowance for every permitted model
    step, which is conservative relative to the director's global token limit.
    """

    if not settings.ai_enabled or settings.ai_provider == "mock":
        return Decimal("0")
    input_price = settings.ai_price_input_per_million_usd
    output_price = settings.ai_price_output_per_million_usd
    if input_price <= 0 or output_price <= 0:
        raise AIBudgetExceededError(
            "Configured positive input/output token prices are required for the AI cap."
        )
    ceiling_tokens = (
        settings.ai_max_request_tokens
        + settings.ai_max_output_tokens * settings.ai_max_model_steps
    )
    estimate = Decimal(ceiling_tokens) * max(input_price, output_price) / Decimal(1_000_000)
    return estimate.quantize(DOLLAR_QUANTUM, rounding=ROUND_UP)
