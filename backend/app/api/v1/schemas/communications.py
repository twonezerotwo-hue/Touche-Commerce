"""Stage 7A communications discovery contracts: drafts only, no outbound sending."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CommunicationsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class ChannelStatus(CommunicationsModel):
    channel: Literal["EMAIL", "WHATSAPP_BUSINESS"]
    state: Literal["NOT_CONFIGURED"] = "NOT_CONFIGURED"
    can_send: Literal[False] = False


class CommunicationsStatusResponse(CommunicationsModel):
    mode: Literal["DRAFT_ONLY"] = "DRAFT_ONLY"
    external_sending_enabled: Literal[False] = False
    can_review_drafts: bool
    can_manage_suppressions: bool = False
    send_permission: Literal["communications.send"] = "communications.send"
    channels: list[ChannelStatus] = Field(default_factory=list)


class CommunicationDraftResponse(CommunicationsModel):
    id: UUID
    conversation_id: UUID
    title: str
    body: str
    draft_kind: str
    status: Literal["PROPOSED", "APPROVED", "REJECTED"]
    version: int
    created_at: datetime
    updated_at: datetime
    source_href: Literal["/ai"] = "/ai"
    sent: Literal[False] = False


class CommunicationDraftListResponse(CommunicationsModel):
    items: list[CommunicationDraftResponse]
    source: Literal["AI_OFFICE"] = "AI_OFFICE"
    truncated: bool = False


class CommunicationPreflightRequest(BaseModel):
    """Preview eligibility without storing, sending or echoing a recipient."""

    model_config = ConfigDict(extra="forbid")
    draft_id: UUID
    draft_version: int = Field(ge=1)
    counterparty_id: UUID | None = None
    channel: Literal["EMAIL", "WHATSAPP_BUSINESS"]
    recipient: str = Field(min_length=3, max_length=254)


PreflightBlocker = Literal[
    "DRAFT_NOT_APPROVED",
    "DRAFT_VERSION_MISMATCH",
    "CHANNEL_NOT_CONFIGURED",
    "SEND_PERMISSION_UNAVAILABLE",
    "RECIPIENT_INVALID",
    "CRM_RECIPIENT_MISMATCH",
    "CONSENT_UNDOCUMENTED",
    "RECIPIENT_SUPPRESSED",
]


class CommunicationPreflightResponse(CommunicationsModel):
    draft_id: UUID
    channel: Literal["EMAIL", "WHATSAPP_BUSINESS"]
    sendable: Literal[False] = False
    external_sending_enabled: Literal[False] = False
    blockers: list[PreflightBlocker]
    recipient_echoed: Literal[False] = False


class RecordSuppressionRequest(BaseModel):
    """A block only; no opt-in claim, recipient address or free-text PII."""

    model_config = ConfigDict(extra="forbid")
    counterparty_id: UUID
    channel: Literal["EMAIL", "WHATSAPP_BUSINESS"]
    reason: Literal["CONTACT_REQUEST", "COMPLIANCE_REVIEW", "IMPORTED_BLOCK"]


class SuppressionResponse(CommunicationsModel):
    id: UUID
    counterparty_id: UUID
    channel: Literal["EMAIL", "WHATSAPP_BUSINESS"]
    reason: Literal["CONTACT_REQUEST", "COMPLIANCE_REVIEW", "IMPORTED_BLOCK"]
    recorded_by: UUID
    created_at: datetime
    effect: Literal["BLOCKED"] = "BLOCKED"
    grants_consent: Literal[False] = False


class SuppressionListResponse(CommunicationsModel):
    items: list[SuppressionResponse]
    truncated: bool = False
