"""Stage 5E records to API responses (no financial calculation here)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.api.v1.schemas.intelligence import (
    CategoryCountResponse,
    CompletenessCountResponse,
    CompletionCheckResponse,
    CostComparisonResponse,
    CostVarianceListResponse,
    CoverageResponse,
    EstimateCostLineResponse,
    EvidenceReferenceResponse,
    FilterOptionResponse,
    FilterOptionsResponse,
    FinancialExceptionListResponse,
    FinancialExceptionResponse,
    FxAssumptionResponse,
    IntelligenceMetricResponse,
    IntelligenceSummaryResponse,
    MarginBucketResponse,
    MoneyTotalResponse,
    MonthlyCommitmentResponse,
    OrderIntelligenceDetailResponse,
    OrderIntelligenceListResponse,
    OrderProfitabilityResponse,
    PercentTotalResponse,
    PurchaseOrderDetailResponse,
    QuoteDetailResponse,
    QuoteLineResponse,
    ReconciliationTimelineResponse,
    ShipmentCostDetailResponse,
    ShipmentDetailResponse,
)
from app.services.intelligence import (
    AnalyzedOrder,
    CostVariancePage,
    CoverageRecord,
    ExceptionPage,
    ExceptionRecord,
    FilterOptionsRecord,
    MetricRecord,
    OrderDetailRecord,
    OrderPage,
    SummaryRecord,
)
from app.services.intelligence_calculations import CALCULATION_VERSION, money


def _amount(value: Decimal | None) -> str | None:
    return None if value is None else str(money(value))


def _quantity(value: Decimal) -> str:
    return format(value.normalize(), "f")


def metric_response(metric: MetricRecord) -> IntelligenceMetricResponse:
    return IntelligenceMetricResponse(
        key=metric.key,
        label=metric.label,
        kind=metric.kind.value,
        money=[
            MoneyTotalResponse(currency=item.currency, amount=str(money(item.amount)))
            for item in metric.money
        ],
        percentages=[
            PercentTotalResponse(currency=item.currency, value=str(item.value))
            for item in metric.percentages
        ],
        percentage=str(metric.percentage) if metric.percentage is not None else None,
        count=metric.count,
        available=metric.available,
        classification=metric.classification,
        completeness=metric.completeness,
        meaning=metric.meaning,
        as_of=metric.as_of,
        data_through=metric.data_through,
    )


def filter_options_response(options: FilterOptionsRecord) -> FilterOptionsResponse:
    return FilterOptionsResponse(
        currencies=list(options.currencies),
        customers=[
            FilterOptionResponse(id=identifier, name=name)
            for identifier, name in options.customers
        ],
        suppliers=[
            FilterOptionResponse(id=identifier, name=name)
            for identifier, name in options.suppliers
        ],
        order_statuses=list(options.order_statuses),
        fulfilment_models=list(options.fulfilment_models),
        reconciliation_statuses=list(options.reconciliation_statuses),
        completeness_statuses=list(options.completeness_statuses),
    )


def order_response(item: AnalyzedOrder) -> OrderProfitabilityResponse:
    facts = item.facts
    result = item.result
    return OrderProfitabilityResponse(
        sales_order_id=facts.sales_order_id,
        order_number=facts.order_number,
        customer_name=facts.customer_name,
        status=facts.status,
        fulfilment_model=facts.fulfilment_model,
        currency=result.currency,
        confirmed_at=facts.confirmed_at,
        expected_delivery_date=facts.expected_delivery_date,
        sales_value=str(result.sales_value),
        estimated_purchase_cost=_amount(result.estimated_purchase_cost),
        estimated_extra_purchase_cost=_amount(result.estimated_extra_purchase_cost),
        estimated_operational_cost=_amount(result.estimated_operational_cost),
        estimated_vat_cashflow=_amount(result.estimated_vat_cashflow),
        estimated_landed_cost=_amount(result.estimated_landed_cost),
        scenario_landed_total_including_vat=_amount(
            result.scenario_landed_total_including_vat
        ),
        committed_purchase_cost=_amount(result.committed_purchase_cost),
        quoted_operational_cost=_amount(result.quoted_operational_cost),
        documented_operational_cost=_amount(result.documented_operational_cost),
        documented_total_cost=_amount(result.documented_total_cost),
        estimated_gross_profit=_amount(result.estimated_gross_profit),
        estimated_gross_margin_pct=_amount(result.estimated_gross_margin_pct),
        estimated_markup_pct=_amount(result.estimated_markup_pct),
        committed_gross_profit=_amount(result.committed_gross_profit),
        committed_gross_margin_pct=_amount(result.committed_gross_margin_pct),
        committed_markup_pct=_amount(result.committed_markup_pct),
        cost_variance=_amount(result.cost_variance),
        cost_variance_pct=_amount(result.cost_variance_pct),
        estimate_status=result.estimate_status.value,
        committed_status=result.committed_status.value,
        completeness=result.completeness.value,
        missing_components=list(result.missing_components),
        classifications=dict(result.classifications),
        purchase_currency_mismatch=result.purchase_currency_mismatch,
        cost_currency_mismatch=result.cost_currency_mismatch,
        partial_fulfilment=result.partial_fulfilment,
        cancelled=result.cancelled,
        reconciliation_status=facts.reconciliation_status,
        latest_run_id=facts.latest_run_id,
        latest_run_at=facts.latest_run_at,
        data_through=facts.data_through,
        open_discrepancy_count=facts.open_discrepancy_count,
        blocking_discrepancy_count=facts.blocking_discrepancy_count,
        run_count=facts.run_count,
    )


def summary_response(record: SummaryRecord) -> IntelligenceSummaryResponse:
    return IntelligenceSummaryResponse(
        as_of=record.as_of,
        data_through=record.data_through,
        calculation_version=record.calculation_version,
        order_count=record.order_count,
        active_order_count=record.active_order_count,
        cancelled_order_count=record.cancelled_order_count,
        metrics=[metric_response(metric) for metric in record.metrics],
        monthly_commitments=[
            MonthlyCommitmentResponse(
                month=item.month,
                currency=item.currency,
                accepted_value=str(item.accepted_value),
                purchase_commitments=str(item.purchase_commitments),
                order_count=item.order_count,
            )
            for item in record.monthly_commitments
        ],
        cost_comparison=[
            CostComparisonResponse(
                currency=item.currency,
                estimated_cost=str(item.estimated_cost),
                documented_cost=str(item.documented_cost),
                variance=str(item.variance),
                order_count=item.order_count,
            )
            for item in record.cost_comparison
        ],
        margin_distribution=[
            MarginBucketResponse(key=item.key, label=item.label, count=item.count)
            for item in record.margin_distribution
        ],
        discrepancy_categories=[
            CategoryCountResponse(key=item.key, count=item.count)
            for item in record.discrepancy_categories
        ],
        completeness=[
            CompletenessCountResponse(status=item.status, count=item.count)
            for item in record.completeness
        ],
        review_orders=[order_response(item) for item in record.review_orders],
        filter_options=filter_options_response(record.filter_options),
    )


def order_list_response(
    page: OrderPage,
    *,
    as_of: date,
    data_through: date | None,
) -> OrderIntelligenceListResponse:
    return OrderIntelligenceListResponse(
        items=[order_response(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        calculation_version=CALCULATION_VERSION,
        as_of=as_of,
        data_through=data_through,
    )


def cost_variance_response(
    page: CostVariancePage,
    *,
    as_of: date,
) -> CostVarianceListResponse:
    return CostVarianceListResponse(
        items=[order_response(item) for item in page.items],
        total=page.total,
        excluded_order_count=page.excluded_order_count,
        limit=page.limit,
        offset=page.offset,
        calculation_version=CALCULATION_VERSION,
        as_of=as_of,
    )


def coverage_response(record: CoverageRecord) -> CoverageResponse:
    return CoverageResponse(
        as_of=record.as_of,
        data_through=record.data_through,
        order_count=record.order_count,
        active_order_count=record.active_order_count,
        estimate=[
            CompletenessCountResponse(status=item.status, count=item.count)
            for item in record.estimate
        ],
        committed=[
            CompletenessCountResponse(status=item.status, count=item.count)
            for item in record.committed
        ],
        reconciliation=[
            CategoryCountResponse(key=item.key, count=item.count)
            for item in record.reconciliation
        ],
        missing_components=[
            CategoryCountResponse(key=item.key, count=item.count)
            for item in record.missing_components
        ],
        calculation_version=CALCULATION_VERSION,
    )


def exception_response(item: ExceptionRecord) -> FinancialExceptionResponse:
    return FinancialExceptionResponse(
        id=item.id,
        run_id=item.run_id,
        sales_order_id=item.sales_order_id,
        order_number=item.order_number,
        customer_name=item.customer_name,
        currency=item.currency,
        order_status=item.order_status,
        code=item.code,
        severity=item.severity,
        status=item.status,
        title=item.title,
        detail=item.detail,
        expected=item.expected,
        observed=item.observed,
        source_entity_type=item.source_entity_type,
        source_entity_id=item.source_entity_id,
        finance_source_reference=item.finance_source_reference,
        reviewer_name=item.reviewer_name,
        resolution_notes=item.resolution_notes,
        resolved_at=item.resolved_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        version=item.version,
    )


def exception_list_response(page: ExceptionPage) -> FinancialExceptionListResponse:
    return FinancialExceptionListResponse(
        items=[exception_response(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


def detail_response(record: OrderDetailRecord) -> OrderIntelligenceDetailResponse:
    item = record.analyzed
    return OrderIntelligenceDetailResponse(
        order=order_response(item),
        quote=QuoteDetailResponse(
            quote_id=record.quote.quote_id,
            quote_number=record.quote.quote_number,
            revision=record.quote.revision,
            status=record.quote.status,
            currency=record.quote.currency,
            incoterm=record.quote.incoterm,
            named_delivery_place=record.quote.named_delivery_place,
            payment_terms=record.quote.payment_terms,
            valid_until=record.quote.valid_until,
            approved_at=record.quote.approved_at,
            lines=[
                QuoteLineResponse(
                    product_id=line.product_id,
                    description=line.description,
                    quantity=_quantity(line.quantity),
                    unit=line.unit,
                    unit_price=str(line.unit_price),
                    line_total=str(money(line.line_total)),
                )
                for line in record.quote.lines
            ],
        ),
        purchase_orders=[
            PurchaseOrderDetailResponse(
                purchase_order_id=po.purchase_order_id,
                po_number=po.po_number,
                status=po.status,
                currency=po.currency,
                total_cost=str(money(po.total_cost)),
                supplier_id=po.supplier_id,
                supplier_name=po.supplier_name,
                classification="COMMITTED" if po.is_committed else "UNAVAILABLE",
            )
            for po in record.purchase_orders
        ],
        shipments=[
            ShipmentDetailResponse(
                shipment_id=shipment.shipment_id,
                shipment_number=shipment.shipment_number,
                status=shipment.status,
                costs=[
                    ShipmentCostDetailResponse(
                        cost_id=cost.cost_id,
                        cost_type=cost.cost_type,
                        stage=cost.stage,
                        currency=cost.currency,
                        amount=str(money(cost.amount)),
                        reference=cost.reference,
                        classification="DOCUMENTED"
                        if cost.is_documented
                        else "ESTIMATED"
                        if cost.is_forecast
                        else "UNAVAILABLE",
                    )
                    for cost in shipment.costs
                ],
            )
            for shipment in record.shipments
        ],
        cost_lines=[
            EstimateCostLineResponse(
                cost_type=line.cost_type,
                original_amount=_amount(line.original_amount),
                original_currency=line.original_currency,
                converted_amount=_amount(line.converted_amount),
                target_currency=line.target_currency,
                basis=line.basis,
                verification_status=line.verification_status,
                source_reference=line.source_reference,
                fx_rate=str(line.fx_rate) if line.fx_rate is not None else None,
                fx_snapshot_id=line.fx_snapshot_id,
                is_expense=line.is_expense,
            )
            for line in record.cost_lines
        ],
        fx_assumptions=[
            FxAssumptionResponse(
                snapshot_id=fx.snapshot_id,
                base_currency=fx.base_currency,
                quote_currency=fx.quote_currency,
                rate=str(fx.rate),
                effective_at=fx.effective_at,
                source=fx.source,
            )
            for fx in record.fx_assumptions
        ],
        checks=[
            CompletionCheckResponse(
                key=check.key,
                label=check.label,
                satisfied=check.satisfied,
                detail=check.detail,
            )
            for check in item.result.checks
        ],
        limitations=list(item.result.limitations),
        runs=[
            ReconciliationTimelineResponse(
                run_id=run.run_id,
                status=run.status,
                as_of=run.as_of,
                data_through=run.data_through,
                currency=run.currency,
                created_at=run.created_at,
                evidence_count=run.evidence_count,
                open_discrepancy_count=run.open_discrepancy_count,
                latest_decision=run.latest_decision,
                latest_review_at=run.latest_review_at,
            )
            for run in record.runs
        ],
        evidence=[
            EvidenceReferenceResponse(
                id=link.id,
                run_id=link.run_id,
                source_entity_type=link.source_entity_type,
                source_entity_id=link.source_entity_id,
                finance_source_type=link.finance_source_type,
                finance_source_reference=link.finance_source_reference,
                currency=link.currency,
                amount=str(money(link.amount)),
                as_of=link.as_of,
                data_through=link.data_through,
                verification_status=link.verification_status,
                created_at=link.created_at,
                verified_at=link.verified_at,
            )
            for link in record.evidence
        ],
        discrepancies=[
            exception_response(discrepancy) for discrepancy in record.discrepancies
        ],
    )
