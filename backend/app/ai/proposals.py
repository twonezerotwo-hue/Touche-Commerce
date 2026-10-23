"""What the model may *propose*, and the only actions a person can approve.

A proposal is text and a reference for a human. The approval classes are:

``DRAFT_PROPOSAL``
    A written draft (RFQ, follow-up, customer update). Approving it records that a
    person reviewed the wording; **nothing is sent**.
``REQUIRES_HUMAN_APPROVAL``
    A suggested operator task. Approving it records the task for the team; no deal,
    order, payment or accounting record is created or changed.

Anything else (sending, signing, paying, posting, accepting, marking a deal won,
deleting) is ``BLOCKED``: it cannot be proposed, and an executor does not exist for
it, so even a hand-crafted request is refused with ``AI_ACTION_NOT_SUPPORTED``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ai.errors import ActionNotSupportedError, ProposalStateError
from app.ai.evidence import EvidenceRegistry
from app.ai.tools.registry import ToolClass
from app.db.models.ai import ProposalActionType, ProposalKind
from app.security.permissions import Permission

MAX_TITLE = 200
MAX_BODY = 6_000
MAX_RATIONALE = 1_200
_DRAFT_KINDS = {"RFQ_EMAIL", "SUPPLIER_FOLLOW_UP", "CUSTOMER_UPDATE", "OTHER"}
_PRIORITIES = {"HIGH", "MEDIUM", "LOW"}
#: Warnings that mean a figure in the text is not backed by a tool result.
BLOCKING_WARNINGS = frozenset({"UNVERIFIED_NUMBER"})


@dataclass(frozen=True)
class ActionSpec:
    action_type: ProposalActionType
    kind: ProposalKind
    tool_class: ToolClass
    permission: Permission
    description: str


#: The complete list of executable actions. There is deliberately nothing else.
ACTIONS: dict[str, ActionSpec] = {
    ProposalActionType.DRAFT_REVIEW.value: ActionSpec(
        ProposalActionType.DRAFT_REVIEW,
        ProposalKind.DRAFT,
        ToolClass.DRAFT_PROPOSAL,
        Permission.TRADE_WRITE,
        "Mark a draft as reviewed and approved for human use. Nothing is sent.",
    ),
    ProposalActionType.OPERATOR_TASK.value: ActionSpec(
        ProposalActionType.OPERATOR_TASK,
        ProposalKind.TASK,
        ToolClass.REQUIRES_HUMAN_APPROVAL,
        Permission.TRADE_WRITE,
        "Record a suggested follow-up as an operator task. No business record changes.",
    ),
}


def action_spec(action_type: str) -> ActionSpec:
    spec = ACTIONS.get(action_type)
    if spec is None:
        raise ActionNotSupportedError()
    return spec


@dataclass(frozen=True)
class NewProposal:
    kind: ProposalKind
    action_type: ProposalActionType
    action_class: ToolClass
    title: str
    payload: dict[str, Any]
    evidence: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)


def _evidence_snapshot(ids: list[str], registry: EvidenceRegistry) -> list[dict[str, Any]]:
    snapshot = []
    for evidence_id in ids:
        found = registry.get(evidence_id)
        if found is not None:
            snapshot.append(found.to_json())
    return snapshot


def extract_proposals(response: dict[str, Any], registry: EvidenceRegistry) -> list[NewProposal]:
    """Turn the *validated* drafts and task proposals into proposal rows."""
    proposals: list[NewProposal] = []
    draft_spec = ACTIONS[ProposalActionType.DRAFT_REVIEW.value]
    for draft in response.get("drafts", []):
        proposals.append(
            NewProposal(
                kind=draft_spec.kind,
                action_type=draft_spec.action_type,
                action_class=draft_spec.tool_class,
                title=str(draft["title"])[:MAX_TITLE],
                payload={
                    "kind": draft["kind"],
                    "title": str(draft["title"])[:MAX_TITLE],
                    "body": draft["body"],
                },
                evidence=_evidence_snapshot(draft.get("evidence", []), registry),
                warnings=list(draft.get("warnings", [])),
            )
        )
    task_spec = ACTIONS[ProposalActionType.OPERATOR_TASK.value]
    for task in response.get("task_proposals", []):
        proposals.append(
            NewProposal(
                kind=task_spec.kind,
                action_type=task_spec.action_type,
                action_class=task_spec.tool_class,
                title=str(task["title"])[:MAX_TITLE],
                payload={
                    "title": str(task["title"])[:MAX_TITLE],
                    "rationale": task.get("rationale", ""),
                    "priority": task.get("priority", "MEDIUM"),
                    "target": task.get("target"),
                },
                evidence=_evidence_snapshot(task.get("evidence", []), registry),
                warnings=list(task.get("warnings", [])),
            )
        )
    return proposals


def apply_edit(kind: str, current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Validate a human edit of a proposal and return the new payload.

    Only wording can change. The target of a task and the evidence it cites stay as the
    model produced them, so an edit cannot redirect a task to an unverified record.
    """
    updated = dict(current)
    title = patch.get("title")
    if title is not None:
        cleaned = " ".join(str(title).split())
        if not 1 <= len(cleaned) <= MAX_TITLE:
            raise ProposalStateError("The title must be 1 to 200 characters.")
        updated["title"] = cleaned
    if kind == ProposalKind.DRAFT.value:
        body = patch.get("body")
        if body is not None:
            text = str(body).strip()
            if not 1 <= len(text) <= MAX_BODY:
                raise ProposalStateError("The draft body must be 1 to 6000 characters.")
            updated["body"] = text
        draft_kind = patch.get("draft_kind")
        if draft_kind is not None:
            if draft_kind not in _DRAFT_KINDS:
                raise ProposalStateError("Unknown draft kind.")
            updated["kind"] = draft_kind
    else:
        rationale = patch.get("rationale")
        if rationale is not None:
            text = str(rationale).strip()
            if len(text) > MAX_RATIONALE:
                raise ProposalStateError("The rationale is too long.")
            updated["rationale"] = text
        priority = patch.get("priority")
        if priority is not None:
            if priority not in _PRIORITIES:
                raise ProposalStateError("Unknown priority.")
            updated["priority"] = priority
    return updated
