"""Request/response schemas for the company profile (document details)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator

_BIC = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")
_IBAN = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")

EssentialField = Literal["legal_name", "tax_number", "address"]


def iban_checksum_ok(iban: str) -> bool:
    """ISO 13616 mod-97 check on an already normalised IBAN."""
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


class CompanyProfileRequest(BaseModel):
    """Full replacement of the profile; omitted or blank fields are cleared."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    legal_name: str | None = Field(default=None, max_length=200)
    tax_office: str | None = Field(default=None, max_length=120)
    tax_number: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=400)
    city: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    website: str | None = Field(default=None, max_length=200)
    bank_name: str | None = Field(default=None, max_length=120)
    iban: str | None = Field(default=None, max_length=40)
    swift_bic: str | None = Field(default=None, max_length=11)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return validate_email(value, check_deliverability=False).normalized
        except EmailNotValidError as exc:
            raise ValueError("must be a valid email address") from exc

    @field_validator("iban")
    @classmethod
    def _iban(cls, value: str | None) -> str | None:
        if not value:
            return None
        compact = re.sub(r"\s+", "", value).upper()
        if not _IBAN.fullmatch(compact) or not iban_checksum_ok(compact):
            raise ValueError("must be a valid IBAN")
        return compact

    @field_validator("swift_bic")
    @classmethod
    def _bic(cls, value: str | None) -> str | None:
        if not value:
            return None
        compact = value.upper()
        if not _BIC.fullmatch(compact):
            raise ValueError("must be an 8 or 11 character SWIFT/BIC code")
        return compact

    @field_validator("website")
    @classmethod
    def _website(cls, value: str | None) -> str | None:
        if value and not value.lower().startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        return value or None


class CompanyProfileResponse(BaseModel):
    company_id: UUID
    exists: bool = Field(description="False until an administrator saves the profile.")
    legal_name: str | None
    tax_office: str | None
    tax_number: str | None
    address: str | None
    city: str | None
    postal_code: str | None
    phone: str | None
    email: str | None
    website: str | None
    bank_name: str | None
    iban: str | None
    swift_bic: str | None
    missing_essentials: list[EssentialField] = Field(
        description="Facts customers expect on a document that are still empty."
    )
    version: int = Field(description="0 when no profile exists; also sent as ETag.")
    updated_at: datetime | None
