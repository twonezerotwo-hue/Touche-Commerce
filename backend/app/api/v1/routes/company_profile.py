"""Company profile endpoints: the legal details printed on trade documents.

Any member of the company may read the profile; changing it needs ``settings.manage``
(the administrator). The first save creates it; later saves send ``If-Match`` with the
current ETag, so two administrators cannot silently overwrite each other.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import get_database
from app.api.security import active_company_id, require_company_permission
from app.api.v1.etag import etag_for, parse_if_match
from app.api.v1.schemas.company_profile import CompanyProfileRequest, CompanyProfileResponse
from app.api.v1.schemas.errors import ErrorEnvelope
from app.api.v1.trade_helpers import write_meta
from app.db.engine import Database
from app.security.permissions import Permission
from app.services.auth import SessionContext
from app.services.company_profile import (
    CompanyProfileService,
    ProfileRecord,
    empty_values,
)

router = APIRouter(prefix="/company", tags=["company"])

Db = Annotated[Database, Depends(get_database)]
ViewContext = Annotated[
    SessionContext, Depends(require_company_permission(Permission.COMPANY_VIEW))
]
ManageContext = Annotated[
    SessionContext, Depends(require_company_permission(Permission.SETTINGS_MANAGE))
]


def _respond(company_id: object, record: ProfileRecord | None) -> CompanyProfileResponse:
    values = dict(record.values) if record is not None else empty_values()
    missing = (
        record.missing_essentials if record is not None else ("legal_name", "tax_number", "address")
    )
    return CompanyProfileResponse.model_validate(
        {
            "company_id": company_id,
            "exists": record is not None,
            **values,
            "missing_essentials": list(missing),
            "version": record.version if record is not None else 0,
            "updated_at": record.updated_at if record is not None else None,
        }
    )


@router.get(
    "/profile",
    response_model=CompanyProfileResponse,
    summary="Legal details printed on this company's documents",
    responses={403: {"model": ErrorEnvelope, "description": "No active company."}},
)
def get_profile(response: Response, context: ViewContext, database: Db) -> CompanyProfileResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    company_id = active_company_id(context)
    record = CompanyProfileService(database).get(company_id)
    response.headers["ETag"] = etag_for(record.version if record else 0)
    return _respond(company_id, record)


@router.put(
    "/profile",
    response_model=CompanyProfileResponse,
    summary="Create or replace the company profile",
    description=(
        "The first save sends no If-Match. Later saves must send the current ETag; a stale "
        "value is 409 VERSION_CONFLICT and a missing one is 428. Blank fields are cleared."
    ),
    responses={
        403: {"model": ErrorEnvelope, "description": "Missing settings.manage."},
        409: {"model": ErrorEnvelope, "description": "Stale version."},
        422: {"model": ErrorEnvelope, "description": "Invalid email, IBAN or BIC."},
        428: {"model": ErrorEnvelope, "description": "If-Match is required."},
    },
)
def put_profile(
    payload: CompanyProfileRequest,
    request: Request,
    response: Response,
    context: ManageContext,
    database: Db,
) -> CompanyProfileResponse:
    response.headers["Cache-Control"] = "no-store"
    expected = parse_if_match(request.headers.get("If-Match"), required=False)
    record = CompanyProfileService(database).save(
        meta=write_meta(context, request),
        expected_version=expected,
        values=payload.model_dump(),
    )
    response.headers["ETag"] = etag_for(record.version)
    return _respond(active_company_id(context), record)
