"""Stage 16B: separate reserved AI budget from actual incurred cost.

Revision ID: 0012_ai_monthly_reservation
Revises: 0011_communication_suppression
Do not invent an actual charge: reserves never modify cost_usd.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_ai_monthly_reservation"
down_revision: str | None = "0011_communication_suppression"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_run",
        sa.Column(
            "reserved_cost_usd",
            sa.Numeric(12, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="touche",
    )
    op.create_check_constraint(
        "ck_ai_run_reserved_cost",
        "ai_run",
        "reserved_cost_usd >= 0",
        schema="touche",
    )


def downgrade() -> None:
    connection = op.get_bind()
    pending = connection.execute(
        sa.text(
            "SELECT count(*) FROM touche.ai_run WHERE reserved_cost_usd > 0"
        )
    ).scalar_one()
    if pending:
        raise RuntimeError("Cannot discard outstanding AI budget reservations")
    op.drop_constraint(
        "ck_ai_run_reserved_cost", "ai_run", schema="touche", type_="check"
    )
    op.drop_column("ai_run", "reserved_cost_usd", schema="touche")
