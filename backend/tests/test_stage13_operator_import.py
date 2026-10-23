"""Stage 13B controlled operator imports: read-only default and atomic writes."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.engine import Database
from app.db.models import Counterparty, Product
from app.services.import_preview import preview_import
from scripts.apply_import import ImportCommitBlocked, apply_if_authorized, commit_preview
from tests.conftest import IdentityWorld


def products_csv() -> bytes:
    return (
        b"sku,name,unit,currency,unit_price\n"
        b"HELLO-1,Warehouse tape,unit,TRY,45.5000\n"
        b"HELLO-2,Logistics box,unit,USD,10.0000\n"
    )


@pytest.mark.integration
def test_trader_can_atomically_import_products_into_only_active_company(
    migration_database: Database, identity_world: IdentityWorld
) -> None:
    csv = products_csv()
    preview = preview_import("batch.csv", csv, kind="products")
    written = commit_preview(
        migration_database,
        preview=preview,
        company_name="Meridian Commodities",
        actor_email=identity_world.email_b,
        source_sha256="a" * 64,
    )
    assert written == 2
    with migration_database.transaction() as session:
        records = session.scalars(
            select(Product).where(Product.company_id == identity_world.company_b)
        ).all()
        assert {record.sku for record in records} == {"HELLO-1", "HELLO-2"}
        other_count = session.scalars(
            select(Product).where(Product.company_id == identity_world.company_a)
        ).all()
        assert not other_count
        assert all(record.currency in {"TRY", "USD"} for record in records)


@pytest.mark.integration
def test_admin_without_trade_write_cannot_import(
    migration_database: Database, identity_world: IdentityWorld
) -> None:
    preview = preview_import("batch.csv", products_csv(), kind="products")
    with pytest.raises(ImportCommitBlocked, match="lacks trade.write"):
        commit_preview(
            migration_database,
            preview=preview,
            company_name="TOUCHE Trading",
            actor_email=identity_world.email_a,
            source_sha256="b" * 64,
        )


@pytest.mark.integration
def test_duplicate_batch_rolls_back_and_never_updates_existing_price(
    migration_database: Database, identity_world: IdentityWorld
) -> None:
    preview = preview_import("batch.csv", products_csv(), kind="products")
    params = {
        "preview": preview,
        "company_name": "Meridian Commodities",
        "actor_email": identity_world.email_b,
        "source_sha256": "c" * 64,
    }
    assert commit_preview(migration_database, **params) == 2
    with pytest.raises(ImportCommitBlocked, match="already exists"):
        commit_preview(migration_database, **params)
    with migration_database.transaction() as session:
        records = session.scalars(
            select(Product).where(Product.company_id == identity_world.company_b)
        ).all()
    assert len(records) == 2
    assert str(next(x for x in records if x.sku == "HELLO-1").unit_price) == "45.5000"


@pytest.mark.integration
def test_trader_can_atomically_import_counterparties(
    migration_database: Database, identity_world: IdentityWorld
) -> None:
    preview = preview_import(
        "firms.csv", b"name,type,country\nABC Trading,supplier,TR\nXYZ LLC,buyer,US\n",
        kind="counterparties",
    )
    assert commit_preview(
        migration_database,
        preview=preview,
        company_name="Meridian Commodities",
        actor_email=identity_world.email_b,
        source_sha256="d" * 64,
    ) == 2
    with migration_database.transaction() as session:
        firms = session.scalars(
            select(Counterparty).where(Counterparty.company_id == identity_world.company_b)
        ).all()
    assert {f.name for f in firms} == {"ABC Trading", "XYZ LLC"}


def test_invalid_file_never_attempts_database_access(tmp_path: Path) -> None:
    source = tmp_path / "items.csv"
    source.write_bytes(products_csv())
    settings = Settings(environment="test")

    for confirm, restored in [
        ("", date.today()),
        ("IMPORT 000000000000", date.today()),
        ("", date.today() - timedelta(days=8)),
    ]:
        with pytest.raises(ImportCommitBlocked):
            apply_if_authorized(
                settings=settings,
                filename=source,
                kind="products",
                company_name="TOUCHE Trading",
                actor_email="trader@example.com",
                confirmed_phrase=confirm,
                restore_tested=restored,
            )


def test_nonlocal_bulk_import_blocked_before_database_access(tmp_path: Path) -> None:
    source = tmp_path / "items.csv"
    source.write_bytes(products_csv())
    settings = Settings(
        environment="production",
        session_cookie_secure=True,
        cors_allowed_origins=["https://commerce.example.com"],
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
    )
    with pytest.raises(ImportCommitBlocked, match="disabled outside"):
        apply_if_authorized(
            settings=settings,
            filename=source,
            kind="products",
            company_name="TOUCHE Trading",
            actor_email="trader@example.com",
            confirmed_phrase="anything",
            restore_tested=date.today(),
        )
