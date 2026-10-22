"""Finance link service: one read-only status observation, never a write."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import Settings
from app.integrations.finance.client import FinanceHealthClient
from app.integrations.finance.contracts import (
    FinanceHealth,
    FinanceHealthProbe,
    FinanceLinkState,
)


class FinanceIntegrationService:
    """Resolve the configured link state without mutating either system.

    A disabled integration performs no network I/O at all.  That is the safe
    default: a Commerce installation must not probe an unrelated process just
    because a default URL happens to be reachable.
    """

    def __init__(
        self,
        settings: Settings,
        probe: FinanceHealthProbe | None = None,
    ) -> None:
        self._settings = settings
        self._probe = probe

    def status(self) -> FinanceHealth:
        if not self._settings.finance_integration_enabled:
            return FinanceHealth(
                state=FinanceLinkState.DISABLED,
                finance_status=None,
                latency_ms=0.0,
                detail=(
                    "Finance integration is disabled; set "
                    "TOUCHE_FINANCE_INTEGRATION_ENABLED=true to probe the local "
                    "Finance health endpoint."
                ),
                checked_at=datetime.now(tz=UTC),
            )

        probe = self._probe or FinanceHealthClient(
            base_url=self._settings.finance_integration_base_url,
            timeout_seconds=self._settings.finance_integration_timeout_seconds,
        )
        return probe.probe()
