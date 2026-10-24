# ruff: noqa: RUF001, F811  (fixtures are imported by name and then used as parameters)
"""Stage 13 generated documents and company profile (live PostgreSQL, real roles).

Promises under test: every document renders in both languages and all four formats; a
Commerce invoice is always a draft and says it is not a tax invoice; a record in the wrong
state produces no customer document; only roles allowed to trade (or to review finance) can
generate; another company's record is invisible; the audit log records what was generated but
never the content; the profile is administrator-only, versioned and validated.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select

from app.db.engine import Database
from app.db.models import AuditAction, AuditRecord
from app.security.permissions import Role
from app.services import admin
from tests.conftest import IdentityWorld
from tests.support import csrf_headers
from tests.test_operations_api import (  # noqa: F401 - fixtures are used by name
    OrderWorld,
    approver,
    client_factory,
    deliver,
    document_storage_root,
    identity_app,
    order_transition,
    plan_shipment,
    sign_in,
    trader,
    won,
    world,
)

pytestmark = pytest.mark.integration

API = "/api/v1"
DOCS = f"{API}/generated-documents"
PROFILE = f"{API}/company/profile"


def pdf_text(response: Any) -> str:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(response.content)).pages)


def fetch(
    client: TestClient,
    kind: str,
    entity_id: Any = None,
    *,
    fmt: str = "pdf",
    locale: str = "en",
) -> Any:
    params: dict[str, str] = {"format": fmt, "locale": locale}
    if entity_id is not None:
        params["entity_id"] = str(entity_id)
    return client.get(f"{DOCS}/{kind}", params=params)


class TestDocumentGeneration:
    def test_an_approved_quotation_renders_in_every_format_and_language(
        self, world: OrderWorld
    ) -> None:
        quote = world.quote
        text = pdf_text(fetch(world.client, "sales_quotation", quote["id"], locale="tr"))
        assert "Satış Teklifi" in text
        assert quote["quote_number"] in text
        assert "Buyer Ltd" in text
        assert "TASLAK" not in text  # approved: not a draft
        english = pdf_text(fetch(world.client, "sales_quotation", quote["id"], locale="en"))
        assert "Sales Quotation" in english and "DRAFT" not in english

        expected = {
            "docx": "wordprocessingml",
            "xlsx": "spreadsheetml",
            "csv": "text/csv",
        }
        for fmt, marker in expected.items():
            response = fetch(world.client, "sales_quotation", quote["id"], fmt=fmt)
            assert response.status_code == 200, response.text
            assert marker in response.headers["content-type"]
            assert response.headers["content-disposition"].startswith("attachment;")
            assert response.headers["cache-control"] == "no-store"
        assert response.content.startswith(b"\xef\xbb\xbf")  # the CSV

    def test_a_commerce_invoice_is_always_a_draft_and_never_a_tax_invoice(
        self, world: OrderWorld
    ) -> None:
        order, _ = won(world)
        invoice = pdf_text(fetch(world.client, "commercial_invoice", order["id"], locale="en"))
        assert "DRAFT" in invoice
        assert "Not a tax invoice" in invoice
        assert f"CI-DRAFT-{order['order_number']}" in invoice
        turkish = pdf_text(fetch(world.client, "commercial_invoice", order["id"], locale="tr"))
        assert "TASLAK" in turkish
        assert "Mali değeri olan fatura değildir" in turkish

        proforma = pdf_text(fetch(world.client, "proforma_invoice", order["id"]))
        assert "Proforma Invoice" in proforma and "not a tax invoice" in proforma
        assert "DRAFT" not in proforma
        confirmation = pdf_text(fetch(world.client, "order_confirmation", order["id"]))
        assert "Order Confirmation" in confirmation and order["order_number"] in confirmation

    def test_purchase_order_packing_list_and_register(self, world: OrderWorld) -> None:
        from tests.test_operations_api import create_purchase_order

        order, _ = won(world)
        purchase = create_purchase_order(world, order)
        assert purchase.status_code == 201, purchase.text
        draft_po = pdf_text(fetch(world.client, "purchase_order", purchase.json()["id"]))
        assert "Supplier One" in draft_po and "DRAFT" in draft_po

        shipment = plan_shipment(world, order)
        assert shipment.status_code == 201, shipment.text
        planned = pdf_text(fetch(world.client, "packing_list", shipment.json()["id"]))
        assert "Packing List" in planned and "DRAFT" in planned
        assert "Jebel Ali" in planned and "Rotterdam" in planned
        assert "Maersk" in planned

        delivered = deliver(world, dict(shipment.json()))
        final = pdf_text(fetch(world.client, "packing_list", delivered["id"]))
        assert "DRAFT" not in final

        register = fetch(world.client, "shipment_register", fmt="csv")
        assert register.status_code == 200, register.text
        assert delivered["shipment_number"] in register.content.decode("utf-8-sig")

    def test_a_cancelled_order_produces_no_customer_document(self, world: OrderWorld) -> None:
        order, _ = won(world)
        cancelled = order_transition(world, order, "CANCELLED", reason="Customer withdrew")
        assert cancelled.status_code == 200, cancelled.text
        for kind in ("order_confirmation", "proforma_invoice", "commercial_invoice"):
            response = fetch(world.client, kind, order["id"])
            assert response.status_code == 409, (kind, response.text)

    def test_bad_requests(self, world: OrderWorld) -> None:
        assert fetch(world.client, "sales_quotation").status_code == 400  # no entity id
        assert fetch(world.client, "no_such_kind", world.quote["id"]).status_code == 422
        assert (
            fetch(world.client, "sales_quotation", world.quote["id"], fmt="exe").status_code == 422
        )
        ghost = "00000000-0000-4000-8000-000000000000"
        assert fetch(world.client, "sales_quotation", ghost).status_code == 404

    def test_generation_is_audited_without_the_content(
        self, world: OrderWorld, migration_database: Database
    ) -> None:
        response = fetch(world.client, "sales_quotation", world.quote["id"], locale="tr")
        assert response.status_code == 200
        with migration_database.session() as session:
            rows = (
                session.execute(
                    select(AuditRecord).where(
                        AuditRecord.action == AuditAction.DOCUMENT_GENERATED.value
                    )
                )
                .scalars()
                .all()
            )
        assert rows, "the generation must leave an audit row"
        details = rows[-1].details
        assert details["kind"] == "sales_quotation"
        assert details["format"] == "pdf" and details["locale"] == "tr"
        flat = str(details)
        assert "Buyer Ltd" not in flat and "Supplier One" not in flat


class TestDocumentAccess:
    def test_roles_that_neither_trade_nor_review_finance_are_refused(
        self,
        world: OrderWorld,
        identity_world: IdentityWorld,
        migration_database: Database,
        client_factory: Callable[..., TestClient],
    ) -> None:
        with migration_database.transaction() as session:
            admin.grant_membership(
                session,
                user_id=identity_world.user_a,
                company_id=identity_world.company_b,
                role=Role.VIEWER,
            )
        viewer, _ = sign_in(
            client_factory, email=identity_world.email_a, company_id=identity_world.company_b
        )
        assert fetch(viewer, "sales_quotation", world.quote["id"]).status_code == 403

    def test_finance_reviewers_may_generate(self, world: OrderWorld) -> None:
        response = fetch(world.approver_client, "sales_quotation", world.quote["id"])
        assert response.status_code == 200, response.text

    def test_anonymous_callers_are_refused(
        self, world: OrderWorld, client_factory: Callable[..., TestClient]
    ) -> None:
        stranger = client_factory()
        assert fetch(stranger, "sales_quotation", world.quote["id"]).status_code == 401

    def test_another_company_cannot_see_the_record(
        self,
        world: OrderWorld,
        identity_world: IdentityWorld,
        migration_database: Database,
        client_factory: Callable[..., TestClient],
    ) -> None:
        with migration_database.transaction() as session:
            admin.grant_membership(
                session,
                user_id=identity_world.user_b,
                company_id=identity_world.company_a,
                role=Role.TRADER,
            )
        outsider, _ = sign_in(
            client_factory, email=identity_world.email_b, company_id=identity_world.company_a
        )
        assert fetch(outsider, "sales_quotation", world.quote["id"]).status_code == 404


@pytest.fixture()
def company_admin(
    identity_world: IdentityWorld,
    migration_database: Database,
    client_factory: Callable[..., TestClient],
) -> tuple[TestClient, str]:
    """An administrator of company B (Bilal keeps trading rights through another account)."""
    with migration_database.transaction() as session:
        admin.grant_membership(
            session,
            user_id=identity_world.user_a,
            company_id=identity_world.company_b,
            role=Role.ADMIN,
        )
    return sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_b
    )


class TestCompanyProfile:
    FIELDS: ClassVar[dict[str, str]] = {
        "legal_name": "Touche Acceptance Ticaret A.Ş.",
        "tax_office": "Şişli",
        "tax_number": "1234567890",
        "address": "Örnek Mah. 1. Sk. No:1",
        "city": "İstanbul",
        "iban": "GB82 WEST 1234 5698 7654 32",
        "swift_bic": "westgb2l",
        "email": "Muhasebe@Example.com",
    }

    def test_it_starts_empty_and_lists_what_documents_will_miss(
        self, trader: tuple[TestClient, str]
    ) -> None:
        body = trader[0].get(PROFILE).json()
        assert body["exists"] is False and body["version"] == 0
        assert body["missing_essentials"] == ["legal_name", "tax_number", "address"]

    def test_only_the_administrator_can_write_and_saves_are_versioned(
        self, company_admin: tuple[TestClient, str], trader: tuple[TestClient, str]
    ) -> None:
        admin_client, csrf = company_admin
        trader_client, trader_csrf = trader
        assert (
            trader_client.put(
                PROFILE, json=self.FIELDS, headers=csrf_headers(trader_csrf)
            ).status_code
            == 403
        )

        created = admin_client.put(PROFILE, json=self.FIELDS, headers=csrf_headers(csrf))
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["version"] == 1 and body["exists"] is True
        assert body["iban"] == "GB82WEST12345698765432"  # normalised, checksum verified
        assert body["swift_bic"] == "WESTGB2L"
        assert body["email"] == "Muhasebe@example.com"
        assert body["missing_essentials"] == []

        no_header = admin_client.put(PROFILE, json=self.FIELDS, headers=csrf_headers(csrf))
        assert no_header.status_code == 428
        stale = admin_client.put(
            PROFILE, json=self.FIELDS, headers={**csrf_headers(csrf), "If-Match": '"v9"'}
        )
        assert stale.status_code == 409
        updated = admin_client.put(
            PROFILE,
            json={**self.FIELDS, "city": "Ankara"},
            headers={**csrf_headers(csrf), "If-Match": created.headers["etag"]},
        )
        assert updated.status_code == 200 and updated.json()["version"] == 2

        # Members read it; a trader sees the saved legal name.
        assert trader_client.get(PROFILE).json()["legal_name"] == self.FIELDS["legal_name"]

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("iban", "GB82 WEST 1234 5698 7654 33"),  # wrong checksum
            ("swift_bic", "NOPE"),
            ("email", "not-an-email"),
            ("website", "javascript:alert(1)"),
        ],
    )
    def test_invalid_details_are_rejected(
        self, company_admin: tuple[TestClient, str], field: str, value: str
    ) -> None:
        client, csrf = company_admin
        response = client.put(PROFILE, json={field: value}, headers=csrf_headers(csrf))
        assert response.status_code == 422, response.text

    def test_the_audit_log_names_changed_fields_but_never_their_values(
        self, company_admin: tuple[TestClient, str], migration_database: Database
    ) -> None:
        client, csrf = company_admin
        assert client.put(PROFILE, json=self.FIELDS, headers=csrf_headers(csrf)).status_code == 200
        with migration_database.session() as session:
            rows = (
                session.execute(
                    select(AuditRecord).where(
                        AuditRecord.action == AuditAction.COMPANY_PROFILE_UPDATED.value
                    )
                )
                .scalars()
                .all()
            )
        details = rows[-1].details
        assert "tax_number" in details["changed_fields"] and "iban" in details["changed_fields"]
        assert "1234567890" not in str(details) and "GB82" not in str(details)

    def test_a_write_from_a_foreign_origin_is_refused_and_changes_nothing(
        self, company_admin: tuple[TestClient, str], trader: tuple[TestClient, str]
    ) -> None:
        """Cross-site requests are stopped by the Origin guard that covers every PUT."""
        client, csrf = company_admin
        forged = client.put(
            PROFILE,
            json={"legal_name": "Injected Ltd"},
            headers={**csrf_headers(csrf), "Origin": "https://evil.example"},
        )
        assert forged.status_code == 403, forged.text
        assert trader[0].get(PROFILE).json()["legal_name"] is None

    def test_documents_use_the_profile_and_warn_when_it_is_missing(
        self, world: OrderWorld, company_admin: tuple[TestClient, str]
    ) -> None:
        before = pdf_text(fetch(world.client, "sales_quotation", world.quote["id"]))
        assert "Seller tax number is not configured." in before

        admin_client, csrf = company_admin
        saved = admin_client.put(PROFILE, json=self.FIELDS, headers=csrf_headers(csrf))
        assert saved.status_code == 200, saved.text
        after = pdf_text(fetch(world.client, "sales_quotation", world.quote["id"]))
        assert "Touche Acceptance Ticaret A.Ş." in after
        assert "1234567890" in after
        assert "IBAN: GB82WEST12345698765432" in after
        assert "not configured" not in after
