from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.staff import StaffExtraOccupation


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
        if nickname:
            stmt = stmt.where(func.lower(StaffExtraOccupation.nickname) == nickname.strip().lower())

        result = await self.session.scalars(stmt)
        return list(result)

    async def list_active_for_nicknames(self, nicknames: list[str]) -> dict[str, list[StaffExtraOccupation]]:
        normalized = {nickname.strip().lower() for nickname in nicknames if nickname and nickname.strip()}
        if not normalized:
            return {}

        result = await self.session.scalars(
            select(StaffExtraOccupation)
            .where(
                StaffExtraOccupation.is_active.is_(True),
                func.lower(StaffExtraOccupation.nickname).in_(normalized),
            )
            .order_by(StaffExtraOccupation.direction, StaffExtraOccupation.occupation)
        )

        grouped: dict[str, list[StaffExtraOccupation]] = {}
        for occupation in result:
            grouped.setdefault(occupation.nickname.lower(), []).append(occupation)
        return grouped

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
        return await self.session.scalar(
            select(StaffExtraOccupation).where(
                func.lower(StaffExtraOccupation.nickname) == nickname,
                func.lower(StaffExtraOccupation.direction) == direction,
                func.lower(StaffExtraOccupation.occupation) == occupation,
                func.lower(StaffExtraOccupation.position) == position,
            )
        )

    @staticmethod
    def _key(nickname: str, direction: str, occupation: str, position: str) -> tuple[str, str, str, str]:
        return (
            nickname.strip().lower(),
            direction.strip().lower(),
            occupation.strip().lower(),
            position.strip().lower(),
        )

