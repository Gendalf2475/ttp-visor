"""staff sheet fields and sender metadata

Revision ID: 0002_staff_sheet_sender
Revises: 0001_initial
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0002_staff_sheet_sender"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("staff_members", sa.Column("nickname", sa.String(length=255), nullable=True))
    op.add_column("staff_members", sa.Column("rank", sa.String(length=128), nullable=True))
    op.add_column("staff_members", sa.Column("mentor", sa.String(length=255), nullable=True))
    op.add_column("staff_members", sa.Column("real_name", sa.String(length=255), nullable=True))
    op.add_column("staff_members", sa.Column("telegram_raw", sa.String(length=255), nullable=True))
    op.execute("update staff_members set nickname = full_name where nickname is null")
    op.create_index("ix_staff_members_nickname", "staff_members", ["nickname"], unique=False)

    op.create_table(
        "staff_active_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("staff_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["staff_members.id"],
            name="fk_staff_active_periods_staff_id_staff_members",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_staff_active_periods"),
    )
    op.create_index("ix_staff_active_periods_staff_id", "staff_active_periods", ["staff_id"], unique=False)
    op.create_index(
        "ix_staff_active_periods_open",
        "staff_active_periods",
        ["staff_id", "ended_at"],
        unique=False,
    )
    op.execute(
        """
        insert into staff_active_periods (staff_id, started_at)
        select id, coalesce(synced_at, created_at, now())
        from staff_members
        where is_active = true
        """
    )

    for table_name in ("support_tickets", "kt_checks", "punishments"):
        op.add_column(table_name, sa.Column("sender_user_id", sa.BigInteger(), nullable=True))
        op.add_column(table_name, sa.Column("sender_username", sa.String(length=64), nullable=True))
        op.add_column(
            table_name,
            sa.Column("sender_is_bot", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        )
        op.create_index(f"ix_{table_name}_sender_user_id", table_name, ["sender_user_id"], unique=False)


def downgrade() -> None:
    for table_name in ("punishments", "kt_checks", "support_tickets"):
        op.drop_index(f"ix_{table_name}_sender_user_id", table_name=table_name)
        op.drop_column(table_name, "sender_is_bot")
        op.drop_column(table_name, "sender_username")
        op.drop_column(table_name, "sender_user_id")

    op.drop_index("ix_staff_active_periods_open", table_name="staff_active_periods")
    op.drop_index("ix_staff_active_periods_staff_id", table_name="staff_active_periods")
    op.drop_table("staff_active_periods")

    op.drop_index("ix_staff_members_nickname", table_name="staff_members")
    op.drop_column("staff_members", "telegram_raw")
    op.drop_column("staff_members", "real_name")
    op.drop_column("staff_members", "mentor")
    op.drop_column("staff_members", "rank")
    op.drop_column("staff_members", "nickname")

