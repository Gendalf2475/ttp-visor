from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.punishments import Punishment
from app.services.parser_punishments import (
    is_invalid_punishment_moderator_alias,
    normalize_punishment_moderator_alias,
)


@dataclass(slots=True)
class PunishmentNormalizationResult:
    scanned: int
    normalized: int
    invalidated: int


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

    async def normalize_moderator_aliases(self) -> PunishmentNormalizationResult:
        rows = list(await self.session.scalars(select(Punishment)))
        normalized_count = 0
        invalidated_count = 0

        for row in rows:
            normalized_alias = normalize_punishment_moderator_alias(row.moderator_alias)
            invalid = is_invalid_punishment_moderator_alias(normalized_alias)

            if row.moderator_alias != normalized_alias:
                row.moderator_alias = normalized_alias
                normalized_count += 1

            next_is_valid = not invalid
            if row.is_valid != next_is_valid:
                row.is_valid = next_is_valid
                if invalid:
                    invalidated_count += 1

        await self.session.flush()
        return PunishmentNormalizationResult(
            scanned=len(rows),
            normalized=normalized_count,
            invalidated=invalidated_count,
        )
