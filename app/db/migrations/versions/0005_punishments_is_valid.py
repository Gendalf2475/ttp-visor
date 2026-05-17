"""add punishment validity flag

Revision ID: 0005_punishments_is_valid
Revises: 0004_staff_deactivated_at
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0005_punishments_is_valid"
down_revision: str | None = "0004_staff_deactivated_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "punishments",
        sa.Column("is_valid", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_index("ix_punishments_is_valid", "punishments", ["is_valid"], unique=False)
    op.execute(
        """
        update punishments
        set moderator_alias = nullif(
            btrim(split_part(replace(moderator_alias, E'\\r', E'\\n'), E'\\n', 1)),
            ''
        )
        where moderator_alias is not null
        """
    )
    op.execute(
        """
        update punishments
        set is_valid = false
        where moderator_alias is null
           or lower(btrim(moderator_alias, ' :')) in (
               'unknown',
               'нарушитель',
               'длительность',
               'причина',
               'дата',
               'модератор'
           )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_punishments_is_valid", table_name="punishments")
    op.drop_column("punishments", "is_valid")
