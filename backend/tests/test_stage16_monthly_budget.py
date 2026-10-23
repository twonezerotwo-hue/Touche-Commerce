"""Stage 16B: conservative USD reservations and company-wide atomic admission."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import SecretStr, ValidationError

from app.ai.budget import reservation_for_run
from app.ai.errors import AIBudgetExceededError
from app.core.config import Settings
from app.db.engine import Database
from app.services.ai_office import AiOfficeService
from tests.conftest import IdentityWorld


def api_settings(**changes: object) -> Settings:
    return Settings(
        **(
            {
                "environment": "test",
                "ai_enabled": True,
                "ai_provider": "openai_compatible",
                "ai_base_url": "https://api.deepseek.com",
                "ai_api_key": SecretStr("unit-test-not-a-live-key"),
                "ai_external_processing_acknowledged": True,
                "ai_price_input_per_million_usd": Decimal("1.00"),
                "ai_price_output_per_million_usd": Decimal("2.00"),
                "ai_monthly_cost_cap_enabled": True,
                "ai_monthly_cost_cap_usd": Decimal("10"),
            }
            | changes
        )
    )


def test_conservative_maximum_token_reservation() -> None:
    settings = api_settings()
    assert reservation_for_run(settings) == Decimal("0.098000")
    assert reservation_for_run(
        api_settings(
            ai_max_request_tokens=1000,
            ai_max_output_tokens=100,
            ai_max_model_steps=2,
            ai_price_input_per_million_usd=Decimal("0.30"),
            ai_price_output_per_million_usd=Decimal("0.31"),
        )
    ) == Decimal("0.000372")


def test_real_provider_prices_must_be_nonzero_when_cap_is_enabled() -> None:
    for changes in (
        {"ai_price_input_per_million_usd": Decimal("0")},
        {"ai_price_output_per_million_usd": Decimal("0")},
        {"ai_monthly_cost_cap_usd": Decimal("0")},
    ):
        with pytest.raises(ValidationError):
            api_settings(**changes)


def test_real_production_ai_cannot_disable_monthly_cap() -> None:
    with pytest.raises(ValidationError, match="monthly_cost_cap_enabled"):
        api_settings(
            environment="production",
            ai_monthly_cost_cap_enabled=False,
            session_cookie_secure=True,
            cors_allowed_origins=["https://app.touche.example"],
        )


def new_conversation(office: AiOfficeService, company_id: UUID, user_id: UUID) -> UUID:
    return office.create_conversation(
        company_id=company_id,
        user_id=user_id,
        title="budget test",
        prompt_version="unit-test-budget",
        request_id=None,
    ).id


def admit(
    office: AiOfficeService,
    company_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    *,
    reserve: Decimal,
    limit: Decimal,
) -> UUID:
    run, _ = office.start_run(
        company_id=company_id,
        user_id=user_id,
        conversation_id=conversation_id,
        user_text="test only",
        provider="stub_external",
        model="stub",
        prompt_version="unit-test-budget",
        is_external=True,
        request_id=None,
        monthly_cost_cap_usd=limit,
        reserved_cost_usd=reserve,
    )
    return run.id


@pytest.mark.integration
def test_monthly_limit_blocks_second_run(
    identity_world: IdentityWorld, test_settings: Settings
) -> None:
    database = Database(test_settings)
    try:
        office = AiOfficeService(database)
        company = identity_world.company_a
        user = identity_world.user_a
        conversation = new_conversation(office, company, user)
        admit(office, company, user, conversation, reserve=Decimal("0.65"), limit=Decimal("1"))
        with pytest.raises(AIBudgetExceededError):
            admit(office, company, user, conversation, reserve=Decimal("0.65"), limit=Decimal("1"))
    finally:
        database.dispose()


@pytest.mark.integration
def test_competing_workers_cannot_both_spend_last_budget(
    identity_world: IdentityWorld, test_settings: Settings
) -> None:
    database = Database(test_settings)
    try:
        office = AiOfficeService(database)
        company = identity_world.company_a
        user = identity_world.user_a
        conversation = new_conversation(office, company, user)

        def attempt(_: int) -> bool:
            try:
                admit(
                    office, company, user, conversation, reserve=Decimal("0.75"),
                    limit=Decimal("1"),
                )
                return True
            except AIBudgetExceededError:
                return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, (1, 2)))
        assert sorted(results) == [False, True]
    finally:
        database.dispose()
