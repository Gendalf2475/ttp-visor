from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.staff import StaffExtraOccupation
from app.utils.text import normalize_nickname


@dataclass(slots=True)
class ExtraOccupationUpsert:
    nickname: str
    direction: str
    occupation: str
    position: str


@dataclass(slots=True)
class ExtraOccupationSyncResult:
    fetched: int
    created: int
    updated: int
    reactivated: int
    deactivated: int


class ExtraOccupationsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_active(self, nickname: str | None = None) -> list[StaffExtraOccupation]:
        if nickname:
            return await self.get_active_by_nickname_ci(nickname)

        stmt = (
            select(StaffExtraOccupation)
            .where(StaffExtraOccupation.is_active.is_(True))
            .order_by(
                StaffExtraOccupation.direction,
                StaffExtraOccupation.nickname,
                StaffExtraOccupation.occupation,
                StaffExtraOccupation.position,
            )
        )

        result = await self.session.scalars(stmt)
        return list(result)

    async def list_active_for_nicknames(self, nicknames: list[str]) -> dict[str, list[StaffExtraOccupation]]:
        return await self.get_many_active_by_nicknames_ci(nicknames)

    async def get_many_active_by_nicknames_ci(
        self,
        nicknames: set[str] | list[str],
    ) -> dict[str, list[StaffExtraOccupation]]:
        normalized = {normalize_nickname(nickname) for nickname in nicknames}
        normalized.discard("")
        if not normalized:
            return {}

        result = await self.session.scalars(
            select(StaffExtraOccupation)
            .where(StaffExtraOccupation.is_active.is_(True))
            .order_by(StaffExtraOccupation.direction, StaffExtraOccupation.occupation)
        )

        grouped: dict[str, list[StaffExtraOccupation]] = {}
        for occupation in result:
            key = normalize_nickname(occupation.nickname)
            if key in normalized:
                grouped.setdefault(key, []).append(occupation)
        return grouped

    async def get_active_by_nickname_ci(self, nickname: str) -> list[StaffExtraOccupation]:
        return (await self.get_many_active_by_nicknames_ci([nickname])).get(normalize_nickname(nickname), [])

    async def sync(
        self,
        rows: list[ExtraOccupationUpsert],
        synced_at: datetime,
    ) -> ExtraOccupationSyncResult:
        created = 0
        updated = 0
        reactivated = 0
        seen_keys: set[tuple[str, str, str, str]] = set()

        for row in rows:
            key = self._key(row.nickname, row.direction, row.occupation, row.position)
            seen_keys.add(key)
            existing = await self._get_by_key(*key)
            if existing is None:
                self.session.add(
                    StaffExtraOccupation(
                        nickname=row.nickname.strip(),
                        direction=row.direction.strip(),
                        occupation=row.occupation.strip(),
                        position=row.position.strip(),
                        is_active=True,
                        first_seen_at=synced_at,
                        last_seen_at=synced_at,
                    )
                )
                created += 1
                continue

            if not existing.is_active:
                existing.is_active = True
                existing.deactivated_at = None
                reactivated += 1
            else:
                updated += 1
            existing.last_seen_at = synced_at

        active_rows = await self.session.scalars(
            select(StaffExtraOccupation).where(StaffExtraOccupation.is_active.is_(True))
        )
        deactivated = 0
        for row in active_rows:
            if self._key(row.nickname, row.direction, row.occupation, row.position) in seen_keys:
                continue
            row.is_active = False
            row.deactivated_at = synced_at
            row.last_seen_at = synced_at
            deactivated += 1

        await self.session.flush()
        return ExtraOccupationSyncResult(
            fetched=len(rows),
            created=created,
            updated=updated,
            reactivated=reactivated,
            deactivated=deactivated,
        )

    async def _get_by_key(
        self,
        nickname: str,
        direction: str,
        occupation: str,
        position: str,
    ) -> StaffExtraOccupation | None:
        wanted = self._key(nickname, direction, occupation, position)
        result = await self.session.scalars(select(StaffExtraOccupation))
        for row in result:
            if self._key(row.nickname, row.direction, row.occupation, row.position) == wanted:
                return row
        return None

    @staticmethod
    def _key(nickname: str, direction: str, occupation: str, position: str) -> tuple[str, str, str, str]:
        return (
            normalize_nickname(nickname),
            direction.strip().lower(),
            occupation.strip().lower(),
            position.strip().lower(),
        )
