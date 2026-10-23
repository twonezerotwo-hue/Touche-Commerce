"""The evidence model and the validator of the model's structured answer.

Tools return *evidence items* (an entity, a human-readable reference, a timestamp,
the exact key facts and how complete the source is). The server assigns the ids a
run's answer may cite (``E1``, ``E2`` …) and computes every link itself. The model's
answer is then validated against that registry:

* an unknown evidence id is removed — nothing is cited that no tool returned;
* a claim can never be stronger than the weakest evidence it cites;
* a figure survives only if its exact value is among the cited evidence's facts;
* a number in free text that appears in no tool result marks the claim
  ``AI_INFERENCE`` with a warning, so an invented amount cannot pass as a source.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

MAX_TEXT = 1_200
MAX_DRAFT_BODY = 6_000
MAX_FINDINGS = 12
MAX_ITEMS = 12


class EvidenceBasis(StrEnum):
    CONFIRMED_SOURCE = "CONFIRMED_SOURCE"
    ESTIMATED = "ESTIMATED"
    INCOMPLETE = "INCOMPLETE"
    AI_INFERENCE = "AI_INFERENCE"
    NOT_AVAILABLE = "NOT_AVAILABLE"


# How strongly a source supports a claim. AI_INFERENCE is not a source basis.
_STRENGTH: dict[EvidenceBasis, int] = {
    EvidenceBasis.CONFIRMED_SOURCE: 3,
    EvidenceBasis.ESTIMATED: 2,
    EvidenceBasis.INCOMPLETE: 1,
    EvidenceBasis.NOT_AVAILABLE: 0,
}

# Links are computed here, never taken from the model.
_HREFS: dict[str, str] = {
    "DEAL": "/deals/{id}",
    "SUPPLIER_QUOTE": "/quotes/{id}",
    "RFQ": "/rfq/{id}",
    "PRICING_SCENARIO": "/pricing/{id}",
    "SALES_ORDER": "/orders/{id}",
    "PURCHASE_ORDER": "/purchase-orders/{id}",
    "SHIPMENT": "/shipments/{id}",
    "RECONCILIATION_RUN": "/finance/reconciliation/{id}",
    "ORDER_PROFITABILITY": "/finance/intelligence/orders/{id}",
    "ORDER_FINANCE": "/finance/orders/{id}",
    "COUNTERPARTY": "/crm",
    "PRODUCT": "/products",
    "DOCUMENT": "/documents",
    "COMPANY": "/",
    "PIPELINE": "/deals",
    "SALES_QUOTE": "/sales-quotes/{id}",
    "INTELLIGENCE_METRIC": "/finance/intelligence",
    "DISCREPANCY": "/finance/intelligence/exceptions",
}

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_NUMBER = re.compile(r"(?<![\w.\-])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\w\-]|\.\d)")
_DRAFT_KINDS = {"RFQ_EMAIL", "SUPPLIER_FOLLOW_UP", "CUSTOMER_UPDATE", "OTHER"}
_PRIORITIES = {"HIGH", "MEDIUM", "LOW"}


def href_for(entity_type: str, entity_id: str) -> str | None:
    template = _HREFS.get(entity_type)
    if template is None:
        return None
    if "{id}" in template and not _UUID.match(entity_id):
        return None
    return template.format(id=entity_id)


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """What a tool reports about one record (before the server assigns an id)."""

    entity_type: str
    entity_id: str
    reference: str
    label: str
    basis: EvidenceBasis
    as_of: str | None = None
    completeness: str = "COMPLETE"
    facts: tuple[tuple[str, str], ...] = ()
    warnings: tuple[str, ...] = ()

    def facts_dict(self) -> dict[str, str]:
        return dict(self.facts)


@dataclass(frozen=True, slots=True)
class RegisteredEvidence:
    id: str
    item: EvidenceItem
    tool: str
    href: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "entity_type": self.item.entity_type,
            "entity_id": self.item.entity_id,
            "reference": self.item.reference,
            "label": self.item.label,
            "basis": str(self.item.basis),
            "as_of": self.item.as_of,
            "completeness": self.item.completeness,
            "facts": dict(self.item.facts),
            "warnings": list(self.item.warnings),
            "tool": self.tool,
            "href": self.href,
        }


def normalise_number(token: str) -> Decimal | None:
    try:
        value = Decimal(token.replace(",", ""))
    except InvalidOperation:
        return None
    return value.normalize()


def extract_numbers(text: str) -> set[Decimal]:
    found: set[Decimal] = set()
    for match in _NUMBER.finditer(text):
        value = normalise_number(match.group(0))
        if value is not None:
            found.add(value)
    return found


def _walk_numbers(value: Any, out: set[Decimal], depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float, Decimal)):
        number = normalise_number(str(value))
        if number is not None:
            out.add(number)
    elif isinstance(value, str):
        out |= extract_numbers(value)
    elif isinstance(value, dict):
        for item in value.values():
            _walk_numbers(item, out, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _walk_numbers(item, out, depth + 1)


class EvidenceRegistry:
    """Evidence gathered during one run, with the numbers the run may talk about."""

    def __init__(self) -> None:
        self._items: dict[str, RegisteredEvidence] = {}
        self._by_key: dict[tuple[str, str, str, tuple[tuple[str, str], ...]], str] = {}
        self._numbers: set[Decimal] = set()

    def register(self, item: EvidenceItem, *, tool: str) -> RegisteredEvidence:
        key = (item.entity_type, item.entity_id, str(item.basis), item.facts)
        existing = self._by_key.get(key)
        if existing is not None:
            return self._items[existing]
        evidence_id = f"E{len(self._items) + 1}"
        registered = RegisteredEvidence(
            id=evidence_id,
            item=item,
            tool=tool,
            href=href_for(item.entity_type, item.entity_id),
        )
        self._items[evidence_id] = registered
        self._by_key[key] = evidence_id
        return registered

    def absorb_numbers(self, payload: Any) -> None:
        _walk_numbers(payload, self._numbers)

    def get(self, evidence_id: str) -> RegisteredEvidence | None:
        return self._items.get(evidence_id)

    def all(self) -> list[RegisteredEvidence]:
        return list(self._items.values())

    def entity_ids(self) -> set[tuple[str, str]]:
        return {(e.item.entity_type, e.item.entity_id) for e in self._items.values()}

    def number_is_known(self, number: Decimal) -> bool:
        if number in self._numbers:
            return True
        # Small whole numbers are counts the model may state; years appear in dates.
        is_whole = number == number.to_integral_value()
        return is_whole and (0 <= number <= 20 or 2000 <= number <= 2100)


# ----------------------------------------------------------------------- parsing
def parse_model_json(text: str) -> dict[str, Any] | None:
    """Extract the single JSON object the model was asked for, or ``None``."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = "".join(ch for ch in value if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return cleaned.strip()[:limit]


def _ids(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value[:8] if isinstance(item, (str, int))]


@dataclass(slots=True)
class ValidationResult:
    response: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def _resolve(
    ids: list[str], registry: EvidenceRegistry, warnings: list[str]
) -> list[RegisteredEvidence]:
    resolved: list[RegisteredEvidence] = []
    for evidence_id in ids:
        found = registry.get(evidence_id)
        if found is None:
            warnings.append("UNKNOWN_EVIDENCE_REMOVED")
        elif found not in resolved:
            resolved.append(found)
    return resolved


def _check_numbers(text: str, registry: EvidenceRegistry) -> bool:
    """True when every number in ``text`` appears in a tool result of this run."""
    return all(registry.number_is_known(number) for number in extract_numbers(text))


def _basis_for(
    claimed: str, evidence: list[RegisteredEvidence], warnings: list[str]
) -> EvidenceBasis:
    try:
        basis = EvidenceBasis(claimed)
    except ValueError:
        warnings.append("BASIS_INVALID")
        basis = EvidenceBasis.AI_INFERENCE
    if basis in (EvidenceBasis.AI_INFERENCE, EvidenceBasis.NOT_AVAILABLE):
        return basis
    if not evidence:
        warnings.append("NO_SOURCE_EVIDENCE")
        return EvidenceBasis.AI_INFERENCE
    weakest = min((e.item.basis for e in evidence), key=lambda b: _STRENGTH[b])
    if _STRENGTH[weakest] < _STRENGTH[basis]:
        warnings.append("BASIS_DOWNGRADED")
        return weakest
    return basis


def validate_response(raw: dict[str, Any], registry: EvidenceRegistry) -> ValidationResult:
    """Normalise and verify the model's answer against the run's evidence."""
    warnings: list[str] = []
    findings: list[dict[str, Any]] = []
    for item in (raw.get("findings") or [])[:MAX_FINDINGS]:
        if not isinstance(item, dict) or not _text(item.get("claim")):
            continue
        local: list[str] = []
        claim = _text(item.get("claim"))
        evidence = _resolve(_ids(item.get("evidence")), registry, local)
        basis = _basis_for(str(item.get("basis") or ""), evidence, local)
        if not _check_numbers(claim, registry):
            local.append("UNVERIFIED_NUMBER")
            basis = EvidenceBasis.AI_INFERENCE
        figures: list[dict[str, str | None]] = []
        for figure in (item.get("figures") or [])[:8]:
            if not isinstance(figure, dict):
                continue
            cited = registry.get(str(figure.get("evidence") or ""))
            value = _text(figure.get("value"), 64)
            number = normalise_number(value) if value else None
            known = (
                cited is not None
                and number is not None
                and any(
                    normalise_number(fact) == number for fact in cited.item.facts_dict().values()
                )
            )
            if not known:
                local.append("UNVERIFIED_FIGURE_REMOVED")
                continue
            figures.append(
                {
                    "label": _text(figure.get("label"), 120),
                    "value": value,
                    "currency": _text(figure.get("currency"), 3) or None,
                    "evidence": cited.id if cited else None,
                }
            )
        findings.append(
            {
                "claim": claim,
                "basis": str(basis),
                "evidence": [e.id for e in evidence],
                "figures": figures,
                "warnings": sorted(set(local)),
            }
        )
        warnings.extend(local)

    recommendations: list[dict[str, Any]] = []
    for item in (raw.get("recommendations") or [])[:MAX_ITEMS]:
        if not isinstance(item, dict) or not _text(item.get("action")):
            continue
        local = []
        evidence = _resolve(_ids(item.get("evidence")), registry, local)
        action = _text(item.get("action"))
        rationale = _text(item.get("rationale"))
        if not _check_numbers(action + " " + rationale, registry):
            local.append("UNVERIFIED_NUMBER")
        priority = str(item.get("priority") or "").upper()
        recommendations.append(
            {
                "action": action,
                "priority": priority if priority in _PRIORITIES else "MEDIUM",
                "rationale": rationale,
                "evidence": [e.id for e in evidence],
                "warnings": sorted(set(local)),
            }
        )
        warnings.extend(local)

    missing: list[dict[str, Any]] = []
    for item in (raw.get("missing_inputs") or [])[:MAX_ITEMS]:
        if not isinstance(item, dict) or not _text(item.get("item")):
            continue
        local = []
        evidence = _resolve(_ids(item.get("evidence")), registry, local)
        missing.append({"item": _text(item.get("item")), "evidence": [e.id for e in evidence]})
        warnings.extend(local)

    drafts: list[dict[str, Any]] = []
    for item in (raw.get("drafts") or [])[:4]:
        if not isinstance(item, dict) or not _text(item.get("body"), MAX_DRAFT_BODY):
            continue
        local = []
        evidence = _resolve(_ids(item.get("evidence")), registry, local)
        body = _text(item.get("body"), MAX_DRAFT_BODY)
        if not _check_numbers(body, registry):
            local.append("UNVERIFIED_NUMBER")
        kind = str(item.get("kind") or "OTHER").upper()
        drafts.append(
            {
                "kind": kind if kind in _DRAFT_KINDS else "OTHER",
                "title": _text(item.get("title"), 200) or "Draft",
                "body": body,
                "evidence": [e.id for e in evidence],
                "warnings": sorted(set(local)),
            }
        )
        warnings.extend(local)

    tasks: list[dict[str, Any]] = []
    known_entities = registry.entity_ids()
    for item in (raw.get("task_proposals") or [])[:MAX_ITEMS]:
        if not isinstance(item, dict) or not _text(item.get("title"), 200):
            continue
        local = []
        evidence = _resolve(_ids(item.get("evidence")), registry, local)
        target = item.get("target") if isinstance(item.get("target"), dict) else None
        clean_target: dict[str, str] | None = None
        if target:
            pair = (str(target.get("entity_type") or ""), str(target.get("entity_id") or ""))
            if pair in known_entities:
                clean_target = {"entity_type": pair[0], "entity_id": pair[1]}
            else:
                local.append("UNKNOWN_TARGET_REMOVED")
        priority = str(item.get("priority") or "").upper()
        tasks.append(
            {
                "title": _text(item.get("title"), 200),
                "rationale": _text(item.get("rationale")),
                "priority": priority if priority in _PRIORITIES else "MEDIUM",
                "target": clean_target,
                "evidence": [e.id for e in evidence],
                "warnings": sorted(set(local)),
            }
        )
        warnings.extend(local)

    summary = _text(raw.get("summary"))
    if summary and not _check_numbers(summary, registry):
        warnings.append("UNVERIFIED_NUMBER")
    response = {
        "summary": summary,
        "findings": findings,
        "recommendations": recommendations,
        "missing_inputs": missing,
        "drafts": drafts,
        "task_proposals": tasks,
    }
    return ValidationResult(response=response, warnings=sorted(set(warnings)))


def unstructured_response(text: str) -> ValidationResult:
    """The model answered in prose: keep it, label it as inference, cite nothing."""
    return ValidationResult(
        response={
            "summary": _text(text, 2_000),
            "findings": [],
            "recommendations": [],
            "missing_inputs": [],
            "drafts": [],
            "task_proposals": [],
        },
        warnings=["RESPONSE_NOT_STRUCTURED"],
    )
