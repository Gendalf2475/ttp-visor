"""extra occupations and punishment details

Revision ID: 0003_extras_punishment_details
Revises: 0002_staff_sheet_sender
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0003_extras_punishment_details"
down_revision: str | None = "0002_staff_sheet_sender"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_extra_occupations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nickname", sa.String(length=255), nullable=False),
        sa.Column("direction", sa.String(length=255), nullable=False),
        sa.Column("occupation", sa.String(length=255), nullable=False),
        sa.Column("position", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_staff_extra_occupations"),
        sa.UniqueConstraint(
            "nickname",
            "direction",
            "occupation",
            "position",
            name="uq_staff_extra_occupations_identity",
        ),
    )
    op.create_index(
        "ix_staff_extra_occupations_nickname",
        "staff_extra_occupations",
        ["nickname"],
        unique=False,
    )
    op.create_index(
        "ix_staff_extra_occupations_is_active",
        "staff_extra_occupations",
        ["is_active"],
        unique=False,
    )

    op.add_column("punishments", sa.Column("punishment_type", sa.String(length=32), nullable=True))
    op.add_column(
        "punishments",
        sa.Column("rule_missing", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index("ix_punishments_punishment_type", "punishments", ["punishment_type"], unique=False)
    op.create_index(
        "ix_punishments_staff_date_type",
        "punishments",
        ["staff_id", "punished_at", "punishment_type"],
        unique=False,
    )
    op.create_index(
        "ix_support_tickets_staff_date",
        "support_tickets",
        ["staff_id", "closed_at"],
        unique=False,
    )
    op.create_index(
        "ix_kt_checks_staff_date",
        "kt_checks",
        ["staff_id", "checked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_kt_checks_staff_date", table_name="kt_checks")
    op.drop_index("ix_support_tickets_staff_date", table_name="support_tickets")
    op.drop_index("ix_punishments_staff_date_type", table_name="punishments")
    op.drop_index("ix_punishments_punishment_type", table_name="punishments")
    op.drop_column("punishments", "rule_missing")
    op.drop_column("punishments", "punishment_type")

    op.drop_index("ix_staff_extra_occupations_is_active", table_name="staff_extra_occupations")
    op.drop_index("ix_staff_extra_occupations_nickname", table_name="staff_extra_occupations")
    op.drop_table("staff_extra_occupations")

