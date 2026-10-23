# ruff: noqa: RUF001  (Turkish keywords are intentional)
"""A deterministic stand-in for a model, used in development, tests and acceptance.

The mock never calls a network. By default it behaves like a careful analyst: it picks
read-only tools from keywords in the operator's request, chains detail tools from the
ids that earlier results returned, and then answers with a structured response that
only repeats what the tool results contain (it cannot invent a number or a citation).

Tests drive the *adversarial* cases (a model that invents evidence, asks for a blocked
tool, loops, or echoes an injected instruction) through ``script``: a callable that
receives the request and the zero-based call index and returns the response.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from app.ai.types import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCall,
    Usage,
    estimate_request_tokens,
    estimate_tokens,
)

MockScript = Callable[[ModelRequest, int], ModelResponse]

_REFERENCE = re.compile(r"\b[A-Z]{2,5}-\d{3,}(?:-[A-Z0-9]+)*\b")
_NUMERIC_FACT = re.compile(r"^-?\d+(?:\.\d+)?$")
_FIGURE_KEYS = (
    "total_value",
    "estimated_profit",
    "estimated_margin_percent",
    "unit_price",
    "landed_cost_total",
    "quoted_total",
    "order_total",
    "variance",
    "amount",
)
_MAX_CHAIN_CALLS = 4

_INTENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("overview", ("overview", "summary", "özet", "genel durum", "dashboard")),
    ("deals", ("deal", "pipeline", "opportunit", "fırsat", "firsat", "active")),
    ("quotes", ("quote", "teklif", "supplier", "tedarik", "compare", "karşılaştır", "rfq")),
    ("pricing", ("pricing", "price", "margin", "landed", "fiyat", "marj", "maliyet")),
    ("orders", ("order", "sipariş", "siparis", "shipment", "sevkiyat", "delay", "gecik")),
    ("finance", ("profit", "kâr", "kar ", "reconcil", "mutabakat", "finance", "finans")),
    ("discrepancies", ("discrepanc", "exception", "uyuşmazlık", "istisna")),
    ("counterparties", ("customer", "müşteri", "counterpart", "tedarikçi", "buyer")),
    ("products", ("product", "ürün", "sku", "catalog", "katalog")),
    ("documents", ("document", "belge", "doküman", "invoice", "fatura")),
    ("draft", ("draft", "taslak", "e-posta", "email", "mail", "follow-up", "mesaj")),
)


def _intents(text: str) -> set[str]:
    lowered = text.lower()
    found = {name for name, words in _INTENTS if any(word in lowered for word in words)}
    return found or {"overview", "deals"}


def _last_turn(messages: tuple[ModelMessage, ...]) -> tuple[str, list[ModelMessage]]:
    """The operator's latest request and everything the model did after it."""
    index = max((i for i, m in enumerate(messages) if m.role == "user"), default=-1)
    if index < 0:
        return "", []
    return messages[index].content, list(messages[index + 1 :])


def _evidence(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for result in results:
        for item in result.get("evidence") or []:
            if isinstance(item, dict) and item.get("id") and item["id"] not in seen:
                seen.add(item["id"])
                items.append(item)
    return items


def _diverse(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One record of each type first, so a long list cannot crowd out a whole category."""
    seen: set[str] = set()
    leaders: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for item in items:
        kind = str(item.get("entity_type"))
        if kind in seen:
            rest.append(item)
        else:
            seen.add(kind)
            leaders.append(item)
    return leaders + rest


def _first(items: list[dict[str, Any]], entity_type: str) -> dict[str, Any] | None:
    return next((i for i in items if i.get("entity_type") == entity_type), None)


class MockProvider:
    name = "mock"
    is_external = False

    def __init__(self, model: str = "mock-trade-director-1", *, script: MockScript | None = None):
        self.model = model
        self._script = script
        self._calls = 0

    # ------------------------------------------------------------------ API
    def complete(self, request: ModelRequest) -> ModelResponse:
        index = self._calls
        self._calls += 1
        if self._script is not None:
            return self._script(request, index)
        text, turn = _last_turn(request.messages)
        results: list[dict[str, Any]] = []
        called: set[str] = set()
        for message in turn:
            if message.role == "assistant":
                for call in message.tool_calls:
                    called.add(f"{call.name}:{json.dumps(call.arguments, sort_keys=True)}")
            elif message.role == "tool":
                try:
                    parsed = json.loads(message.content)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    results.append(parsed)
        planned = [
            (name, args)
            for name, args in self._plan(text, results)
            if f"{name}:{json.dumps(args, sort_keys=True)}" not in called
        ]
        allowed = {tool.name for tool in request.tools}
        planned = [(n, a) for n, a in planned if n in allowed]
        if planned and len(called) < 8:
            calls = tuple(
                ToolCall(id=f"mock_{index}_{i}", name=name, arguments=args)
                for i, (name, args) in enumerate(planned[:_MAX_CHAIN_CALLS])
            )
            return self._response(request, "", calls, "tool_calls")
        answer = json.dumps(self._answer(text, results), ensure_ascii=False)
        return self._response(request, answer, (), "stop")

    def _response(
        self, request: ModelRequest, content: str, calls: tuple[ToolCall, ...], reason: str
    ) -> ModelResponse:
        usage = Usage(
            input_tokens=estimate_request_tokens(request),
            output_tokens=estimate_tokens(content)
            + sum(estimate_tokens(str(c.arguments)) for c in calls),
        )
        return ModelResponse(
            content=content,
            tool_calls=calls,
            usage=usage,
            finish_reason=reason,
            provider=self.name,
            model=self.model,
        )

    # ------------------------------------------------------------- planning
    def _plan(self, text: str, results: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
        intents = _intents(text)
        evidence = _evidence(results)
        references = _REFERENCE.findall(text)
        plan: list[tuple[str, dict[str, Any]]] = []

        if "overview" in intents:
            plan.append(("get_company_trade_overview", {}))
        if intents & {"deals", "quotes", "pricing"} or not intents - {"draft"}:
            plan.append(("list_active_deals", {}))
        if intents & {"orders", "finance"}:
            plan.append(("list_sales_orders", {}))
        if "discrepancies" in intents or "finance" in intents:
            plan.append(("list_financial_discrepancies", {"status": "OPEN"}))
        if "counterparties" in intents:
            plan.append(("search_counterparties", {}))
        if "products" in intents:
            plan.append(("search_products", {}))

        deal = _first(evidence, "DEAL")
        if deal is not None and intents & {"deals", "quotes", "pricing", "draft"}:
            plan.append(("get_deal_details", {"deal_id": deal["entity_id"]}))
            if intents & {"quotes", "draft"}:
                plan.append(("get_supplier_quotes", {"deal_id": deal["entity_id"]}))
            if "quotes" in intents:
                plan.append(("compare_supplier_offers", {"deal_id": deal["entity_id"]}))
            if "pricing" in intents:
                plan.append(("get_pricing_scenario", {"deal_id": deal["entity_id"]}))
        elif references and intents & {"deals", "quotes", "pricing"}:
            plan.append(("get_deal_details", {"reference": references[0]}))

        order = _first(evidence, "SALES_ORDER")
        if order is not None:
            oid = order["entity_id"]
            plan.append(("get_order_details", {"order_id": oid}))
            plan.append(("get_shipment_status", {"order_id": oid}))
            plan.append(("get_purchase_commitments", {"order_id": oid}))
            if "finance" in intents:
                plan.append(("get_order_profitability", {"order_id": oid}))
                plan.append(("get_finance_reconciliation", {"order_id": oid}))
            if "documents" in intents:
                plan.append(
                    ("get_document_metadata", {"entity_type": "SALES_ORDER", "entity_id": oid})
                )
        elif references and "orders" in intents:
            plan.append(("get_order_details", {"reference": references[0]}))
        return plan

    # --------------------------------------------------------------- answer
    def _answer(self, text: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        evidence = _diverse(_evidence(results))
        intents = _intents(text)
        findings: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        recommendations: list[dict[str, Any]] = []
        tasks: list[dict[str, Any]] = []

        for item in evidence[:8]:
            facts: dict[str, str] = item.get("facts") or {}
            figures = [
                {
                    "label": key.replace("_", " "),
                    "value": facts[key],
                    "currency": facts.get("currency"),
                    "evidence": item["id"],
                }
                for key in _FIGURE_KEYS
                if key in facts and _NUMERIC_FACT.match(str(facts[key]))
            ][:2]
            findings.append(
                {
                    "claim": f"{item.get('reference')}: {item.get('label')}",
                    "basis": item.get("basis", "CONFIRMED_SOURCE"),
                    "evidence": [item["id"]],
                    "figures": figures,
                }
            )
            warnings = [str(w).replace("_", " ").lower() for w in item.get("warnings") or []]
            incomplete = item.get("completeness") not in (None, "COMPLETE")
            for warning in warnings[:2]:
                missing.append(
                    {"item": f"{item.get('reference')}: {warning}", "evidence": [item["id"]]}
                )
            if incomplete or warnings:
                recommendations.append(
                    {
                        "action": (
                            f"Review {item.get('reference')} and complete the missing information."
                        ),
                        "priority": "MEDIUM",
                        "rationale": "The recorded source is partial or carries a warning.",
                        "evidence": [item["id"]],
                    }
                )
                tasks.append(
                    {
                        "title": f"Complete missing inputs for {item.get('reference')}",
                        "rationale": "; ".join(warnings[:2]) or "The source record is incomplete.",
                        "priority": "MEDIUM",
                        "target": {
                            "entity_type": item.get("entity_type"),
                            "entity_id": item.get("entity_id"),
                        },
                        "evidence": [item["id"]],
                    }
                )

        drafts: list[dict[str, Any]] = []
        if "draft" in intents and evidence:
            drafts.append(self._draft(text, evidence))

        names = sorted({r.get("tool", "") for r in results if r.get("tool")})
        if evidence:
            summary = (
                f"Reviewed {len(evidence)} recorded source(s) using {', '.join(names)}. "
                "Every statement below cites a stored record."
            )
        else:
            summary = "No matching records were found for this request in the active company."
            findings.append(
                {
                    "claim": "No matching records were returned.",
                    "basis": "NOT_AVAILABLE",
                    "evidence": [],
                }
            )
        return {
            "summary": summary,
            "findings": findings,
            "recommendations": recommendations[:4],
            "missing_inputs": missing[:6],
            "drafts": drafts,
            "task_proposals": tasks[:4],
        }

    def _draft(self, text: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        lowered = text.lower()
        if "rfq" in lowered:
            kind, title = "RFQ_EMAIL", "Request for quotation"
        elif any(word in lowered for word in ("customer", "müşteri", "buyer")):
            kind, title = "CUSTOMER_UPDATE", "Customer update"
        else:
            kind, title = "SUPPLIER_FOLLOW_UP", "Supplier follow-up"
        lines = [f"- {i.get('reference')}: {i.get('label')}" for i in evidence[:5]]
        body = (
            "Hello,\n\nI am following up on the items below. Please confirm availability, "
            "pricing and lead time.\n\n" + "\n".join(lines) + "\n\nThank you."
        )
        return {
            "kind": kind,
            "title": title,
            "body": body,
            "evidence": [i["id"] for i in evidence[:5]],
        }
