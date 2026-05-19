from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.punishments import Punishment
from app.services.parser_punishments import (
    PUNISHMENT_TYPES,
    action_from_punishment_type,
    classify_punishment_type,
    is_invalid_punishment_moderator_alias,
    normalize_punishment_text,
    normalize_punishment_moderator_alias,
)


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PunishmentNormalizationResult:
    scanned: int
    normalized: int
    invalidated: int
    types_fixed: int
    actions_fixed: int
    ban_fixed: int = 0
    mute_fixed: int = 0
    warn_fixed: int = 0
    unban_fixed: int = 0
    unmute_fixed: int = 0
    unwarn_fixed: int = 0

    @property
    def fixed_total(self) -> int:
        return self.normalized + self.invalidated + self.types_fixed + self.actions_fixed

    @property
    def type_counts(self) -> dict[str, int]:
        return {
            "ban": self.ban_fixed,
            "mute": self.mute_fixed,
            "warn": self.warn_fixed,
            "unban": self.unban_fixed,
            "unmute": self.unmute_fixed,
            "unwarn": self.unwarn_fixed,
        }


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
        punishment_id = int(await self.session.scalar(stmt))
        if not _stored_punishment_type(values.get("punishment_type")):
            logger.warning(
                "Punishment saved with empty or invalid punishment_type: "
                "id=%s event_key=%s chat_id=%s message_id=%s punishment_type=%r",
                punishment_id,
                values.get("event_key"),
                values.get("chat_id"),
                values.get("message_id"),
                values.get("punishment_type"),
            )
        return punishment_id

    async def normalize_moderator_aliases(self) -> PunishmentNormalizationResult:
        return await self.normalize_punishments()

    async def normalize_punishments(self) -> PunishmentNormalizationResult:
        rows = list(await self.session.scalars(select(Punishment)))
        normalized_count = 0
        invalidated_count = 0
        types_fixed_count = 0
        actions_fixed_count = 0
        type_counts = {punishment_type: 0 for punishment_type in PUNISHMENT_TYPES}

        for row in rows:
            normalized_alias = normalize_punishment_moderator_alias(row.moderator_alias)
            invalid = is_invalid_punishment_moderator_alias(normalized_alias)
            detected_type = classify_punishment_type(normalize_punishment_text(row.raw_text))
            detected_action = action_from_punishment_type(detected_type)

            if row.moderator_alias != normalized_alias:
                row.moderator_alias = normalized_alias
                normalized_count += 1

            current_type = _stored_punishment_type(row.punishment_type)
            if detected_type and current_type != detected_type:
                row.punishment_type = detected_type
                types_fixed_count += 1
                type_counts[detected_type] += 1

            if detected_action and row.action != detected_action:
                row.action = detected_action
                actions_fixed_count += 1

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
            types_fixed=types_fixed_count,
            actions_fixed=actions_fixed_count,
            ban_fixed=type_counts["ban"],
            mute_fixed=type_counts["mute"],
            warn_fixed=type_counts["warn"],
            unban_fixed=type_counts["unban"],
            unmute_fixed=type_counts["unmute"],
            unwarn_fixed=type_counts["unwarn"],
        )


def _stored_punishment_type(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized in PUNISHMENT_TYPES else None
