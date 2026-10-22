"""Pure unit tests for the Stage 4 state machines and allocation rules.

No database and no HTTP: these are the invariants every service call relies on.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.errors import BadRequestError, InvalidTransitionError, ReasonRequiredError
from app.services.order_state import (
    allowed_purchase_order_targets,
    allowed_sales_order_targets,
    allowed_shipment_targets,
    ensure_tracking_source,
    is_delayed,
    validate_allocation,
    validate_purchase_order_transition,
    validate_sales_order_transition,
    validate_shipment_transition,
)

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


class TestSalesOrderStateMachine:
    def test_a_new_order_is_confirmed_and_cannot_jump_to_fulfilled(self) -> None:
        assert allowed_sales_order_targets("CONFIRMED") == ("IN_FULFILLMENT", "CANCELLED")
        with pytest.raises(InvalidTransitionError):
            validate_sales_order_transition("CONFIRMED", "FULFILLED", None)

    def test_fulfilled_is_derived_and_never_set_directly(self) -> None:
        with pytest.raises(InvalidTransitionError) as raised:
            validate_sales_order_transition("IN_FULFILLMENT", "FULFILLED", "manual")
        assert raised.value.details == {
            "hint": "Record delivery against a shipment instead."
        }

    def test_closed_is_only_reachable_from_fulfilled(self) -> None:
        assert validate_sales_order_transition("FULFILLED", "CLOSED", "Complete") == "Complete"
        with pytest.raises(InvalidTransitionError):
            validate_sales_order_transition("CONFIRMED", "CLOSED", "Complete")

    def test_cancellation_requires_a_reason(self) -> None:
        with pytest.raises(ReasonRequiredError):
            validate_sales_order_transition("CONFIRMED", "CANCELLED", "  ")
        assert (
            validate_sales_order_transition(
                "CONFIRMED", "CANCELLED", "Customer withdrew the order"
            )
            == "Customer withdrew the order"
        )

    def test_cancelled_and_closed_are_terminal(self) -> None:
        assert allowed_sales_order_targets("CANCELLED") == ()
        assert allowed_sales_order_targets("CLOSED") == ()


class TestPurchaseOrderStateMachine:
    def test_purchase_orders_start_in_draft_and_are_not_sent(self) -> None:
        assert allowed_purchase_order_targets("DRAFT") == ("APPROVED", "CANCELLED")
        with pytest.raises(InvalidTransitionError):
            validate_purchase_order_transition(
                "DRAFT",
                "RECORDED_SENT",
                None,
                dispatched_at=NOW,
                dispatch_channel="EMAIL",
                dispatch_reference="msg-1",
                supplier_confirmation_reference=None,
            )

    def test_recording_a_dispatch_needs_channel_time_and_reference(self) -> None:
        with pytest.raises(BadRequestError) as raised:
            validate_purchase_order_transition(
                "APPROVED",
                "RECORDED_SENT",
                None,
                dispatched_at=NOW,
                dispatch_channel=None,
                dispatch_reference=None,
                supplier_confirmation_reference=None,
            )
        assert raised.value.details is not None
        fields = {item["field"] for item in raised.value.details}
        assert fields == {"dispatch_channel", "dispatch_reference"}

        assert (
            validate_purchase_order_transition(
                "APPROVED",
                "RECORDED_SENT",
                None,
                dispatched_at=NOW,
                dispatch_channel="EMAIL",
                dispatch_reference="msg-1",
                supplier_confirmation_reference=None,
            )
            is None
        )

    def test_supplier_confirmation_requires_a_reference(self) -> None:
        with pytest.raises(BadRequestError):
            validate_purchase_order_transition(
                "RECORDED_SENT",
                "SUPPLIER_CONFIRMED",
                None,
                dispatched_at=NOW,
                dispatch_channel="EMAIL",
                dispatch_reference="msg-1",
                supplier_confirmation_reference="   ",
            )

    def test_received_follows_supplier_confirmation(self) -> None:
        assert allowed_purchase_order_targets("SUPPLIER_CONFIRMED") == (
            "IN_FULFILLMENT",
            "CANCELLED",
        )
        assert allowed_purchase_order_targets("IN_FULFILLMENT") == (
            "RECEIVED",
            "CANCELLED",
        )


class TestShipmentStateMachine:
    def test_dispatch_needs_a_reference_and_arrival_needs_a_timestamp(self) -> None:
        with pytest.raises(BadRequestError) as raised:
            validate_shipment_transition(
                "BOOKED",
                "DISPATCHED",
                None,
                actual_dispatch_at=NOW,
                actual_arrival_at=None,
                delivery_evidence_reference=None,
                has_tracking_reference=False,
            )
        assert raised.value.details is not None
        assert raised.value.details[0]["field"] == "tracking_reference"

        with pytest.raises(BadRequestError):
            validate_shipment_transition(
                "DISPATCHED",
                "ARRIVED",
                None,
                actual_dispatch_at=NOW,
                actual_arrival_at=None,
                delivery_evidence_reference=None,
                has_tracking_reference=True,
            )

    def test_delivery_requires_evidence(self) -> None:
        with pytest.raises(BadRequestError) as raised:
            validate_shipment_transition(
                "ARRIVED",
                "DELIVERED",
                None,
                actual_dispatch_at=NOW,
                actual_arrival_at=NOW,
                delivery_evidence_reference="   ",
                has_tracking_reference=True,
            )
        assert raised.value.details is not None
        assert raised.value.details[0]["field"] == "delivery_evidence_reference"

        assert (
            validate_shipment_transition(
                "ARRIVED",
                "DELIVERED",
                None,
                actual_dispatch_at=NOW,
                actual_arrival_at=NOW,
                delivery_evidence_reference="POD-1",
                has_tracking_reference=True,
            )
            is None
        )

    def test_cancellation_requires_a_reason(self) -> None:
        with pytest.raises(ReasonRequiredError):
            validate_shipment_transition(
                "PLANNED",
                "CANCELLED",
                None,
                actual_dispatch_at=None,
                actual_arrival_at=None,
                delivery_evidence_reference=None,
                has_tracking_reference=False,
            )

    def test_backwards_or_skipped_transitions_are_refused(self) -> None:
        assert allowed_shipment_targets("PLANNED") == ("BOOKED", "CANCELLED")
        with pytest.raises(InvalidTransitionError):
            validate_shipment_transition(
                "PLANNED",
                "DELIVERED",
                None,
                actual_dispatch_at=NOW,
                actual_arrival_at=NOW,
                delivery_evidence_reference="POD-1",
                has_tracking_reference=True,
            )


class TestTrackingAndDelayHonesty:
    def test_only_manual_or_documentary_provenance_is_accepted(self) -> None:
        assert ensure_tracking_source("MANUAL") == "MANUAL"
        assert ensure_tracking_source("DOCUMENT_EVIDENCE") == "DOCUMENT_EVIDENCE"
        with pytest.raises(BadRequestError):
            ensure_tracking_source("VERIFIED_EXTERNAL")

    def test_an_eta_is_not_an_arrival(self) -> None:
        assert is_delayed(
            status="IN_TRANSIT",
            estimated_arrival_at=NOW - timedelta(days=2),
            delivered_at=None,
            now=NOW,
        )
        assert not is_delayed(
            status="DELIVERED",
            estimated_arrival_at=NOW - timedelta(days=2),
            delivered_at=NOW,
            now=NOW,
        )
        assert not is_delayed(
            status="IN_TRANSIT", estimated_arrival_at=None, delivered_at=None, now=NOW
        )


class TestAllocation:
    def test_decimal_quantities_are_subtracted_exactly(self) -> None:
        remaining = validate_allocation(
            ordered=Decimal("100.000"),
            already_allocated=Decimal("0"),
            requested=Decimal("40.125"),
            order_unit="kg",
            unit="kg",
        )
        assert remaining == Decimal("59.875")

    def test_over_allocation_is_refused(self) -> None:
        with pytest.raises(BadRequestError) as raised:
            validate_allocation(
                ordered=Decimal("20.000"),
                already_allocated=Decimal("15.000"),
                requested=Decimal("5.001"),
                order_unit="mt",
                unit="mt",
            )
        assert raised.value.details is not None
        assert raised.value.details["remaining"] == "5.000"

    def test_unit_mismatch_is_refused(self) -> None:
        with pytest.raises(BadRequestError) as raised:
            validate_allocation(
                ordered=Decimal("20.000"),
                already_allocated=Decimal("0"),
                requested=Decimal("1.000"),
                order_unit="mt",
                unit="kg",
            )
        assert raised.value.details is not None
        assert raised.value.details[0]["type"] == "unit_mismatch"

    def test_zero_and_negative_quantities_are_refused(self) -> None:
        for value in (Decimal("0"), Decimal("-1")):
            with pytest.raises(BadRequestError):
                validate_allocation(
                    ordered=Decimal("20.000"),
                    already_allocated=Decimal("0"),
                    requested=value,
                    order_unit="mt",
                    unit="mt",
                )



