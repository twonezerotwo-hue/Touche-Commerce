"""Record → response mapping for Stage 4 (no business rules live here)."""

from __future__ import annotations

from app.api.v1.schemas.operations import (
    CurrencyOrderValueResponse,
    CustomerAcceptanceListResponse,
    CustomerAcceptanceResponse,
    DocumentListResponse,
    DocumentResponse,
    FulfilmentLineResponse,
    FulfilmentSummaryResponse,
    OperationsSummaryResponse,
    OrderAmendmentResponse,
    PurchaseOrderItemResponse,
    PurchaseOrderListResponse,
    PurchaseOrderResponse,
    PurchaseOrderSummaryResponse,
    PurchaseOrderTransitionResponse,
    SalesOrderItemResponse,
    SalesOrderListResponse,
    SalesOrderResponse,
    SalesOrderSummaryResponse,
    SalesOrderTransitionResponse,
    ShipmentCostResponse,
    ShipmentEventResponse,
    ShipmentItemResponse,
    ShipmentListResponse,
    ShipmentReferenceResponse,
    ShipmentResponse,
    ShipmentSummaryResponse,
)
from app.services.documents import DocumentRecord
from app.services.operations import OperationsSummary
from app.services.procurement import (
    PurchaseOrderPage,
    PurchaseOrderRecord,
    PurchaseOrderSummaryRecord,
)
from app.services.sales_orders import (
    AcceptanceRecord,
    OrderItemRecord,
    OrderPage,
    SalesOrderRecord,
    SalesOrderSummaryRecord,
)
from app.services.shipments import (
    FulfilmentSummary,
    ShipmentPage,
    ShipmentRecord,
    ShipmentSummaryRecord,
)


def acceptance_response(record: AcceptanceRecord) -> CustomerAcceptanceResponse:
    return CustomerAcceptanceResponse(
        id=record.id,
        company_id=record.company_id,
        deal_id=record.deal_id,
        sales_quote_id=record.sales_quote_id,
        sales_quote_revision=record.sales_quote_revision,
        channel=record.channel,
        accepted_at=record.accepted_at,
        accepted_by_name=record.accepted_by_name,
        evidence_reference=record.evidence_reference,
        evidence_document_id=record.evidence_document_id,
        notes=record.notes,
        recorded_by=record.recorded_by,
        recorded_at=record.recorded_at,
    )


def acceptance_list_response(
    records: tuple[AcceptanceRecord, ...],
) -> CustomerAcceptanceListResponse:
    return CustomerAcceptanceListResponse(
        items=[acceptance_response(record) for record in records]
    )


def _order_item(record: OrderItemRecord) -> SalesOrderItemResponse:
    return SalesOrderItemResponse(
        id=record.id,
        product_id=record.product_id,
        sku=record.sku,
        name=record.name,
        description=record.description,
        quantity=record.quantity,
        unit=record.unit,
        unit_price=record.unit_price,
        line_total=record.line_total,
    )


def order_response(record: SalesOrderRecord) -> SalesOrderResponse:
    return SalesOrderResponse(
        id=record.id,
        company_id=record.company_id,
        order_number=record.order_number,
        deal_id=record.deal_id,
        deal_reference=record.deal_reference,
        sales_quote_id=record.sales_quote_id,
        quote_number=record.quote_number,
        sales_quote_revision=record.sales_quote_revision,
        acceptance_evidence_id=record.acceptance_evidence_id,
        customer_id=record.customer_id,
        customer_name=record.customer_name,
        currency=record.currency,
        incoterm=record.incoterm,
        named_delivery_place=record.named_delivery_place,
        payment_terms_snapshot=record.payment_terms_snapshot,
        fulfilment_model=record.fulfilment_model,
        order_total=record.order_total,
        status=record.status,
        expected_delivery_date=record.expected_delivery_date,
        notes=record.notes,
        confirmed_at=record.confirmed_at,
        cancelled_at=record.cancelled_at,
        cancellation_reason=record.cancellation_reason,
        version=record.version,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
        items=[_order_item(item) for item in record.items],
        transitions=[
            SalesOrderTransitionResponse(
                from_status=item.from_status,
                to_status=item.to_status,
                reason=item.reason,
                actor_id=item.actor_id,
                occurred_at=item.occurred_at,
                version_after=item.version_after,
            )
            for item in record.transitions
        ],
        amendments=[
            OrderAmendmentResponse(
                reason=item.reason,
                changes=item.changes,
                actor_id=item.actor_id,
                created_at=item.created_at,
                version_after=item.version_after,
            )
            for item in record.amendments
        ],
        accepted_terms=record.accepted_terms,
        allowed_transitions=list(record.allowed_transitions),
    )


def order_summary_response(
    record: SalesOrderSummaryRecord,
) -> SalesOrderSummaryResponse:
    return SalesOrderSummaryResponse(
        id=record.id,
        company_id=record.company_id,
        order_number=record.order_number,
        deal_id=record.deal_id,
        deal_reference=record.deal_reference,
        sales_quote_id=record.sales_quote_id,
        quote_number=record.quote_number,
        sales_quote_revision=record.sales_quote_revision,
        customer_id=record.customer_id,
        customer_name=record.customer_name,
        currency=record.currency,
        incoterm=record.incoterm,
        named_delivery_place=record.named_delivery_place,
        fulfilment_model=record.fulfilment_model,
        order_total=record.order_total,
        status=record.status,
        confirmed_at=record.confirmed_at,
        expected_delivery_date=record.expected_delivery_date,
        version=record.version,
        updated_at=record.updated_at,
    )


def order_list_response(page: OrderPage) -> SalesOrderListResponse:
    return SalesOrderListResponse(
        items=[order_summary_response(item) for item in page.items],
        next_cursor=page.next_cursor,
        has_more=page.next_cursor is not None,
    )


def fulfilment_response(summary: FulfilmentSummary) -> FulfilmentSummaryResponse:
    return FulfilmentSummaryResponse(
        sales_order_id=summary.sales_order_id,
        order_number=summary.order_number,
        order_status=summary.order_status,
        lines=[
            FulfilmentLineResponse(
                sales_order_item_id=line.sales_order_item_id,
                sku=line.sku,
                unit=line.unit,
                ordered=line.ordered,
                allocated=line.allocated,
                delivered=line.delivered,
                remaining=line.remaining,
            )
            for line in summary.lines
        ],
        completion_ratio=summary.completion_ratio,
        fully_delivered=summary.fully_delivered,
        delivered_any=summary.delivered_any,
    )


def po_response(record: PurchaseOrderRecord) -> PurchaseOrderResponse:
    return PurchaseOrderResponse(
        id=record.id,
        company_id=record.company_id,
        po_number=record.po_number,
        sales_order_id=record.sales_order_id,
        order_number=record.order_number,
        supplier_id=record.supplier_id,
        supplier_name=record.supplier_name,
        supplier_quote_id=record.supplier_quote_id,
        currency=record.currency,
        incoterm=record.incoterm,
        named_delivery_place=record.named_delivery_place,
        payment_terms=record.payment_terms,
        total_cost=record.total_cost,
        status=record.status,
        expected_dispatch_date=record.expected_dispatch_date,
        expected_delivery_date=record.expected_delivery_date,
        dispatch_channel=record.dispatch_channel,
        dispatched_at=record.dispatched_at,
        dispatch_reference=record.dispatch_reference,
        supplier_confirmation_reference=record.supplier_confirmation_reference,
        supplier_confirmed_at=record.supplier_confirmed_at,
        approved_by=record.approved_by,
        approved_at=record.approved_at,
        notes=record.notes,
        cancelled_at=record.cancelled_at,
        cancellation_reason=record.cancellation_reason,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
        items=[
            PurchaseOrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                sku=item.sku,
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                unit_cost=item.unit_cost,
                line_total=item.line_total,
            )
            for item in record.items
        ],
        transitions=[
            PurchaseOrderTransitionResponse(
                from_status=item.from_status,
                to_status=item.to_status,
                reason=item.reason,
                evidence_reference=item.evidence_reference,
                actor_id=item.actor_id,
                occurred_at=item.occurred_at,
                version_after=item.version_after,
            )
            for item in record.transitions
        ],
        allowed_transitions=list(record.allowed_transitions),
    )


def po_summary_response(
    record: PurchaseOrderSummaryRecord,
) -> PurchaseOrderSummaryResponse:
    return PurchaseOrderSummaryResponse(
        id=record.id,
        company_id=record.company_id,
        po_number=record.po_number,
        sales_order_id=record.sales_order_id,
        order_number=record.order_number,
        supplier_id=record.supplier_id,
        supplier_name=record.supplier_name,
        currency=record.currency,
        total_cost=record.total_cost,
        status=record.status,
        expected_dispatch_date=record.expected_dispatch_date,
        expected_delivery_date=record.expected_delivery_date,
        approved_at=record.approved_at,
        version=record.version,
        updated_at=record.updated_at,
    )


def po_list_response(page: PurchaseOrderPage) -> PurchaseOrderListResponse:
    return PurchaseOrderListResponse(
        items=[po_summary_response(item) for item in page.items],
        next_cursor=page.next_cursor,
        has_more=page.next_cursor is not None,
    )


def shipment_response(record: ShipmentRecord) -> ShipmentResponse:
    return ShipmentResponse(
        id=record.id,
        company_id=record.company_id,
        shipment_number=record.shipment_number,
        sales_order_id=record.sales_order_id,
        order_number=record.order_number,
        purchase_order_id=record.purchase_order_id,
        transport_mode=record.transport_mode,
        origin=record.origin,
        destination=record.destination,
        carrier=record.carrier,
        forwarder=record.forwarder,
        planned_dispatch_at=record.planned_dispatch_at,
        actual_dispatch_at=record.actual_dispatch_at,
        estimated_arrival_at=record.estimated_arrival_at,
        actual_arrival_at=record.actual_arrival_at,
        delivered_at=record.delivered_at,
        status=record.status,
        tracking_reference=record.tracking_reference,
        tracking_source=record.tracking_source,
        delivery_evidence_reference=record.delivery_evidence_reference,
        delay_reason=record.delay_reason,
        cancellation_reason=record.cancellation_reason,
        notes=record.notes,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
        items=[
            ShipmentItemResponse(
                id=item.id,
                sales_order_item_id=item.sales_order_item_id,
                product_id=item.product_id,
                sku=item.sku,
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                delivered_quantity=item.delivered_quantity,
            )
            for item in record.items
        ],
        events=[
            ShipmentEventResponse(
                id=item.id,
                event_type=item.event_type,
                occurred_at=item.occurred_at,
                location=item.location,
                notes=item.notes,
                evidence_reference=item.evidence_reference,
                tracking_source=item.tracking_source,
                recorded_by=item.recorded_by,
                recorded_at=item.recorded_at,
            )
            for item in record.events
        ],
        references=[
            ShipmentReferenceResponse(
                id=item.id,
                reference_type=item.reference_type,
                reference_value=item.reference_value,
                provenance=item.provenance,
                created_at=item.created_at,
            )
            for item in record.references
        ],
        costs=[
            ShipmentCostResponse(
                id=item.id,
                cost_type=item.cost_type,
                stage=item.stage,
                amount=item.amount,
                currency=item.currency,
                reference=item.reference,
                notes=item.notes,
                recorded_at=item.recorded_at,
            )
            for item in record.costs
        ],
        is_delayed=record.is_delayed,
        allowed_transitions=list(record.allowed_transitions),
    )


def shipment_summary_response(
    record: ShipmentSummaryRecord,
) -> ShipmentSummaryResponse:
    return ShipmentSummaryResponse(
        id=record.id,
        company_id=record.company_id,
        shipment_number=record.shipment_number,
        sales_order_id=record.sales_order_id,
        order_number=record.order_number,
        transport_mode=record.transport_mode,
        origin=record.origin,
        destination=record.destination,
        carrier=record.carrier,
        forwarder=record.forwarder,
        status=record.status,
        estimated_arrival_at=record.estimated_arrival_at,
        actual_dispatch_at=record.actual_dispatch_at,
        delivered_at=record.delivered_at,
        tracking_reference=record.tracking_reference,
        version=record.version,
        updated_at=record.updated_at,
        is_delayed=record.is_delayed,
    )


def shipment_list_response(page: ShipmentPage) -> ShipmentListResponse:
    return ShipmentListResponse(
        items=[shipment_summary_response(item) for item in page.items],
        next_cursor=page.next_cursor,
        has_more=page.next_cursor is not None,
    )


def document_response(record: DocumentRecord) -> DocumentResponse:
    return DocumentResponse(
        id=record.id,
        company_id=record.company_id,
        document_type=record.document_type,
        linked_entity_type=record.linked_entity_type,
        linked_entity_id=record.linked_entity_id,
        title=record.title,
        original_filename=record.original_filename,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        version=record.version,
        supersedes_document_id=record.supersedes_document_id,
        status=record.status,
        verification_status=record.verification_status,
        is_draft=record.is_draft,
        uploaded_by=record.uploaded_by,
        uploaded_at=record.uploaded_at,
        archived_at=record.archived_at,
        download_path=f"/documents/{record.id}/download",
    )


def document_list_response(
    records: tuple[DocumentRecord, ...], *, max_upload_bytes: int
) -> DocumentListResponse:
    return DocumentListResponse(
        items=[document_response(item) for item in records],
        max_upload_bytes=max_upload_bytes,
    )


def operations_summary_response(summary: OperationsSummary) -> OperationsSummaryResponse:
    return OperationsSummaryResponse(
        orders_total=summary.orders_total,
        orders_confirmed=summary.orders_confirmed,
        orders_in_fulfillment=summary.orders_in_fulfillment,
        orders_fulfilled=summary.orders_fulfilled,
        orders_closed=summary.orders_closed,
        orders_cancelled=summary.orders_cancelled,
        order_value_by_currency=[
            CurrencyOrderValueResponse(
                currency=item.currency,
                order_count=item.order_count,
                total_value=item.total_value,
            )
            for item in summary.order_value_by_currency
        ],
        purchase_orders_total=summary.purchase_orders_total,
        purchase_orders_open=summary.purchase_orders_open,
        active_shipments=summary.active_shipments,
        delayed_shipments=summary.delayed_shipments,
        delivered_shipments=summary.delivered_shipments,
        documents_total=summary.documents_total,
        delivered_shipments_without_evidence=summary.delivered_shipments_without_evidence,
        generated_at=summary.generated_at,
    )


__all__ = [
    "acceptance_list_response",
    "acceptance_response",
    "document_list_response",
    "document_response",
    "fulfilment_response",
    "operations_summary_response",
    "order_list_response",
    "order_response",
    "order_summary_response",
    "po_list_response",
    "po_response",
    "po_summary_response",
    "shipment_list_response",
    "shipment_response",
    "shipment_summary_response",
]
