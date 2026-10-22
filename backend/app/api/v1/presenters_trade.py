"""Presenters turning trade service records into API schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.api.v1.schemas.trade import (
    CounterpartyListResponse,
    CounterpartyResponse,
    DashboardActivity,
    DashboardCurrencyTotal,
    DashboardStatusCount,
    DashboardSummaryResponse,
    DealItemResponse,
    DealListResponse,
    DealResponse,
    DealSummaryResponse,
    DealTransitionResponse,
    ProductListResponse,
    ProductResponse,
)
from app.services.catalog import ProductPage, ProductRecord
from app.services.crm import CounterpartyPage, CounterpartyRecord
from app.services.trade import (
    DashboardSummary,
    DealItemRecord,
    DealPage,
    DealRecord,
    DealTransitionRecord,
)


def counterparty_response(record: CounterpartyRecord) -> CounterpartyResponse:
    return CounterpartyResponse(
        id=record.id,
        company_id=record.company_id,
        name=record.name,
        type=record.type,
        country=record.country,
        contact_name=record.contact_name,
        email=record.email,
        phone=record.phone,
        notes=record.notes,
        status=record.status,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def counterparty_list_response(page: CounterpartyPage) -> CounterpartyListResponse:
    return CounterpartyListResponse(
        items=[counterparty_response(item) for item in page.items],
        next_cursor=page.next_cursor,
        has_more=page.next_cursor is not None,
    )


def product_response(record: ProductRecord) -> ProductResponse:
    return ProductResponse(
        id=record.id,
        company_id=record.company_id,
        sku=record.sku,
        name=record.name,
        unit=record.unit,
        currency=record.currency,
        unit_price=record.unit_price,
        status=record.status,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def product_list_response(page: ProductPage) -> ProductListResponse:
    return ProductListResponse(
        items=[product_response(item) for item in page.items],
        next_cursor=page.next_cursor,
        has_more=page.next_cursor is not None,
    )


def deal_item_response(record: DealItemRecord) -> DealItemResponse:
    return DealItemResponse(
        id=record.id,
        product_id=record.product_id,
        sku=record.sku,
        name=record.name,
        unit=record.unit,
        quantity=record.quantity,
        unit_price=record.unit_price,
        line_total=record.line_total,
    )


def deal_transition_response(record: DealTransitionRecord) -> DealTransitionResponse:
    return DealTransitionResponse(
        id=record.id,
        from_status=record.from_status,
        to_status=record.to_status,
        reason=record.reason,
        actor_id=record.actor_id,
        request_id=record.request_id,
        version_after=record.version_after,
        occurred_at=record.occurred_at,
    )


def deal_summary_response(record: DealRecord) -> DealSummaryResponse:
    return DealSummaryResponse(
        id=record.id,
        company_id=record.company_id,
        reference=record.reference,
        title=record.title,
        status=record.status.value,
        counterparty_id=record.counterparty_id,
        counterparty_name=record.counterparty_name,
        currency=record.currency,
        expected_close_date=record.expected_close_date,
        total_value=record.total_value,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def deal_response(record: DealRecord) -> DealResponse:
    return DealResponse(
        id=record.id,
        company_id=record.company_id,
        reference=record.reference,
        title=record.title,
        status=record.status.value,
        counterparty_id=record.counterparty_id,
        counterparty_name=record.counterparty_name,
        currency=record.currency,
        expected_close_date=record.expected_close_date,
        notes=record.notes,
        total_value=record.total_value,
        version=record.version,
        created_by=record.created_by,
        closed_at=record.closed_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        items=[deal_item_response(item) for item in record.items],
        transitions=[deal_transition_response(item) for item in record.transitions],
        allowed_transitions=[status.value for status in record.allowed_transitions],
    )


def deal_list_response(page: DealPage) -> DealListResponse:
    return DealListResponse(
        items=[deal_summary_response(item) for item in page.items],
        next_cursor=page.next_cursor,
        has_more=page.next_cursor is not None,
    )


def dashboard_response(
    summary: DashboardSummary, *, company_id: UUID
) -> DashboardSummaryResponse:
    return DashboardSummaryResponse(
        company_id=company_id,
        generated_at=datetime.now(tz=UTC),
        deals_total=summary.deals_total,
        status_counts=[
            DashboardStatusCount(
                status=item.status,
                deal_count=item.deal_count,
                total_value=item.total_value,
            )
            for item in summary.status_counts
        ],
        pipeline=[
            DashboardCurrencyTotal(
                currency=item.currency,
                deal_count=item.deal_count,
                total_value=item.total_value,
            )
            for item in summary.pipeline
        ],
        counterparties_total=summary.counterparties_total,
        counterparties_active=summary.counterparties_active,
        products_total=summary.products_total,
        products_active=summary.products_active,
        recent_deals=[deal_summary_response(item) for item in summary.recent_deals],
        recent_activity=[
            DashboardActivity(
                action=item.action,
                outcome=item.outcome,
                occurred_at=item.occurred_at,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
            )
            for item in summary.recent_activity
        ],
    )


__all__ = [
    "counterparty_list_response",
    "counterparty_response",
    "dashboard_response",
    "deal_list_response",
    "deal_response",
    "deal_summary_response",
    "product_list_response",
    "product_response",
]



