"""Allow a dispatch timestamp to survive after a purchase order is sent.

``ck_purchase_order_dispatched_at`` required ``status = 'RECORDED_SENT'`` to be
exactly equivalent to ``dispatched_at IS NOT NULL``. That made the very next
legitimate transition (``SUPPLIER_CONFIRMED``) fail, because the recorded
dispatch time must stay on the record. The corrected rule only forbids a
dispatch time *before* the order was sent.

Revision ID: 0007_purchase_order_dispatch
Revises: 0006_shipment_dispatch
Create Date: 2026-10-22
"""

from __future__ import annotations

from alembic import op

revision: str = "0007_purchase_order_dispatch"
down_revision: str | None = "0006_shipment_dispatch"
branch_labels: str | None = None
depends_on: str | None = None

_OLD = "(status = 'RECORDED_SENT') = (dispatched_at IS NOT NULL)"
_NEW = "status NOT IN ('DRAFT','APPROVED') OR dispatched_at IS NULL"


def upgrade() -> None:
    op.drop_constraint(
        "ck_purchase_order_dispatched_at",
        "purchase_order",
        schema="touche",
        type_="check",
    )
    op.create_check_constraint(
        "ck_purchase_order_dispatched_at",
        "purchase_order",
        _NEW,
        schema="touche",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_purchase_order_dispatched_at",
        "purchase_order",
        schema="touche",
        type_="check",
    )
    op.create_check_constraint(
        "ck_purchase_order_dispatched_at",
        "purchase_order",
        _OLD,
        schema="touche",
    )
