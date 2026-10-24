# ruff: noqa: RUF001  (Turkish test data is intentional)
"""Stage 13C CSV/XLSX import wizard: inspect, preview and commit over real sessions.

Runs against the isolated PostgreSQL test database with the runtime role, so row level
security, ``trade.write`` and the audit trail are the real ones.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook  # type: ignore[import-untyped]
from sqlalchemy import func, select

from app.db.engine import Database
from app.db.models import AuditAction, AuditRecord, ImportBatch, Product
from app.services.import_service import sha256_of
from tests.conftest import IdentityWorld
from tests.support import csrf_headers
from tests.test_finance_api import sign_in

pytestmark = pytest.mark.integration

API = "/api/v1/imports"

PRODUCTS_CSV = (
    b"sku,name,unit,currency,unit_price\n"
    b"IMP-001,Hazelnut kernel,kg,USD,3.2500\n"
    b"IMP-002,Almond kernel,kg,EUR,4.1000\n"
    b"IMP-003,Dried apricot,kg,TRY,95.0000\n"
)

TURKISH_CSV = (
    "stok_kodu,ürün_adı,birim,para_birimi,birim_fiyat\nTR-001,Fındık içi,kg,TRY,150.5\n"
).encode()


@pytest.fixture()
def trader(
    identity_world: IdentityWorld, client_factory: Callable[..., TestClient]
) -> tuple[TestClient, str]:
    return sign_in(client_factory, email=identity_world.email_b)


@pytest.fixture()
def viewer(
    identity_world: IdentityWorld, client_factory: Callable[..., TestClient]
) -> tuple[TestClient, str]:
    return sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_b
    )


def upload(
    session: tuple[TestClient, str],
    path: str,
    data: bytes,
    *,
    filename: str = "katalog.csv",
    form: dict[str, Any] | None = None,
) -> Any:
    client, csrf = session
    fields: dict[str, Any] = {"kind": "products", **(form or {})}
    return client.post(
        f"{API}/{path}",
        data=fields,
        files={"file": (filename, data, "application/octet-stream")},
        headers=csrf_headers(csrf),
    )


def commit(
    session: tuple[TestClient, str],
    data: bytes,
    *,
    filename: str = "katalog.csv",
    form: dict[str, Any] | None = None,
    sha: str | None = None,
) -> Any:
    return upload(
        session,
        "commit",
        data,
        filename=filename,
        form={"expected_sha256": sha or sha256_of(data), **(form or {})},
    )


def xlsx(rows: list[list[Any]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def product_count(database: Database, company_id: UUID) -> int:
    with database.session() as session:
        return int(
            session.execute(
                select(func.count()).select_from(Product).where(Product.company_id == company_id)
            ).scalar_one()
        )


# --------------------------------------------------------------- inspect / preview
def test_inspect_maps_english_and_turkish_headings(trader: tuple[TestClient, str]) -> None:
    english = upload(trader, "inspect", PRODUCTS_CSV).json()
    assert [h["field"] for h in english["headers"]] == [
        "sku",
        "name",
        "unit",
        "currency",
        "unit_price",
    ]
    assert english["required"] == ["currency", "name", "sku", "unit", "unit_price"]
    turkish = upload(trader, "inspect", TURKISH_CSV, filename="tr.csv").json()
    assert [h["field"] for h in turkish["headers"]] == [
        "sku",
        "name",
        "unit",
        "currency",
        "unit_price",
    ]
    unknown = upload(trader, "inspect", b"sku,mystery\nA,B\n").json()
    assert unknown["headers"][1] == {"heading": "mystery", "field": None}


def test_preview_classifies_rows_and_writes_nothing(
    trader: tuple[TestClient, str], migration_database: Database, identity_world: IdentityWorld
) -> None:
    data = (
        b"sku,name,unit,currency,unit_price\n"
        b"P-1,Good,kg,USD,1.5000\n"
        b"P-2,Bad currency,kg,usd1,1.0000\n"
        b"P-1,Duplicate in file,kg,USD,2.0000\n"
    )
    before = product_count(migration_database, identity_world.company_b)
    body = upload(trader, "preview", data).json()
    assert body["total_rows"] == 3
    assert (body["new_rows"], body["invalid_rows"]) == (1, 2)
    statuses = {row["row"]: row["status"] for row in body["rows"]}
    assert statuses == {2: "NEW", 3: "INVALID", 4: "INVALID"}
    assert body["can_commit"] is False
    assert len(body["source_sha256"]) == 64
    assert product_count(migration_database, identity_world.company_b) == before


def test_preview_flags_records_that_already_exist_in_the_company(
    trader: tuple[TestClient, str],
) -> None:
    assert commit(trader, PRODUCTS_CSV).status_code == 201
    again = (
        b"sku,name,unit,currency,unit_price\n"
        b"imp-001,Renamed,kg,USD,9.0000\n"
        b"NEW-9,Fresh,kg,USD,1.0000\n"
    )
    body = upload(trader, "preview", again).json()
    by_row = {row["row"]: row for row in body["rows"]}
    assert by_row[2]["status"] == "EXISTS"  # keys match case-insensitively
    assert "will not be changed" in by_row[2]["errors"][0]
    assert by_row[3]["status"] == "NEW"
    assert (body["new_rows"], body["existing_rows"], body["can_commit"]) == (1, 1, True)


# ------------------------------------------------------------------------ commit
def test_commit_creates_rows_ledger_and_audit_in_one_transaction(
    trader: tuple[TestClient, str],
    migration_database: Database,
    identity_world: IdentityWorld,
) -> None:
    before = product_count(migration_database, identity_world.company_b)
    response = commit(trader, PRODUCTS_CSV)
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["total_rows"], body["created_rows"], body["skipped_rows"]) == (3, 3, 0)
    assert body["replayed"] is False
    assert product_count(migration_database, identity_world.company_b) == before + 3

    listed = trader[0].get("/api/v1/products", params={"search": "IMP-"}).json()
    assert {item["sku"] for item in listed["items"]} == {"IMP-001", "IMP-002", "IMP-003"}
    hazelnut = next(i for i in listed["items"] if i["sku"] == "IMP-001")
    assert (hazelnut["unit_price"], hazelnut["currency"]) == ("3.2500", "USD")

    with migration_database.session() as session:
        batch = session.scalars(select(ImportBatch)).one()
        audit = list(
            session.scalars(
                select(AuditRecord).where(AuditRecord.action == AuditAction.IMPORT_COMMITTED.value)
            )
        )
    assert batch.created_rows == 3 and batch.filename == "katalog.csv"
    assert len(audit) == 1 and audit[0].outcome == "success"
    flat = str(audit[0].details)
    assert "IMP-001" not in flat and "Hazelnut" not in flat and "3.25" not in flat
    assert audit[0].details["created_rows"] == 3


def test_the_same_file_is_idempotent(
    trader: tuple[TestClient, str], migration_database: Database, identity_world: IdentityWorld
) -> None:
    assert commit(trader, PRODUCTS_CSV).status_code == 201
    count = product_count(migration_database, identity_world.company_b)
    repeat = commit(trader, PRODUCTS_CSV)
    assert repeat.status_code == 200
    assert repeat.json()["replayed"] is True and repeat.json()["created_rows"] == 3
    assert product_count(migration_database, identity_world.company_b) == count
    assert upload(trader, "preview", PRODUCTS_CSV).json()["already_imported"] is True
    with migration_database.session() as session:
        assert session.scalar(select(func.count()).select_from(ImportBatch)) == 1


def test_a_file_that_changed_since_the_preview_is_refused(
    trader: tuple[TestClient, str], migration_database: Database, identity_world: IdentityWorld
) -> None:
    previewed = upload(trader, "preview", PRODUCTS_CSV).json()["source_sha256"]
    tampered = PRODUCTS_CSV.replace(b"3.2500", b"0.0100")
    before = product_count(migration_database, identity_world.company_b)
    response = commit(trader, tampered, sha=previewed)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    assert product_count(migration_database, identity_world.company_b) == before


def test_existing_records_block_the_commit_unless_skipped_and_are_never_updated(
    trader: tuple[TestClient, str],
) -> None:
    assert commit(trader, PRODUCTS_CSV).status_code == 201
    mixed = (
        b"sku,name,unit,currency,unit_price\n"
        b"IMP-001,Overwritten name,kg,USD,99.0000\n"
        b"IMP-777,Brand new,kg,USD,1.0000\n"
    )
    blocked = commit(trader, mixed)
    assert blocked.status_code == 409
    assert "already exist" in blocked.json()["error"]["message"]
    assert trader[0].get("/api/v1/products", params={"search": "IMP-777"}).json()["items"] == []

    allowed = commit(trader, mixed, form={"skip_existing": "true"})
    assert allowed.status_code == 201, allowed.text
    assert (allowed.json()["created_rows"], allowed.json()["skipped_rows"]) == (1, 1)
    items = trader[0].get("/api/v1/products", params={"search": "IMP-001"}).json()["items"]
    assert items[0]["name"] == "Hazelnut kernel" and items[0]["unit_price"] == "3.2500"


def test_invalid_rows_block_the_whole_import(
    trader: tuple[TestClient, str], migration_database: Database, identity_world: IdentityWorld
) -> None:
    bad = b"sku,name,unit,currency,unit_price\nOK-1,Fine,kg,USD,1.0000\nBAD-2,Broken,kg,USD,-5\n"
    before = product_count(migration_database, identity_world.company_b)
    response = commit(trader, bad)
    assert response.status_code == 400
    assert product_count(migration_database, identity_world.company_b) == before


def test_counterparties_and_turkish_columns_import(trader: tuple[TestClient, str]) -> None:
    firms = (
        "firma_adı,firma_türü,ülke,e_posta\n"
        "Anadolu Gıda,supplier,TR,satis@example.com\n"
        "Rotterdam Foods,buyer,NL,buy@example.com\n"
    ).encode()
    response = upload(
        trader,
        "commit",
        firms,
        filename="firmalar.csv",
        form={
            "kind": "counterparties",
            "expected_sha256": sha256_of(firms),
        },
    )
    assert response.status_code == 201, response.text
    listed = trader[0].get("/api/v1/counterparties", params={"search": "Anadolu"}).json()
    assert listed["items"][0]["name"] == "Anadolu Gıda"
    assert listed["items"][0]["type"] == "supplier"

    tr_products = commit(trader, TURKISH_CSV, filename="tr.csv")
    assert tr_products.status_code == 201, tr_products.text


def test_xlsx_import_and_unsafe_workbooks(trader: tuple[TestClient, str]) -> None:
    good = xlsx(
        [
            ["sku", "name", "unit", "currency", "unit_price"],
            ["X-1", "Sheet product", "kg", "EUR", "2.5"],
        ]
    )
    response = commit(trader, good, filename="katalog.xlsx")
    assert response.status_code == 201, response.text

    formula = xlsx(
        [
            ["sku", "name", "unit", "currency", "unit_price"],
            ["X-2", "Formula", "kg", "EUR", "=1+1"],
        ]
    )
    assert upload(trader, "preview", formula, filename="f.xlsx").status_code == 400
    assert upload(trader, "preview", b"MZ-not-a-workbook", filename="e.xlsx").status_code == 400
    assert upload(trader, "preview", b"a,b\n1,2\n", filename="macro.xlsm").status_code == 400
    assert upload(trader, "preview", b"x" * 2_000_001, filename="big.csv").status_code == 413
    assert upload(trader, "preview", b"", filename="empty.csv").status_code == 400


def test_column_mapping_lets_unknown_headings_be_assigned(trader: tuple[TestClient, str]) -> None:
    data = b"Kod,Ad,Birim,Kur,Fiyat\nM-1,Mapped,kg,USD,5.0000\n"
    assert upload(trader, "preview", data).status_code == 400
    mapping = '{"Kod":"sku","Ad":"name","Birim":"unit","Kur":"currency","Fiyat":"unit_price"}'
    ok = upload(trader, "preview", data, form={"mapping": mapping})
    assert ok.status_code == 200, ok.text
    assert ok.json()["rows"][0]["values"]["sku"] == "M-1"
    assert upload(trader, "preview", data, form={"mapping": "not json"}).status_code == 400
    assert upload(trader, "preview", data, form={"mapping": "[1,2]"}).status_code == 400


# ------------------------------------------------------------------ permissions
def test_a_viewer_cannot_inspect_preview_or_commit(
    viewer: tuple[TestClient, str], migration_database: Database, identity_world: IdentityWorld
) -> None:
    before = product_count(migration_database, identity_world.company_b)
    for path in ("inspect", "preview"):
        assert upload(viewer, path, PRODUCTS_CSV).status_code == 403
    assert commit(viewer, PRODUCTS_CSV).status_code == 403
    assert product_count(migration_database, identity_world.company_b) == before
    assert viewer[0].get(API).status_code == 200  # viewers may read the history


def test_unauthenticated_requests_are_refused(api_client: TestClient) -> None:
    response = api_client.post(
        f"{API}/preview",
        data={"kind": "products"},
        files={"file": ("a.csv", PRODUCTS_CSV, "text/csv")},
    )
    assert response.status_code == 401


def test_imports_never_cross_companies(
    trader: tuple[TestClient, str],
    identity_world: IdentityWorld,
    client_factory: Callable[..., TestClient],
) -> None:
    assert commit(trader, PRODUCTS_CSV).status_code == 201
    other = sign_in(
        client_factory, email=identity_world.email_a, company_id=identity_world.company_a
    )
    assert other[0].get(API).json() == {"items": []}
    assert other[0].get("/api/v1/products", params={"search": "IMP-"}).json()["items"] == []
    assert trader[0].get(API).json()["items"][0]["created_rows"] == 3
