"""Presenters turning Stage 3 service records into API schemas."""

from __future__ import annotations

from typing import Any

from app.api.v1.schemas.sourcing import (
    FxRateListResponse,
    FxRateResponse,
    PricingCostComponentResponse,
    PricingScenarioListResponse,
    PricingScenarioResponse,
    PricingScenarioSummaryResponse,
    RfqBatchResponse,
    RfqItemResponse,
    RfqListResponse,
    RfqQuoteSummaryResponse,
    RfqResponse,
    RfqRevisionDetailResponse,
    RfqRevisionResponse,
    RfqSummaryResponse,
    SalesQuoteItemResponse,
    SalesQuoteListResponse,
    SalesQuoteResponse,
    SalesQuoteRevisionDetailResponse,
    SalesQuoteRevisionResponse,
    SalesQuoteSummaryResponse,
    SupplierQuoteItemResponse,
    SupplierQuoteListResponse,
    SupplierQuoteResponse,
    SupplierQuoteRevisionDetailResponse,
    SupplierQuoteRevisionResponse,
    SupplierQuoteSummaryResponse,
)
from app.services.fx import FxRatePage, FxRateRecord
from app.services.pricing import (
    ScenarioComponentRecord,
    ScenarioPage,
    ScenarioRecord,
    ScenarioSummaryRecord,
)
from app.services.rfqs import (
    RfqItemRecord,
    RfqPage,
    RfqQuoteSummary,
    RfqRecord,
    RfqRevisionRecord,
    RfqSummaryRecord,
)
from app.services.sales_quotes import (
    SalesQuoteItemRecord,
    SalesQuotePage,
    SalesQuoteRecord,
    SalesQuoteRevisionRecord,
    SalesQuoteSummaryRecord,
)
from app.services.supplier_quotes import (
    QuoteItemRecord,
    QuotePage,
    QuoteRecord,
    QuoteRevisionRecord,
    QuoteSummaryRecord,
)


def fx_rate_response(record: FxRateRecord) -> FxRateResponse:
    return FxRateResponse(
        id=record.id,
        company_id=record.company_id,
        base_currency=record.base_currency,
        quote_currency=record.quote_currency,
        rate=record.rate,
        effective_at=record.effective_at,
        source=record.source,
        recorded_by=record.recorded_by,
        recorded_at=record.recorded_at,
    )


def fx_rate_list_response(page: FxRatePage) -> FxRateListResponse:
    return FxRateListResponse(
        items=[fx_rate_response(item) for item in page.items],
        next_cursor=page.next_cursor,
        has_more=page.next_cursor is not None,
    )


def rfq_item_response(record: RfqItemRecord) -> RfqItemResponse:
    return RfqItemResponse(
        id=record.id,
        product_id=record.product_id,
        sku=record.sku,
        name=record.name,
        unit=record.unit,
        description=record.description,
        quantity=record.quantity,
        notes=record.notes,
    )


def rfq_quote_summary_response(record: RfqQuoteSummary) -> RfqQuoteSummaryResponse:
    return RfqQuoteSummaryResponse(
        id=record.id,
        revision=record.revision,
        status=record.status,
        currency=record.currency,
        total_value=record.total_value,
        valid_until=record.valid_until,
        received_at=record.received_at,
    )


def rfq_revision_response(record: RfqRevisionRecord) -> RfqRevisionResponse:
    return RfqRevisionResponse(
        revision=record.revision,
        reason=record.reason,
        actor_id=record.actor_id,
        created_at=record.created_at,
    )


def rfq_revision_detail_response(
    record: RfqRevisionRecord, snapshot: dict[str, Any]
) -> RfqRevisionDetailResponse:
    return RfqRevisionDetailResponse(
        revision=record.revision,
        reason=record.reason,
        actor_id=record.actor_id,
        created_at=record.created_at,
        snapshot=snapshot,
    )


def rfq_summary_response(record: RfqSummaryRecord) -> RfqSummaryResponse:
    return RfqSummaryResponse(
        id=record.id,
        company_id=record.company_id,
        deal_id=record.deal_id,
        deal_reference=record.deal_reference,
        supplier_counterparty_id=record.supplier_counterparty_id,
        supplier_name=record.supplier_name,
        reference_number=record.reference_number,
        requested_currency=record.requested_currency,
        response_due_date=record.response_due_date,
        status=record.status,
        revision=record.revision,
        version=record.version,
        item_count=record.item_count,
        quote_count=record.quote_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def rfq_response(record: RfqRecord) -> RfqResponse:
    return RfqResponse(
        id=record.id,
        company_id=record.company_id,
        deal_id=record.deal_id,
        deal_reference=record.deal_reference,
        supplier_counterparty_id=record.supplier_counterparty_id,
        supplier_name=record.supplier_name,
        reference_number=record.reference_number,
        requested_currency=record.requested_currency,
        requested_delivery_terms=record.requested_delivery_terms,
        delivery_location=record.delivery_location,
        response_due_date=record.response_due_date,
        notes=record.notes,
        status=record.status,
        revision=record.revision,
        version=record.version,
        sent_channel=record.sent_channel,
        sent_at=record.sent_at,
        sent_evidence=record.sent_evidence,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
        items=[rfq_item_response(item) for item in record.items],
        quotes=[rfq_quote_summary_response(item) for item in record.quotes],
        revisions=[rfq_revision_response(item) for item in record.revisions],
        allowed_transitions=list(record.allowed_transitions),
        is_editable=record.is_editable,
    )


def rfq_list_response(page: RfqPage) -> RfqListResponse:
    return RfqListResponse(
        items=[rfq_summary_response(item) for item in page.items],
        next_cursor=page.next_cursor,
        has_more=page.next_cursor is not None,
    )


def rfq_batch_response(records: tuple[RfqRecord, ...]) -> RfqBatchResponse:
    return RfqBatchResponse(items=[rfq_response(record) for record in records])



def supplier_quote_item_response(record: QuoteItemRecord) -> SupplierQuoteItemResponse:
    return SupplierQuoteItemResponse(
        id=record.id,
        product_id=record.product_id,
        sku=record.sku,
        name=record.name,
        unit=record.unit,
        description=record.description,
        quantity=record.quantity,
        unit_price=record.unit_price,
        moq=record.moq,
        notes=record.notes,
        line_total=record.line_total,
    )


def supplier_quote_revision_response(
    record: QuoteRevisionRecord,
) -> SupplierQuoteRevisionResponse:
    return SupplierQuoteRevisionResponse(
        revision=record.revision,
        reason=record.reason,
        actor_id=record.actor_id,
        created_at=record.created_at,
    )


def supplier_quote_revision_detail_response(
    record: QuoteRevisionRecord, snapshot: dict[str, Any]
) -> SupplierQuoteRevisionDetailResponse:
    return SupplierQuoteRevisionDetailResponse(
        revision=record.revision,
        reason=record.reason,
        actor_id=record.actor_id,
        created_at=record.created_at,
        snapshot=snapshot,
    )


def supplier_quote_summary_response(
    record: QuoteSummaryRecord,
) -> SupplierQuoteSummaryResponse:
    return SupplierQuoteSummaryResponse(
        id=record.id,
        company_id=record.company_id,
        rfq_id=record.rfq_id,
        rfq_reference=record.rfq_reference,
        deal_id=record.deal_id,
        deal_reference=record.deal_reference,
        supplier_counterparty_id=record.supplier_counterparty_id,
        supplier_name=record.supplier_name,
        supplier_reference=record.supplier_reference,
        currency=record.currency,
        incoterm=record.incoterm,
        valid_until=record.valid_until,
        status=record.status,
        revision=record.revision,
        received_at=record.received_at,
        superseded_by_quote_id=record.superseded_by_quote_id,
        version=record.version,
        item_count=record.item_count,
        total_value=record.total_value,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def supplier_quote_response(record: QuoteRecord) -> SupplierQuoteResponse:
    return SupplierQuoteResponse(
        id=record.id,
        company_id=record.company_id,
        rfq_id=record.rfq_id,
        rfq_reference=record.rfq_reference,
        deal_id=record.deal_id,
        deal_reference=record.deal_reference,
        supplier_counterparty_id=record.supplier_counterparty_id,
        supplier_name=record.supplier_name,
        supplier_reference=record.supplier_reference,
        currency=record.currency,
        incoterm=record.incoterm,
        named_delivery_place=record.named_delivery_place,
        payment_terms=record.payment_terms,
        shipping_conditions=record.shipping_conditions,
        lead_time_days=record.lead_time_days,
        valid_until=record.valid_until,
        status=record.status,
        revision=record.revision,
        source_reference=record.source_reference,
        notes=record.notes,
        received_at=record.received_at,
        supersedes_quote_id=record.supersedes_quote_id,
        superseded_by_quote_id=record.superseded_by_quote_id,
        version=record.version,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
        items=[supplier_quote_item_response(item) for item in record.items],
        revisions=[supplier_quote_revision_response(item) for item in record.revisions],
        total_value=record.total_value,
        is_active=record.is_active,
    )


def supplier_quote_list_response(page: QuotePage) -> SupplierQuoteListResponse:
    return SupplierQuoteListResponse(
        items=[supplier_quote_summary_response(item) for item in page.items],
        next_cursor=page.next_cursor,
        has_more=page.next_cursor is not None,
    )



def pricing_component_response(
    record: ScenarioComponentRecord,
) -> PricingCostComponentResponse:
    return PricingCostComponentResponse(
        id=record.id,
        cost_type=record.cost_type,
        amount=record.amount,
        currency=record.currency,
        basis=record.basis,
        source_reference=record.source_reference,
        verification_status=record.verification_status,
        fx_rate_snapshot_id=record.fx_rate_snapshot_id,
        product_id=record.product_id,
        product_sku=record.product_sku,
        product_name=record.product_name,
        notes=record.notes,
    )


def pricing_scenario_summary_response(
    record: ScenarioSummaryRecord,
) -> PricingScenarioSummaryResponse:
    return PricingScenarioSummaryResponse(
        id=record.id,
        company_id=record.company_id,
        deal_id=record.deal_id,
        deal_reference=record.deal_reference,
        supplier_quote_id=record.supplier_quote_id,
        rfq_reference=record.rfq_reference,
        supplier_name=record.supplier_name,
        target_currency=record.target_currency,
        status=record.status,
        landed_total=record.landed_total,
        sales_total=record.sales_total,
        gross_margin=record.gross_margin,
        gross_margin_pct=record.gross_margin_pct,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def pricing_scenario_response(record: ScenarioRecord) -> PricingScenarioResponse:
    return PricingScenarioResponse(
        id=record.id,
        company_id=record.company_id,
        deal_id=record.deal_id,
        deal_reference=record.deal_reference,
        supplier_quote_id=record.supplier_quote_id,
        rfq_id=record.rfq_id,
        rfq_reference=record.rfq_reference,
        supplier_counterparty_id=record.supplier_counterparty_id,
        supplier_name=record.supplier_name,
        quote_currency=record.quote_currency,
        quote_revision=record.quote_revision,
        target_currency=record.target_currency,
        sales_incoterm=record.sales_incoterm,
        sales_named_place=record.sales_named_place,
        status=record.status,
        calculation_version=record.calculation_version,
        pricing_inputs=record.pricing_inputs,
        calculated_results=record.calculated_results,
        completeness=record.completeness,
        version=record.version,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
        components=[pricing_component_response(item) for item in record.components],
    )


def pricing_scenario_list_response(page: ScenarioPage) -> PricingScenarioListResponse:
    return PricingScenarioListResponse(
        items=[pricing_scenario_summary_response(item) for item in page.items],
        next_cursor=page.next_cursor,
        has_more=page.next_cursor is not None,
    )



def sales_quote_item_response(record: SalesQuoteItemRecord) -> SalesQuoteItemResponse:
    return SalesQuoteItemResponse(
        id=record.id,
        product_id=record.product_id,
        sku=record.sku,
        name=record.name,
        unit=record.unit,
        description=record.description,
        quantity=record.quantity,
        unit_price=record.unit_price,
        line_total=record.line_total,
    )


def sales_quote_revision_response(
    record: SalesQuoteRevisionRecord,
) -> SalesQuoteRevisionResponse:
    return SalesQuoteRevisionResponse(
        revision=record.revision,
        reason=record.reason,
        actor_id=record.actor_id,
        created_at=record.created_at,
    )


def sales_quote_revision_detail_response(
    record: SalesQuoteRevisionRecord, snapshot: dict[str, Any]
) -> SalesQuoteRevisionDetailResponse:
    return SalesQuoteRevisionDetailResponse(
        revision=record.revision,
        reason=record.reason,
        actor_id=record.actor_id,
        created_at=record.created_at,
        snapshot=snapshot,
    )


def sales_quote_summary_response(record: SalesQuoteSummaryRecord) -> SalesQuoteSummaryResponse:
    return SalesQuoteSummaryResponse(
        id=record.id,
        company_id=record.company_id,
        deal_id=record.deal_id,
        deal_reference=record.deal_reference,
        quote_number=record.quote_number,
        revision=record.revision,
        scenario_id=record.scenario_id,
        scenario_status=record.scenario_status,
        customer_id=record.customer_id,
        customer_name=record.customer_name,
        currency=record.currency,
        valid_until=record.valid_until,
        status=record.status,
        total_value=record.total_value,
        version=record.version,
        approved_at=record.approved_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def sales_quote_response(record: SalesQuoteRecord) -> SalesQuoteResponse:
    return SalesQuoteResponse(
        id=record.id,
        company_id=record.company_id,
        deal_id=record.deal_id,
        deal_reference=record.deal_reference,
        quote_number=record.quote_number,
        revision=record.revision,
        scenario_id=record.scenario_id,
        scenario_status=record.scenario_status,
        customer_id=record.customer_id,
        customer_name=record.customer_name,
        currency=record.currency,
        valid_until=record.valid_until,
        incoterm=record.incoterm,
        named_delivery_place=record.named_delivery_place,
        payment_terms=record.payment_terms,
        status=record.status,
        notes=record.notes,
        approved_by=record.approved_by,
        approved_at=record.approved_at,
        rejection_reason=record.rejection_reason,
        submitted_by=record.submitted_by,
        submitted_at=record.submitted_at,
        supersedes_sales_quote_id=record.supersedes_sales_quote_id,
        superseded_by_sales_quote_id=record.superseded_by_sales_quote_id,
        version=record.version,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
        items=[sales_quote_item_response(item) for item in record.items],
        revisions=[sales_quote_revision_response(item) for item in record.revisions],
        total_value=record.total_value,
        allowed_transitions=list(record.allowed_transitions),
        can_submit=record.can_submit,
    )


def sales_quote_list_response(page: SalesQuotePage) -> SalesQuoteListResponse:
    return SalesQuoteListResponse(
        items=[sales_quote_summary_response(item) for item in page.items],
        next_cursor=page.next_cursor,
        has_more=page.next_cursor is not None,
    )


__all__ = [
    "fx_rate_list_response",
    "fx_rate_response",
    "pricing_component_response",
    "pricing_scenario_list_response",
    "pricing_scenario_response",
    "pricing_scenario_summary_response",
    "rfq_batch_response",
    "rfq_item_response",
    "rfq_list_response",
    "rfq_quote_summary_response",
    "rfq_response",
    "rfq_revision_detail_response",
    "rfq_revision_response",
    "rfq_summary_response",
    "sales_quote_item_response",
    "sales_quote_list_response",
    "sales_quote_response",
    "sales_quote_revision_detail_response",
    "sales_quote_revision_response",
    "sales_quote_summary_response",
    "supplier_quote_item_response",
    "supplier_quote_list_response",
    "supplier_quote_response",
    "supplier_quote_revision_detail_response",
    "supplier_quote_revision_response",
    "supplier_quote_summary_response",
]

