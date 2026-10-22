"""Reconciliation records to API responses (no financial calculations here)."""

from __future__ import annotations

from typing import Any

from app.api.v1.schemas.reconciliation import (
    CompletenessCheckResponse,
    DiscrepancyListResponse,
    DiscrepancyResponse,
    EvidenceLinkListResponse,
    EvidenceLinkResponse,
    OrderFinanceEvidenceGap,
    OrderFinanceOrder,
    OrderFinancePurchaseOrder,
    OrderFinanceResponse,
    OrderFinanceShipment,
    OrderFinanceShipmentCost,
    ReconciliationListResponse,
    ReconciliationMetricsResponse,
    ReconciliationRunResponse,
    ReconciliationRunSummaryResponse,
    ReviewResponse,
    SourceReferenceResponse,
)
from app.services.reconciliation import (
    DiscrepancyPage,
    DiscrepancyRecord,
    EvidencePage,
    EvidenceRecord,
    OrderFinanceRecord,
    ReviewRecord,
    RunPage,
    RunRecord,
    RunSummaryRecord,
    SourceReferenceRecord,
)
from app.services.reconciliation_calculations import quantize_money


def _amount(value: Any) -> str | None:
    if value is None:
        return None
    return str(quantize_money(value))


def metrics_response(snapshot: dict[str, Any]) -> ReconciliationMetricsResponse:
    metrics = snapshot.get("commercial", {}).get("metrics", {})
    checks = metrics.get("completeness_checks", []) if isinstance(metrics, dict) else []
    return ReconciliationMetricsResponse(
        accepted_sales_order_value=str(metrics.get("accepted_sales_order_value", "0.00")),
        purchase_commitments_total=metrics.get("purchase_commitments_total"),
        purchase_commitment_count=int(metrics.get("purchase_commitment_count", 0)),
        estimated_landed_cost=metrics.get("estimated_landed_cost"),
        recorded_operational_costs=metrics.get("recorded_operational_costs"),
        estimate_vs_recorded_variance=metrics.get("estimate_vs_recorded_variance"),
        commitment_based_margin=metrics.get("commitment_based_margin"),
        commitment_based_margin_pct=metrics.get("commitment_based_margin_pct"),
        document_supported_margin=None,
        completeness_score=str(metrics.get("completeness_score", "0.00")),
        completeness_checks=[
            CompletenessCheckResponse.model_validate(check)
            for check in checks
            if isinstance(check, dict)
        ],
    )


def source_reference_response(row: SourceReferenceRecord) -> SourceReferenceResponse:
    return SourceReferenceResponse(
        id=row.id,
        source_type=row.source_type,
        source_reference=row.source_reference,
        is_transaction_level=row.is_transaction_level,
        currency=row.currency,
        observed_amount=_amount(row.observed_amount),
        as_of=row.as_of,
        data_through=row.data_through,
        content_hash=row.content_hash,
        payload=row.payload,
    )


def evidence_response(row: EvidenceRecord) -> EvidenceLinkResponse:
    return EvidenceLinkResponse(
        id=row.id,
        source_entity_type=row.source_entity_type,
        source_entity_id=row.source_entity_id,
        finance_source_reference_id=row.finance_source_reference_id,
        finance_source_type=row.source_type,
        finance_source_reference=row.source_reference,
        currency=row.currency,
        amount=str(quantize_money(row.amount)),
        as_of=row.as_of,
        data_through=row.data_through,
        provenance=row.provenance,
        verification_status=row.verification_status,
        notes=row.notes,
        created_by=row.created_by,
        created_at=row.created_at,
        verified_by=row.verified_by,
        verified_at=row.verified_at,
    )


def discrepancy_response(row: DiscrepancyRecord) -> DiscrepancyResponse:
    return DiscrepancyResponse(
        id=row.id,
        run_id=row.run_id,
        code=row.code,
        severity=row.severity,
        status=row.status,
        title=row.title,
        detail=row.detail,
        expected=row.expected,
        observed=row.observed,
        source_entity_type=row.source_entity_type,
        source_entity_id=row.source_entity_id,
        finance_source_reference_id=row.finance_source_reference_id,
        assigned_to=row.assigned_to,
        resolution_notes=row.resolution_notes,
        resolved_by=row.resolved_by,
        resolved_at=row.resolved_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
    )


def review_response(row: ReviewRecord) -> ReviewResponse:
    return ReviewResponse(
        id=row.id,
        decision=row.decision,
        previous_status=row.previous_status,
        new_status=row.new_status,
        notes=row.notes,
        reviewer_id=row.reviewer_id,
        reviewer_name=row.reviewer_name,
        created_at=row.created_at,
    )


def run_summary_response(row: RunSummaryRecord) -> ReconciliationRunSummaryResponse:
    return ReconciliationRunSummaryResponse(
        id=row.id,
        sales_order_id=row.sales_order_id,
        order_number=row.order_number,
        customer_name=row.customer_name,
        currency=row.currency,
        as_of=row.as_of,
        data_through=row.data_through,
        status=row.status,
        version=row.version,
        created_at=row.created_at,
        evidence_count=row.evidence_count,
        open_discrepancy_count=row.open_discrepancy_count,
        blocking_discrepancy_count=row.blocking_discrepancy_count,
    )


def run_response(row: RunRecord) -> ReconciliationRunResponse:
    open_discrepancies = sum(1 for item in row.discrepancies if item.status == "OPEN")
    blocking = sum(
        1 for item in row.discrepancies if item.status == "OPEN" and item.severity == "BLOCKING"
    )
    return ReconciliationRunResponse(
        id=row.id,
        company_id=row.company_id,
        sales_order_id=row.sales_order_id,
        order_number=row.order_number,
        customer_name=row.customer_name,
        finance_company_id=row.finance_company_id,
        currency=row.currency,
        finance_currency=row.finance_currency,
        as_of=row.as_of,
        data_through=row.data_through,
        status=row.status,
        calculation_version=row.calculation_version,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        evidence_count=len(row.evidence),
        open_discrepancy_count=open_discrepancies,
        blocking_discrepancy_count=blocking,
        metrics=metrics_response(row.source_snapshot),
        classifications=dict(row.source_snapshot.get("commercial", {}).get("classifications", {})),
        limitations=list(row.source_snapshot.get("commercial", {}).get("limitations", [])),
        finance_snapshot=dict(row.source_snapshot.get("finance", {})),
        source_references=[source_reference_response(item) for item in row.source_references],
        evidence_links=[evidence_response(item) for item in row.evidence],
        discrepancies=[discrepancy_response(item) for item in row.discrepancies],
        reviews=[review_response(item) for item in row.reviews],
        created_by=row.created_by,
    )


def run_list_response(
    page: RunPage,
    *,
    limit: int,
    offset: int,
    currency: str | None,
    status_counts: dict[str, int],
    open_discrepancy_count: int,
    blocking_discrepancy_count: int,
) -> ReconciliationListResponse:
    return ReconciliationListResponse(
        items=[run_summary_response(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
        currency=currency,
        status_counts=status_counts,
        open_discrepancy_count=open_discrepancy_count,
        blocking_discrepancy_count=blocking_discrepancy_count,
    )


def evidence_list_response(
    page: EvidencePage, *, limit: int, offset: int
) -> EvidenceLinkListResponse:
    return EvidenceLinkListResponse(
        items=[evidence_response(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


def discrepancy_list_response(
    page: DiscrepancyPage, *, limit: int, offset: int
) -> DiscrepancyListResponse:
    return DiscrepancyListResponse(
        items=[discrepancy_response(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


def order_finance_response(row: OrderFinanceRecord) -> OrderFinanceResponse:
    return OrderFinanceResponse(
        order=OrderFinanceOrder(
            sales_order_id=row.sales_order_id,
            order_number=row.order_number,
            customer_name=row.customer_name,
            status=row.facts.status,
            fulfilment_model=row.facts.fulfilment_model,
            currency=row.currency,
            order_total=str(quantize_money(row.facts.order_total)),
            confirmed_at=row.facts.confirmed_at,
            expected_delivery_date=row.facts.expected_delivery_date,
        ),
        purchase_orders=[
            OrderFinancePurchaseOrder(
                purchase_order_id=item.purchase_order_id,
                po_number=item.po_number,
                status=item.status,
                currency=item.currency,
                total_cost=str(quantize_money(item.total_cost)),
                is_committed=item.is_committed,
            )
            for item in row.facts.purchase_orders
        ],
        shipments=[
            OrderFinanceShipment(
                shipment_id=shipment.shipment_id,
                shipment_number=shipment.shipment_number,
                status=shipment.status,
                costs=[
                    OrderFinanceShipmentCost(
                        cost_id=cost.cost_id,
                        cost_type=cost.cost_type,
                        stage=cost.stage,
                        currency=cost.currency,
                        amount=str(quantize_money(cost.amount)),
                        reference=cost.reference,
                    )
                    for cost in shipment.costs
                ],
            )
            for shipment in row.facts.shipments
        ],
        metrics=ReconciliationMetricsResponse(
            accepted_sales_order_value=str(quantize_money(row.metrics.accepted_sales_order_value)),
            purchase_commitments_total=_amount(row.metrics.purchase_commitments_total),
            purchase_commitment_count=row.metrics.purchase_commitment_count,
            estimated_landed_cost=_amount(row.metrics.estimated_landed_cost),
            recorded_operational_costs=_amount(row.metrics.recorded_operational_costs),
            estimate_vs_recorded_variance=_amount(row.metrics.estimate_vs_recorded_variance),
            commitment_based_margin=_amount(row.metrics.commitment_based_margin),
            commitment_based_margin_pct=_amount(row.metrics.commitment_based_margin_pct),
            document_supported_margin=None,
            completeness_score=str(quantize_money(row.metrics.completeness_score)),
            completeness_checks=[
                CompletenessCheckResponse(
                    key=check.key,
                    label=check.label,
                    satisfied=check.satisfied,
                    detail=check.detail,
                )
                for check in row.metrics.completeness_checks
            ],
        ),
        classifications=row.classifications,
        limitations=list(row.limitations),
        missing_evidence=[
            OrderFinanceEvidenceGap(
                code=draft.code.value,
                severity=draft.severity.value,
                title=draft.title,
                detail=draft.detail,
                expected=dict(draft.expected),
                observed=dict(draft.observed),
                source_entity_type=draft.source_entity_type,
                source_entity_id=draft.source_entity_id,
            )
            for draft in row.evidence_gaps
        ],
        latest_run_id=row.latest_run_id,
        latest_run_status=row.latest_run_status,
        latest_run_at=row.latest_run_at,
    )
