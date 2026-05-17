"""add event ignore filters

Revision ID: 0007_event_ignore_filters
Revises: 0006_kt_ticket_ranges
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0007_event_ignore_filters"
down_revision: str | None = "0006_kt_ticket_ranges"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EVENT_TABLES = ("punishments", "support_tickets", "kt_checks")


def upgrade() -> None:
    for table_name in EVENT_TABLES:
        op.add_column(
            table_name,
            sa.Column("is_ignored", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        )
        op.add_column(table_name, sa.Column("ignore_reason", sa.Text(), nullable=True))
        op.create_index(f"ix_{table_name}_is_ignored", table_name, ["is_ignored"], unique=False)
        op.execute(f"update {table_name} set is_ignored = false where is_ignored is null")


def downgrade() -> None:
    for table_name in reversed(EVENT_TABLES):
        op.drop_index(f"ix_{table_name}_is_ignored", table_name=table_name)
        op.drop_column(table_name, "ignore_reason")
        op.drop_column(table_name, "is_ignored")
