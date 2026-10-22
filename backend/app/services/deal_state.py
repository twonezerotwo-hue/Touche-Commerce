"""The deal state machine (ADR-025).

The graph is explicit data, not a chain of ``if`` statements, so it can be
tested exhaustively without a database and rendered by the UI without
duplicating the rules:

* ``WON`` is **disabled**: no edge targets it until the sales-order module
  exists, so a deal can never claim a win that has no order behind it;
* ``LOST`` and ``CANCELLED`` are terminal and require a written reason;
* every other status is reachable from a documented predecessor only.

Nothing here touches the database; :mod:`app.services.trade` owns persistence
and calls :func:`validate_transition` inside the transaction that updates the
deal, so a rejected transition can never leave a partial state behind.
"""

from __future__ import annotations

from app.core.errors import (
    AlreadyWonError,
    InvalidTransitionError,
    ReasonRequiredError,
    TransitionDisabledError,
)
from app.db.models import DealStatus

ALLOWED_TRANSITIONS: dict[DealStatus, frozenset[DealStatus]] = {
    DealStatus.DRAFT: frozenset({DealStatus.OPEN, DealStatus.CANCELLED}),
    DealStatus.OPEN: frozenset(
        {DealStatus.NEGOTIATION, DealStatus.LOST, DealStatus.CANCELLED}
    ),
    DealStatus.NEGOTIATION: frozenset({DealStatus.OPEN, DealStatus.LOST, DealStatus.CANCELLED}),
    DealStatus.WON: frozenset(),
    DealStatus.LOST: frozenset(),
    DealStatus.CANCELLED: frozenset(),
}

TERMINAL_STATUSES: frozenset[DealStatus] = frozenset(
    {DealStatus.WON, DealStatus.LOST, DealStatus.CANCELLED}
)

REASON_REQUIRED_TARGETS: frozenset[DealStatus] = frozenset(
    {DealStatus.LOST, DealStatus.CANCELLED}
)

#: Transitions whose implementation is deliberately deferred (ADR-025).
DISABLED_TARGETS: frozenset[DealStatus] = frozenset({DealStatus.WON})

REASON_MIN_LENGTH = 3
REASON_MAX_LENGTH = 500


def parse_status(value: str) -> DealStatus:
    """Parse an API/stored status value, raising ``ValueError`` when unknown."""
    try:
        return DealStatus(value)
    except ValueError as exc:
        raise ValueError(f"Unknown deal status: {value!r}") from exc


def allowed_targets(current: DealStatus) -> tuple[DealStatus, ...]:
    """Targets reachable from ``current`` in a stable, UI friendly order."""
    targets = ALLOWED_TRANSITIONS.get(current, frozenset())
    return tuple(target for target in DealStatus if target in targets)


def is_terminal(status: DealStatus) -> bool:
    return status in TERMINAL_STATUSES


def requires_reason(target: DealStatus) -> bool:
    return target in REASON_REQUIRED_TARGETS


def normalise_reason(reason: str | None) -> str | None:
    """Collapse whitespace; an empty reason is ``None``, never an empty string."""
    if reason is None:
        return None
    cleaned = " ".join(reason.split())
    return cleaned or None


def validate_transition(
    current: DealStatus,
    target: DealStatus,
    reason: str | None,
) -> str | None:
    """Return the normalised reason or raise a contract error.

    Order matters: an already-won deal reports ``ALREADY_WON`` (not a generic
    invalid transition), and any attempt to reach ``WON`` reports
    ``TRANSITION_DISABLED`` (not ``INVALID_TRANSITION``) because the edge is
    intentionally absent rather than unknown.
    """
    if current is DealStatus.WON:
        raise AlreadyWonError()

    if target in DISABLED_TARGETS:
        raise TransitionDisabledError(
            details={"from": str(current), "to": str(target), "code": "TRANSITION_DISABLED"}
        )

    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransitionError(
            details={
                "from": str(current),
                "to": str(target),
                "allowed": [str(value) for value in allowed_targets(current)],
            }
        )

    cleaned = normalise_reason(reason)
    if requires_reason(target):
        if cleaned is None or not (REASON_MIN_LENGTH <= len(cleaned) <= REASON_MAX_LENGTH):
            raise ReasonRequiredError(
                details=[
                    {
                        "field": "reason",
                        "message": (
                            "A reason of 3 to 500 characters is required when moving a "
                            f"deal to {target}."
                        ),
                        "type": "reason_required",
                    }
                ]
            )
        return cleaned

    if cleaned is not None and len(cleaned) > REASON_MAX_LENGTH:
        raise ReasonRequiredError(
            details=[
                {
                    "field": "reason",
                    "message": "The reason must be at most 500 characters.",
                    "type": "reason_too_long",
                }
            ]
        )
    return cleaned


__all__ = [
    "ALLOWED_TRANSITIONS",
    "DISABLED_TARGETS",
    "REASON_MAX_LENGTH",
    "REASON_MIN_LENGTH",
    "REASON_REQUIRED_TARGETS",
    "TERMINAL_STATUSES",
    "allowed_targets",
    "is_terminal",
    "normalise_reason",
    "parse_status",
    "requires_reason",
    "validate_transition",
]
