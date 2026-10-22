"""Drop the over-strict shipment dispatch ordering constraint.

A shipment can legitimately leave *before* its planned dispatch date, so
``actual_dispatch_at >= planned_dispatch_at`` rejected valid operational data
and surfaced as a 500 when dispatch was recorded. The planned date is a plan,
not a lower bound; arrival and delivery ordering constraints remain.

Revision ID: 0006_shipment_dispatch
Revises: 0005_orders
Create Date: 2026-10-22
"""

from __future__ import annotations

from alembic import op

revision: str = "0006_shipment_dispatch"
down_revision: str | None = "0005_orders"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_shipment_dispatch_order",
        "shipment",
        schema="touche",
        type_="check",
    )


def downgrade() -> None:
    op.create_check_constraint(
        "ck_shipment_dispatch_order",
        "shipment",
        "actual_dispatch_at IS NULL OR planned_dispatch_at IS NULL "
        "OR actual_dispatch_at >= planned_dispatch_at",
        schema="touche",
    )
