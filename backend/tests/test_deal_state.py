"""Unit tests for the deal state machine (no database required)."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.errors import (
    AlreadyWonError,
    InvalidTransitionError,
    ReasonRequiredError,
    TransitionDisabledError,
)
from app.db.models import DealStatus
from app.services.deal_state import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    allowed_targets,
    is_terminal,
    normalise_reason,
    parse_status,
    requires_reason,
    validate_transition,
)


class TestGraph:
    def test_transition_graph_is_explicit_and_acyclic_towards_terminal_states(self) -> None:
        assert set(ALLOWED_TRANSITIONS) == set(DealStatus)
        assert ALLOWED_TRANSITIONS[DealStatus.DRAFT] == frozenset(
            {DealStatus.OPEN, DealStatus.CANCELLED}
        )
        assert ALLOWED_TRANSITIONS[DealStatus.OPEN] == frozenset(
            {DealStatus.NEGOTIATION, DealStatus.LOST, DealStatus.CANCELLED}
        )
        assert ALLOWED_TRANSITIONS[DealStatus.NEGOTIATION] == frozenset(
            {DealStatus.OPEN, DealStatus.LOST, DealStatus.CANCELLED}
        )
        for terminal in TERMINAL_STATUSES:
            assert ALLOWED_TRANSITIONS[terminal] == frozenset()
        assert {
            DealStatus.WON,
            DealStatus.LOST,
            DealStatus.CANCELLED,
        } == TERMINAL_STATUSES

    def test_won_is_never_an_allowed_target(self) -> None:
        for status in DealStatus:
            assert DealStatus.WON not in allowed_targets(status)

    def test_allowed_targets_are_stable_and_ordered(self) -> None:
        assert allowed_targets(DealStatus.DRAFT) == (
            DealStatus.OPEN,
            DealStatus.CANCELLED,
        )
        assert allowed_targets(DealStatus.WON) == ()

    def test_terminal_and_reason_rules(self) -> None:
        assert is_terminal(DealStatus.LOST)
        assert not is_terminal(DealStatus.OPEN)
        assert requires_reason(DealStatus.LOST)
        assert requires_reason(DealStatus.CANCELLED)
        assert not requires_reason(DealStatus.OPEN)

    def test_parse_status_rejects_unknown_values(self) -> None:
        assert parse_status("OPEN") is DealStatus.OPEN
        with pytest.raises(ValueError, match="Unknown deal status"):
            parse_status("SHIPPED")


class TestValidation:
    def test_forward_transition_is_accepted(self) -> None:
        assert validate_transition(DealStatus.DRAFT, DealStatus.OPEN, None) is None
        assert validate_transition(DealStatus.OPEN, DealStatus.NEGOTIATION, None) is None
        assert validate_transition(DealStatus.NEGOTIATION, DealStatus.OPEN, None) is None

    def test_won_target_is_disabled_not_invalid(self) -> None:
        with pytest.raises(TransitionDisabledError) as excinfo:
            validate_transition(DealStatus.NEGOTIATION, DealStatus.WON, None)
        assert excinfo.value.status_code == 409
        assert str(excinfo.value.code) == "TRANSITION_DISABLED"

    def test_already_won_reports_its_own_code(self) -> None:
        with pytest.raises(AlreadyWonError) as excinfo:
            validate_transition(DealStatus.WON, DealStatus.OPEN, None)
        assert str(excinfo.value.code) == "ALREADY_WON"

    def test_unreachable_edge_lists_allowed_targets(self) -> None:
        with pytest.raises(InvalidTransitionError) as excinfo:
            validate_transition(DealStatus.DRAFT, DealStatus.LOST, "not yet")
        details: Any = excinfo.value.details
        assert details["from"] == "DRAFT"
        assert details["to"] == "LOST"
        assert details["allowed"] == ["OPEN", "CANCELLED"]

    @pytest.mark.parametrize("target", [DealStatus.LOST, DealStatus.CANCELLED])
    def test_terminal_transitions_require_a_reason(self, target: DealStatus) -> None:
        with pytest.raises(ReasonRequiredError):
            validate_transition(DealStatus.OPEN, target, None)
        with pytest.raises(ReasonRequiredError):
            validate_transition(DealStatus.OPEN, target, "   ")

    def test_reason_is_normalised(self) -> None:
        reason = validate_transition(
            DealStatus.OPEN, DealStatus.LOST, "  buyer   withdrew\nbudget  "
        )
        assert reason == "buyer withdrew budget"
        assert normalise_reason("   ") is None

    def test_reason_length_is_bounded(self) -> None:
        with pytest.raises(ReasonRequiredError):
            validate_transition(DealStatus.OPEN, DealStatus.LOST, "no")
        with pytest.raises(ReasonRequiredError):
            validate_transition(DealStatus.OPEN, DealStatus.LOST, "x" * 501)
        assert validate_transition(DealStatus.OPEN, DealStatus.LOST, "x" * 500)

    def test_optional_reason_on_open_transition_is_allowed_and_trimmed(self) -> None:
        assert validate_transition(DealStatus.DRAFT, DealStatus.OPEN, "  ") is None
        assert (
            validate_transition(DealStatus.DRAFT, DealStatus.OPEN, " customer asked ")
            == "customer asked"
        )
