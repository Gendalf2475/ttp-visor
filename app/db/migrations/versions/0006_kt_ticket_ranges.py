"""add KT ticket range fields

Revision ID: 0006_kt_ticket_ranges
Revises: 0005_punishments_is_valid
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0006_kt_ticket_ranges"
down_revision: str | None = "0005_punishments_is_valid"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "kt_checks",
        sa.Column("tickets_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column("kt_checks", sa.Column("ticket_numbers", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("kt_checks", sa.Column("raw_range_text", sa.Text(), nullable=True))
    op.execute("update kt_checks set tickets_count = 1 where tickets_count is null")


def downgrade() -> None:
    op.drop_column("kt_checks", "raw_range_text")
    op.drop_column("kt_checks", "ticket_numbers")
    op.drop_column("kt_checks", "tickets_count")
