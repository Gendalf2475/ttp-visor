from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.punishments import Punishment


class PunishmentsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(self, values: Mapping[str, Any]) -> int:
        stmt = insert(Punishment).values(**values)
        update_values = {
            key: getattr(stmt.excluded, key)
            for key in values
            if key not in {"event_key", "created_at"}
        }
        update_values["updated_at"] = func.now()
        stmt = (
            stmt.on_conflict_do_update(
                index_elements=[Punishment.event_key],
                set_=update_values,
            )
            .returning(Punishment.id)
        )
        return int(await self.session.scalar(stmt))

