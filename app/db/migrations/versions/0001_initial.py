"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_key", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("role", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_staff_members"),
        sa.UniqueConstraint("external_key", name="uq_staff_members_external_key"),
        sa.UniqueConstraint("telegram_id", name="uq_staff_members_telegram_id"),
    )
    op.create_index("ix_staff_members_is_active", "staff_members", ["is_active"], unique=False)
    op.create_index("ix_staff_members_username", "staff_members", ["username"], unique=False)

    op.create_table(
        "moderator_bindings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("staff_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("alias_normalized", sa.String(length=255), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_username", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_members.id"], name="fk_moderator_bindings_staff_id_staff_members", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_moderator_bindings"),
        sa.UniqueConstraint("alias_normalized", name="uq_moderator_bindings_alias_normalized"),
    )
    op.create_index("ix_moderator_bindings_staff_id", "moderator_bindings", ["staff_id"], unique=False)
    op.create_index("ix_moderator_bindings_telegram_username", "moderator_bindings", ["telegram_username"], unique=False)

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(length=255), nullable=False),
        sa.Column("ticket_id", sa.String(length=128), nullable=True),
        sa.Column("staff_id", sa.Integer(), nullable=True),
        sa.Column("moderator_alias", sa.String(length=255), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_members.id"], name="fk_support_tickets_staff_id_staff_members", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_support_tickets"),
        sa.UniqueConstraint("event_key", name="uq_support_tickets_event_key"),
    )
    op.create_index("ix_support_tickets_closed_at", "support_tickets", ["closed_at"], unique=False)
    op.create_index("ix_support_tickets_staff_id", "support_tickets", ["staff_id"], unique=False)
    op.create_index("ix_support_tickets_source", "support_tickets", ["chat_id", "message_id"], unique=False)

    op.create_table(
        "kt_checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(length=255), nullable=False),
        sa.Column("ticket_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("staff_id", sa.Integer(), nullable=True),
        sa.Column("moderator_alias", sa.String(length=255), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_members.id"], name="fk_kt_checks_staff_id_staff_members", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_kt_checks"),
        sa.UniqueConstraint("event_key", name="uq_kt_checks_event_key"),
    )
    op.create_index("ix_kt_checks_checked_at", "kt_checks", ["checked_at"], unique=False)
    op.create_index("ix_kt_checks_staff_id", "kt_checks", ["staff_id"], unique=False)
    op.create_index("ix_kt_checks_source", "kt_checks", ["chat_id", "message_id"], unique=False)

    op.create_table(
        "punishments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(length=255), nullable=False),
        sa.Column("punishment_id", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("staff_id", sa.Integer(), nullable=True),
        sa.Column("moderator_alias", sa.String(length=255), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("punished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_members.id"], name="fk_punishments_staff_id_staff_members", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_punishments"),
        sa.UniqueConstraint("event_key", name="uq_punishments_event_key"),
    )
    op.create_index("ix_punishments_action", "punishments", ["action"], unique=False)
    op.create_index("ix_punishments_punished_at", "punishments", ["punished_at"], unique=False)
    op.create_index("ix_punishments_source", "punishments", ["chat_id", "message_id"], unique=False)
    op.create_index("ix_punishments_staff_id", "punishments", ["staff_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_punishments_staff_id", table_name="punishments")
    op.drop_index("ix_punishments_source", table_name="punishments")
    op.drop_index("ix_punishments_punished_at", table_name="punishments")
    op.drop_index("ix_punishments_action", table_name="punishments")
    op.drop_table("punishments")

    op.drop_index("ix_kt_checks_source", table_name="kt_checks")
    op.drop_index("ix_kt_checks_staff_id", table_name="kt_checks")
    op.drop_index("ix_kt_checks_checked_at", table_name="kt_checks")
    op.drop_table("kt_checks")

    op.drop_index("ix_support_tickets_source", table_name="support_tickets")
    op.drop_index("ix_support_tickets_staff_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_closed_at", table_name="support_tickets")
    op.drop_table("support_tickets")

    op.drop_index("ix_moderator_bindings_telegram_username", table_name="moderator_bindings")
    op.drop_index("ix_moderator_bindings_staff_id", table_name="moderator_bindings")
    op.drop_table("moderator_bindings")

    op.drop_index("ix_staff_members_username", table_name="staff_members")
    op.drop_index("ix_staff_members_is_active", table_name="staff_members")
    op.drop_table("staff_members")

