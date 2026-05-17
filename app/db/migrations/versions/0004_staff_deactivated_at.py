"""add staff deactivated timestamp

Revision ID: 0004_staff_deactivated_at
Revises: 0003_extras_punishment_details
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0004_staff_deactivated_at"
down_revision: str | None = "0003_extras_punishment_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("staff_members", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("staff_members", "deactivated_at")
